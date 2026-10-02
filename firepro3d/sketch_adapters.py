"""Per-primitive solver adapters — parametric-constraint-system.md §5.1/§5.3.

Pure of Qt *logic*: each adapter reads an item's variables, exposes its
handles as ``PointExpr``s over a variable offset, maps grip index -> handle
name, and writes solved values back in ONE call per item (§3 write-back).
Angles are radians inside the solver; scene coords are Qt Y-down; app
rotations are Y-up CCW (2d-geometry.md).
"""
from __future__ import annotations

import math

import numpy as np
from PyQt6.QtCore import QPointF, QRectF

from .sketch_solver import ANG_SCALE, PointExpr, raw_point

# D28 (user, 2026-10-01): angle variables are stiff -- 1 rad costs as much as
# 1000 mm of travel, so geometry rotates only when nothing else satisfies.
ANG_W = ANG_SCALE ** 2

# D29 (user, 2026-10-02): a solve that can only be satisfied by collapsing a
# shape is a CONFLICT. The size floors below are the SAME floors each item's
# write-back clamps to (one home); a value within DEGEN_EPS of its floor -- or
# an arc span within DEGEN_EPS rad of 0 / 2*pi -- is a collapse.
DEGEN_EPS = 1e-6
RECT_MIN = 1e-6          # _RectAdapter.write clamp
CIRCLE_MIN = 1.0         # CircleItem.set_radius floor
ARC_R_MIN = 0.01         # _ArcAdapter.write / ArcItem.set_radius floor

# §5.3 grip index -> handle name, keyed by to_dict() type (file-format).
# Polyline (i -> v<i>) and text / block instance (move grip -> ins) are
# computed by their adapters' grip_handle().
GRIP_HANDLES = {
    "draw_line": {0: "p1", 2: "p2"},
    "reference_line": {0: "p1", 2: "p2"},
    "draw_rectangle": {0: "tl", 1: "tm", 2: "tr", 3: "rm", 4: "br",
                       5: "bm", 6: "bl", 7: "lm", 8: "center"},
    "draw_circle": {0: "center"},
    "arc": {0: "center", 1: "start", 2: "end"},
    "polygon": {0: "center"},
    "draw_ellipse": {0: "center"},
}
# Rect handle -> (sign of local u, sign of local v); v is Qt Y-down LOCAL, so
# "top" (v = -h/2) is the local min-y edge (§5.3).
_RECT_LOCAL = {"tl": (-1, -1), "tm": (0, -1), "tr": (1, -1), "rm": (1, 0),
               "br": (1, 1), "bm": (0, 1), "bl": (-1, 1), "lm": (-1, 0),
               "center": (0, 0)}
_RECT_EDGES = {"top": ("tl", "tr"), "right": ("tr", "br"),
               "bottom": ("br", "bl"), "left": ("bl", "tl")}


class _Adapter:
    """Base adapter: ``read`` / ``points`` / ``edges`` / ``write``."""

    type_key = ""

    def read(self, item) -> list:
        raise NotImplementedError

    def write(self, item, v) -> None:
        raise NotImplementedError

    def nvars(self, item) -> int:
        return len(self.read(item))

    def var_weights(self, item) -> list:
        return [1.0] * self.nvars(item)

    def size_floors(self, item) -> dict:
        """D29: ``{local var index: floor}`` for the item's size variables."""
        return {}

    def degenerate(self, item, vals) -> bool:
        """D29: whether *vals* (this item's variables) collapse the shape --
        a size variable at / below its floor (+ ``DEGEN_EPS``)."""
        return any(float(vals[i]) <= f + DEGEN_EPS
                   for i, f in self.size_floors(item).items())

    def points(self, item, off: int) -> dict:
        return {}

    def edges(self, item, off: int) -> dict:
        return {}

    def grip_handle(self, item, index: int):
        return GRIP_HANDLES.get(self.type_key, {}).get(index)

    def pin_vars(self, item, index: int) -> tuple:
        """Local variable indices a drag of grip *index* pins (raw handle ->
        its 2 vars; derived / translate grips -> every var)."""
        name = self.grip_handle(item, index)
        e = self.points(item, 0).get(name) if name else None
        if e is not None and e.raw is not None:
            return tuple(e.raw)
        return tuple(range(self.nvars(item)))


class _LineAdapter(_Adapter):
    """vars x1 y1 x2 y2; handles ``p1`` ``p2`` + edge ``edge``."""

    def __init__(self, key):
        self.type_key = key

    def read(self, it):
        return [it._pt1.x(), it._pt1.y(), it._pt2.x(), it._pt2.y()]

    def points(self, it, off):
        return {"p1": raw_point(off, off + 1), "p2": raw_point(off + 2, off + 3)}

    def edges(self, it, off):
        p = self.points(it, off)
        return {"edge": (p["p1"], p["p2"])}

    def write(self, it, v):
        it._pt1 = QPointF(float(v[0]), float(v[1]))
        it._pt2 = QPointF(float(v[2]), float(v[3]))
        it.setLine(it._pt1.x(), it._pt1.y(), it._pt2.x(), it._pt2.y())


def _rect_point_fn(su, sv):
    def fn(v):
        cx, cy, w, h, th = v
        u, vv = su * w / 2.0, sv * h / 2.0
        c, s = math.cos(th), math.sin(th)
        # Qt rotate(-θ) of local (u, v) about the centre (RectangleItem.
        # _rotation_transform): x' = u c + v s, y' = -u s + v c.
        p = np.array([cx + u * c + vv * s, cy - u * s + vv * c])
        dp = np.array([[1.0, 0.0, su / 2.0 * c, sv / 2.0 * s, -u * s + vv * c],
                       [0.0, 1.0, -su / 2.0 * s, sv / 2.0 * c, -u * c - vv * s]])
        return p, dp
    return fn


class _RectAdapter(_Adapter):
    """vars cx cy w h th (scene centre; th = Y-up CCW radians). Write-back
    canonicalises the pivot to the centre (pivot=None) — identical scene
    geometry (§5.1)."""

    type_key = "draw_rectangle"

    def read(self, it):
        r = it.rect()
        c = it._rotation_transform().map(r.center())
        return [c.x(), c.y(), r.width(), r.height(), math.radians(it._angle)]

    def var_weights(self, it):
        return [1.0, 1.0, 1.0, 1.0, ANG_W]          # D28: prefer move/resize over rotate

    def size_floors(self, it):
        return {2: RECT_MIN, 3: RECT_MIN}

    def points(self, it, off):
        idx = tuple(range(off, off + 5))
        return {name: PointExpr(idx=idx, fn=_rect_point_fn(su, sv))
                for name, (su, sv) in _RECT_LOCAL.items()}

    def edges(self, it, off):
        p = self.points(it, off)
        return {e: (p[a], p[b]) for e, (a, b) in _RECT_EDGES.items()}

    def write(self, it, v):
        cx, cy, w, h, th = (float(t) for t in v)
        w, h = max(w, RECT_MIN), max(h, RECT_MIN)
        it.prepareGeometryChange()
        it.setRect(QRectF(cx - w / 2.0, cy - h / 2.0, w, h))
        it.set_angle(math.degrees(th), None)


class _CircleAdapter(_Adapter):
    """vars cx cy r; handle ``center``."""

    type_key = "draw_circle"

    def read(self, it):
        return [it._center.x(), it._center.y(), float(it._radius)]

    def points(self, it, off):
        return {"center": raw_point(off, off + 1)}

    def size_floors(self, it):
        return {2: CIRCLE_MIN}

    def write(self, it, v):
        it._center = QPointF(float(v[0]), float(v[1]))
        it.set_radius(float(v[2]))        # rebuilds the rect about _center (1 mm floor)


def _arc_point_fn(v):
    cx, cy, r, t = v
    c, s = math.cos(t), math.sin(t)
    return (np.array([cx + r * c, cy - r * s]),
            np.array([[1.0, 0.0, c, -r * s], [0.0, 1.0, -s, -r * c]]))


class _ArcAdapter(_Adapter):
    """vars cx cy r ts te (radians, Y-up CCW). Endpoint = c + r(cos t, -sin t)."""

    type_key = "arc"

    def read(self, it):
        ts = math.radians(it._start_deg)
        return [it._center.x(), it._center.y(), float(it._radius), ts,
                ts + math.radians(it._span_deg)]

    def var_weights(self, it):
        return [1.0, 1.0, 1.0, ANG_W, ANG_W]         # D28

    def size_floors(self, it):
        return {2: ARC_R_MIN}

    def degenerate(self, it, vals):
        """Radius at its floor, or the span (te - ts) wrapped to ~0 / ~2*pi
        (write-back maps a 0 span to a full circle)."""
        if super().degenerate(it, vals):
            return True
        m = float(vals[4] - vals[3]) % (2.0 * math.pi)
        return m <= DEGEN_EPS or (2.0 * math.pi - m) <= DEGEN_EPS

    def points(self, it, off):
        def end(k):
            return PointExpr(idx=(off, off + 1, off + 2, off + k), fn=_arc_point_fn)
        return {"center": raw_point(off, off + 1), "start": end(3), "end": end(4)}

    def write(self, it, v):
        cx, cy, r, ts, te = (float(t) for t in v)
        it._center = QPointF(cx, cy)
        it._radius = max(r, ARC_R_MIN)
        it._start_deg = math.degrees(ts) % 360.0
        span = math.degrees(te - ts) % 360.0           # keeps span_deg > 0 (§5.1)
        it._span_deg = span if span > 1e-9 else 360.0
        it._rebuild_path()


class _PolylineAdapter(_Adapter):
    """2 vars per vertex; ``v<i>`` + segments ``s<i>`` (closing one if closed)."""

    type_key = "polyline"

    def read(self, it):
        out = []
        for p in it._points:
            out += [p.x(), p.y()]
        return out

    def grip_handle(self, it, index):
        return f"v{index}" if 0 <= index < len(it._points) else None

    def points(self, it, off):
        return {f"v{i}": raw_point(off + 2 * i, off + 2 * i + 1)
                for i in range(len(it._points))}

    def edges(self, it, off):
        p = self.points(it, off)
        n = len(it._points)
        out = {f"s{i}": (p[f"v{i}"], p[f"v{i + 1}"]) for i in range(n - 1)}
        if it.is_closed():
            out[f"s{n - 1}"] = (p[f"v{n - 1}"], p["v0"])
        return out

    def write(self, it, v):
        it._points = [QPointF(float(v[2 * i]), float(v[2 * i + 1]))
                      for i in range(len(it._points))]
        it._rebuild_path()


class _CenterRotAdapter(_Adapter):
    """Polygon (cx cy R rot) / ellipse (cx cy rx ry rot): only ``center`` (§5.1).

    ``fields`` are the item attributes after the centre; ``_rotation_deg`` must
    be last (it carries the D28 weight). ``floors`` mirror the item's own
    anti-degeneracy floors.
    """

    def __init__(self, key, fields, floors):
        self.type_key, self._fields, self._floors = key, fields, floors

    def read(self, it):
        vals = [it._center.x(), it._center.y()]
        for f in self._fields:
            v = getattr(it, f)
            vals.append(math.radians(v) if f == "_rotation_deg" else float(v))
        return vals

    def var_weights(self, it):
        return [1.0] * (1 + len(self._fields)) + [ANG_W]   # D28

    def size_floors(self, it):
        return {2 + k: self._floors[f] for k, f in enumerate(self._fields)
                if f in self._floors}

    def points(self, it, off):
        return {"center": raw_point(off, off + 1)}

    def write(self, it, v):
        it._center = QPointF(float(v[0]), float(v[1]))
        for f, val in zip(self._fields, v[2:]):
            if f == "_rotation_deg":
                setattr(it, f, math.degrees(float(val)))
            else:
                setattr(it, f, max(float(val), self._floors.get(f, 0.0)))
        it._regenerate()


class _InsAdapter(_Adapter):
    """Text (``pos()``) / nested block instance (``block_pos()``): only ``ins``."""

    def __init__(self, key):
        self.type_key = key

    def read(self, it):
        if self.type_key == "text":
            return [it.pos().x(), it.pos().y()]
        return [float(c) for c in it.block_pos()]

    def grip_handle(self, it, index):
        return "ins"

    def points(self, it, off):
        return {"ins": raw_point(off, off + 1)}

    def write(self, it, v):
        if self.type_key == "text":
            it.setPos(float(v[0]), float(v[1]))
            it.sync_data_from_item()
        else:
            it.set_block_pos(float(v[0]), float(v[1]))


def _registry():
    from .block_instance import BlockInstance
    from .geometry_2d import (_AXIS_MIN, ArcItem, CircleItem, EllipseItem, LineItem,
                              PolylineItem, RectangleItem, ReferenceLineItem,
                              RegularPolygonItem)
    from .text_item import TextItem
    return {
        LineItem: _LineAdapter("draw_line"),
        ReferenceLineItem: _LineAdapter("reference_line"),
        RectangleItem: _RectAdapter(),
        CircleItem: _CircleAdapter(),
        ArcItem: _ArcAdapter(),
        PolylineItem: _PolylineAdapter(),
        RegularPolygonItem: _CenterRotAdapter(
            "polygon", ("_radius_mm", "_rotation_deg"), {"_radius_mm": _AXIS_MIN}),
        EllipseItem: _CenterRotAdapter(
            "draw_ellipse", ("_rx", "_ry", "_rotation_deg"),
            {"_rx": _AXIS_MIN, "_ry": _AXIS_MIN}),
        TextItem: _InsAdapter("text"),
        BlockInstance: _InsAdapter("block_instance"),
    }


_REG = None


def adapter_for(item):
    """The item's adapter by EXACT type (subclass-safe), or None (spline, other)."""
    global _REG
    if _REG is None:
        _REG = _registry()
    return _REG.get(type(item))
