"""
scene_tools.py
==============
Geometry editing tools for Model_Space, composed as ``scene._tools``
(``SceneTools``).  Extracted from Model_Space.py to keep the main scene class
focused on interactive mouse/keyboard handling.

Tools included:
- Offset (line intersection, polyline offset, perpendicular distance)
- Rotate, Scale, Mirror
- Join, Explode
- Break, Break-at-Point
- Fillet, Chamfer
- Stretch (crossing window)
- Trim, Extend
- Merge, Hatch
- Geometry helpers (grip hit, item segments, intersections)
"""

from __future__ import annotations

import contextlib
import copy
import math
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPen, QBrush, QColor
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem,
    QGraphicsPathItem, QGraphicsRectItem,
)

from .geometry_2d import (
    PolylineItem, LineItem, RectangleItem, CircleItem, ArcItem,
)
from .node import Node

from . import geometry_intersect as gi
from . import tool_geometry
from .stroke_style import copy_style
from .arc_math import yup_angle

from .tool_geometry import extract_edges  # re-exported for existing importers


def _fresh_end(item, end: str) -> None:
    """Reset one end of an in-place-trimmed item to By Linetype (LT2-3)."""
    st = getattr(item, "style", None)
    if st is not None:
        st[end]["end"] = "by_linetype"


# ``extract_edges`` moved to ``tool_geometry.py`` (Model_Space decomposition,
# slice A) and is re-exported above so existing importers keep working.


class SceneTools:
    """Geometry editing tools for Model_Space, composed as ``scene._tools``.

    Holds a back-reference to the owning ``Model_Space`` (``self._scene``);
    scene-graph mutation and shared placement state go through it, while
    sibling tool methods are called on ``self``.
    """

    def __init__(self, scene):
        self._scene = scene

    # ======================================================================
    # OFFSET COMMAND helpers
    # ======================================================================

    # ─────────────────────────────────────────────────────────────────────────
    # OFFSET COMMAND helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _offset_line_intersection(
        self, p1: QPointF, d1: QPointF, p2: QPointF, d2: QPointF
    ) -> "QPointF | None":
        """Delegates to :func:`tool_geometry.offset_line_intersection`."""
        return tool_geometry.offset_line_intersection(p1, d1, p2, d2)

    def _offset_polyline_pts(
        self, pts: list, signed_dist: float
    ) -> list:
        """Delegates to :func:`tool_geometry.offset_polyline_pts`."""
        return tool_geometry.offset_polyline_pts(pts, signed_dist)

    # Offset item creation, the cursor distance and the preview live in
    # tool_geometry.offset_item / distance_to_item and ModifyToolsController
    # (scene-tools.md D9).

    # ======================================================================
    # ARRAY / ROTATE / SCALE / MIRROR / JOIN / EXPLODE / BREAK
    # FILLET / CHAMFER / STRETCH / TRIM / EXTEND / MERGE / HATCH
    # GEOMETRY HELPERS
    # ======================================================================

    # Array lives in ModifyToolsController (scene-tools.md D10: on-canvas
    # linear only; the ArrayDialog / array_items path is retired).

    # -------------------------------------------------------------------------
    # ROTATE SELECTED (Sprint M recovery)

    # -------------------------------------------------------------------------
    # INTERACTIVE TRANSFORMS (Rotate / Scale / Mirror)

    # Rotate lives in ModifyToolsController.commit_rotate (scene-tools.md D8:
    # per-item manip_rotate; the legacy rect->polyline _apply_rotate is retired).
    # Flip / Mirror live in ModifyToolsController.commit_reflect (P1 DD4:
    # per-item manip_reflect; the legacy _apply_mirror is retired).
    # Scale lives in ModifyToolsController.commit_scale (P1 DD4: per-item
    # manip_scale_about; the legacy _apply_scale is retired).

    # -------------------------------------------------------------------------
    # GEOMETRY OPERATIONS (Join / Explode)

    def join_selected_items(self):
        """Join selected lines/polylines into a single polyline if endpoints match."""
        items = [i for i in self._scene.selectedItems()
                 if isinstance(i, (LineItem, PolylineItem))]
        if len(items) < 2:
            self._scene._show_status("Select 2+ lines/polylines to join", 3000)
            return
        TOL = 1.0  # tolerance in scene units
        # Extract segments as ordered point lists
        segments = []
        seg_items = [i for i in items]       # source item per segment
        for item in items:
            if isinstance(item, LineItem):
                segments.append([QPointF(item._pt1), QPointF(item._pt2)])
            elif isinstance(item, PolylineItem):
                segments.append([QPointF(p) for p in item._points])
        # Greedy chain builder
        chain = list(segments.pop(0))
        # Source (item, reversed-into-chain) of the chain's first / last
        # segment -- the outer ends take their end settings (LT2-3).
        head_src = tail_src = (seg_items.pop(0), False)
        changed = True
        while changed and segments:
            changed = False
            for i, seg in enumerate(segments):
                head, tail = chain[0], chain[-1]
                s_head, s_tail = seg[0], seg[-1]
                def _close(a, b):
                    return abs(a.x()-b.x()) < TOL and abs(a.y()-b.y()) < TOL
                if _close(tail, s_head):
                    chain.extend(seg[1:])
                    tail_src = (seg_items[i], False)
                    segments.pop(i); seg_items.pop(i); changed = True; break
                elif _close(tail, s_tail):
                    chain.extend(reversed(seg[:-1]))
                    tail_src = (seg_items[i], True)
                    segments.pop(i); seg_items.pop(i); changed = True; break
                elif _close(head, s_tail):
                    chain = seg[:-1] + chain
                    head_src = (seg_items[i], False)
                    segments.pop(i); seg_items.pop(i); changed = True; break
                elif _close(head, s_head):
                    chain = list(reversed(seg[1:])) + chain
                    head_src = (seg_items[i], True)
                    segments.pop(i); seg_items.pop(i); changed = True; break
        if segments:
            self._scene._show_status("Cannot join: endpoints do not match", 3000)
            return
        # Create merged polyline
        color = items[0].pen().color().name()
        lw = items[0].pen().widthF()
        pl = PolylineItem(chain[0], color=color, lineweight=lw)
        copy_style(items[0], pl)
        for end, (src, rev) in (("start", head_src), ("finish", tail_src)):
            src_st = getattr(src, "style", None)
            if src_st is not None and pl.style is not None:
                src_end = ("finish" if end == "start" else "start") if rev else end
                pl.style[end] = copy.deepcopy(src_st[src_end])
        for pt in chain[1:]:
            pl.append_point(pt)
        pl.finalize()
        # Remove originals
        for item in items:
            if item.scene() is self._scene:
                self._scene.removeItem(item)
            if isinstance(item, LineItem) and item in self._scene._draw_lines:
                self._scene._draw_lines.remove(item)
            elif isinstance(item, PolylineItem) and item in self._scene._polylines:
                self._scene._polylines.remove(item)
        self._scene.addItem(pl)
        self._scene._polylines.append(pl)
        pl.setSelected(True)
        self._scene.push_undo_state()
        self._scene._show_status("Joined into polyline", 2000)

    def explode_selected_items(self):
        """Explode polylines into lines and rectangles into 4 lines."""
        items = [i for i in self._scene.selectedItems()
                 if isinstance(i, (PolylineItem, RectangleItem))]
        if not items:
            self._scene._show_status("Select polylines or rectangles to explode", 3000)
            return
        for item in items:
            color = item.pen().color().name()
            lw = item.pen().widthF()
            if isinstance(item, PolylineItem):
                pts = item._points
                for i in range(len(pts) - 1):
                    ln = LineItem(QPointF(pts[i]), QPointF(pts[i+1]),
                                  color=color, lineweight=lw)
                    copy_style(item, ln)
                    self._scene.addItem(ln)
                    self._scene._draw_lines.append(ln)
                if item.scene() is self._scene:
                    self._scene.removeItem(item)
                if item in self._scene._polylines:
                    self._scene._polylines.remove(item)
            elif isinstance(item, RectangleItem):
                # Scene corners (data rotation applied), not the local rect().
                g = item.grip_points()
                corners = [g[0], g[2], g[4], g[6]]
                for i in range(4):
                    ln = LineItem(QPointF(corners[i]), QPointF(corners[(i+1)%4]),
                                  color=color, lineweight=lw)
                    copy_style(item, ln)
                    self._scene.addItem(ln)
                    self._scene._draw_lines.append(ln)
                if item.scene() is self._scene:
                    self._scene.removeItem(item)
                if item in self._scene._draw_rects:
                    self._scene._draw_rects.remove(item)
        self._scene.push_undo_state()
        self._scene._show_status("Exploded into individual segments", 2000)

    # -------------------------------------------------------------------------
    # BREAK / BREAK AT POINT

    def _break_item(self, item, bp1: QPointF, bp2: QPointF):
        """Break *item* between two points, removing the segment between them."""
        if isinstance(item, LineItem):
            t1 = gi.point_on_segment_param(bp1, item._pt1, item._pt2)
            t2 = gi.point_on_segment_param(bp2, item._pt1, item._pt2)
            if t1 > t2:
                t1, t2 = t2, t1
                bp1, bp2 = bp2, bp1
            proj1 = QPointF(item._pt1.x() + t1*(item._pt2.x()-item._pt1.x()),
                            item._pt1.y() + t1*(item._pt2.y()-item._pt1.y()))
            proj2 = QPointF(item._pt1.x() + t2*(item._pt2.x()-item._pt1.x()),
                            item._pt1.y() + t2*(item._pt2.y()-item._pt1.y()))
            color = item.pen().color().name()
            lw = item.pen().widthF()
            l1 = LineItem(QPointF(item._pt1), proj1, color=color, lineweight=lw)
            l2 = LineItem(proj2, QPointF(item._pt2), color=color, lineweight=lw)
            copy_style(item, l1, fresh_ends=("finish",))
            copy_style(item, l2, fresh_ends=("start",))
            if item.scene() is self._scene:
                self._scene.removeItem(item)
            if item in self._scene._draw_lines:
                self._scene._draw_lines.remove(item)
            for ln in (l1, l2):
                self._scene.addItem(ln)
                self._scene._draw_lines.append(ln)
        elif isinstance(item, CircleItem):
            # Convert to arc, removing segment between the two angles
            a1 = yup_angle(item._center, bp1)
            a2 = yup_angle(item._center, bp2)
            span = (a1 - a2) % 360
            arc = ArcItem(QPointF(item._center), item._radius, a2, span,
                          color=item.pen().color().name(),
                          lineweight=item.pen().widthF())
            copy_style(item, arc, fresh_ends=("start", "finish"))
            if item.scene() is self._scene:
                self._scene.removeItem(item)
            if item in self._scene._draw_circles:
                self._scene._draw_circles.remove(item)
            self._scene.addItem(arc)
            self._scene._draw_arcs.append(arc)

    def _break_at_point(self, item, bp: QPointF):
        """Split *item* into two at *bp*."""
        if isinstance(item, LineItem):
            t = gi.point_on_segment_param(bp, item._pt1, item._pt2)
            proj = QPointF(item._pt1.x() + t*(item._pt2.x()-item._pt1.x()),
                           item._pt1.y() + t*(item._pt2.y()-item._pt1.y()))
            color = item.pen().color().name()
            lw = item.pen().widthF()
            l1 = LineItem(QPointF(item._pt1), proj, color=color, lineweight=lw)
            l2 = LineItem(proj, QPointF(item._pt2), color=color, lineweight=lw)
            copy_style(item, l1, fresh_ends=("finish",))
            copy_style(item, l2, fresh_ends=("start",))
            if item.scene() is self._scene:
                self._scene.removeItem(item)
            if item in self._scene._draw_lines:
                self._scene._draw_lines.remove(item)
            for ln in (l1, l2):
                self._scene.addItem(ln)
                self._scene._draw_lines.append(ln)
        elif isinstance(item, CircleItem):
            a = yup_angle(item._center, bp)
            arc = ArcItem(QPointF(item._center), item._radius,
                          a + 0.5, 359.0,
                          color=item.pen().color().name(),
                          lineweight=item.pen().widthF())
            copy_style(item, arc, fresh_ends=("start", "finish"))
            if item.scene() is self._scene:
                self._scene.removeItem(item)
            if item in self._scene._draw_circles:
                self._scene._draw_circles.remove(item)
            self._scene.addItem(arc)
            self._scene._draw_arcs.append(arc)
        elif isinstance(item, ArcItem):
            a = yup_angle(item._center, bp)
            # Normalize to arc range
            rel = (a - item._start_deg) % 360
            if rel > abs(item._span_deg):
                return  # point outside arc
            s = item._span_deg
            a1 = ArcItem(QPointF(item._center), item._radius,
                         item._start_deg, rel,
                         color=item.pen().color().name(),
                         lineweight=item.pen().widthF())
            a2 = ArcItem(QPointF(item._center), item._radius,
                         item._start_deg + rel, s - rel,
                         color=item.pen().color().name(),
                         lineweight=item.pen().widthF())
            copy_style(item, a1, fresh_ends=("finish",))
            copy_style(item, a2, fresh_ends=("start",))
            if item.scene() is self._scene:
                self._scene.removeItem(item)
            if item in self._scene._draw_arcs:
                self._scene._draw_arcs.remove(item)
            for ai in (a1, a2):
                self._scene.addItem(ai)
                self._scene._draw_arcs.append(ai)

    # -------------------------------------------------------------------------
    # FILLET / CHAMFER

    def _compute_fillet(self, item1, item2, radius):
        """Delegates to :func:`tool_geometry.compute_fillet`."""
        return tool_geometry.compute_fillet(item1, item2, radius)

    def _commit_fillet(self, data):
        """Create the fillet arc and trim the source lines."""
        if data is None:
            return
        arc = ArcItem(data["center"], data["radius"], data["start"], data["span"],
                      color=data["item1"].pen().color().name(),
                      lineweight=data["item1"].pen().widthF())
        copy_style(data["item1"], arc, fresh_ends=("start", "finish"))
        self._scene.addItem(arc)
        self._scene._draw_arcs.append(arc)
        # Trim lines to tangent points
        setattr(data["item1"], data["near1"], QPointF(data["tp1"]))
        _fresh_end(data["item1"], "start" if data["near1"] == "_pt1" else "finish")
        item1 = data["item1"]
        item1.setLine(item1._pt1.x(), item1._pt1.y(), item1._pt2.x(), item1._pt2.y())
        setattr(data["item2"], data["near2"], QPointF(data["tp2"]))
        _fresh_end(data["item2"], "start" if data["near2"] == "_pt1" else "finish")
        item2 = data["item2"]
        item2.setLine(item2._pt1.x(), item2._pt1.y(), item2._pt2.x(), item2._pt2.y())

    def _compute_chamfer(self, item1, item2, dist):
        """Delegates to :func:`tool_geometry.compute_chamfer`."""
        return tool_geometry.compute_chamfer(item1, item2, dist)

    def _commit_chamfer(self, data):
        """Create chamfer bevel line and trim source lines."""
        if data is None:
            return
        ln = LineItem(data["cp1"], data["cp2"],
                      color=data["item1"].pen().color().name(),
                      lineweight=data["item1"].pen().widthF())
        copy_style(data["item1"], ln, fresh_ends=("start", "finish"))
        self._scene.addItem(ln)
        self._scene._draw_lines.append(ln)
        setattr(data["item1"], data["near1"], QPointF(data["cp1"]))
        _fresh_end(data["item1"], "start" if data["near1"] == "_pt1" else "finish")
        item1 = data["item1"]
        item1.setLine(item1._pt1.x(), item1._pt1.y(), item1._pt2.x(), item1._pt2.y())
        setattr(data["item2"], data["near2"], QPointF(data["cp2"]))
        _fresh_end(data["item2"], "start" if data["near2"] == "_pt1" else "finish")
        item2 = data["item2"]
        item2.setLine(item2._pt1.x(), item2._pt1.y(), item2._pt2.x(), item2._pt2.y())

    # -------------------------------------------------------------------------
    # STRETCH

    def begin_stretch_crossing(self, scene_rect: QRectF):
        """Collect vertices inside crossing window, transition to base point pick."""
        self._scene._stretch_vertices = []
        self._scene._stretch_full_items = []
        all_geom = self._all_geometry_items()
        for item in all_geom:
            if not hasattr(item, "grip_points"):
                continue
            grips = item.grip_points()
            inside = [(idx, g) for idx, g in enumerate(grips)
                      if scene_rect.contains(g)]
            if not inside:
                continue
            if len(inside) == len(grips):
                self._scene._stretch_full_items.append(item)
            else:
                for idx, g in inside:
                    self._scene._stretch_vertices.append((item, idx, QPointF(g)))
        if not self._scene._stretch_vertices and not self._scene._stretch_full_items:
            self._scene._show_status("No vertices in crossing window", 3000)
            return
        count = len(self._scene._stretch_vertices) + len(self._scene._stretch_full_items)
        self._scene._show_status(f"Captured {count} items/vertices. Pick base point.")
        self._scene.instructionChanged.emit("Pick base point")

    def _commit_stretch(self, delta: QPointF):
        """Apply stretch delta to captured vertices and full items."""
        for item in self._scene._stretch_full_items:
            if hasattr(item, 'translate'):
                item.translate(delta.x(), delta.y())
            elif isinstance(item, Node):
                item.moveBy(delta.x(), delta.y())
        for item, idx, _orig in self._scene._stretch_vertices:
            grips = item.grip_points()
            if idx < len(grips):
                new_pt = QPointF(grips[idx].x() + delta.x(),
                                 grips[idx].y() + delta.y())
                item.apply_grip(idx, new_pt)

    # =========================================================================
    # TRIM / EXTEND / MERGE  (Sprint Y)
    # =========================================================================

    def _all_geometry_items(self):
        """Return a flat list of all construction geometry items in the scene."""
        from .geometry_2d import (
            LineItem, RectangleItem, CircleItem, ArcItem, PolylineItem,
            RegularPolygonItem, EllipseItem, SplineItem,
        )
        items = []
        items.extend(self._scene._draw_lines)
        items.extend(getattr(self._scene, "_reference_lines", []))
        items.extend(self._scene._draw_rects)
        items.extend(self._scene._draw_circles)
        items.extend(self._scene._draw_arcs)
        items.extend(getattr(self._scene, "_draw_ellipses", []))
        items.extend(getattr(self._scene, "_draw_splines", []))
        items.extend(self._scene._polylines)
        items.extend(self._scene._draw_polygons)
        # Text (containment C5) — appended last (callers that key off this
        # list order stay stable).
        items.extend(getattr(self._scene, "_texts", []))
        return items

    def _find_geometry_at(self, pos: QPointF):
        """Find the geometry item nearest to pos (within tolerance)."""
        from .geometry_2d import (
            LineItem, RectangleItem, CircleItem, ArcItem, PolylineItem,
        )
        tol = 8.0
        views = self._scene.views()
        if views:
            scale = views[0].transform().m11()
            tol = 8.0 / max(scale, 1e-6)

        best_item = None
        best_dist = tol
        for item in self._all_geometry_items():
            if hasattr(item, 'shape'):
                path = item.shape()
                # Check if point is near the item's shape
                item_pos = item.mapFromScene(pos)
                if path.contains(item_pos):
                    return item
                # Also check distance to bounding rect as fallback
            if hasattr(item, 'grip_points'):
                for gpt in item.grip_points():
                    d = math.hypot(pos.x() - gpt.x(), pos.y() - gpt.y())
                    if d < best_dist:
                        best_dist = d
                        best_item = item
        return best_item

    def _find_endpoint_hit(self, pos: QPointF):
        """Find endpoint grip on any geometry item near pos (not just selected).
        Returns (item, grip_index, QPointF) or None."""
        from .geometry_2d import (
            LineItem, PolylineItem, ArcItem,
        )
        views = self._scene.views()
        if not views:
            return None
        scale = views[0].transform().m11()
        tol = 8.0 / max(scale, 1e-6)

        for item in self._all_geometry_items():
            if not hasattr(item, 'grip_points'):
                continue
            grips = item.grip_points()
            for idx, gpt in enumerate(grips):
                # Only allow endpoints — skip midpoints, centers, etc.
                if isinstance(item, LineItem) and idx == 1:
                    continue  # skip midpoint
                if isinstance(item, ArcItem) and idx == 0:
                    continue  # skip center
                if math.hypot(pos.x() - gpt.x(), pos.y() - gpt.y()) <= tol:
                    return (item, idx, QPointF(gpt))
        return None

    def _clear_trim_state(self):
        """Clean up trim edge highlight and state."""
        if self._scene._trim_edge_highlight is not None:
            if self._scene._trim_edge_highlight.scene() is self._scene:
                self._scene.removeItem(self._scene._trim_edge_highlight)
            self._scene._trim_edge_highlight = None
        self._scene._trim_edge = None

    def _clear_extend_state(self):
        """Clean up extend boundary highlight and state."""
        if self._scene._extend_boundary_highlight is not None:
            if self._scene._extend_boundary_highlight.scene() is self._scene:
                self._scene.removeItem(self._scene._extend_boundary_highlight)
            self._scene._extend_boundary_highlight = None
        self._scene._extend_boundary = None

    def _highlight_item(self, item, color="#ff4400"):
        """Create a bright overlay highlight for an item."""
        highlight_pen = QPen(QColor(color), 3, Qt.PenStyle.SolidLine)
        highlight_pen.setCosmetic(True)
        if hasattr(item, 'line'):
            line = item.line()
            h = QGraphicsLineItem(line)
            h.setPen(highlight_pen)
            h.setZValue(250)
            self._scene.addItem(h)
            return h
        elif isinstance(item, RectangleItem) and item._angle != 0.0:
            # Data-rotated rect: highlight the rotated footprint, not rect().
            h = QGraphicsPathItem(item.mapToScene(item.get_closed_path()))
            h.setPen(highlight_pen)
            h.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            h.setZValue(250)
            self._scene.addItem(h)
            return h
        elif hasattr(item, 'rect'):
            h = QGraphicsRectItem(item.rect())
            h.setPen(highlight_pen)
            h.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            h.setZValue(250)
            self._scene.addItem(h)
            return h
        elif hasattr(item, 'path'):
            h = QGraphicsPathItem(item.path())
            h.setPen(highlight_pen)
            h.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            h.setZValue(250)
            self._scene.addItem(h)
            return h
        return None

    def _handle_trim_click(self, pos: QPointF):
        """Handle mouse click during trim mode."""
        from .geometry_2d import (
            LineItem, CircleItem, ArcItem, PolylineItem,
        )

        if self._scene.mode == "trim":
            # Phase 1: select cutting edge
            item = self._find_geometry_at(pos)
            if item is not None:
                self._scene._trim_edge = item
                self._scene._trim_edge_highlight = self._highlight_item(item)
                self._scene.mode = "trim_pick"
                self._scene.modeChanged.emit("trim_pick")
                self._scene.instructionChanged.emit(
                    "Click segment to trim (right-click to cancel)")
            return

        elif self._scene.mode == "trim_pick":
            # Phase 2: click segment to trim at intersection with cutting edge
            item = self._find_geometry_at(pos)
            if item is None or item is self._scene._trim_edge:
                return

            edge = self._scene._trim_edge
            # Find intersections between item and edge
            intersections = self._compute_intersections(item, edge)
            if not intersections:
                self._scene._show_status("No intersection found")
                return

            # Determine which portion to remove based on click position
            hit = gi.nearest_intersection(pos, intersections)
            if hit is None:
                return

            if isinstance(item, LineItem):
                # Shorten line by moving the nearer endpoint to the intersection
                grips = item.grip_points()
                d0 = math.hypot(pos.x() - grips[0].x(), pos.y() - grips[0].y())
                d2 = math.hypot(pos.x() - grips[2].x(), pos.y() - grips[2].y())
                if d0 < d2:
                    item.apply_grip(0, hit)  # move p1 to intersection
                    _fresh_end(item, "start")
                else:
                    item.apply_grip(2, hit)  # move p2 to intersection
                    _fresh_end(item, "finish")
                self._scene.push_undo_state()
                self._scene._show_status("Trimmed line")

            elif isinstance(item, CircleItem):
                # Convert circle to arc by removing the clicked portion
                ANG_EPS = 0.01  # degrees — tolerance for angle comparison
                center = item._center
                r = item._radius
                # Compute angle of each intersection point
                int_angles = []
                for ipt in intersections:
                    angle = yup_angle(center, ipt)
                    int_angles.append(angle % 360)

                if len(int_angles) < 2:
                    self._scene._show_status(
                        "Need at least two intersections to trim a circle")
                    return

                click_angle = yup_angle(center, pos) % 360

                if len(int_angles) > 2:
                    # Multiple intersections: find the bracketing pair that
                    # contains click_angle with the smallest angular span
                    sorted_angles = sorted(int_angles)
                    best_pair = None
                    best_span = 360.0
                    for i in range(len(sorted_angles)):
                        aa = sorted_angles[i]
                        ab = sorted_angles[(i + 1) % len(sorted_angles)]
                        # Check if click_angle lies between aa and ab (CCW)
                        if ab > aa:
                            in_range = aa <= click_angle <= ab
                            span_test = ab - aa
                        else:
                            in_range = click_angle >= aa or click_angle <= ab
                            span_test = (ab + 360 - aa) % 360
                        if in_range and span_test < best_span:
                            best_span = span_test
                            best_pair = (aa, ab)
                    if best_pair is None:
                        # Fallback: two angles closest to click
                        by_dist = sorted(
                            int_angles,
                            key=lambda a: min(abs(a - click_angle),
                                              360 - abs(a - click_angle)))
                        best_pair = tuple(sorted(by_dist[:2]))
                    a1, a2 = best_pair
                else:
                    a1, a2 = sorted(int_angles[:2])

                # Determine which arc to keep (the one NOT clicked)
                if a1 + ANG_EPS < click_angle < a2 - ANG_EPS:
                    # Click is in the shorter arc — keep the outer arc
                    start = a2
                    span = (a1 + 360 - a2) % 360
                else:
                    start = a1
                    span = a2 - a1

                # Validate resulting arc
                if span < ANG_EPS or span > 360 - ANG_EPS:
                    self._scene._show_status("Trim would produce degenerate arc")
                    return

                color = item.pen().color().name()
                lw = item.pen().widthF()
                arc = ArcItem(center, r, start, span, color, lw)
                copy_style(item, arc, fresh_ends=("start", "finish"))
                self._scene.addItem(arc)
                self._scene._draw_arcs.append(arc)

                # Remove original circle
                self._scene.removeItem(item)
                if item in self._scene._draw_circles:
                    self._scene._draw_circles.remove(item)
                self._scene.push_undo_state()
                self._scene._show_status("Trimmed circle to arc")

            elif isinstance(item, ArcItem):
                center = item._center
                int_angles = []
                for ipt in intersections:
                    angle = yup_angle(center, ipt) % 360
                    int_angles.append(angle)

                if not int_angles:
                    return
                trim_angle = int_angles[0]
                click_angle = yup_angle(center, pos) % 360

                start = item._start_deg % 360
                span = item._span_deg
                end = (start + span) % 360

                # Compute angular position of click within arc span
                rel_click = (click_angle - start) % 360
                rel_trim = (trim_angle - start) % 360
                # The trim point must fall strictly inside the (CCW, span > 0)
                # arc, else the kept span would be <= 0 (a CW / empty arc).
                if not (0.01 < rel_trim < span - 0.01):
                    self._scene._show_status("Trim point is not on the arc")
                    return

                if rel_click < rel_trim:
                    # Click is before trim point — keep from trim to end
                    item._start_deg = trim_angle
                    item._span_deg = span - rel_trim
                    _fresh_end(item, "start")
                else:
                    # Click is after trim point — keep from start to trim
                    item._span_deg = rel_trim
                    _fresh_end(item, "finish")

                item._rebuild_path()
                self._scene.push_undo_state()
                self._scene._show_status("Trimmed arc")

    def _handle_extend_click(self, pos: QPointF):
        """Handle mouse click during extend mode."""
        from .geometry_2d import LineItem, ArcItem, PolylineItem

        if self._scene.mode == "extend":
            item = self._find_geometry_at(pos)
            if item is not None:
                self._scene._extend_boundary = item
                self._scene._extend_boundary_highlight = self._highlight_item(item, "#00aa00")
                self._scene.mode = "extend_pick"
                self._scene.modeChanged.emit("extend_pick")
                self._scene.instructionChanged.emit(
                    "Click near endpoint to extend (right-click to cancel)")
            return

        elif self._scene.mode == "extend_pick":
            endpoint_hit = self._find_endpoint_hit(pos)
            if endpoint_hit is None:
                return
            item, grip_idx, grip_pt = endpoint_hit
            boundary = self._scene._extend_boundary

            if isinstance(item, (LineItem, PolylineItem)):
                # For polylines, only allow extending from first or last vertex
                if isinstance(item, PolylineItem):
                    n_verts = len(item._points)
                    if grip_idx != 0 and grip_idx != n_verts - 1:
                        self._scene._show_status("Can only extend from first or last vertex")
                        return

                intersections = self._compute_extend_intersections(
                    item, grip_idx, boundary)
                if not intersections:
                    self._scene._show_status("No intersection with boundary")
                    return
                hit = gi.nearest_intersection(grip_pt, intersections)
                if hit:
                    item.apply_grip(grip_idx, hit)
                    self._scene.push_undo_state()
                    kind = "polyline" if isinstance(item, PolylineItem) else "line"
                    self._scene._show_status(f"Extended {kind} to boundary")

    def _handle_merge_click(self, pos: QPointF):
        """Handle mouse click during merge points mode."""
        endpoint_hit = self._find_endpoint_hit(pos)
        if endpoint_hit is None:
            self._scene._show_status("No endpoint found nearby")
            return

        item, grip_idx, grip_pt = endpoint_hit

        if self._scene._merge_point1 is None:
            # First click — store the target point
            self._scene._merge_point1 = (item, grip_idx, grip_pt)
            self._scene.instructionChanged.emit("Click second endpoint to merge")
            # Create visual indicator
            marker = QGraphicsEllipseItem(-4, -4, 8, 8)
            marker.setPos(grip_pt)
            marker.setBrush(QBrush(QColor("#ff4400")))
            marker.setPen(QPen(QColor("#ff4400")))
            marker.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            marker.setZValue(300)
            self._scene.addItem(marker)
            self._scene._merge_preview = marker
        else:
            # Second click — move second endpoint to first
            target_pt = self._scene._merge_point1[2]
            item.apply_grip(grip_idx, target_pt)
            self._scene.push_undo_state()
            self._scene._show_status("Points merged")
            # Clean up
            if self._scene._merge_preview is not None:
                if self._scene._merge_preview.scene() is self._scene:
                    self._scene.removeItem(self._scene._merge_preview)
                self._scene._merge_preview = None
            self._scene._merge_point1 = None
            self._scene.instructionChanged.emit("Click first endpoint")

    def _compute_intersections(self, item, edge):
        """Delegates to :func:`tool_geometry.compute_intersections`."""
        return tool_geometry.compute_intersections(item, edge)

    def _compute_extend_intersections(self, item, grip_idx, boundary):
        """Delegates to :func:`tool_geometry.compute_extend_intersections`."""
        return tool_geometry.compute_extend_intersections(item, grip_idx, boundary)

    def _get_item_segments(self, item):
        """Delegates to :func:`tool_geometry.get_item_segments`."""
        return tool_geometry.get_item_segments(item)

    # ======================================================================
    # ALIGN TOOL
    # ======================================================================

    def _press_align(self, event, pos, snapped, item_under, node_under, pipe_under):
        """Two-pick align handler.

        First click: store reference edge nearest to cursor.
        Second click: find target item, compute perpendicular translation
        to align its nearest parallel edge with the reference, and move it.
        """
        from .gridline import GridlineItem
        from .geometry_intersect import is_parallel, perpendicular_translation

        if self._scene._align_reference is None:
            # ── First pick: reference edge ──────────────────────────────
            result = self._find_nearest_edge(pos)
            if result is None:
                self._scene._show_status("No edge found near cursor")
                return
            edge, ref_item = result
            self._scene._align_reference = (edge, ref_item)
            # Remove any hover highlight before creating reference highlight
            if self._scene._align_highlight is not None:
                if self._scene._align_highlight.scene() is self._scene:
                    self._scene.removeItem(self._scene._align_highlight)
                self._scene._align_highlight = None
            # Visual highlight: dashed line along the reference edge
            highlight = QGraphicsLineItem(
                edge[0].x(), edge[0].y(), edge[1].x(), edge[1].y())
            pen = QPen(QColor("#00bfff"), 2)
            pen.setCosmetic(True)
            pen.setStyle(Qt.PenStyle.DashLine)
            highlight.setPen(pen)
            highlight.setZValue(9999)
            self._scene.addItem(highlight)
            self._scene._align_highlight = highlight
            self._scene.instructionChanged.emit("Click element to align")
        else:
            # ── Second pick: target ─────────────────────────────────────
            ref_edge, ref_item = self._scene._align_reference

            # Determine target: selected items or item under cursor
            selected = [s for s in self._scene.selectedItems()
                        if s is not ref_item and s is not self._scene._align_highlight]
            if selected and item_under in selected:
                # Multi-select: item_under is the anchor
                self._execute_align(ref_edge, ref_item, item_under,
                                    group=selected)
            elif item_under is not None and item_under is not ref_item:
                # Single item
                self._execute_align(ref_edge, ref_item, item_under)
            else:
                result = self._find_nearest_edge(pos)
                if result is None:
                    self._scene._show_status("No target edge found")
                    return
                target_edge, target_item = result
                if target_item is ref_item:
                    self._scene._show_status("Target must differ from reference")
                    return
                self._execute_align(ref_edge, ref_item, target_item)

            # Clean up reference state
            self._scene._align_reference = None
            if self._scene._align_highlight is not None:
                if self._scene._align_highlight.scene() is self._scene:
                    self._scene.removeItem(self._scene._align_highlight)
                self._scene._align_highlight = None
            if self._scene._align_ghost is not None:
                if self._scene._align_ghost.scene() is self._scene:
                    self._scene.removeItem(self._scene._align_ghost)
                self._scene._align_ghost = None
            self._scene.instructionChanged.emit("Click reference edge")

    def _execute_align(self, ref_edge, ref_item, target, group=None):
        """Align *target* (and optional *group*) to *ref_edge*.

        Finds the nearest parallel edge on the target, computes the
        perpendicular delta, and moves the target accordingly.
        """
        from .gridline import GridlineItem
        from .geometry_intersect import is_parallel, perpendicular_translation

        delta = QPointF(0, 0)
        best_edge = None

        target_edges = extract_edges(target)
        ref_p1, ref_p2 = ref_edge

        if not target_edges:
            # Point-like item — project its position onto the reference line
            delta = perpendicular_translation(ref_p1, ref_p2, target.scenePos())
        else:
            best_dist = float("inf")
            for te in target_edges:
                if is_parallel(ref_p1, ref_p2, te[0], te[1]):
                    mid = QPointF((te[0].x() + te[1].x()) / 2,
                                  (te[0].y() + te[1].y()) / 2)
                    d = perpendicular_translation(ref_p1, ref_p2, mid)
                    dist = math.hypot(d.x(), d.y())
                    if dist < best_dist:
                        best_dist = dist
                        best_edge = te
                        delta = d

            if best_edge is None:
                self._scene._show_status("No parallel edge found on target")
                return

        items_to_move = [target] + (group[1:] if group else [])
        # Constraint seam (parametric-constraint-system.md §8): the move is
        # one edit; the context exits (solve) before the single undo push.
        ctl = getattr(self._scene, "constraint_ctl", None)
        with (ctl.edit(items_to_move) if ctl is not None
              else contextlib.nullcontext()):
            for item in items_to_move:
                if isinstance(item, GridlineItem):
                    if getattr(item, '_locked', False):
                        self._scene._show_status("Gridline is locked — skipped")
                        continue
                    # Use move_perpendicular for gridlines
                    # Compute signed perpendicular distance
                    nx, ny = item._perpendicular_vector()
                    dist_signed = delta.x() * nx + delta.y() * ny
                    item.move_perpendicular(dist_signed)
                elif hasattr(item, "translate"):
                    # Translate contract: 2D primitives keep pos() == (0,0)
                    # and move their internal coordinates.
                    item.translate(delta.x(), delta.y())
                elif hasattr(item, "manip_translate"):   # Text (D7)
                    item.manip_translate(delta.x(), delta.y())
                else:
                    item.moveBy(delta.x(), delta.y())

        self._scene.push_undo_state()
        self._scene._show_status("Aligned")
        for v in self._scene.views():
            v.viewport().update()

    def _find_nearest_edge(self, pos):
        """Spatial query: find the nearest edge segment to *pos*.

        Returns ``(edge, item)`` where *edge* is ``(QPointF, QPointF)``
        and *item* is the owning scene item, or ``None`` if nothing found.
        """
        tol = 20.0
        views = self._scene.views()
        if views:
            scale = views[0].transform().m11()
            tol = 20.0 / max(scale, 1e-6)

        search_rect = QRectF(pos.x() - tol, pos.y() - tol, tol * 2, tol * 2)
        candidates = self._scene.items(search_rect)

        best_edge = None
        best_item = None
        best_dist = tol

        for item in candidates:
            # Skip our own highlight / ghost items
            if item is self._scene._align_highlight or item is self._scene._align_ghost:
                continue
            # Skip lock indicator items
            if type(item).__name__ == '_LockIndicator':
                continue
            # Skip invisible items
            if not item.isVisible():
                continue
            edges = extract_edges(item)
            for edge in edges:
                d = self._point_to_segment_dist(pos, edge[0], edge[1])
                if d < best_dist:
                    best_dist = d
                    best_edge = edge
                    best_item = item

        if best_edge is None:
            return None
        return (best_edge, best_item)

    @staticmethod
    def _point_to_segment_dist(p, s1, s2):
        """Delegates to :func:`tool_geometry.point_to_segment_dist`."""
        return tool_geometry.point_to_segment_dist(p, s1, s2)

    def _move_align(self, event, snapped):
        """Live preview for the align tool.

        Before reference pick: highlight the nearest edge under the cursor
        with a dashed line.
        After reference pick: show a ghost dotted line where the target edge
        would land after alignment.
        """
        from .geometry_intersect import is_parallel, perpendicular_translation

        pos = snapped

        if self._scene._align_reference is None:
            # ── Pre-reference: highlight nearest edge ───────────────────
            result = self._find_nearest_edge(pos)
            if result is not None:
                edge, _ = result
                if self._scene._align_highlight is not None:
                    # Update existing highlight
                    self._scene._align_highlight.setLine(
                        edge[0].x(), edge[0].y(),
                        edge[1].x(), edge[1].y())
                else:
                    highlight = QGraphicsLineItem(
                        edge[0].x(), edge[0].y(),
                        edge[1].x(), edge[1].y())
                    pen = QPen(QColor("#00bfff"), 2)
                    pen.setCosmetic(True)
                    pen.setStyle(Qt.PenStyle.DashLine)
                    highlight.setPen(pen)
                    highlight.setZValue(9999)
                    self._scene.addItem(highlight)
                    self._scene._align_highlight = highlight
            else:
                # No edge nearby — remove highlight
                if self._scene._align_highlight is not None:
                    if self._scene._align_highlight.scene() is self._scene:
                        self._scene.removeItem(self._scene._align_highlight)
                    self._scene._align_highlight = None
        else:
            # ── Post-reference: ghost line showing projected position ───
            ref_edge, ref_item = self._scene._align_reference
            ref_p1, ref_p2 = ref_edge

            result = self._find_nearest_edge(pos)
            if result is not None:
                target_edge, target_item = result
                if target_item is not ref_item:
                    # Find nearest parallel edge
                    target_edges = extract_edges(target_item)
                    best_te = None
                    best_delta = QPointF(0, 0)
                    best_dist = float("inf")
                    for te in target_edges:
                        if is_parallel(ref_p1, ref_p2, te[0], te[1]):
                            mid = QPointF((te[0].x() + te[1].x()) / 2,
                                          (te[0].y() + te[1].y()) / 2)
                            d = perpendicular_translation(ref_p1, ref_p2, mid)
                            dist = math.hypot(d.x(), d.y())
                            if dist < best_dist:
                                best_dist = dist
                                best_te = te
                                best_delta = d

                    if best_te is not None:
                        # Show ghost line at projected position
                        gp1 = QPointF(best_te[0].x() + best_delta.x(),
                                      best_te[0].y() + best_delta.y())
                        gp2 = QPointF(best_te[1].x() + best_delta.x(),
                                      best_te[1].y() + best_delta.y())
                        if self._scene._align_ghost is not None:
                            self._scene._align_ghost.setLine(
                                gp1.x(), gp1.y(), gp2.x(), gp2.y())
                        else:
                            ghost = QGraphicsLineItem(
                                gp1.x(), gp1.y(), gp2.x(), gp2.y())
                            pen = QPen(QColor("#00ff88"), 2)
                            pen.setCosmetic(True)
                            pen.setStyle(Qt.PenStyle.DotLine)
                            ghost.setPen(pen)
                            ghost.setZValue(9999)
                            self._scene.addItem(ghost)
                            self._scene._align_ghost = ghost
                        return

            # No valid target — remove ghost
            if self._scene._align_ghost is not None:
                if self._scene._align_ghost.scene() is self._scene:
                    self._scene.removeItem(self._scene._align_ghost)
                self._scene._align_ghost = None