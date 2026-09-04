"""Placement-input coordination — Slice 7 of the Model_Space decomposition.

Owns the Dynamic-Input HUD lifecycle, placement-variant cycling, seed/publish/
resolve, schema selection, template getters, and placement-anchor accessors.
A plain object that back-references the scene (self._scene) for scene-graph
mutation, signal emission, and reads of stay-scene-side state (incl. the ALIGN
tracking scratch, which is irreducible core snap-plumbing — see
docs/specs/model-space-architecture.md §5/§6).
"""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt
from PyQt6.QtCore import QPointF

from .dynamic_input import SCHEMAS, seed_line
from .cad_math import CAD_Math


class PlacementInputCoordinator:
    def __init__(self, scene):
        self._scene = scene
        self.dynamic_input = None          # DynamicInputHud | None (lazily created)
        self._pipe_hud_reference = None    # Pipe | None
        self._resolved_point = None        # QPointF | None (HUD seed source)
        self._variant_index: dict[str, int] = {}
        self._PLACEMENT_VARIANTS: dict[str, list] = {}
        self._init_placement_variants()

    # -------------------------------------------------------------------------
    # Placement-variant registry (moved from Model_Space._init_placement_variants)

    def _init_placement_variants(self):
        """Build the placement-variant registry + the sticky per-mode index.

        Called from ``__init__``.  Each variant is
        ``(label, first-point instruction, apply_fn(s))``; ``apply_fn`` sets
        the tool's variant flag so entry and ←/→ both drive geometry through the
        same state.  The lambdas receive the scene (``s``) at cycle time so they
        can call scene methods directly.
        """
        from firepro3d.model_space import _ARC_VARIANT_CENTER, _ARC_VARIANT_START

        self._PLACEMENT_VARIANTS = {
            "draw_arc": [
                ("Center Point Arc", "Select center point to begin",
                 lambda s: setattr(s, "_arc_variant", _ARC_VARIANT_CENTER)),
                ("Start Point Arc", "Select start point to begin",
                 lambda s: setattr(s, "_arc_variant", _ARC_VARIANT_START)),
            ],
            "draw_rectangle": [
                ("Corner Rectangle", "Pick first corner",
                 lambda s: setattr(s, "_draw_rect_from_center", False)),
                ("Center Rectangle", "Pick center point",
                 lambda s: setattr(s, "_draw_rect_from_center", True)),
            ],
            "wall": [
                ("Wall (Line)", "Pick wall start point",
                 lambda s: s._set_wall_primitive("line")),
                ("Wall (Polyline)", "Pick wall start point",
                 lambda s: s._set_wall_primitive("polyline")),
                ("Wall (Corner Rectangle)", "Pick first corner",
                 lambda s: s._set_wall_primitive("rect", from_center=False)),
                ("Wall (Center Rectangle)", "Pick centre point",
                 lambda s: s._set_wall_primitive("rect", from_center=True)),
            ],
            "floor": [
                ("Floor (Corner Rectangle)", "Pick first corner",
                 lambda s: s._set_floor_primitive("rect", from_center=False)),
                ("Floor (Center Rectangle)", "Pick centre point",
                 lambda s: s._set_floor_primitive("rect", from_center=True)),
                ("Floor (Polygon)", "Pick first boundary point",
                 lambda s: s._set_floor_primitive("polygon")),
            ],
        }
        self._variant_index = {m: 0 for m in self._PLACEMENT_VARIANTS}

    # -------------------------------------------------------------------------
    # Placement-variant cycling (moved from Model_Space — C2c)

    def _at_placement_step_zero(self) -> bool:
        """True while the current tool has not placed its first point.

        Cycling the variant only makes sense before the first click; once a
        point is down the geometry is committed to a variant.
        """
        s = self._scene
        if s.mode == "draw_arc":
            return s._draw_arc_step == 0
        if s.mode == "draw_rectangle":
            return s._draw_rect_anchor is None and not s._draw_rect_rotating
        if s.mode == "wall":
            return (s._wall_anchor is None
                    and s._wall_rect_anchor is None
                    and not s._wall_rect_rotating)
        if s.mode == "floor":
            return (s._floor_active is None
                    and s._floor_rect_anchor is None
                    and not s._floor_rect_rotating)
        return False

    def _apply_current_variant(self) -> None:
        """Apply the sticky variant's state and emit the hinted step-0 readout.

        No-op for a mode with no variants.  Emits ``"<label> (←/→ to change):
        <instr>"`` so the readout advertises the cycle while it is still live.
        """
        variants = self._PLACEMENT_VARIANTS.get(self._scene.mode)
        if not variants:
            return
        label, instr, apply_fn = variants[self._variant_index[self._scene.mode]]
        apply_fn(self._scene)
        self._scene.instructionChanged.emit(f"{label} (←/→ to change): {instr}")

    def cycle_placement_variant(self, direction: int) -> bool:
        """←/→ cycle the placement variant; return False to fall through.

        Only cycles at step 0 of a multi-variant tool while no HUD field holds
        focus.  Returns False otherwise so the arrow key reaches the view's
        default scroll.

        Args:
            direction: +1 for the next variant, -1 for the previous.

        Returns:
            True when a variant was cycled (and the arrow key is consumed),
            False when cycling is not applicable.
        """
        if (self._scene.mode not in self._PLACEMENT_VARIANTS
                or not self._at_placement_step_zero()
                or self._scene.is_input_mode()):
            return False
        n = len(self._PLACEMENT_VARIANTS[self._scene.mode])
        self._variant_index[self._scene.mode] = (
            self._variant_index[self._scene.mode] + direction) % n
        self._apply_current_variant()
        return True

    # -------------------------------------------------------------------------
    # HUD lifecycle + commit dispatch (moved from Model_Space — C2a)

    def is_input_mode(self) -> bool:
        """Whether a HUD field has the keyboard and the cursor is therefore inert.

        Deliberately *not* "a HUD exists" (decision S1): the HUD is on screen
        for the whole placement, and for most of that time it is a read-only
        readout that must leave the mouse, Ctrl+Z and the click-commit path
        completely alone.

        Returns:
            True while a ``DynamicInputHud`` field holds focus.
        """
        hud = self.dynamic_input
        return hud is not None and hud.is_engaged()

    def _hud_available(self) -> bool:
        """Whether the current placement can carry a HUD at all.

        The same gate for the passive readout and for engaging it, so the HUD
        the user is looking at is always one they can type into.

        Refuses when there is nothing coherent to read out or edit: the mode has
        no schema, the mode has no applier, or an *anchored* schema has no
        anchor.  The anchor gate is keyed on ``schema.requires_anchor``, which
        covers every placement plus the one transform that has a real anchor
        (``move``, whose base point is measured from).  The genuinely
        anchorless transforms — ``distance``, ``spacing_count`` — leave it and
        so open as soon as their source is armed.

        The applier gate is what keeps the refusal honest for the anchorless
        transforms: skipping the anchor gate would otherwise let them open a HUD
        whose Enter reaches nothing, raising inside a Qt signal handler and
        stealing Enter from the mode's own working commit path.  Modes mapped
        in ``_SCHEMA_FOR_MODE`` but not yet in ``_APPLIER_FOR_MODE`` simply do
        not open a HUD.
        """
        if self._scene.mode not in self._scene._APPLIER_FOR_MODE:
            return False
        schema = self.active_schema()
        if schema is None:
            return False
        return not (schema.requires_anchor
                    and self.get_placement_anchor() is None)

    def _create_dynamic_input(self):
        """Build and show the HUD for the current mode as a passive readout.

        The HUD is parented to the first **visible** view, not ``views()[0]``.
        More than one view is attached to the plan scene — the main window
        keeps a vestigial view that is never parented into the tab widget and
        never shown — and index 0 is that orphan, so parenting there built a
        correct HUD inside an invisible widget tree: shown, but with no visible
        ancestor to carry it onto the screen.  Visibility is the right
        discriminator rather than focus because Tab arrives at the focused view
        but focus may be sitting on a ribbon widget, whereas exactly one plan
        view is visible at a time in the central tab stack.

        Returns:
            The live ``DynamicInputHud``, or None when it could not be shown —
            in which case nothing was left behind and the scene is unchanged.
        """
        view = self._visible_view()
        if view is None:
            return None
        schema = self.active_schema()

        from .dynamic_input import DynamicInputHud
        hud = DynamicInputHud(schema, self._scene.scale_manager, view.viewport())
        hud.committed.connect(self._on_dynamic_input_committed)
        hud.cancelled.connect(self._on_dynamic_input_cancelled)
        hud.fieldCommitted.connect(self._on_dynamic_input_field_committed)
        self.dynamic_input = hud
        if hasattr(view, "place_dynamic_input"):
            # No scene latch while it is only a readout: passing None puts it
            # back on the cursor, which it now tracks frame by frame.  The latch
            # happens on engage, when the cursor goes inert and chasing it would
            # be meaningless.
            view.place_dynamic_input(hud, None)
        hud.show()
        hud.raise_()
        # Self-correcting: a HUD the user cannot see is worse than none at all —
        # engaging it would make the cursor inert with no visible way back.
        # Rather than trusting the parent choice above to be the only way that
        # can happen, confirm it really reached the screen and unwind if not.
        if not hud.isVisible():
            self.end_dynamic_input()
            return None
        return hud

    def _on_dynamic_input_field_committed(self) -> None:
        """Redraw the placement preview from the HUD's current field values.

        Fires on each Tab field-commit while a field is engaged (§4.5 keeps the
        mouse inert, so the ghost would otherwise sit frozen at its engage-time
        seed).  Reads values non-destructively — the invalid-flag machinery
        stays on the real Tab/Enter path — resolves them through the active
        schema, and drives the same preview helper the mouse uses.

        Placement schemas (``returns_point``) resolve to the ``QPointF`` the
        preview helpers consume and redraw directly.  The ``move`` transform
        redraws too: its ``{"offset": ...}`` is converted to the target point
        its ghost helper takes (base anchor + offset).  The gridline replicate
        transforms are deferred — they carry a signed side the typed value
        alone does not fix, so their preview-on-commit lands with their
        applier.  A no-op if the HUD closed between signal and slot.
        """
        hud = self.dynamic_input
        schema = self._scene.active_schema()
        if hud is None or schema is None:
            return
        anchor = self._scene.get_placement_anchor()
        if schema.requires_anchor and anchor is None:
            return
        resolved = schema.resolve(anchor, hud.current_values())
        if schema.returns_point:
            self._scene._preview_from_resolved(resolved)
        elif schema.name == "rotation":
            # The rectangle and polygon rotate transforms' preview is an *angle*,
            # not a point, so it does not route through ``_transform_preview_point``
            # / ``_preview_from_resolved`` (which are point-based).  Dispatch to
            # the mode-appropriate helper.
            if self._scene.mode == "polygon":
                self._scene._preview_polygon_rotation(resolved["angle_deg"])
            else:
                self._scene._preview_rectangle_rotation(resolved["angle_deg"])
        else:
            # A transform schema resolves to a scalar/offset dict, not a point,
            # but its preview helper takes the point the resolved value lands on.
            # Each anchored transform projects its dict onto that point so the
            # mouse path and this typed path stay identical.  The gridline
            # replicate transforms carry a signed side the typed value alone does
            # not fix, so their preview-on-commit is deferred and they fall
            # through to the no-op.
            point = self._scene._transform_preview_point(resolved, anchor)
            if point is None:
                return
            self._scene._preview_from_resolved(point)
        for v in self._scene.views():
            v.viewport().update()

    def _sync_dynamic_input(self) -> None:
        """Reconcile the HUD with the live placement state — create, reseed, close.

        The single owner of the HUD's existence during cursor mode.  Called once
        per mouse move and once per press, after the mode's own handler has run,
        so it sees the anchor and resolved point that handler just produced: a
        first click arms the anchor and the HUD appears, a second commits and it
        goes away, all without either press handler knowing the HUD exists.

        A no-op while engaged.  The user is typing; the mouse is inert by
        definition, so there is nothing new to reflect and reseeding would
        overwrite their entry.
        """
        if self.is_input_mode():
            return
        if not self._hud_available():
            if self.dynamic_input is not None:
                self.end_dynamic_input()
            return
        schema = self.active_schema()
        hud = self.dynamic_input
        if hud is not None and hud.schema is not schema:
            # Mode changed under a live HUD without passing through set_mode.
            # Its editors belong to the old schema, so it cannot be reused.
            self.end_dynamic_input()
            hud = None
        if hud is None:
            hud = self._create_dynamic_input()
            if hud is None:
                return
        self._arm_pipe_relative(schema)
        hud.set_values(
            self._seed_values_for(schema, self.get_placement_anchor()))
        self._arm_arc_coupling(hud, schema)
        self._arm_track_direction(hud, schema)
        view = self._visible_view()
        if view is not None and hasattr(view, "place_dynamic_input"):
            # Re-placed every frame: an unengaged HUD follows the cursor.
            view.place_dynamic_input(hud)

    def begin_dynamic_input(self, seed: str = "") -> bool:
        """Engage input mode, opening the HUD first if one is not already up.

        Under decision S1 this no longer *creates* the HUD in the normal case —
        the placement already has one, showing the very numbers being engaged —
        it moves the keyboard into it.  The create path survives for the engage
        that arrives before any mouse move has synced one (Tab straight after
        the first click, with the pointer still stationary).

        Refuses, changing nothing, when input mode is already active or the
        placement cannot carry a HUD (see :meth:`_hud_available`).

        Args:
            seed: The keystroke that engaged the HUD, placed into the first
                field so typing continues naturally.  Empty for Tab, which
                engages without contributing a character.

        Returns:
            True when input mode was entered, False when the engage was
            refused.  Callers use this to decide whether to accept the key.
        """
        if self.is_input_mode():
            return False
        if not self._hud_available():
            return False
        schema = self.active_schema()
        hud = self.dynamic_input
        if hud is None or hud.schema is not schema:
            if hud is not None:
                self.end_dynamic_input()
            hud = self._create_dynamic_input()
            if hud is None:
                return False
        # Reseeded even when the HUD was already up: the sync runs on mouse
        # moves, and the anchor can have been armed by a click the pointer never
        # moved after, leaving the readout a frame behind what Enter would
        # commit.
        self._arm_pipe_relative(schema)
        hud.set_values(
            self._seed_values_for(schema, self.get_placement_anchor()))
        self._arm_arc_coupling(hud, schema)
        self._arm_track_direction(hud, schema)
        view = self._visible_view()
        if view is not None and hasattr(view, "place_dynamic_input"):
            # Latch to the resolved placement point — the constrained position
            # actually on screen.  From here the cursor is inert, so the HUD
            # rides pan and zoom with the geometry it is editing instead of
            # chasing a pointer whose movement means nothing.
            view.place_dynamic_input(hud, self.get_resolved_point())
        hud.engage(seed)
        return True

    def _visible_view(self):
        """Return the attached view the user is actually looking at.

        The plan scene has more than one view attached and only one of them is
        on screen (see :meth:`begin_dynamic_input`), so anything that puts a
        widget in front of the user, or hands focus back to the canvas, has to
        pick by visibility instead of by index.

        Returns:
            The first visible ``QGraphicsView`` on this scene, or None when no
            attached view is visible.
        """
        return next((v for v in self._scene.views() if v.isVisible()), None)

    def end_dynamic_input(self) -> None:
        """Close the HUD entirely — the placement it was reading out is over.

        Safe to call when no HUD is open, so every exit path (commit, mode
        switch, the anchor going away) can call it unconditionally.  Escape does
        *not* come here: it steps back to cursor mode and leaves the readout up
        (see :meth:`_on_dynamic_input_cancelled`).

        Focus goes back to the visible view — not to every attached view — or
        the canvas would keep receiving keys for a widget that is gone, and the
        last ``setFocus`` in the loop would have handed focus to the invisible
        orphan view the scene also carries (see :meth:`_create_dynamic_input`).
        It is claimed only when the HUD actually held it: a passive readout
        being retired must not yank focus away from whatever the user is really
        working in, such as the property panel.
        """
        hud = self.dynamic_input
        # Cleared first: the tear-down below can re-enter through focus and
        # paint events, which must already see cursor mode.
        self.dynamic_input = None
        if hud is None:
            return
        was_engaged = hud.is_engaged()
        hud.hide()
        # deleteLater only *schedules* deletion: until the deferred-delete pass
        # runs, the HUD is alive and would still be wired.  A stray signal in
        # that window would resolve one schema's values against an anchor the
        # scene has already moved past, so the connections go first.
        hud.committed.disconnect(self._on_dynamic_input_committed)
        hud.cancelled.disconnect(self._on_dynamic_input_cancelled)
        # Also out of the viewport's paint and focus chains for that window.
        hud.setParent(None)
        hud.deleteLater()
        if was_engaged:
            view = self._visible_view()
            if view is not None:
                view.setFocus(Qt.FocusReason.OtherFocusReason)
        # Every view still repaints: the HUD's departure has to clear from any
        # viewport that was painting it, visible or not.
        for v in self._scene.views():
            v.viewport().update()

    def _on_dynamic_input_cancelled(self) -> None:
        """Escape rung 0: hand the placement back to the cursor.

        Only input mode is abandoned. The mode and its anchor survive, so
        Escape steps back to the cursor rather than throwing away a placement
        the user is midway through — a second Escape, handled elsewhere, is
        what cancels that.

        Under decision S1 the HUD itself survives too, reverting to the passive
        readout it is for the rest of the placement; closing it would leave the
        user with no numbers at all for a placement that is still live, and the
        next mouse move would only build it again.  Focus is pushed back to the
        view explicitly — the HUD is now transparent to the mouse but still
        holds the keyboard until someone takes it.
        """
        hud = self.dynamic_input
        if hud is None:
            return
        hud.disengage()
        view = self._visible_view()
        if view is not None:
            view.setFocus(Qt.FocusReason.OtherFocusReason)
        # The cursor is live again, so put the readout back under it rather than
        # leaving it latched where the placement was engaged.
        if view is not None and hasattr(view, "place_dynamic_input"):
            view.place_dynamic_input(hud, None)

    def _on_dynamic_input_committed(self, values: dict) -> None:
        """Resolve *values* into geometry and hand it to the click-commit path.

        Ordering is load-bearing: the schema resolves **before** the HUD is
        torn down and long before the applier runs, because appliers such as
        ``_commit_draw_line_at`` re-read the scene's anchor state and then call
        ``clear_placement_state()``.  Resolving afterwards would read an anchor
        the commit had already cleared.

        The HUD is torn down only once the applier reports success (decision
        D2).  A refusal — a length under the too-short floor, say — keeps it
        open with the offending field flagged, so the placement survives and
        the user can simply retype.  Closing first and applying afterwards is
        what made a typed ``0.3`` vanish into a status-bar message that
        appeared after the HUD had already gone.

        Args:
            values: Field values from the HUD, in schema units.
        """
        schema = self._scene.active_schema()
        anchor = self._scene.get_placement_anchor()
        if schema is None or (schema.requires_anchor and anchor is None):
            self.end_dynamic_input()
            return
        hud = self.dynamic_input
        if self._scene.mode == "pipe" and schema.name == "line":
            if self._scene._commit_pipe_typed(values):
                self.end_dynamic_input()
            # A refusal (off-grid angle or a hard rejection) leaves the HUD open
            # with the field flagged inside _commit_pipe_typed; nothing else.
            return
        geometry = schema.resolve(anchor, values)
        # On-path Navigate at the FIRST point (BUG A): the ``track`` schema is a
        # placement schema, so ``get_placement_anchor`` hands back the tracking
        # ray's ORIGIN even before the mode's own first click — non-None — which
        # satisfies the anchor gate above.  But the mode's commit-only appliers
        # (``_commit_draw_line_at`` / ``_commit_draw_circle_at``) refuse when no
        # per-mode anchor is armed, and a False verdict becomes a red field.  A
        # typed Distance on a path at the first point is really "click here to
        # arm the first point", so route the resolved point through the mode's
        # PRESS handler (the arm-or-commit entry a real first click takes),
        # exactly as ``_apply_wall_dynamic_input`` already does for walls.  With
        # a per-mode anchor armed (second point), this branch is skipped and the
        # segment commits through the normal applier as before.
        if (schema.name == "track"
                and self._mode_placement_anchor() is None
                and self._scene._commit_track_first_point(geometry)):
            self.end_dynamic_input()
            return
        if self.apply_dynamic_input(geometry):
            # An applier may have torn the HUD down itself (e.g. by calling
            # set_mode); end_dynamic_input is a no-op in that case.
            self.end_dynamic_input()
        elif hud is not None and hud is self.dynamic_input:
            hud.reject_commit()

    def apply_dynamic_input(self, geometry):
        """Apply resolved *geometry* through the current mode's commit path.

        Dispatches through ``_APPLIER_FOR_MODE``, the same table
        ``begin_dynamic_input`` gates on, so a HUD can never open for a mode
        this cannot commit.  The raise is therefore unreachable from the UI and
        survives only as a programmer-error backstop for a direct call.

        Args:
            geometry: A ``QPointF`` for placement schemas, or the transform
                dict for the others.

        Returns:
            The applier's verdict: True when it committed, False when it
            refused (decision D2).  Forwarded verbatim so the one rule lives in
            the commit path and nothing mirrors its threshold.

        Raises:
            NotImplementedError: When the current mode has no applier.  Not
                reachable through the HUD — the engage gate refuses first.
        """
        applier = self._scene._APPLIER_FOR_MODE.get(self._scene.mode)
        if applier is None:
            raise NotImplementedError(
                f"no dynamic-input applier for {self._scene.mode!r}")
        return bool(getattr(self._scene, applier)(geometry))

    # -------------------------------------------------------------------------
    # Placement anchor accessors (moved from Model_Space — C2b)

    def get_placement_anchor(self) -> "QPointF | None":
        """Return the active placement's anchor point in scene coordinates.

        One accessor for what were six per-mode anchor variables.

        ``None`` means no placement anchor exists. Placement schemas must not
        engage without one, and callers must not paper over ``None`` by
        substituting a fallback point — doing so defeats the gate. Transform
        schemas have no anchor by nature and are gated separately.

        The returned point is always a fresh copy, so callers are free to
        mutate it; it never aliases the scene's or an item's internal state.

        Returns:
            A copy of the anchor point, or None when no anchor exists.
        """
        # On-path Navigate: the ``track`` schema measures Distance from the
        # tracking path's ORIGIN (D4), not the mode's own placement anchor, so
        # while the track swap is live the anchor is the winning ray's origin.
        # ``resolve_track(origin, {Distance, __dir__})`` then lands
        # ``origin + Distance·direction``.
        if self._scene._align_track_schema() is not None:
            ox, oy = self._scene._align_track_ray.origin
            return QPointF(ox, oy)
        return self._mode_placement_anchor()

    def _mode_placement_anchor(self) -> "QPointF | None":
        """The mode's *own* placement anchor, ignoring any on-path track swap.

        Split out of :meth:`get_placement_anchor` so the commit path can ask
        "does the current mode already have a first-point anchor armed?" without
        the ``track`` schema substituting the tracking ray's origin (which is
        non-None even at the first-point step, and is exactly what would mask a
        first point as a second point — BUG A).  ``get_placement_anchor``
        returns the track-ray origin while the swap is live; this returns the
        real per-mode anchor (``None`` at the first-point step).
        """
        if self._scene.mode in ("draw_line", "draw_gridline"):
            a = self._scene._draw_line_anchor
            return QPointF(a) if a is not None else None
        if self._scene.mode == "draw_rectangle":
            # Sizing step: the first-click anchor.  Rotate step: the pivot the
            # rotation turns about (the first-click anchor — one of the rect's
            # corners — in corner mode, the centre in centre mode).  Both
            # variants store it in ``_draw_rect_pivot``.
            if self._scene._draw_rect_rotating:
                p = self._scene._draw_rect_pivot
                return QPointF(p) if p is not None else None
            a = self._scene._draw_rect_anchor
            return QPointF(a) if a is not None else None
        if self._scene.mode == "draw_circle":
            a = self._scene._draw_circle_center
            return QPointF(a) if a is not None else None
        if self._scene.mode == "polygon":
            # Both sizing and rotate steps pivot about _polygon_center.
            a = self._scene._polygon_center
            return QPointF(a) if a is not None else None
        if self._scene.mode == "draw_arc":
            # The anchor is the FIRST click, stored in ``_draw_arc_center`` for
            # both variants (the centre in center-first, the start point in
            # start-first).  None at step 0, before that first click.
            a = self._scene._draw_arc_center
            return QPointF(a) if (self._scene._draw_arc_step in (1, 2)
                                  and a is not None) else None
        if self._scene.mode == "wall":
            if self._scene._wall_primitive == "rect":
                # Rotate step: pivot is the anchor.
                if self._scene._wall_rect_rotating:
                    p = self._scene._wall_rect_pivot
                    return QPointF(p) if p is not None else None
                a = self._scene._wall_rect_anchor
                return QPointF(a) if a is not None else None
            a = self._scene._wall_anchor
            return QPointF(a) if a is not None else None
        if self._scene.mode == "floor":
            if self._scene._floor_primitive == "rect":
                # Rotate step: pivot is the anchor.
                if self._scene._floor_rect_rotating:
                    p = self._scene._floor_rect_pivot
                    return QPointF(p) if p is not None else None
                a = self._scene._floor_rect_anchor
                return QPointF(a) if a is not None else None
            # Polygon: anchor is the last placed vertex (rubber-band from it).
            fa = self._scene._floor_active
            if fa is not None and fa._points:
                return QPointF(fa._points[-1])
            return None
        if self._scene.mode == "polyline":
            pl = self._scene._polyline_active
            if pl is not None and pl._points:
                return QPointF(pl._points[-1])
            return None
        if self._scene.mode in ("pipe", "move"):
            # node_start_pos holds a Node in pipe mode but a raw QPointF in
            # move mode (set_mode's cleanup relies on the same distinction).
            nsp = self._scene.node_start_pos
            if nsp is None:
                return None
            # scenePos() is already a fresh point; the raw QPointF is stored.
            from .node import Node
            return nsp.scenePos() if isinstance(nsp, Node) else QPointF(nsp)
        return None

    # -------------------------------------------------------------------------
    # Schema selection (moved from Model_Space — C2b)

    def active_schema(self):
        """Return the Schema for the current mode, or None.

        Warning:
            A non-None schema implies neither a published point nor an
            applier.  ``_SCHEMA_FOR_MODE`` is a forward declaration — it
            describes the migration's end state, while the
            ``publish_placement_state`` call sites and the appliers land one
            task at a time, so a mapped mode may still return a schema while
            ``get_resolved_point()`` stays None and no applier exists.  A
            caller that needs a seeded position must gate on
            ``get_resolved_point() is not None``, and a caller that intends to
            commit must gate on ``_APPLIER_FOR_MODE`` — never on this returning
            a schema, or it will open a HUD that can only dead-end.  Read the
            tables for the current state rather than trusting a count written
            here, which goes stale every time a mode is migrated.

        Returns:
            The registered ``Schema`` for ``self._scene.mode``, or None when
            the mode has no dynamic-input schema.
        """
        # On-path Navigate (D4) overrides the primitive readout while the cursor
        # is soft-snapped to a single ALIGN path: the ``track`` schema replaces
        # the mode's Length/Angle (or X/Y, R, …) with one signed Distance field.
        # Refused for transform modes / rotate steps and for modes that cannot
        # commit a typed point — see ``_align_track_schema``.
        track = self._scene._align_track_schema()
        if track is not None:
            return track
        return self._base_schema()

    def _base_schema(self):
        """The mode's normal (non-track) schema — the primitive readout.

        Split out of :meth:`active_schema` so the track-swap gate can consult
        the primitive schema without recursing through the swap itself.
        """
        if self._scene.mode == "draw_arc":
            return self._arc_schema_for_step()
        if self._scene.mode == "draw_rectangle":
            return self._rectangle_schema_for_step()
        if self._scene.mode == "polygon":
            return self._polygon_schema_for_step()
        if self._scene.mode == "wall":
            return self._wall_schema_for_primitive()
        if self._scene.mode == "floor":
            return self._floor_schema_for_primitive()
        key = self._scene._SCHEMA_FOR_MODE.get(self._scene.mode)
        return SCHEMAS.get(key) if key else None

    def _rectangle_schema_for_step(self):
        """Return the rectangle schema for the current step.

        Rectangle placement is 3-step (Task 12): the two-click **sizing** step
        types the far corner (the ``rectangle`` X/Y schema), then the
        **rotate** step types the absolute orientation (the ``rotation``
        transform).  ``_draw_rect_rotating`` picks which one is live.  Unlike
        arc there is no anchorless step 0 — the sizing schema has an anchor from
        the first click, and before that first click the anchor gate keeps the
        HUD shut anyway.
        """
        if self._scene._draw_rect_rotating:
            return SCHEMAS.get("rotation")
        return SCHEMAS.get("rectangle")

    def _polygon_schema_for_step(self):
        """Return the polygon schema for the current step.

        Polygon placement is 3-step: the sizing step types the radius (the
        ``polygon`` schema), then the rotate step types the orientation (the
        ``rotation`` schema).  ``_polygon_rotating`` picks which one is live.
        Step 0 has no anchor before the first click, so the anchor gate keeps
        the HUD shut then — exactly like draw_rectangle.
        """
        if self._scene._polygon_rotating:
            return SCHEMAS.get("rotation")
        return SCHEMAS.get("polygon")

    def _arc_schema_for_step(self):
        """Return the arc schema for the current step, or None.

        Arc is the one mode whose schema changes mid-placement: step 1 types the
        radius + start angle (the ``line`` schema, Length=radius, Angle=start°),
        step 2 types the sweep (``arc_span``).  Step 0 has no HUD — there is no
        anchor before the first click, so nothing to read out or seed from.
        """
        if self._scene._draw_arc_step == 1:
            return SCHEMAS.get("line")
        if self._scene._draw_arc_step == 2:
            return SCHEMAS.get("arc_span")
        return None

    def _wall_schema_for_primitive(self):
        """HUD schema for the active wall primitive.

        Line/polyline → ``line`` schema.  Rect → step-aware: sizing step uses
        ``rectangle`` schema; rotate step uses ``rotation`` schema (mirrors
        ``_rectangle_schema_for_step``).
        """
        if self._scene._wall_primitive == "rect":
            if self._scene._wall_rect_rotating:
                return SCHEMAS.get("rotation")
            return SCHEMAS.get("rectangle")
        return SCHEMAS.get("line")

    def _floor_schema_for_primitive(self):
        """HUD schema for the active floor primitive.

        Rect → step-aware: sizing step uses ``rectangle`` schema, rotate step
        uses ``rotation`` schema.  Polygon → ``line`` schema (per-segment
        length/angle readout, same as the wall line/polyline).  Mirrors
        ``_wall_schema_for_primitive``.
        """
        if self._scene._floor_primitive == "rect":
            if self._scene._floor_rect_rotating:
                return SCHEMAS.get("rotation")
            return SCHEMAS.get("rectangle")
        return SCHEMAS.get("line")

    # -------------------------------------------------------------------------
    # Published placement state (moved from Model_Space — C2b)

    def get_resolved_point(self) -> "QPointF | None":
        """Return the last point published by ``publish_placement_state``.

        This is the *constrained* position actually shown on screen, which is
        what the HUD seeds from.  Distinct from ``_last_scene_pos``, which
        holds the raw cursor and so can disagree with the preview whenever a
        constraint (Ctrl, 45° snap, ALIGN) is active.

        This — not ``active_schema()`` — is the gate for "is there a live
        placement to seed from".  Most modes that ``active_schema()`` answers
        for do not publish yet (see its warning), so None here is the normal
        state in eight of the ten mapped modes.

        The returned point is always a fresh copy; callers may mutate it.

        Returns:
            A copy of the resolved point, or None when nothing is published.
        """
        p = self._resolved_point
        return QPointF(p) if p is not None else None

    def clear_placement_state(self) -> None:
        """Drop the published point and readout (placement finished/cancelled)."""
        self._resolved_point = None
        self._scene._draw_dim_hint = None
        self._pipe_hud_reference = None

    def publish_placement_state(self, anchor, point) -> None:
        """Record the resolved placement point and derive the HUD readout.

        Call once per frame per mode, at the point where the mode has finished
        constraining its position (OSNAP → ALIGN → Ctrl → 45° snap).  This
        is the single source for both the live read-only readout and the
        values the HUD seeds with, so the two cannot disagree.

        A schema-driven mode's readout is the ``DynamicInputHud`` widget itself
        (decision S1), which ``_sync_dynamic_input`` reseeds from the point
        recorded here.  There is no painted string to build — ``_draw_dim_hint``
        is only cleared, so a stale hint from a mode that hand-builds its own
        cannot survive into one that does not.  One HUD, not two, enforced at
        the single site that assigns the string rather than by a second test in
        ``Model_View.drawForeground``.

        Args:
            anchor: The placement anchor, or None when the mode has not
                established one yet.
            point: The fully constrained point under the cursor.
        """
        # No-op in input mode. The HUD seeded from the point published at
        # engage time, and the user is now editing those numbers; a late
        # publish would move the seed under them.
        if self.is_input_mode():
            return
        self._resolved_point = QPointF(point) if point is not None else None
        self._scene._draw_dim_hint = None

    # -------------------------------------------------------------------------
    # HUD arming helpers (moved from Model_Space — C2b)

    def _arm_pipe_relative(self, schema) -> None:
        """Hold the reference pipe and set the Angle label for the pipe HUD.

        Called from ``begin_dynamic_input`` BEFORE ``set_values`` so the seed
        can read ``_pipe_hud_reference``.  No-op unless this is the pipe mode's
        ``line`` schema.
        """
        hud = self.dynamic_input
        if self._scene.mode != "pipe" or hud is None or schema.name != "line":
            self._pipe_hud_reference = None
            return
        ref = self._scene._pipe_reference_pipe()
        self._pipe_hud_reference = ref
        hud.set_field_label("Angle", "Rel A" if ref is not None else "A")
        hud.editor("Angle").setProperty("relative", ref is not None)

    def _seed_pipe_line(self, anchor) -> dict:
        """Seed the pipe HUD's Length + (relative|absolute) Angle.

        Connected: Angle is the relative angle in ``snap_point_45``'s frame,
        ``(get_vector_angle(start, preview) - 90) - base`` — the same quantity
        the mouse snaps, so accepting the seed round-trips to the mouse output.
        Free: seed the absolute Y-up angle via ``seed_line``.
        """
        point = self.get_resolved_point()
        start = anchor
        end = anchor if point is None else point
        ref = self._pipe_hud_reference
        if ref is None:
            return seed_line(start, end)
        length = CAD_Math.get_vector_length(start, end)
        base = CAD_Math.get_vector_angle(ref.node1.scenePos(),
                                         ref.node2.scenePos())
        abs_ang = CAD_Math.get_vector_angle(start, end) - 90.0
        rel = ((abs_ang - base) + 180.0) % 360.0 - 180.0   # → (-180, 180]
        return {"Length": length, "Angle": rel}

    def _seed_values_for(self, schema, anchor) -> dict:
        """Return the values *schema*'s HUD should open with.

        WYSIWYG: a placement seeds from the **resolved** point — the
        constrained position actually drawn on screen — never from the raw
        cursor, so the numbers in the HUD are the ones the user is looking at.
        The anchor stands in when nothing has been published yet, which seeds a
        zero-length placement rather than an empty HUD.

        Args:
            schema: The active ``Schema``.
            anchor: The placement anchor, or None for a transform schema.

        Returns:
            Values keyed by field name, in schema (scene) units.
        """
        if schema.name == "track":
            # The track schema has no cursor-derived inverse (``seed`` is None):
            # its one Distance field is the signed distance-along-ray the seam
            # already measured when it recovered the winning ray.  Seeding it
            # keeps the readout showing how far along the path the cursor sits.
            return {"Distance": self._scene._align_track_dist}
        if self._scene.mode == "pipe" and schema.name == "line":
            # Pipe's Angle is relative (connected) or absolute (free); the frame
            # must match _commit_pipe_typed's, so seed via the dedicated helper.
            return self._seed_pipe_line(anchor)
        if schema.is_placement:
            # Explicit None test, never truthiness: PyQt gives QPointF a
            # __bool__ that is False at the origin, so ``point or anchor`` would
            # silently discard a resolved point of exactly (0, 0) and read out a
            # zero-length placement.  Snapping to the origin is ordinary in CAD,
            # and the readout is now rebuilt every frame, so that would be
            # visible whenever the cursor crossed it.
            point = self.get_resolved_point()
            return schema.seed(anchor, anchor if point is None else point)
        return self._transform_seed_values(schema)

    def _transform_seed_values(self, schema) -> dict:
        """Return seed values for a transform schema, read from scene state.

        Transforms have no anchor and no cursor-derived inverse, so each reads
        the state its own commit path already uses — the replicate spacing and
        count for the gridline modes, the live displacement for a move.

        Args:
            schema: A transform ``Schema`` (``returns_point`` False).

        Returns:
            Values keyed by field name; empty for an unrecognised schema, which
            leaves the HUD's editors at their own defaults.
        """
        if schema.name == "displacement":
            anchor = self.get_placement_anchor()
            point = self.get_resolved_point()
            if anchor is None or point is None:
                return {"dX": 0.0, "dY": 0.0}
            # Y-up, matching resolve_displacement's negation.
            return {"dX": point.x() - anchor.x(),
                    "dY": -(point.y() - anchor.y())}
        if schema.name == "rotation":
            # Seed the live orientation: the pivot→resolved-point heading, the
            # same absolute angle the mouse and ``resolve_rotation`` use.  0°
            # (axis-aligned) before anything is published.  The pivot differs by
            # mode — the polygon rotate step pivots about its centre, the
            # rectangle about its stored pivot, the wall-rectangle about its
            # own stored pivot — so dispatch to the matching angle helper (all
            # share the same Y-up formula).
            point = self.get_resolved_point()
            if point is None:
                return {"Angle": 0.0}
            if self._scene.mode == "polygon":
                return {"Angle": self._scene._polygon_rotation_angle_to(point)}
            if self._scene.mode == "wall":
                return {"Angle": self._scene._wall_rect_rotation_angle_to(point)}
            if self._scene.mode == "floor":
                return {"Angle": self._scene._floor_rect_rotation_angle_to(point)}
            return {"Angle": self._scene._rect_rotation_angle_to(point)}
        if schema.name == "arc_span":
            # Live span from the resolved point — the same sweep the third click
            # or a typed Span commits.  Without this the readout sits at 0 the
            # whole span step (a transform has no cursor-derived inverse).
            # ArcLength stays in scene units; ``set_values`` converts it to mm.
            point = self.get_resolved_point()
            if point is None or self._scene._draw_arc_center is None:
                return {"Span": 0.0, "ArcLength": 0.0}
            cx, cy = self._scene._draw_arc_center.x(), self._scene._draw_arc_center.y()
            end_deg = math.degrees(math.atan2(-(point.y() - cy),
                                              point.x() - cx))
            span = end_deg - self._scene._draw_arc_start_deg
            if span <= 0:
                span += 360.0
            return {"Span": span,
                    "ArcLength": math.radians(span) * self._scene._draw_arc_radius}
        # ``_replicate_spacing`` is a *signed* perpendicular projection, so it
        # passes through 0.0 as the cursor crosses the source gridline — 0.0 is
        # not reliably "never set".  Treating it as unset is still correct
        # because the commit path rejects ``abs(dist) < 0.5`` anyway, so a
        # seeded zero could never be placed.  Explicit ``!= 0.0`` (matching the
        # comparison the modal path already uses) rather than truthiness, since
        # every other value here is a legitimate signed distance.
        #
        # Seeded as a **magnitude**: ``Distance`` and ``Spacing`` carry
        # ``minimum=0.0``, so the raw signed projection would seed text the
        # field itself rejects on the very next read.  The side stays with the
        # cursor and is reapplied by the appliers
        # (:meth:`_replicate_side_sign`) — offsetting by a typed magnitude onto
        # the side you are pointing at, rather than by a signed quantity whose
        # sign is invisible in the geometry.
        spacing = abs(self._scene._replicate_spacing
                      if self._scene._replicate_spacing != 0.0 else 1000.0)
        if schema.name == "distance":
            return {"Distance": spacing}
        if schema.name == "spacing_count":
            return {"Spacing": spacing,
                    "Count": max(1, int(self._scene._replicate_count))}
        return {}

    def _arm_arc_coupling(self, hud, schema) -> None:
        """Arm the HUD's Span-to-ArcLength coupling for the ``arc_span`` schema.

        The coupling recomputes ``ArcLength = radius * radians(Span)`` as the
        user edits, so it needs the sweep radius in the millimetres the
        ``ArcLength`` DIMENSION editor stores.  The radius is fixed once step 2
        is reached, so arming it at seed time (before or at engage) is enough.

        ``_draw_arc_radius`` is in scene units; it is converted through the same
        DIMENSION scene->mm path the HUD's dimension editors use
        (``DynamicInputHud.scene_to_mm``, guarded on calibration: an
        uncalibrated scene treats one unit as one mm, a calibrated one routes
        through ``ScaleManager.scene_to_mm``), so the coupling and the editor
        agree.  A no-op for every other schema; ``set_coupling_radius`` is
        harmlessly ignored by non-arc HUDs, but the guard keeps intent clear.
        """
        if schema is None or schema.name != "arc_span":
            return
        hud.set_coupling_radius(hud.scene_to_mm(self._scene._draw_arc_radius))

    def _arm_track_direction(self, hud, schema) -> None:
        """Inject the winning path's unit direction into a ``track`` HUD.

        ``resolve_track`` reads the direction from the values dict under the
        reserved ``"__dir__"`` key, injected by ``DynamicInputHud.values`` from
        whatever ``set_track_direction`` last armed.  The direction is fixed for
        as long as the cursor stays on one path, so arming it at seed time (each
        sync and at engage) keeps it current as the swap turns on and off.  A
        no-op for every other schema; other HUDs ignore the armed direction.
        """
        if schema is None or schema.name != "track":
            return
        direction = (self._scene._align_track_ray.direction
                     if self._scene._align_track_ray is not None else None)
        hud.set_track_direction(direction)

    # -------------------------------------------------------------------------
    # Template getters (moved from Model_Space — C2b)

    def _get_wall_template(self) -> "WallSegment":
        """Return (lazily-created) wall template for pre-placement editing."""
        from .wall import WallSegment
        if self._scene._wall_template is None:
            self._scene._wall_template = WallSegment(QPointF(0, 0), QPointF(100, 0))
            self._scene._wall_template.name = "(Template)"
            self._scene._wall_template._alignment = self._scene._wall_alignment
            self._scene._wall_template._scale_manager_ref = self._scene.scale_manager
        # Always sync levels with current active level
        self._scene._wall_template.level = self._scene.active_level
        self._scene._wall_template._base_level = self._scene.active_level
        if self._scene._level_manager is not None:
            levels = self._scene._level_manager.levels
            active_idx = next(
                (i for i, l in enumerate(levels)
                 if l.name == self._scene.active_level), 0)
            if active_idx + 1 < len(levels):
                self._scene._wall_template._top_level = levels[active_idx + 1].name
        return self._scene._wall_template

    def _get_floor_template(self) -> "FloorSlab":
        """Return (lazily-created) floor slab template for pre-placement editing."""
        from .floor_slab import FloorSlab
        if self._scene._floor_template is None:
            self._scene._floor_template = FloorSlab(color="#8888cc")
            self._scene._floor_template.name = "(Template)"
            self._scene._floor_template._scale_manager_ref = self._scene.scale_manager
        # Always sync level with current active level
        self._scene._floor_template.level = self._scene.active_level
        return self._scene._floor_template

    def _get_roof_template(self) -> "RoofItem":
        """Return (lazily-created) roof template for pre-placement editing."""
        from .roof_item import RoofItem
        if self._scene._roof_template is None:
            self._scene._roof_template = RoofItem(color="#D2B48C")
            self._scene._roof_template.name = "(Template)"
            self._scene._roof_template._scale_manager_ref = self._scene.scale_manager
        self._scene._roof_template.level = self._scene.active_level
        return self._scene._roof_template

    def _get_gridline_template(self) -> "GridlineItem":
        """Return (lazily-created) gridline template for pre-placement editing.

        The template is NOT added to the scene and NOT appended to
        ``_gridlines``, so editing it via the property panel never triggers
        ``push_undo_state()`` (``GridlineItem.set_property`` guards the undo
        push with ``self.scene() is not None``).
        """
        if self._scene._gridline_template is None:
            from .gridline import GridlineItem as _GLItem
            tmpl = _GLItem(QPointF(0, 0), QPointF(0, 1000))
            tmpl._label_text = "(Template)"
            tmpl._is_template = True
            self._scene._gridline_template = tmpl
        return self._scene._gridline_template

    def _get_geometry_template(self):
        """Return (lazily-created) geometry template for line/rect/circle/polyline."""
        from .construction_geometry import GeometryTemplate
        if self._scene._geometry_template is None:
            self._scene._geometry_template = GeometryTemplate()
        # Sync with active level
        self._scene._geometry_template.level = self._scene.active_level
        return self._scene._geometry_template
