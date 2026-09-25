"""Modify-tool behaviour home (scene-tools.md I1).

Owns NO state (model-space-architecture.md §5.3): every transient lives on the
scene and is reached via ``self._scene``. Dispatch rows on ``Model_Space``
point at thin scene shells that forward here.

Slice 1 relocates the Move / Paste gesture (press, move, preview, handle-snap,
typed-displacement applier, ghost-silhouette builders) verbatim. Calls between
relocated methods go back through the scene shells (``s._move_handle_snap``
etc.), so a test or caller that patches the scene attribute still reaches the
behaviour it patched.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath

from .cad_math import CAD_Math
from .gridline import GridlineItem
from .handle_snap import HandleSnapSession
from .sprinkler import Sprinkler

# Modes whose ghost + selection-capture behave like Move.
TRANSFORM_MODES = frozenset({"move", "paste", "duplicate", "rotate", "array"})
# Tools whose originals are dimmed while they run (D11; paste has no originals).
DIM_ORIGINAL_TOOLS = frozenset({"move", "duplicate", "rotate", "array"})


class ModifyToolsController:
    """Behaviour for the 2D modify tools. See docs/specs/scene-tools.md."""

    # tool name -> scene mode entered by start()
    _TOOL_MODE = {"copy": "copy_base", "cut": "copy_base", "paste": "paste",
                  "duplicate": "duplicate", "move": "move", "rotate": "rotate",
                  "offset": "offset", "array": "array"}
    _SELECT_FIRST = {"copy", "cut", "duplicate", "move", "rotate", "array"}
    # Tools whose ribbon button is a plain (non-modal) button.
    _PLAIN_TOOLS = frozenset({"cut"})
    # Extra modes a tool passes through after its entry mode.
    _TOOL_EXTRA_MODES = {"offset": ("offset_side",)}
    # Modes an Undo / Redo must cancel first: their transient state (base
    # point, captured selection, armed payload) would outlive the restore.
    CANCEL_ON_UNDO_MODES = frozenset({"copy_base", "paste", "duplicate", "move",
                                      "rotate"})

    @classmethod
    def tool_modes(cls, tool: str):
        """Scene mode(s) that mean *tool* is running (lights its button).

        Args:
            tool: A ``_TOOL_MODE`` key.

        Returns:
            A tuple of mode names, or None for a plain (non-modal) tool.
        """
        if tool in cls._PLAIN_TOOLS or tool not in cls._TOOL_MODE:
            return None
        return (cls._TOOL_MODE[tool],) + cls._TOOL_EXTRA_MODES.get(tool, ())

    def __init__(self, scene):
        self._scene = scene

    def start(self, tool: str) -> bool:
        """Enter *tool* (scene-tools.md D3 select-first).

        Args:
            tool: One of the ``_TOOL_MODE`` keys.

        Returns:
            True if a mode was entered.
        """
        s = self._scene
        sel = list(s.selectedItems())
        if tool in self._SELECT_FIRST and not sel:
            s._show_status("Select items first", 3000)
            return False
        if tool == "paste":
            return self.begin_paste()
        if tool == "offset":
            return self.begin_offset(sel)      # Task 12
        s._copy_is_cut = (tool == "cut")
        s._selected_items = sel
        s.set_mode(self._TOOL_MODE[tool])
        # D11: dim the originals. After set_mode — its clear() restores any
        # previous dim first, so entering a mode never undoes its own dim.
        if tool in DIM_ORIGINAL_TOOLS and s.mode == self._TOOL_MODE[tool]:
            from .transform_ghost import dim_items
            s._ghost_dimmed = dim_items(self._transformable(sel))
        return True

    @staticmethod
    def _transformable(items) -> list:
        """The items a transform acts on — ``move_items``' filter (D11 dim).

        A Sprinkler resolves to its Node; otherwise an item qualifies if it
        is a Node or has ``translate`` / ``manip_translate``. Selectable items
        a Move cannot move (underlays) are left out, so they are never dimmed
        (their opacity is persisted by save).

        Args:
            items: Candidate items (usually the captured selection).

        Returns:
            The de-duplicated transformable items, in order.
        """
        from .node import Node
        out, seen = [], set()
        for it in items or ():
            if isinstance(it, Sprinkler) and it.node is not None:
                it = it.node
            if id(it) in seen:
                continue
            if (isinstance(it, Node) or hasattr(it, "translate")
                    or hasattr(it, "manip_translate")):
                seen.add(id(it))
                out.append(it)
        return out

    # ── Copy / Cut (D4) ─────────────────────────────────────────────────────

    CLIPBOARD_UNAVAILABLE = "Clipboard unavailable — nothing copied"

    def write_clipboard(self, items, base: QPointF):
        """Write *items* + *base* to the system clipboard (I1 payload).

        The write is read back: the OS clipboard can refuse it (another
        process holding it, a locked session), and Cut must never delete
        what it failed to copy.

        Args:
            items: Scene items to serialise.
            base: The copy base point (scene coordinates).

        Returns:
            The number of records written, or None if the write did not land.
        """
        import json
        from PyQt6.QtWidgets import QApplication
        from .constants import CLIPBOARD_FORMAT_VERSION
        s = self._scene
        data = s._clipboard_item_dicts(items)
        payload = {"fp3d_clipboard": CLIPBOARD_FORMAT_VERSION,
                   "base": [base.x(), base.y()],
                   "scene_role": s.scene_role, "items": data}
        text = json.dumps(payload)
        clip = QApplication.clipboard()
        clip.setText(text)
        if clip.text() != text:
            return None
        return len(data)

    def press_copy_base(self, event, pos, snapped, *_):
        """``copy_base`` click: the snapped base point commits Copy / Cut.

        Copy returns to Select with the selection intact; Cut deletes the
        selection in the same (single) undo step.
        """
        s = self._scene
        items = [it for it in (s._selected_items or s.selectedItems())
                 if it.scene() is s]
        n = self.write_clipboard(items, snapped)
        was_cut = s._copy_is_cut and n is not None
        if n is None:
            s._show_status(self.CLIPBOARD_UNAVAILABLE, 5000)
        elif was_cut:
            sel = list(items)
            s.blockSignals(True)
            try:
                s._bulk_delete(sel, set(sel))
            finally:
                s.blockSignals(False)
            s.selectionChanged.emit()
            s.push_undo_state()
            s._show_status(f"Cut {n} item(s)")
        else:
            s._show_status(f"Copied {n} item(s)")
        s._copy_is_cut = False
        s._selected_items = []
        s.set_mode(None)
        if not was_cut:
            for it in items:
                if it.scene() is s:
                    it.setSelected(True)

    # ── Paste (D5, D13) ─────────────────────────────────────────────────────

    def begin_paste(self) -> bool:
        """Validate the clipboard and arm ``paste`` with the ghost on the cursor.

        Refusals (empty / foreign clipboard, containment D13) leave the mode
        untouched and only post a status message.

        Returns:
            True if ``paste`` was entered.
        """
        s = self._scene
        payload = s.clipboard_payload()
        if not payload or not payload.get("items"):
            s._show_status("Nothing to paste", 3000)
            return False
        types = {d.get("type", "") for d in payload["items"]}
        if s.scene_role != "block_editor" and types & set(s._GEOM_TYPE_REGISTRY):
            s._show_status("2D geometry can only be pasted in the Block Editor", 4000)
            return False
        # D13 allow-list: the Block Editor accepts only what _add_from_dict
        # registers; anything else (plan entities, gridline records with no
        # type key, openings, view markers, …) refuses the whole paste.
        if s.scene_role == "block_editor" and not types <= set(s._GEOM_TYPE_REGISTRY):
            s._show_status("Plan elements can't be pasted into the Block Editor", 4000)
            return False
        s.set_mode("paste")
        s._paste_payload = payload
        # The copied base point is the anchor of the ghost and the dX/dY HUD.
        s.node_start_pos = QPointF(*payload["base"])
        s._move_ghost_base = self._clipboard_ghost_paths(payload["items"])
        s._move_ghost = []
        # D5: the ghost rides the cursor from the moment Paste is entered.
        if s._last_scene_pos is not None:
            self._preview_from_move(QPointF(s._last_scene_pos))
        return True

    def commit_paste(self, offset: QPointF) -> None:
        """Paste the armed payload once, translated by *offset*; one undo step."""
        s = self._scene
        records = s._paste_payload["items"]
        s.clearSelection()
        new_items = s.paste_items(offset, data=records)
        skipped = len(records) - len(new_items)
        if new_items:
            s.push_undo_state()
        s._paste_payload = None
        s.node_start_pos = None
        s._move_ghost = []
        s._move_ghost_base = []
        s.clear_placement_state()
        s.set_mode(None)
        if not new_items:
            s._show_status("Nothing pasted", 3000)
            return
        for it in new_items:
            it.setSelected(True)
        msg = f"Pasted {len(new_items)} item(s)"
        s._show_status(msg + (f" ({skipped} skipped)" if skipped else ""))

    def _apply_paste_displacement(self, params: dict) -> bool:
        """Typed dX/dY for ``paste`` (D5): commit one paste at base + offset.

        Args:
            params: ``resolve_displacement``'s output — ``{"offset": QPointF}``.

        Returns:
            True — the paste is unconditional.
        """
        self.commit_paste(params["offset"])
        return True

    def begin_offset(self, sel) -> bool:   # replaced in Task 12
        self._scene.set_mode("offset")
        return True

    def clear(self, new_mode) -> None:
        """Idempotent teardown on every mode change (called from set_mode)."""
        s = self._scene
        # D11: every mode change (commit, Esc, tool switch) ends in set_mode,
        # so this is the one place the dimmed originals get their exact
        # prior opacity back.
        from .transform_ghost import restore_items
        restore_items(getattr(s, "_ghost_dimmed", None))
        s._ghost_dimmed = []
        if new_mode not in ("paste", "move", "duplicate"):
            s._move_ghost = []
            s._move_ghost_base = []
        if new_mode != "paste":
            s._paste_payload = None
        if new_mode != "rotate":
            s._rotate_pivot = None
            s._rotate_start_deg = None
            s._rotate_ray = None
        if new_mode in (None, "select"):
            s._copy_is_cut = False
            s._selected_items = None

    # ── Move / Paste gesture ────────────────────────────────────────────────

    def _press_paste_move(self, event, pos, snapped, item_under, node_under, pipe_under):
        s = self._scene
        if s.mode == "paste":
            # D5: the base is armed by begin_paste — one click commits.
            if s._paste_payload is None or s.node_start_pos is None:
                s.set_mode(None)          # entered without begin_paste
                return
            self.commit_paste(CAD_Math.get_vector(s.node_start_pos, snapped))
            return
        if s.node_start_pos is None:
            s.node_start_pos = snapped
            s._move_ghost_base = s._build_move_ghost_base()
            s._begin_move_handle_snap(snapped)
        else:
            snapped = s._move_handle_snap(event, snapped)
            offset = CAD_Math.get_vector(s.node_start_pos, snapped)
            if s.mode == "duplicate":
                self.commit_duplicate(offset)
                return
            if s.mode == "move":
                s.move_items(offset)
            s.push_undo_state()
            s.node_start_pos = None
            s._move_ghost = []
            s._move_ghost_base = []
            s.set_mode(None)

    def _preview_from_move(self, target) -> None:
        """Slide the move/paste ghost silhouette so the base point lands on
        ``target``.

        Rebuilds ``_move_ghost`` (read by ``drawForeground`` block 8) as the
        base silhouette translated by ``target - node_start_pos`` and repaints.
        A no-op before the base point is set.
        """
        s = self._scene
        if s.node_start_pos is None:
            return
        offset = QPointF(target.x() - s.node_start_pos.x(),
                         target.y() - s.node_start_pos.y())
        s._move_ghost = [p.translated(offset.x(), offset.y())
                         for p in s._move_ghost_base]
        for v in s.views():
            v.viewport().update()

    def _move_paste_move(self, event, snapped):
        """Ghost preview for paste/move: silhouette rides the cursor after the
        base point is set. Before that, show the plain cursor marker."""
        s = self._scene
        if s.node_start_pos is None:
            s.update_preview_node(snapped)
            s.preview_pipe.hide()
            return
        snapped = s._move_handle_snap(event, snapped)
        s.preview_node.hide()
        s.preview_pipe.hide()
        offset = QPointF(snapped.x() - s.node_start_pos.x(),
                         snapped.y() - s.node_start_pos.y())
        s._preview_from_move(snapped)
        # Feed the dynamic-input HUD its live dX/dY seed (measured from the
        # base point in ``_transform_seed_values``).  The status-bar readout
        # below is a separate surface and stays: S1 retired the painted
        # on-canvas Dim HUD, which move never used, not the status line — and
        # it carries ``dist``, which the two-field HUD does not.  A no-op while
        # a field has focus, so a mid-edit reseed cannot land.  ``paste``
        # seeds its dX/dY from the copied base point the same way (D5).
        s.publish_placement_state(s.node_start_pos, snapped)
        s._show_status(
            f"dx={offset.x():.1f}  dy={-offset.y():.1f}  "
            f"dist={math.hypot(offset.x(), offset.y()):.1f}", timeout=0)

    def begin_move_from(self, base: QPointF) -> None:
        """Enter the Move tool on the current selection with *base* preset.

        Skips Move's first (base-point) click: the selection immediately rides
        the cursor from *base*, and the next click places it (same commit /
        undo / Esc as an ordinary Move). Used by Block Editor import to place
        geometry by its picked base point.

        Args:
            base: Scene point that tracks the cursor.
        """
        s = self._scene
        s.set_mode("move")
        # D11: the imported geometry rides the cursor like any Move — dim it.
        from .transform_ghost import dim_items
        s._ghost_dimmed = dim_items(self._transformable(s._selected_items or []))
        s.node_start_pos = QPointF(base)
        s._move_ghost_base = s._build_move_ghost_base()
        s._begin_move_handle_snap(s.node_start_pos)

    def _begin_move_handle_snap(self, base: QPointF) -> None:
        """S2: build the Move tool's HandleSnapSession once the base is set.

        Move and Duplicate only (a paste has no scene items yet). The moving
        set is what ``move_items`` will move (``_selected_items``, else the
        live selection) plus each Sprinkler's Node; for Move none of it is a
        target, for Duplicate the originals stay targets (D6). The
        picked base point is itself a handle (rest = the base): the
        destination has no cursor snap, so this is how "base onto a point"
        still lands.

        Args:
            base: The Move base point — the handle offsets' anchor.
        """
        s = self._scene
        s._move_handle_session = None
        view = s._snap_view()
        # Built regardless of the snap toggles (items are at rest until the
        # commit); _move_handle_snap gates its use per frame.
        if s.mode not in ("move", "duplicate") or view is None:
            return
        moving = list(s._selected_items or s.selectedItems())
        moving += [it.node for it in moving
                   if isinstance(it, Sprinkler) and it.node is not None]
        if moving:
            # Duplicate's originals stay put, so they remain targets (D6).
            s._move_handle_session = HandleSnapSession(
                s._snap_engine, s, view, moving, QPointF(base),
                extra_handles=[QPointF(base)],
                exclude_moving=(s.mode == "move"))

    def _move_handle_snap(self, event, snapped: QPointF) -> QPointF:
        """S2: after the Move base point, the selection's own snap points
        (and the base point) snap to geometry — handles only: the destination
        has no cursor snap (``get_effective_position`` returns the raw cursor
        in this step), so without a hit the destination is the raw cursor.

        *event* is the scene's ``QGraphicsSceneMouseEvent`` (dispatched from
        ``mousePressEvent`` / ``mouseMoveEvent``), so the raw cursor is
        ``event.scenePos()``; direct callers without one fall back to
        *snapped*.

        Returns:
            The corrected destination (winning handle exactly on its target;
            marker published to ``_snap_result``), else *snapped* unchanged
            (the raw cursor from a real mouse event).
        """
        s = self._scene
        hs = s._move_handle_session
        if (hs is None or s.mode not in ("move", "duplicate")
                or s.node_start_pos is None
                or not s._snap_enabled or not s._snap_engine.enabled):
            return snapped
        # Zoom/pan between the base click and here: re-collect the targets
        # (visible rect + aperture scale). Safe — the moved items are at rest
        # until the commit (the preview is a ghost).
        hs.sync_view(s._snap_view())
        scene_pos = getattr(event, "scenePos", None)
        raw = scene_pos() if scene_pos is not None else snapped
        hit = hs.best(raw)
        if hit is None:
            return snapped
        corrected, res = hit
        s._snap_result = res          # marker only (never a hysteresis held)
        # No ALIGN in the destination step (handles only); kept defensive for
        # direct callers that computed *snapped* through the picker.
        s._align_result = None
        s._align_track_ray = None
        return corrected

    def _apply_move_displacement(self, params: dict) -> bool:
        """Apply a typed dX/dY displacement (transform schema — dict, not point).

        The commit half of the ``move`` branch of :meth:`_press_paste_move`,
        so a typed displacement and a dragged one share ``move_items`` and one
        undo push.  ``paste`` has its own applier
        (:meth:`_apply_paste_displacement`, D5).

        Every displacement commits: unlike the length/radius/spacing schemas
        there is no magnitude floor, so this always reports success (decision
        D2's verdict is still returned for the dispatcher's sake).

        Args:
            params: ``resolve_displacement``'s output — ``{"offset": QPointF}``,
                already Y-flipped into scene coordinates.

        Returns:
            True — the move is unconditional.
        """
        s = self._scene
        if s.mode == "duplicate":
            self.commit_duplicate(params["offset"])
            return True
        s.move_items(params["offset"])
        s.push_undo_state()
        s.node_start_pos = None
        s._move_ghost = []
        s._move_ghost_base = []
        s.clear_placement_state()
        s.set_mode(None)
        return True

    # ── Duplicate (D6) ──────────────────────────────────────────────────────

    def commit_duplicate(self, offset: QPointF) -> None:
        """Place one copy of the selection at *offset*; originals untouched.

        One undo step; returns to Select with the copies selected (D3).
        """
        s = self._scene
        src = [it for it in (s._selected_items or s.selectedItems())
               if it.scene() is s]
        # The same per-item serialiser + paste path as Copy/Paste, so every
        # selectable kind (2D geometry, text, nodes, gridlines, blocks) copies.
        records = s._clipboard_item_dicts(src)
        s.clearSelection()
        new_items = s.paste_items(offset, data=records)
        if new_items:
            s.push_undo_state()
        s._selected_items = []
        s.node_start_pos = None
        s._move_ghost = []
        s._move_ghost_base = []
        s.clear_placement_state()
        s.set_mode(None)
        if not new_items:
            s._show_status("Nothing duplicated", 3000)
            return
        for new in new_items:
            new.setSelected(True)
        skipped = len(records) - len(new_items)
        msg = f"Duplicated {len(new_items)} item(s)"
        s._show_status(msg + (f" ({skipped} skipped)" if skipped else ""))

    # ── Rotate (D8) ─────────────────────────────────────────────────────────
    # Angles are Y-up, CCW+ (scene Y is down): a +X point turned +90° about
    # the origin lands at scene (0, -100), visually up.

    @staticmethod
    def _heading(pivot: QPointF, p: QPointF) -> float:
        """Y-up heading (degrees, CCW+ from +X) of the ray *pivot* -> *p*."""
        return math.degrees(math.atan2(-(p.y() - pivot.y()), p.x() - pivot.x()))

    @staticmethod
    def _norm(d: float) -> float:
        """Normalise a sweep to (-180, 180]."""
        d = (d + 180.0) % 360.0 - 180.0
        return 180.0 if d == -180.0 else d

    def _rotatable(self, items) -> list:
        """The transformable *items* that can rotate (have ``manip_rotate``)."""
        return [it for it in self._transformable(items)
                if hasattr(it, "manip_rotate")]

    def rotate_delta_to(self, point) -> float:
        """Live relative sweep for *point* (0 until the start ray is picked).

        The one formula the ghost, the status readout and the HUD seed share.

        Args:
            point: The cursor (resolved) point, or None.

        Returns:
            The Y-up CCW+ sweep from the start ray to the pivot->*point* ray.
        """
        s = self._scene
        if (s._rotate_pivot is None or s._rotate_start_deg is None
                or point is None):
            return 0.0
        return self._norm(self._heading(s._rotate_pivot, point)
                          - s._rotate_start_deg)

    def press_rotate(self, event, pos, snapped, *_):
        """Rotate click: pivot, then start ray, then the end ray commits."""
        s = self._scene
        if s._rotate_pivot is None:
            s._rotate_pivot = QPointF(snapped)
            s._move_ghost_base = self._shape_paths_for_move(
                self._rotatable(s._selected_items))
            s._move_ghost = list(s._move_ghost_base)
            s.instructionChanged.emit(
                "Pick start of rotation (or type an angle)")
            return
        if s._rotate_start_deg is None:
            if (abs(snapped.x() - s._rotate_pivot.x()) < 1e-9
                    and abs(snapped.y() - s._rotate_pivot.y()) < 1e-9):
                return                    # a ray needs a direction
            s._rotate_start_deg = self._heading(s._rotate_pivot, snapped)
            s.instructionChanged.emit("Pick end of rotation (or type an angle)")
            return
        self.commit_rotate(self.rotate_delta_to(snapped))

    def move_rotate(self, event, snapped):
        """Rotate cursor: the ghost sweeps, the pivot->cursor ray follows."""
        s = self._scene
        s.preview_pipe.hide()
        if s._rotate_pivot is None:
            s.update_preview_node(snapped)
            return
        s.preview_node.hide()
        delta = self.rotate_delta_to(snapped)
        s._rotate_ray = (QPointF(s._rotate_pivot), QPointF(snapped))
        self.preview_rotate(delta)
        # Feed the HUD its live relative-angle seed (_transform_seed_values).
        s.publish_placement_state(s._rotate_pivot, snapped)
        s._show_status(f"Angle: {delta:.1f}°", timeout=0)

    def preview_rotate(self, delta_deg: float) -> None:
        """Rebuild the ghost as the base silhouette turned by *delta_deg*.

        ``QTransform.rotate`` is visually clockwise in the Y-down scene, so a
        Y-up CCW+ sweep maps to ``rotate(-delta_deg)``.
        """
        from PyQt6.QtGui import QTransform
        s = self._scene
        p = s._rotate_pivot
        if p is None:
            return
        t = (QTransform().translate(p.x(), p.y()).rotate(-delta_deg)
             .translate(-p.x(), -p.y()))
        s._move_ghost = [t.map(path) for path in s._move_ghost_base]
        for v in s.views():
            v.viewport().update()

    def commit_rotate(self, delta_deg: float) -> bool:
        """Rotate the selection by *delta_deg* (Y-up CCW+) about the pivot.

        Every item turns through its own ``manip_rotate`` (rectangles stay
        rectangles, D8). One undo step; returns to Select with the rotated
        items selected.

        Args:
            delta_deg: The relative sweep.

        Returns:
            True — a rotation always commits once the pivot is armed.
        """
        s = self._scene
        pivot = s._rotate_pivot
        if pivot is None:
            return False
        items = [it for it in (s._selected_items or [])
                 if it.scene() is s]
        targets = self._rotatable(items)
        for it in targets:
            it.manip_rotate(float(delta_deg), QPointF(pivot))
        for it in targets:
            fitting = getattr(it, "fitting", None)
            if fitting is not None:
                fitting.update()
        tools = getattr(s, "_tools", None)
        if tools is not None and targets:
            tools._solve_constraints()
        if targets:
            s.push_undo_state()
        s._move_ghost = []
        s._move_ghost_base = []
        s.clear_placement_state()
        s._selected_items = []
        s.set_mode(None)
        for it in items:
            if it.scene() is s:
                it.setSelected(True)
        s._show_status(f"Rotated {len(targets)} item(s) {delta_deg:.1f}°")
        return True

    def apply_rotate_by(self, params: dict) -> bool:
        """Typed relative angle (``rotate_by``): commit about the pivot."""
        return self.commit_rotate(float(params["delta_deg"]))

    # ── Ghost silhouettes ───────────────────────────────────────────────────

    def _shape_paths_for_move(self, items):
        """Scene-coord QPainterPath silhouettes for live scene *items*.
        Nodes have no useful shape() — emit a small cross marker."""
        from .model_space import _GHOST_NODE_MARKER_MM
        from .node import Node
        from .sprinkler import Sprinkler
        from .transform_ghost import ghost_base_paths
        paths = []
        for item in items:
            if isinstance(item, Sprinkler) and item.node is not None:
                item = item.node
            if isinstance(item, Node):
                c = item.scenePos()
                r = _GHOST_NODE_MARKER_MM
                p = QPainterPath()
                p.moveTo(c.x() - r, c.y()); p.lineTo(c.x() + r, c.y())
                p.moveTo(c.x(), c.y() - r); p.lineTo(c.x(), c.y() + r)
                paths.append(p)
                continue
            if isinstance(item, GridlineItem):
                # Ghost the centerline (grip endpoints), not the fat hit-strip
                # + bubbles that shape() returns.
                pts = item.grip_points()
                p = QPainterPath()
                p.moveTo(pts[0]); p.lineTo(pts[1])
                paths.append(p)
                continue
            # D11: trace the drawn geometry (halo_scene_path), not the fat
            # shape() hit region (double-rotated for rotated rects).
            traced = ghost_base_paths([item])
            if traced:
                paths.extend(traced)
                continue
            if hasattr(item, "sceneBoundingRect"):
                p = QPainterPath(); p.addRect(item.sceneBoundingRect())
                paths.append(p)
        return paths

    def _clipboard_ghost_paths(self, data):
        """Scene-coord silhouettes reconstructed from clipboard *data* dicts,
        without adding anything to the scene. Covers the copyable types."""
        from .model_space import _GHOST_NODE_MARKER_MM
        from .transform_ghost import ghost_base_paths
        paths = []
        if not data:
            return paths
        # One home for the type → class table (the scene's _add_from_dict
        # registry): the ghost can never disagree with what a paste creates.
        geom_ctors = {t: cls for t, (cls, _attr)
                      in self._scene._GEOM_TYPE_REGISTRY.items()}
        for obj in data:
            t = obj.get("type", "")
            if not t and "origin" in obj and "angle" in obj:
                # Gridline record: GridlineItem.to_dict() carries no "type".
                ox, oy = obj.get("origin", [0.0, 0.0])
                length = float(obj.get("length", 0.0))
                th = math.radians(float(obj.get("angle", 0.0)))
                p = QPainterPath(); p.moveTo(ox, oy)
                p.lineTo(ox + length * math.cos(th), oy - length * math.sin(th))
                paths.append(p)
            elif t == "node":
                c = QPointF(obj.get("x", 0.0), obj.get("y", 0.0))
                r = _GHOST_NODE_MARKER_MM
                p = QPainterPath()
                p.moveTo(c.x() - r, c.y()); p.lineTo(c.x() + r, c.y())
                p.moveTo(c.x(), c.y() - r); p.lineTo(c.x(), c.y() + r)
                for seg in obj.get("pipes", []):
                    p.moveTo(c.x(), c.y()); p.lineTo(seg.get("x", 0.0), seg.get("y", 0.0))
                paths.append(p)
            elif t in geom_ctors:
                try:
                    item = geom_ctors[t].from_dict(obj)
                except Exception:
                    continue
                paths.extend(ghost_base_paths([item]))
        return paths

    def _build_move_ghost_base(self):
        """Base silhouettes (offset 0) of the live selection (Move/Duplicate).
        Paste builds its own from the payload (``begin_paste``)."""
        s = self._scene
        return s._shape_paths_for_move(s._selected_items or s.selectedItems())
