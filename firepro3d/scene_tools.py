"""
scene_tools.py
==============
Mixin providing geometry editing tools for Model_Space.

Extracted from Model_Space.py to keep the main scene class focused on
interactive mouse/keyboard handling.  Mixed into Model_Space's MRO.

Tools included:
- Offset (line intersection, polyline offset, perpendicular distance)
- Array (linear + polar)
- Rotate, Scale, Mirror
- Join, Explode
- Break, Break-at-Point
- Fillet, Chamfer
- Stretch (crossing window)
- Trim, Extend
- Merge, Hatch
- Constraints (concentric, dimensional)
- Geometry helpers (grip hit, item segments, intersections)
"""

from __future__ import annotations

import math
import json
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPen, QBrush, QColor, QPainterPath, QFont
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsLineItem, QApplication

from .construction_geometry import (
    ConstructionLine, PolylineItem, LineItem, RectangleItem, CircleItem, ArcItem,
)
from .node import Node
from .annotations import HatchItem
from .cad_math import CAD_Math
from . import geometry_intersect as gi


class SceneToolsMixin:
    """Geometry editing tools for the plan-view scene."""

    # ======================================================================
    # OFFSET COMMAND helpers
    # ======================================================================

    # ─────────────────────────────────────────────────────────────────────────
    # OFFSET COMMAND helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _offset_line_intersection(
        self, p1: QPointF, d1: QPointF, p2: QPointF, d2: QPointF
    ) -> "QPointF | None":
        """Return intersection of two infinite lines (p1+t*d1) and (p2+s*d2), or None."""
        denom = d1.x() * d2.y() - d1.y() * d2.x()
        if abs(denom) < 1e-10:
            return None  # parallel
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        t = (dx * d2.y() - dy * d2.x()) / denom
        return QPointF(p1.x() + t * d1.x(), p1.y() + t * d1.y())

    def _offset_polyline_pts(
        self, pts: list, signed_dist: float
    ) -> list:
        """Return offset polyline points (miter join at corners)."""
        n = len(pts)
        if n < 2:
            return list(pts)
        # Per-segment left-side unit normals
        normals = []
        for i in range(n - 1):
            dx = pts[i + 1].x() - pts[i].x()
            dy = pts[i + 1].y() - pts[i].y()
            seg_len = math.hypot(dx, dy)
            if seg_len < 1e-10:
                normals.append(None)
            else:
                normals.append((-dy / seg_len, dx / seg_len))

        result = []
        for i in range(n):
            if i == 0:
                nx, ny = normals[0] if normals[0] else (0.0, 0.0)
                result.append(QPointF(pts[0].x() + signed_dist * nx,
                                      pts[0].y() + signed_dist * ny))
            elif i == n - 1:
                nx, ny = normals[-1] if normals[-1] else (0.0, 0.0)
                result.append(QPointF(pts[-1].x() + signed_dist * nx,
                                      pts[-1].y() + signed_dist * ny))
            else:
                n1 = normals[i - 1]
                n2 = normals[i]
                if n1 is None:
                    n1 = n2
                if n2 is None:
                    n2 = n1
                # Offset lines: p_prev + t*(pts[i]-pts[i-1]) + d*n1
                #               pts[i] + s*(pts[i+1]-pts[i]) + d*n2
                op1 = QPointF(pts[i - 1].x() + signed_dist * n1[0],
                              pts[i - 1].y() + signed_dist * n1[1])
                op2 = QPointF(pts[i].x() + signed_dist * n1[0],
                              pts[i].y() + signed_dist * n1[1])
                op3 = QPointF(pts[i].x() + signed_dist * n2[0],
                              pts[i].y() + signed_dist * n2[1])
                op4 = QPointF(pts[i + 1].x() + signed_dist * n2[0],
                              pts[i + 1].y() + signed_dist * n2[1])
                d1 = QPointF(op2.x() - op1.x(), op2.y() - op1.y())
                d2 = QPointF(op4.x() - op3.x(), op4.y() - op3.y())
                inter = self._offset_line_intersection(op1, d1, op3, d2)
                if inter is not None:
                    result.append(inter)
                else:
                    result.append(op2)  # fallback: parallel segments
        return result

    def _perpendicular_distance(self, source, pt: QPointF) -> float:
        """Return the perpendicular distance from *pt* to *source* entity."""
        if isinstance(source, LineItem):
            line = source.line()
            p1 = source.mapToScene(line.p1())
            p2 = source.mapToScene(line.p2())
            dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
            seg_len = math.hypot(dx, dy)
            if seg_len < 1e-10:
                return math.hypot(pt.x() - p1.x(), pt.y() - p1.y())
            # Point-to-line distance (not segment — infinite line)
            return abs(dx * (p1.y() - pt.y()) - dy * (p1.x() - pt.x())) / seg_len

        if isinstance(source, PolylineItem):
            pts = source._points
            if len(pts) < 2:
                return 0.0
            # Minimum distance to any segment
            min_d = float("inf")
            for i in range(len(pts) - 1):
                a, b = pts[i], pts[i + 1]
                dx, dy = b.x() - a.x(), b.y() - a.y()
                seg_len = math.hypot(dx, dy)
                if seg_len < 1e-10:
                    continue
                d = abs(dx * (a.y() - pt.y()) - dy * (a.x() - pt.x())) / seg_len
                min_d = min(min_d, d)
            return min_d if min_d < float("inf") else 0.0

        if isinstance(source, CircleItem):
            cx = source.x() + source.boundingRect().center().x()
            cy = source.y() + source.boundingRect().center().y()
            r = source.boundingRect().width() / 2
            return abs(math.hypot(pt.x() - cx, pt.y() - cy) - r)

        if isinstance(source, RectangleItem):
            r = source.mapRectToScene(source.rect())
            # Distance to nearest edge
            cx = max(r.left(), min(pt.x(), r.right()))
            cy = max(r.top(), min(pt.y(), r.bottom()))
            if r.contains(pt):
                # Inside: distance to nearest edge
                return min(pt.x() - r.left(), r.right() - pt.x(),
                           pt.y() - r.top(), r.bottom() - pt.y())
            return math.hypot(pt.x() - cx, pt.y() - cy)

        if isinstance(source, ArcItem):
            cx, cy = source._center.x(), source._center.y()
            return abs(math.hypot(pt.x() - cx, pt.y() - cy) - source._radius)

        return 0.0

    def _offset_signed_dist(self, source, dist: float, side_pt: QPointF) -> float:
        """Return +dist or -dist depending on which side of source the cursor is on."""
        if isinstance(source, LineItem):
            line = source.line()
            p1 = source.mapToScene(line.p1())
            p2 = source.mapToScene(line.p2())
            dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
            # Cross product with cursor vector: positive → left of line
            cross = dx * (side_pt.y() - p1.y()) - dy * (side_pt.x() - p1.x())
            return dist if cross >= 0 else -dist
        if isinstance(source, PolylineItem):
            pts = source._points
            if len(pts) < 2:
                return dist
            p1, p2 = pts[0], pts[1]
            dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
            cross = dx * (side_pt.y() - p1.y()) - dy * (side_pt.x() - p1.x())
            return dist if cross >= 0 else -dist
        if isinstance(source, CircleItem):
            cx = source.x() + source.boundingRect().center().x()
            cy = source.y() + source.boundingRect().center().y()
            d = math.hypot(side_pt.x() - cx, side_pt.y() - cy)
            r = source.boundingRect().width() / 2
            return dist if d >= r else -dist
        if isinstance(source, RectangleItem):
            # cursor outside → grow, cursor inside → shrink
            r = source.mapRectToScene(source.rect())
            if r.contains(side_pt):
                return -dist
            return dist
        if isinstance(source, ArcItem):
            cx, cy = source._center.x(), source._center.y()
            d = math.hypot(side_pt.x() - cx, side_pt.y() - cy)
            return dist if d >= source._radius else -dist
        return dist

    def _make_offset_item(self, source, signed_dist: float):
        """Create and return a new item that is the offset of source, or None."""
        color = source.pen().color()
        lw = source.pen().widthF()

        if isinstance(source, LineItem):
            line = source.line()
            p1 = source.mapToScene(line.p1())
            p2 = source.mapToScene(line.p2())
            dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
            seg_len = math.hypot(dx, dy)
            if seg_len < 1e-10:
                return None
            nx, ny = -dy / seg_len, dx / seg_len
            new_p1 = QPointF(p1.x() + signed_dist * nx, p1.y() + signed_dist * ny)
            new_p2 = QPointF(p2.x() + signed_dist * nx, p2.y() + signed_dist * ny)
            item = LineItem(new_p1, new_p2, color, lw)
            item.user_layer = getattr(source, "user_layer", self.active_user_layer)
            item.level = getattr(source, "level", DEFAULT_LEVEL)
            return item

        if isinstance(source, PolylineItem):
            pts = source._points
            new_pts = self._offset_polyline_pts(pts, signed_dist)
            if len(new_pts) < 2:
                return None
            item = PolylineItem(new_pts[0], color, lw)
            for p in new_pts[1:]:
                item.append_point(p)
            item.user_layer = getattr(source, "user_layer", self.active_user_layer)
            item.level = getattr(source, "level", DEFAULT_LEVEL)
            return item

        if isinstance(source, CircleItem):
            r = source.boundingRect().width() / 2
            new_r = r + signed_dist
            if new_r <= 0:
                return None
            # CircleItem stores center as scene position of its bounding rect centre
            scene_rect = source.mapRectToScene(source.rect())
            cx = scene_rect.center().x()
            cy = scene_rect.center().y()
            item = CircleItem(QPointF(cx, cy), new_r, color, lw)
            item.user_layer = getattr(source, "user_layer", self.active_user_layer)
            item.level = getattr(source, "level", DEFAULT_LEVEL)
            return item

        if isinstance(source, RectangleItem):
            r = source.mapRectToScene(source.rect())
            new_r = r.adjusted(-signed_dist, -signed_dist, signed_dist, signed_dist)
            if new_r.width() <= 0 or new_r.height() <= 0:
                return None
            item = RectangleItem(new_r.topLeft(), new_r.bottomRight(), color, lw)
            item.user_layer = getattr(source, "user_layer", self.active_user_layer)
            item.level = getattr(source, "level", DEFAULT_LEVEL)
            return item

        if isinstance(source, ArcItem):
            new_r = source._radius + signed_dist
            if new_r <= 0:
                return None
            item = ArcItem(source._center, new_r,
                           source._start_deg, source._span_deg, color, lw)
            item.user_layer = getattr(source, "user_layer", self.active_user_layer)
            item.level = getattr(source, "level", DEFAULT_LEVEL)
            return item
        return None

    def _clear_offset_preview(self):
        if self._offset_preview is not None:
            if self._offset_preview.scene() is self:
                self.removeItem(self._offset_preview)
            self._offset_preview = None


    # ======================================================================
    # ARRAY / ROTATE / SCALE / MIRROR / JOIN / EXPLODE / BREAK
    # FILLET / CHAMFER / STRETCH / TRIM / EXTEND / MERGE / HATCH
    # CONSTRAINTS / GEOMETRY HELPERS
    # ======================================================================

    # -------------------------------------------------------------------------
    # ARRAY (Sprint J)

    def array_items(self, params: dict):
        """
        Duplicate selected items in a linear or polar array.

        params keys
        -----------
        mode : "linear" | "polar"

        Linear:
          rows, cols        : int
          x_spacing         : float  (scene units per column)
          y_spacing         : float  (scene units per row)

        Polar:
          cx, cy            : float  (centre of rotation in scene coords)
          count             : int    (total number of copies incl. original)
          total_angle       : float  (degrees, e.g. 360 for full circle)
          rotate_items      : bool   (rotate geometry orientation; Nodes only)
        """
        items = self.selectedItems()
        if not items:
            return

        # Only duplicate pipes whose both endpoints are in the selection
        selected_nodes = {i for i in items if isinstance(i, Node)}

        # Serialise selected items
        def _serialise(item):
            if isinstance(item, Node):
                sprinkler = item.sprinkler.get_properties() if item.has_sprinkler() else None
                pipes_d = []
                for p in item.pipes:
                    other = p.node1 if p.node2 == item else p.node2
                    if other in selected_nodes:
                        pipes_d.append({"x": other.pos().x(), "y": other.pos().y()})
                return {"type": "node", "x": item.pos().x(), "y": item.pos().y(),
                        "sprinkler": sprinkler, "pipes": pipes_d}
            elif hasattr(item, "to_dict"):
                return item.to_dict()
            return None

        data = [d for item in items if (d := _serialise(item)) is not None]
        if not data:
            return

        old_clip = QApplication.clipboard().text()

        mode = params.get("mode", "linear")

        if mode == "linear":
            rows = max(1, int(params.get("rows", 1)))
            cols = max(1, int(params.get("cols", 1)))
            xs   = float(params.get("x_spacing", 100))
            ys   = float(params.get("y_spacing", 100))

            QApplication.clipboard().setText(json.dumps(data))
            for r in range(rows):
                for c in range(cols):
                    if r == 0 and c == 0:
                        continue  # skip the original position
                    self.paste_items(QPointF(c * xs, -r * ys))

        elif mode == "polar":
            cx    = float(params.get("cx", 0))
            cy    = float(params.get("cy", 0))
            count = max(2, int(params.get("count", 4)))
            ta    = float(params.get("total_angle", 360))
            # angle step
            if abs(ta - 360) < 0.01:
                step = math.radians(ta / count)
            else:
                step = math.radians(ta / (count - 1))

            for i in range(1, count):
                angle = step * i
                cos_a, sin_a = math.cos(angle), math.sin(angle)
                rotated = []
                for obj in data:
                    rot = dict(obj)
                    if "x" in rot and "y" in rot:
                        ox, oy = rot["x"] - cx, rot["y"] - cy
                        rot["x"] = cx + ox * cos_a - oy * sin_a
                        rot["y"] = cy + ox * sin_a + oy * cos_a
                    # Rotate geometry point pairs
                    for key in ("pt1", "pt2"):
                        if key in rot:
                            ox = rot[key][0] - cx
                            oy = rot[key][1] - cy
                            rot[key] = [
                                cx + ox * cos_a - oy * sin_a,
                                cy + ox * sin_a + oy * cos_a,
                            ]
                    # Rotate circle centre
                    for cx_k, cy_k in (("cx", "cy"),):
                        if cx_k in rot and cy_k in rot:
                            ox = rot[cx_k] - cx
                            oy = rot[cy_k] - cy
                            rot[cx_k] = cx + ox * cos_a - oy * sin_a
                            rot[cy_k] = cy + ox * sin_a + oy * cos_a
                    # Rotate polyline vertices
                    if "points" in rot:
                        new_pts = []
                        for px, py in rot["points"]:
                            ox, oy = px - cx, py - cy
                            new_pts.append([cx + ox * cos_a - oy * sin_a,
                                            cy + ox * sin_a + oy * cos_a])
                        rot["points"] = new_pts
                    rotated.append(rot)
                QApplication.clipboard().setText(json.dumps(rotated))
                self.paste_items(QPointF(0, 0))

        QApplication.clipboard().setText(old_clip)
        self.push_undo_state()

    # -------------------------------------------------------------------------
    # ROTATE SELECTED (Sprint M recovery)

    # -------------------------------------------------------------------------
    # INTERACTIVE TRANSFORMS (Rotate / Scale / Mirror)

    def _apply_rotate(self, pivot: QPointF, angle_deg: float, items: list = None):
        """Rotate *items* around *pivot* by *angle_deg*."""
        if items is None:
            items = self._selected_items or self.selectedItems()
        rp = CAD_Math.rotate_point
        for item in items:
            if isinstance(item, Node):
                new_pos = rp(item.scenePos(), pivot, angle_deg)
                item.setPos(new_pos)
                item.fitting.update()
            elif isinstance(item, (LineItem, ConstructionLine)):
                item._pt1 = rp(item._pt1, pivot, angle_deg)
                item._pt2 = rp(item._pt2, pivot, angle_deg)
                if isinstance(item, LineItem):
                    item.setLine(item._pt1.x(), item._pt1.y(),
                                 item._pt2.x(), item._pt2.y())
                else:
                    item._recompute_line()
            elif isinstance(item, PolylineItem):
                item._points = [rp(p, pivot, angle_deg) for p in item._points]
                item._rebuild_path()
            elif isinstance(item, CircleItem):
                item._center = rp(item._center, pivot, angle_deg)
                r = item._radius
                item.setRect(item._center.x() - r, item._center.y() - r, 2*r, 2*r)
            elif isinstance(item, RectangleItem):
                # Convert to polyline (axis-aligned rect can't represent rotation)
                rect = item.rect()
                corners = [QPointF(rect.left(), rect.top()),
                           QPointF(rect.right(), rect.top()),
                           QPointF(rect.right(), rect.bottom()),
                           QPointF(rect.left(), rect.bottom()),
                           QPointF(rect.left(), rect.top())]
                rotated = [rp(c, pivot, angle_deg) for c in corners]
                pl = PolylineItem(rotated[0],
                                  color=item.pen().color().name(),
                                  lineweight=item.pen().widthF())
                for pt in rotated[1:]:
                    pl.append_point(pt)
                pl.finalize()
                pl.user_layer = getattr(item, "user_layer", "0")
                pl.level = getattr(item, "level", DEFAULT_LEVEL)
                self.addItem(pl)
                self._polylines.append(pl)
                # Remove original rect
                if item.scene() is self:
                    self.removeItem(item)
                if item in self._draw_rects:
                    self._draw_rects.remove(item)
            elif isinstance(item, ArcItem):
                item._center = rp(item._center, pivot, angle_deg)
                item._start_deg += angle_deg
                item._rebuild_path()

    def _apply_scale(self, base: QPointF, factor: float, items: list = None):
        """Scale *items* relative to *base* by *factor*."""
        if items is None:
            items = self._selected_items or self.selectedItems()
        sp = CAD_Math.scale_point
        for item in items:
            if isinstance(item, Node):
                new_pos = sp(item.scenePos(), base, factor)
                item.setPos(new_pos)
                item.fitting.update()
            elif isinstance(item, (LineItem, ConstructionLine)):
                item._pt1 = sp(item._pt1, base, factor)
                item._pt2 = sp(item._pt2, base, factor)
                if isinstance(item, LineItem):
                    item.setLine(item._pt1.x(), item._pt1.y(),
                                 item._pt2.x(), item._pt2.y())
                else:
                    item._recompute_line()
            elif isinstance(item, PolylineItem):
                item._points = [sp(p, base, factor) for p in item._points]
                item._rebuild_path()
            elif isinstance(item, CircleItem):
                item._center = sp(item._center, base, factor)
                item._radius *= factor
                r = item._radius
                item.setRect(item._center.x() - r, item._center.y() - r, 2*r, 2*r)
            elif isinstance(item, RectangleItem):
                rect = item.rect()
                tl = sp(rect.topLeft(), base, factor)
                br = sp(rect.bottomRight(), base, factor)
                item.setRect(QRectF(tl, br))
            elif isinstance(item, ArcItem):
                item._center = sp(item._center, base, factor)
                item._radius *= factor
                item._rebuild_path()

    def _apply_mirror(self, axis_p1: QPointF, axis_p2: QPointF):
        """Create mirrored copies of selected items across the axis line."""
        items = self._selected_items or self.selectedItems()
        mp = CAD_Math.mirror_point
        new_items = []
        for item in items:
            if isinstance(item, Node):
                new_pos = mp(item.scenePos(), axis_p1, axis_p2)
                node = self.add_node(new_pos.x(), new_pos.y())
                if item.has_sprinkler():
                    self.add_sprinkler(node, None)
                new_items.append(node)
            elif isinstance(item, LineItem):
                p1 = mp(item._pt1, axis_p1, axis_p2)
                p2 = mp(item._pt2, axis_p1, axis_p2)
                ln = LineItem(p1, p2, color=item.pen().color().name(),
                              lineweight=item.pen().widthF())
                ln.user_layer = getattr(item, "user_layer", "0")
                ln.level = getattr(item, "level", DEFAULT_LEVEL)
                self.addItem(ln)
                self._draw_lines.append(ln)
                new_items.append(ln)
            elif isinstance(item, PolylineItem):
                pts = [mp(p, axis_p1, axis_p2) for p in item._points]
                pl = PolylineItem(pts[0], color=item.pen().color().name(),
                                  lineweight=item.pen().widthF())
                for pt in pts[1:]:
                    pl.append_point(pt)
                pl.finalize()
                pl.user_layer = getattr(item, "user_layer", "0")
                pl.level = getattr(item, "level", DEFAULT_LEVEL)
                self.addItem(pl)
                self._polylines.append(pl)
                new_items.append(pl)
            elif isinstance(item, CircleItem):
                c = mp(item._center, axis_p1, axis_p2)
                ci = CircleItem(c, item._radius, color=item.pen().color().name(),
                                lineweight=item.pen().widthF())
                ci.user_layer = getattr(item, "user_layer", "0")
                ci.level = getattr(item, "level", DEFAULT_LEVEL)
                self.addItem(ci)
                self._draw_circles.append(ci)
                new_items.append(ci)
            elif isinstance(item, RectangleItem):
                rect = item.rect()
                tl = mp(rect.topLeft(), axis_p1, axis_p2)
                br = mp(rect.bottomRight(), axis_p1, axis_p2)
                ri = RectangleItem(tl, br, color=item.pen().color().name(),
                                   lineweight=item.pen().widthF())
                ri.user_layer = getattr(item, "user_layer", "0")
                ri.level = getattr(item, "level", DEFAULT_LEVEL)
                self.addItem(ri)
                self._draw_rects.append(ri)
                new_items.append(ri)
            elif isinstance(item, ArcItem):
                c = mp(item._center, axis_p1, axis_p2)
                # Mirror reverses arc direction
                ai = ArcItem(c, item._radius, item._start_deg,
                             -item._span_deg, color=item.pen().color().name(),
                             lineweight=item.pen().widthF())
                ai.user_layer = getattr(item, "user_layer", "0")
                ai.level = getattr(item, "level", DEFAULT_LEVEL)
                self.addItem(ai)
                self._draw_arcs.append(ai)
                new_items.append(ai)
            elif isinstance(item, ConstructionLine):
                p1 = mp(item._pt1, axis_p1, axis_p2)
                p2 = mp(item._pt2, axis_p1, axis_p2)
                cl = ConstructionLine(p1, p2)
                self.addItem(cl)
                self._construction_lines.append(cl)
                new_items.append(cl)
        return new_items

    # -------------------------------------------------------------------------
    # GEOMETRY OPERATIONS (Join / Explode)

    def join_selected_items(self):
        """Join selected lines/polylines into a single polyline if endpoints match."""
        items = [i for i in self.selectedItems()
                 if isinstance(i, (LineItem, PolylineItem))]
        if len(items) < 2:
            self._show_status("Select 2+ lines/polylines to join", 3000)
            return
        TOL = 1.0  # tolerance in scene units
        # Extract segments as ordered point lists
        segments = []
        for item in items:
            if isinstance(item, LineItem):
                segments.append([QPointF(item._pt1), QPointF(item._pt2)])
            elif isinstance(item, PolylineItem):
                segments.append([QPointF(p) for p in item._points])
        # Greedy chain builder
        chain = list(segments.pop(0))
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
                    segments.pop(i); changed = True; break
                elif _close(tail, s_tail):
                    chain.extend(reversed(seg[:-1]))
                    segments.pop(i); changed = True; break
                elif _close(head, s_tail):
                    chain = seg[:-1] + chain
                    segments.pop(i); changed = True; break
                elif _close(head, s_head):
                    chain = list(reversed(seg[1:])) + chain
                    segments.pop(i); changed = True; break
        if segments:
            self._show_status("Cannot join: endpoints do not match", 3000)
            return
        # Create merged polyline
        color = items[0].pen().color().name()
        lw = items[0].pen().widthF()
        pl = PolylineItem(chain[0], color=color, lineweight=lw)
        for pt in chain[1:]:
            pl.append_point(pt)
        pl.finalize()
        pl.user_layer = getattr(items[0], "user_layer", "0")
        pl.level = getattr(items[0], "level", DEFAULT_LEVEL)
        # Remove originals
        for item in items:
            if item.scene() is self:
                self.removeItem(item)
            if isinstance(item, LineItem) and item in self._draw_lines:
                self._draw_lines.remove(item)
            elif isinstance(item, PolylineItem) and item in self._polylines:
                self._polylines.remove(item)
        self.addItem(pl)
        self._polylines.append(pl)
        pl.setSelected(True)
        self.push_undo_state()
        self._show_status("Joined into polyline", 2000)

    def explode_selected_items(self):
        """Explode polylines into lines and rectangles into 4 lines."""
        items = [i for i in self.selectedItems()
                 if isinstance(i, (PolylineItem, RectangleItem))]
        if not items:
            self._show_status("Select polylines or rectangles to explode", 3000)
            return
        for item in items:
            color = item.pen().color().name()
            lw = item.pen().widthF()
            layer = getattr(item, "user_layer", "0")
            if isinstance(item, PolylineItem):
                pts = item._points
                for i in range(len(pts) - 1):
                    ln = LineItem(QPointF(pts[i]), QPointF(pts[i+1]),
                                  color=color, lineweight=lw)
                    ln.user_layer = layer
                    self.addItem(ln)
                    self._draw_lines.append(ln)
                if item.scene() is self:
                    self.removeItem(item)
                if item in self._polylines:
                    self._polylines.remove(item)
            elif isinstance(item, RectangleItem):
                rect = item.rect()
                corners = [rect.topLeft(), rect.topRight(),
                           rect.bottomRight(), rect.bottomLeft()]
                for i in range(4):
                    ln = LineItem(QPointF(corners[i]), QPointF(corners[(i+1)%4]),
                                  color=color, lineweight=lw)
                    ln.user_layer = layer
                    self.addItem(ln)
                    self._draw_lines.append(ln)
                if item.scene() is self:
                    self.removeItem(item)
                if item in self._draw_rects:
                    self._draw_rects.remove(item)
        self.push_undo_state()
        self._show_status("Exploded into individual segments", 2000)

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
            layer = getattr(item, "user_layer", "0")
            l1 = LineItem(QPointF(item._pt1), proj1, color=color, lineweight=lw)
            l2 = LineItem(proj2, QPointF(item._pt2), color=color, lineweight=lw)
            l1.user_layer = layer; l2.user_layer = layer
            if item.scene() is self:
                self.removeItem(item)
            if item in self._draw_lines:
                self._draw_lines.remove(item)
            for ln in (l1, l2):
                self.addItem(ln)
                self._draw_lines.append(ln)
        elif isinstance(item, CircleItem):
            # Convert to arc, removing segment between the two angles
            a1 = math.degrees(math.atan2(bp1.y()-item._center.y(), bp1.x()-item._center.x()))
            a2 = math.degrees(math.atan2(bp2.y()-item._center.y(), bp2.x()-item._center.x()))
            span = (a1 - a2) % 360
            arc = ArcItem(QPointF(item._center), item._radius, a2, span,
                          color=item.pen().color().name(),
                          lineweight=item.pen().widthF())
            arc.user_layer = getattr(item, "user_layer", "0")
            arc.level = getattr(item, "level", DEFAULT_LEVEL)
            if item.scene() is self:
                self.removeItem(item)
            if item in self._draw_circles:
                self._draw_circles.remove(item)
            self.addItem(arc)
            self._draw_arcs.append(arc)

    def _break_at_point(self, item, bp: QPointF):
        """Split *item* into two at *bp*."""
        if isinstance(item, LineItem):
            t = gi.point_on_segment_param(bp, item._pt1, item._pt2)
            proj = QPointF(item._pt1.x() + t*(item._pt2.x()-item._pt1.x()),
                           item._pt1.y() + t*(item._pt2.y()-item._pt1.y()))
            color = item.pen().color().name()
            lw = item.pen().widthF()
            layer = getattr(item, "user_layer", "0")
            l1 = LineItem(QPointF(item._pt1), proj, color=color, lineweight=lw)
            l2 = LineItem(proj, QPointF(item._pt2), color=color, lineweight=lw)
            l1.user_layer = layer; l2.user_layer = layer
            if item.scene() is self:
                self.removeItem(item)
            if item in self._draw_lines:
                self._draw_lines.remove(item)
            for ln in (l1, l2):
                self.addItem(ln)
                self._draw_lines.append(ln)
        elif isinstance(item, CircleItem):
            a = math.degrees(math.atan2(bp.y()-item._center.y(), bp.x()-item._center.x()))
            arc = ArcItem(QPointF(item._center), item._radius,
                          a + 0.5, 359.0,
                          color=item.pen().color().name(),
                          lineweight=item.pen().widthF())
            arc.user_layer = getattr(item, "user_layer", "0")
            arc.level = getattr(item, "level", DEFAULT_LEVEL)
            if item.scene() is self:
                self.removeItem(item)
            if item in self._draw_circles:
                self._draw_circles.remove(item)
            self.addItem(arc)
            self._draw_arcs.append(arc)
        elif isinstance(item, ArcItem):
            a = math.degrees(math.atan2(bp.y()-item._center.y(), bp.x()-item._center.x()))
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
            a1.user_layer = getattr(item, "user_layer", "0")
            a2.user_layer = getattr(item, "user_layer", "0")
            a1.level = getattr(item, "level", DEFAULT_LEVEL)
            a2.level = getattr(item, "level", DEFAULT_LEVEL)
            if item.scene() is self:
                self.removeItem(item)
            if item in self._draw_arcs:
                self._draw_arcs.remove(item)
            for ai in (a1, a2):
                self.addItem(ai)
                self._draw_arcs.append(ai)

    # -------------------------------------------------------------------------
    # FILLET / CHAMFER

    def _compute_fillet(self, item1, item2, radius):
        """Compute fillet arc data between two line items. Returns dict or None."""
        if not isinstance(item1, LineItem) or not isinstance(item2, LineItem):
            return None
        ix = gi.line_line_intersection_unbounded(item1._pt1, item1._pt2,
                                                 item2._pt1, item2._pt2)
        if ix is None:
            return None  # parallel lines
        # Determine which ends are near intersection
        def _near_end(item, ix):
            d1 = CAD_Math.get_vector_length(item._pt1, ix)
            d2 = CAD_Math.get_vector_length(item._pt2, ix)
            return ("_pt1", "_pt2") if d1 < d2 else ("_pt2", "_pt1")
        near1, far1 = _near_end(item1, ix)
        near2, far2 = _near_end(item2, ix)
        # Vectors from intersection along each line
        u1 = CAD_Math.get_unit_vector(ix, getattr(item1, far1))
        u2 = CAD_Math.get_unit_vector(ix, getattr(item2, far2))
        # Half-angle between the two lines
        dot = u1.x()*u2.x() + u1.y()*u2.y()
        dot = max(-1.0, min(1.0, dot))
        half = math.acos(dot) / 2
        if half < 1e-6:
            return None  # lines too close to parallel
        # Bisector
        bx = u1.x() + u2.x()
        by = u1.y() + u2.y()
        bl = math.hypot(bx, by)
        if bl < 1e-12:
            return None
        bx /= bl; by /= bl
        # Fillet center distance from intersection
        d = radius / math.sin(half)
        center = QPointF(ix.x() + bx * d, ix.y() + by * d)
        # Tangent points (perpendicular foot from center to each line)
        tp1 = CAD_Math.point_on_line_nearest(center, item1._pt1, item1._pt2)
        tp2 = CAD_Math.point_on_line_nearest(center, item2._pt1, item2._pt2)
        # Arc angles
        sa = math.degrees(math.atan2(tp1.y()-center.y(), tp1.x()-center.x()))
        ea = math.degrees(math.atan2(tp2.y()-center.y(), tp2.x()-center.x()))
        span = (ea - sa) % 360
        if span > 180:
            span -= 360
        return {"center": center, "radius": radius, "start": sa, "span": span,
                "tp1": tp1, "tp2": tp2,
                "item1": item1, "near1": near1,
                "item2": item2, "near2": near2}

    def _commit_fillet(self, data):
        """Create the fillet arc and trim the source lines."""
        if data is None:
            return
        arc = ArcItem(data["center"], data["radius"], data["start"], data["span"],
                      color=data["item1"].pen().color().name(),
                      lineweight=data["item1"].pen().widthF())
        arc.user_layer = getattr(data["item1"], "user_layer", "0")
        arc.level = getattr(data["item1"], "level", DEFAULT_LEVEL)
        self.addItem(arc)
        self._draw_arcs.append(arc)
        # Trim lines to tangent points
        setattr(data["item1"], data["near1"], QPointF(data["tp1"]))
        item1 = data["item1"]
        item1.setLine(item1._pt1.x(), item1._pt1.y(), item1._pt2.x(), item1._pt2.y())
        setattr(data["item2"], data["near2"], QPointF(data["tp2"]))
        item2 = data["item2"]
        item2.setLine(item2._pt1.x(), item2._pt1.y(), item2._pt2.x(), item2._pt2.y())

    def _compute_chamfer(self, item1, item2, dist):
        """Compute chamfer data between two line items. Returns dict or None."""
        if not isinstance(item1, LineItem) or not isinstance(item2, LineItem):
            return None
        ix = gi.line_line_intersection_unbounded(item1._pt1, item1._pt2,
                                                 item2._pt1, item2._pt2)
        if ix is None:
            return None
        def _near_end(item, ix):
            d1 = CAD_Math.get_vector_length(item._pt1, ix)
            d2 = CAD_Math.get_vector_length(item._pt2, ix)
            return ("_pt1", "_pt2") if d1 < d2 else ("_pt2", "_pt1")
        near1, far1 = _near_end(item1, ix)
        near2, far2 = _near_end(item2, ix)
        u1 = CAD_Math.get_unit_vector(ix, getattr(item1, far1))
        u2 = CAD_Math.get_unit_vector(ix, getattr(item2, far2))
        cp1 = QPointF(ix.x() + u1.x()*dist, ix.y() + u1.y()*dist)
        cp2 = QPointF(ix.x() + u2.x()*dist, ix.y() + u2.y()*dist)
        return {"cp1": cp1, "cp2": cp2,
                "item1": item1, "near1": near1,
                "item2": item2, "near2": near2}

    def _commit_chamfer(self, data):
        """Create chamfer bevel line and trim source lines."""
        if data is None:
            return
        ln = LineItem(data["cp1"], data["cp2"],
                      color=data["item1"].pen().color().name(),
                      lineweight=data["item1"].pen().widthF())
        ln.user_layer = getattr(data["item1"], "user_layer", "0")
        ln.level = getattr(data["item1"], "level", DEFAULT_LEVEL)
        self.addItem(ln)
        self._draw_lines.append(ln)
        setattr(data["item1"], data["near1"], QPointF(data["cp1"]))
        item1 = data["item1"]
        item1.setLine(item1._pt1.x(), item1._pt1.y(), item1._pt2.x(), item1._pt2.y())
        setattr(data["item2"], data["near2"], QPointF(data["cp2"]))
        item2 = data["item2"]
        item2.setLine(item2._pt1.x(), item2._pt1.y(), item2._pt2.x(), item2._pt2.y())

    # -------------------------------------------------------------------------
    # STRETCH

    def begin_stretch_crossing(self, scene_rect: QRectF):
        """Collect vertices inside crossing window, transition to base point pick."""
        self._stretch_vertices = []
        self._stretch_full_items = []
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
                self._stretch_full_items.append(item)
            else:
                for idx, g in inside:
                    self._stretch_vertices.append((item, idx, QPointF(g)))
        if not self._stretch_vertices and not self._stretch_full_items:
            self._show_status("No vertices in crossing window", 3000)
            return
        count = len(self._stretch_vertices) + len(self._stretch_full_items)
        self._show_status(f"Captured {count} items/vertices. Pick base point.")
        self.instructionChanged.emit("Pick base point")

    def _commit_stretch(self, delta: QPointF):
        """Apply stretch delta to captured vertices and full items."""
        for item in self._stretch_full_items:
            if hasattr(item, 'translate'):
                item.translate(delta.x(), delta.y())
            elif isinstance(item, Node):
                item.moveBy(delta.x(), delta.y())
        for item, idx, _orig in self._stretch_vertices:
            grips = item.grip_points()
            if idx < len(grips):
                new_pt = QPointF(grips[idx].x() + delta.x(),
                                 grips[idx].y() + delta.y())
                item.apply_grip(idx, new_pt)

    # -------------------------------------------------------------------------
    # GRIP HELPERS (Sprint I)

    def _find_grip_hit(self, pos: QPointF):
        """
        Return *(item, grip_index)* if *pos* is within 8 screen pixels of any
        grip handle on a selected item, else *None*.
        """
        views = self.views()
        if not views:
            return None
        scale = views[0].transform().m11()
        grip_px = getattr(self, "_grip_tolerance_px", 200)
        tol   = grip_px / max(scale, 1e-6)

        for item in self.selectedItems():
            if not hasattr(item, "grip_points"):
                continue
            for idx, gpt in enumerate(item.grip_points()):
                if math.hypot(pos.x() - gpt.x(), pos.y() - gpt.y()) <= tol:
                    return (item, idx)
        return None

    # =========================================================================
    # TRIM / EXTEND / MERGE  (Sprint Y)
    # =========================================================================

    def _all_geometry_items(self):
        """Return a flat list of all construction geometry items in the scene."""
        from .construction_geometry import (
            LineItem, RectangleItem, CircleItem, ArcItem, PolylineItem,
        )
        items = []
        items.extend(self._draw_lines)
        items.extend(self._draw_rects)
        items.extend(self._draw_circles)
        items.extend(self._draw_arcs)
        items.extend(self._polylines)
        return items

    def _find_geometry_at(self, pos: QPointF):
        """Find the geometry item nearest to pos (within tolerance)."""
        from .construction_geometry import (
            LineItem, RectangleItem, CircleItem, ArcItem, PolylineItem,
        )
        tol = 8.0
        views = self.views()
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
        from .construction_geometry import (
            LineItem, PolylineItem, ArcItem,
        )
        views = self.views()
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
        if self._trim_edge_highlight is not None:
            if self._trim_edge_highlight.scene() is self:
                self.removeItem(self._trim_edge_highlight)
            self._trim_edge_highlight = None
        self._trim_edge = None

    def _clear_extend_state(self):
        """Clean up extend boundary highlight and state."""
        if self._extend_boundary_highlight is not None:
            if self._extend_boundary_highlight.scene() is self:
                self.removeItem(self._extend_boundary_highlight)
            self._extend_boundary_highlight = None
        self._extend_boundary = None

    def _highlight_item(self, item, color="#ff4400"):
        """Create a bright overlay highlight for an item."""
        highlight_pen = QPen(QColor(color), 3, Qt.PenStyle.SolidLine)
        highlight_pen.setCosmetic(True)
        if hasattr(item, 'line'):
            line = item.line()
            h = QGraphicsLineItem(line)
            h.setPen(highlight_pen)
            h.setZValue(250)
            self.addItem(h)
            return h
        elif hasattr(item, 'rect'):
            h = QGraphicsRectItem(item.rect())
            h.setPen(highlight_pen)
            h.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            h.setZValue(250)
            self.addItem(h)
            return h
        elif hasattr(item, 'path'):
            h = QGraphicsPathItem(item.path())
            h.setPen(highlight_pen)
            h.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            h.setZValue(250)
            self.addItem(h)
            return h
        return None

    def _handle_trim_click(self, pos: QPointF):
        """Handle mouse click during trim mode."""
        from .construction_geometry import (
            LineItem, CircleItem, ArcItem, PolylineItem,
        )

        if self.mode == "trim":
            # Phase 1: select cutting edge
            item = self._find_geometry_at(pos)
            if item is not None:
                self._trim_edge = item
                self._trim_edge_highlight = self._highlight_item(item)
                self.mode = "trim_pick"
                self.modeChanged.emit("trim_pick")
                self.instructionChanged.emit(
                    "Click segment to trim (right-click to cancel)")
            return

        elif self.mode == "trim_pick":
            # Phase 2: click segment to trim at intersection with cutting edge
            item = self._find_geometry_at(pos)
            if item is None or item is self._trim_edge:
                return

            edge = self._trim_edge
            # Find intersections between item and edge
            intersections = self._compute_intersections(item, edge)
            if not intersections:
                self._show_status("No intersection found")
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
                else:
                    item.apply_grip(2, hit)  # move p2 to intersection
                self.push_undo_state()
                self._show_status("Trimmed line")

            elif isinstance(item, CircleItem):
                # Convert circle to arc by removing the clicked portion
                ANG_EPS = 0.01  # degrees — tolerance for angle comparison
                center = item._center
                r = item._radius
                # Compute angle of each intersection point
                int_angles = []
                for ipt in intersections:
                    angle = math.degrees(math.atan2(
                        ipt.y() - center.y(), ipt.x() - center.x()))
                    int_angles.append(angle % 360)

                if len(int_angles) < 2:
                    self._show_status(
                        "Need at least two intersections to trim a circle")
                    return

                click_angle = math.degrees(math.atan2(
                    pos.y() - center.y(), pos.x() - center.x())) % 360

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
                    self._show_status("Trim would produce degenerate arc")
                    return

                color = item.pen().color().name()
                lw = item.pen().widthF()
                arc = ArcItem(center, r, start, span, color, lw)
                arc.user_layer = getattr(item, 'user_layer', 'Default')
                arc.level = getattr(item, 'level', 'Level 1')
                self.addItem(arc)
                self._draw_arcs.append(arc)

                # Remove original circle
                self.removeItem(item)
                if item in self._draw_circles:
                    self._draw_circles.remove(item)
                self.push_undo_state()
                self._show_status("Trimmed circle to arc")

            elif isinstance(item, ArcItem):
                center = item._center
                int_angles = []
                for ipt in intersections:
                    angle = math.degrees(math.atan2(
                        ipt.y() - center.y(), ipt.x() - center.x())) % 360
                    int_angles.append(angle)

                if not int_angles:
                    return
                trim_angle = int_angles[0]
                click_angle = math.degrees(math.atan2(
                    pos.y() - center.y(), pos.x() - center.x())) % 360

                start = item._start_deg % 360
                span = item._span_deg
                end = (start + span) % 360

                # Compute angular position of click within arc span
                rel_click = (click_angle - start) % 360
                rel_trim = (trim_angle - start) % 360

                if rel_click < rel_trim:
                    # Click is before trim point — keep from trim to end
                    item._start_deg = trim_angle
                    item._span_deg = span - rel_trim
                else:
                    # Click is after trim point — keep from start to trim
                    item._span_deg = rel_trim

                item._rebuild_path()
                self.push_undo_state()
                self._show_status("Trimmed arc")

    def _handle_extend_click(self, pos: QPointF):
        """Handle mouse click during extend mode."""
        from .construction_geometry import LineItem, ArcItem, PolylineItem

        if self.mode == "extend":
            item = self._find_geometry_at(pos)
            if item is not None:
                self._extend_boundary = item
                self._extend_boundary_highlight = self._highlight_item(item, "#00aa00")
                self.mode = "extend_pick"
                self.modeChanged.emit("extend_pick")
                self.instructionChanged.emit(
                    "Click near endpoint to extend (right-click to cancel)")
            return

        elif self.mode == "extend_pick":
            endpoint_hit = self._find_endpoint_hit(pos)
            if endpoint_hit is None:
                return
            item, grip_idx, grip_pt = endpoint_hit
            boundary = self._extend_boundary

            if isinstance(item, (LineItem, PolylineItem)):
                # For polylines, only allow extending from first or last vertex
                if isinstance(item, PolylineItem):
                    n_verts = len(item._points)
                    if grip_idx != 0 and grip_idx != n_verts - 1:
                        self._show_status("Can only extend from first or last vertex")
                        return

                intersections = self._compute_extend_intersections(
                    item, grip_idx, boundary)
                if not intersections:
                    self._show_status("No intersection with boundary")
                    return
                hit = gi.nearest_intersection(grip_pt, intersections)
                if hit:
                    item.apply_grip(grip_idx, hit)
                    self.push_undo_state()
                    kind = "polyline" if isinstance(item, PolylineItem) else "line"
                    self._show_status(f"Extended {kind} to boundary")

    def _handle_merge_click(self, pos: QPointF):
        """Handle mouse click during merge points mode."""
        endpoint_hit = self._find_endpoint_hit(pos)
        if endpoint_hit is None:
            self._show_status("No endpoint found nearby")
            return

        item, grip_idx, grip_pt = endpoint_hit

        if self._merge_point1 is None:
            # First click — store the target point
            self._merge_point1 = (item, grip_idx, grip_pt)
            self.instructionChanged.emit("Click second endpoint to merge")
            # Create visual indicator
            marker = QGraphicsEllipseItem(-4, -4, 8, 8)
            marker.setPos(grip_pt)
            marker.setBrush(QBrush(QColor("#ff4400")))
            marker.setPen(QPen(QColor("#ff4400")))
            marker.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            marker.setZValue(300)
            self.addItem(marker)
            self._merge_preview = marker
        else:
            # Second click — move second endpoint to first
            target_pt = self._merge_point1[2]
            item.apply_grip(grip_idx, target_pt)
            self.push_undo_state()
            self._show_status("Points merged")
            # Clean up
            if self._merge_preview is not None:
                if self._merge_preview.scene() is self:
                    self.removeItem(self._merge_preview)
                self._merge_preview = None
            self._merge_point1 = None
            self.instructionChanged.emit("Click first endpoint")

    def _handle_hatch_click(self, pos: QPointF):
        """Handle mouse click during hatch mode."""
        item = self._find_geometry_at(pos)
        if item is None:
            return

        if not hasattr(item, 'is_closed') or not item.is_closed():
            self._show_status("Object is not closed — cannot hatch")
            return

        closed_path = item.get_closed_path()
        if closed_path is None:
            self._show_status("Cannot get closed path for hatching")
            return

        hatch = HatchItem(closed_path, item.pos())
        hatch._source_item = item
        self.addItem(hatch)
        self._hatch_items.append(hatch)
        hatch.setSelected(True)
        hatch.user_layer = getattr(item, "user_layer", self.active_user_layer)
        hatch.level = getattr(item, "level", self.active_level)
        self.push_undo_state()
        self._show_status("Hatch applied")

    def _handle_constraint_concentric_click(self, pos: QPointF):
        """Handle mouse click during concentric constraint mode."""
        from .construction_geometry import CircleItem, ArcItem
        item = self._find_geometry_at(pos)
        if item is None or not isinstance(item, (CircleItem, ArcItem)):
            self._show_status("Please select a circle or arc")
            return

        if self._constraint_circle_a is None:
            self._constraint_circle_a = item
            self.instructionChanged.emit("Select second circle")
        else:
            from .constraints import ConcentricConstraint
            constraint = ConcentricConstraint(self._constraint_circle_a, item)
            self._constraints.append(constraint)
            self._solve_constraints(self._constraint_circle_a)
            self.push_undo_state()
            self._constraint_circle_a = None
            self._show_status("Concentric constraint applied")
            self.instructionChanged.emit("Select first circle")
            for v in self.views():
                v.viewport().update()

    def _handle_constraint_dimensional_click(self, pos: QPointF):
        """Handle mouse click during dimensional constraint mode."""
        endpoint_hit = self._find_endpoint_hit(pos)
        if endpoint_hit is None:
            self._show_status("No grip point found nearby")
            return

        item, grip_idx, grip_pt = endpoint_hit

        if self._constraint_grip_a is None:
            self._constraint_grip_a = (item, grip_idx, grip_pt)
            self.instructionChanged.emit("Click second grip point")
        else:
            item_a, grip_a, pt_a = self._constraint_grip_a
            current_dist = math.hypot(
                grip_pt.x() - pt_a.x(), grip_pt.y() - pt_a.y())

            # Show dialog for distance
            from PyQt6.QtWidgets import QDoubleSpinBox, QDialogButtonBox
            dlg = QDialog()
            dlg.setWindowTitle("Dimensional Constraint")
            layout = QVBoxLayout(dlg)
            layout.addWidget(QLabel("Set constraint distance:"))
            spin = QDoubleSpinBox()
            spin.setRange(0.01, 1e6)
            spin.setDecimals(2)
            spin.setValue(current_dist)
            layout.addWidget(spin)
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok |
                QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            layout.addWidget(buttons)

            if dlg.exec() == QDialog.DialogCode.Accepted:
                from .constraints import DimensionalConstraint
                dist = spin.value()
                constraint = DimensionalConstraint(
                    item_a, grip_a, item, grip_idx, dist)
                self._constraints.append(constraint)
                self._solve_constraints()
                self.push_undo_state()
                self._show_status(f"Dimensional constraint: {dist:.1f}")

            self._constraint_grip_a = None
            self.instructionChanged.emit("Click first grip point")
            for v in self.views():
                v.viewport().update()

    def _solve_constraints(self, moved_item=None):
        """Run the constraint solver with convergence detection.

        Called after every movement operation.  If the solver stalls for 3
        consecutive iterations (no progress) we assume a conflict and report
        it via the status bar.
        """
        MAX_ITERATIONS = 20
        prev_unsatisfied = float('inf')
        stall_count = 0

        for _iteration in range(MAX_ITERATIONS):
            all_satisfied = True
            unsatisfied: list = []
            for c in self._constraints:
                if not c.enabled:
                    continue
                if not c.solve(moved_item):
                    all_satisfied = False
                    unsatisfied.append(c)
            if all_satisfied:
                break

            # Convergence / stall detection
            n = len(unsatisfied)
            if n >= prev_unsatisfied:
                stall_count += 1
                if stall_count >= 3:
                    self._report_constraint_conflict(unsatisfied)
                    break
            else:
                stall_count = 0
            prev_unsatisfied = n

        for v in self.views():
            v.viewport().update()

    def _report_constraint_conflict(self, unsatisfied: list):
        """Emit a status message about conflicting constraints."""
        ids = [str(getattr(c, 'id', '?')) for c in unsatisfied[:3]]
        msg = f"⚠ Constraint conflict: {', '.join(ids)} cannot be satisfied simultaneously"
        self._show_status(msg, timeout=5000)

    def _compute_intersections(self, item, edge):
        """Compute intersection points between two geometry items."""
        from .construction_geometry import (
            LineItem, CircleItem, ArcItem, RectangleItem, PolylineItem,
        )

        results = []

        # Get segments/shapes from both items
        item_segs = self._get_item_segments(item)
        edge_segs = self._get_item_segments(edge)

        for seg in item_segs:
            for eseg in edge_segs:
                if seg[0] == "line" and eseg[0] == "line":
                    pt = gi.line_line_intersection(
                        seg[1], seg[2], eseg[1], eseg[2])
                    if pt:
                        results.append(pt)
                elif seg[0] == "line" and eseg[0] == "circle":
                    pts = gi.line_circle_intersections(
                        seg[1], seg[2], eseg[1], eseg[2])
                    results.extend(pts)
                elif seg[0] == "circle" and eseg[0] == "line":
                    pts = gi.line_circle_intersections(
                        eseg[1], eseg[2], seg[1], seg[2])
                    results.extend(pts)
                elif seg[0] == "line" and eseg[0] == "arc":
                    pts = gi.line_arc_intersections(
                        seg[1], seg[2], eseg[1], eseg[2],
                        eseg[3], eseg[4])
                    results.extend(pts)
                elif seg[0] == "arc" and eseg[0] == "line":
                    pts = gi.line_arc_intersections(
                        eseg[1], eseg[2], seg[1], seg[2],
                        seg[3], seg[4])
                    results.extend(pts)
        return results

    def _compute_extend_intersections(self, item, grip_idx, boundary):
        """Compute where *item* would intersect *boundary* if extended.

        Only returns intersections in the forward direction from the
        extending endpoint (away from the interior of the item).
        """
        from .construction_geometry import LineItem, PolylineItem

        raw_results: list[QPointF] = []
        extend_pt: QPointF | None = None
        direction: tuple[float, float] | None = None

        if isinstance(item, LineItem):
            grips = item.grip_points()
            p1, p2 = grips[0], grips[2]
            if grip_idx == 0:
                extend_pt, fixed_pt = p1, p2
            else:
                extend_pt, fixed_pt = p2, p1
            direction = (extend_pt.x() - fixed_pt.x(),
                         extend_pt.y() - fixed_pt.y())

            boundary_segs = self._get_item_segments(boundary)
            for bseg in boundary_segs:
                if bseg[0] == "line":
                    pt = gi.line_line_intersection_unbounded(p1, p2, bseg[1], bseg[2])
                    if pt:
                        raw_results.append(pt)
                elif bseg[0] == "circle":
                    raw_results.extend(
                        gi.line_circle_intersections_unbounded(p1, p2, bseg[1], bseg[2]))
                elif bseg[0] == "arc":
                    pts = gi.line_circle_intersections_unbounded(p1, p2, bseg[1], bseg[2])
                    for pt in pts:
                        angle = math.degrees(math.atan2(
                            pt.y() - bseg[1].y(), pt.x() - bseg[1].x())) % 360
                        if gi._angle_in_arc(angle, bseg[3], bseg[4]):
                            raw_results.append(pt)

        elif isinstance(item, PolylineItem):
            vertices = item._points
            if len(vertices) < 2:
                return []
            if grip_idx == 0:
                extend_pt = vertices[0]
                neighbor = vertices[1]
            elif grip_idx == len(vertices) - 1:
                extend_pt = vertices[-1]
                neighbor = vertices[-2]
            else:
                return []  # cannot extend from interior vertex

            direction = (extend_pt.x() - neighbor.x(),
                         extend_pt.y() - neighbor.y())

            boundary_segs = self._get_item_segments(boundary)
            for bseg in boundary_segs:
                if bseg[0] == "line":
                    pt = gi.line_line_intersection_unbounded(
                        neighbor, extend_pt, bseg[1], bseg[2])
                    if pt:
                        raw_results.append(pt)
                elif bseg[0] == "circle":
                    raw_results.extend(
                        gi.line_circle_intersections_unbounded(
                            neighbor, extend_pt, bseg[1], bseg[2]))
                elif bseg[0] == "arc":
                    pts = gi.line_circle_intersections_unbounded(
                        neighbor, extend_pt, bseg[1], bseg[2])
                    for pt in pts:
                        angle = math.degrees(math.atan2(
                            pt.y() - bseg[1].y(), pt.x() - bseg[1].x())) % 360
                        if gi._angle_in_arc(angle, bseg[3], bseg[4]):
                            raw_results.append(pt)

        # Filter to forward direction only
        if extend_pt is not None and direction is not None:
            dx, dy = direction
            forward = []
            for pt in raw_results:
                vx = pt.x() - extend_pt.x()
                vy = pt.y() - extend_pt.y()
                dot = vx * dx + vy * dy
                if dot > -1e-6:
                    forward.append(pt)
            return forward if forward else raw_results

        return raw_results

    def _get_item_segments(self, item):
        """Return geometric representation of an item as list of tuples.
        Returns: [("line", p1, p2), ("circle", center, radius),
                  ("arc", center, radius, start_deg, span_deg)]"""
        from .construction_geometry import (
            LineItem, CircleItem, ArcItem, RectangleItem, PolylineItem,
        )
        segs = []
        if isinstance(item, LineItem):
            grips = item.grip_points()
            segs.append(("line", grips[0], grips[2]))
        elif isinstance(item, CircleItem):
            segs.append(("circle", item._center, item._radius))
        elif isinstance(item, ArcItem):
            segs.append(("arc", item._center, item._radius,
                         item._start_deg, item._span_deg))
        elif isinstance(item, RectangleItem):
            grips = item.grip_points()
            # 9 grips: TL, TM, TR, RM, BR, BM, BL, LM, Center
            tl = grips[0]
            tr = grips[2]
            br = grips[4]
            bl = grips[6]
            segs.append(("line", tl, tr))
            segs.append(("line", tr, br))
            segs.append(("line", br, bl))
            segs.append(("line", bl, tl))
        elif isinstance(item, PolylineItem):
            pts = item._points
            for i in range(len(pts) - 1):
                segs.append(("line", QPointF(pts[i]), QPointF(pts[i + 1])))
        return segs