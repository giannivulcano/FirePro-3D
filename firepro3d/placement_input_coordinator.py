"""Placement-input coordination — Slice 7 of the Model_Space decomposition.

Owns the Dynamic-Input HUD lifecycle, placement-variant cycling, seed/publish/
resolve, schema selection, template getters, and placement-anchor accessors.
A plain object that back-references the scene (self._scene) for scene-graph
mutation, signal emission, and reads of stay-scene-side state (incl. the ALIGN
tracking scratch, which is irreducible core snap-plumbing — see
docs/specs/model-space-architecture.md §5/§6).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt


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
        schema = self._scene.active_schema()
        if schema is None:
            return False
        return not (schema.requires_anchor
                    and self._scene.get_placement_anchor() is None)

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
        schema = self._scene.active_schema()

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
        schema = self._scene.active_schema()
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
        self._scene._arm_pipe_relative(schema)
        hud.set_values(
            self._scene._seed_values_for(schema, self._scene.get_placement_anchor()))
        self._scene._arm_arc_coupling(hud, schema)
        self._scene._arm_track_direction(hud, schema)
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
        schema = self._scene.active_schema()
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
        self._scene._arm_pipe_relative(schema)
        hud.set_values(
            self._scene._seed_values_for(schema, self._scene.get_placement_anchor()))
        self._scene._arm_arc_coupling(hud, schema)
        self._scene._arm_track_direction(hud, schema)
        view = self._visible_view()
        if view is not None and hasattr(view, "place_dynamic_input"):
            # Latch to the resolved placement point — the constrained position
            # actually on screen.  From here the cursor is inert, so the HUD
            # rides pan and zoom with the geometry it is editing instead of
            # chasing a pointer whose movement means nothing.
            view.place_dynamic_input(hud, self._scene.get_resolved_point())
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
                and self._scene._mode_placement_anchor() is None
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
