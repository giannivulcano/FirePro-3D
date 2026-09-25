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


class ModifyToolsController:
    """Behaviour for the 2D modify tools. See docs/specs/scene-tools.md."""

    # tool name -> scene mode entered by start()
    _TOOL_MODE = {"copy": "copy_base", "cut": "copy_base", "paste": "paste",
                  "duplicate": "duplicate", "move": "move", "rotate": "rotate",
                  "offset": "offset", "array": "array"}
    _SELECT_FIRST = {"copy", "cut", "duplicate", "move", "rotate", "array"}

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
            return self.begin_paste()          # Task 7 (returns False until then)
        if tool == "offset":
            return self.begin_offset(sel)      # Task 12
        s._copy_is_cut = (tool == "cut")
        s._selected_items = sel
        s.set_mode(self._TOOL_MODE[tool])
        return True

    def begin_paste(self) -> bool:     # replaced in Task 7
        return False

    def begin_offset(self, sel) -> bool:   # replaced in Task 12
        self._scene.set_mode("offset")
        return True

    def clear(self, new_mode) -> None:
        """Idempotent teardown on every mode change (called from set_mode)."""
        s = self._scene
        if new_mode not in ("paste", "move"):
            s._move_ghost = []
            s._move_ghost_base = []

    # ── Move / Paste gesture ────────────────────────────────────────────────

    def _press_paste_move(self, event, pos, snapped, item_under, node_under, pipe_under):
        s = self._scene
        if s.node_start_pos is None:
            s.node_start_pos = snapped
            s._move_ghost_base = s._build_move_ghost_base(is_paste=(s.mode == "paste"))
            s._begin_move_handle_snap(snapped)
        else:
            snapped = s._move_handle_snap(event, snapped)
            offset = CAD_Math.get_vector(s.node_start_pos, snapped)
            if s.mode == "paste":
                s.paste_items(offset)
            elif s.mode == "move":
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
        # a field has focus, so a mid-edit reseed cannot land.  ``paste`` also
        # reaches here, harmlessly: it has no schema, so nothing seeds from it.
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
        s.node_start_pos = QPointF(base)
        s._move_ghost_base = s._build_move_ghost_base(is_paste=False)
        s._begin_move_handle_snap(s.node_start_pos)

    def _begin_move_handle_snap(self, base: QPointF) -> None:
        """S2: build the Move tool's HandleSnapSession once the base is set.

        Move only (a paste has no scene items yet). The moving set is what
        ``move_items`` will move (``_selected_items``, else the live
        selection) plus each Sprinkler's Node, so none of it is a target. The
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
        if s.mode != "move" or view is None:
            return
        moving = list(s._selected_items or s.selectedItems())
        moving += [it.node for it in moving
                   if isinstance(it, Sprinkler) and it.node is not None]
        if moving:
            s._move_handle_session = HandleSnapSession(
                s._snap_engine, s, view, moving, QPointF(base),
                extra_handles=[QPointF(base)])

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
        if (hs is None or s.mode != "move" or s.node_start_pos is None
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
        undo push.  Only ``move`` routes here — ``paste`` is deliberately kept
        out of the schema and anchor tables (F2), because it commits through
        ``paste_items`` and would otherwise be applied as a move of the current
        selection.

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
        s.move_items(params["offset"])
        s.push_undo_state()
        s.node_start_pos = None
        s._move_ghost = []
        s._move_ghost_base = []
        s.clear_placement_state()
        s.set_mode(None)
        return True

    # ── Ghost silhouettes ───────────────────────────────────────────────────

    def _shape_paths_for_move(self, items):
        """Scene-coord QPainterPath silhouettes for live scene *items*.
        Nodes have no useful shape() — emit a small cross marker."""
        from .model_space import _GHOST_NODE_MARKER_MM
        from .node import Node
        from .sprinkler import Sprinkler
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
            if hasattr(item, "shape"):
                try:
                    paths.append(item.mapToScene(item.shape()))
                    continue
                except Exception:
                    pass
            if hasattr(item, "sceneBoundingRect"):
                p = QPainterPath(); p.addRect(item.sceneBoundingRect())
                paths.append(p)
        return paths

    def _clipboard_ghost_paths(self, data):
        """Scene-coord silhouettes reconstructed from clipboard *data* dicts,
        without adding anything to the scene. Covers the copyable types."""
        from .model_space import _GHOST_NODE_MARKER_MM
        from .geometry_2d import (
            LineItem, ReferenceLineItem, RectangleItem, CircleItem, ArcItem, PolylineItem,
            RegularPolygonItem as _RegularPolygonItem, EllipseItem as _EllipseItem,
            SplineItem as _SplineItem,
        )
        paths = []
        if not data:
            return paths
        geom_ctors = {
            "draw_line": LineItem, "reference_line": ReferenceLineItem,
            "draw_rectangle": RectangleItem,
            "draw_circle": CircleItem, "draw_arc": ArcItem, "polyline": PolylineItem,
            "polygon": _RegularPolygonItem, "draw_ellipse": _EllipseItem,
            "draw_spline": _SplineItem,
        }
        for obj in data:
            t = obj.get("type", "")
            if t == "gridline":
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
                    paths.append(item.mapToScene(item.shape()))
                except Exception:
                    pass
        return paths

    def _build_move_ghost_base(self, is_paste: bool):
        """Base silhouettes (offset 0). Paste → clipboard; move → live selection."""
        s = self._scene
        if is_paste:
            return s._clipboard_ghost_paths(s.clipboard_data())
        return s._shape_paths_for_move(s._selected_items or s.selectedItems())
