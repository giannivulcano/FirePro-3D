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

from .geometry_2d import ARC_MIN_RADIUS, CIRCLE_MIN_RADIUS, RECT_MIN_SIZE
from .sketch_solver import ANG_SCALE, PointExpr, raw_point

# D28 (user, 2026-10-01): angle variables are stiff -- 1 rad costs as much as
# 1000 mm of travel.
ANG_W = ANG_SCALE ** 2
# D34 (user, 2026-10-02): "translate, then resize, then rotate" -- size
# variables (rect w/h, circle / arc r, ellipse rx/ry, polygon R) carry this
# goal weight; positions 1, angles ANG_W. Declared per adapter by its
# size_floors() keys (sizes) and angle_vars() (angles); see var_weights().
# (The weights alone still let a rect TILT a little to meet a point -- the
# controller's translate-first pass makes the order strict, _solve_x.)
W_SIZE = 1e3

# Write-back tolerance (§3, one write per CHANGED item): a solve that moved
# an item by less than this is not written. A drag's pinned item still
# leaks ~1e-9 x the frame's offset (1 / (W_EDIT * W_PIN): 7e-9 mm on a 7 mm
# frame, measured) -- it must not be re-written (VC9 F2: a rect write
# canonicalises its pivot). POS is a tenth of the solver's own LIN_TOL.
# The angle bar is LIN_TOL at a 100 mm lever (VC9 R5): D34's stiff pass
# leaves ~5e-9 rad of solver noise in an unmoved angle (measured, a 200x100
# rect) -- below this it is never written (``_Adapter.settled``), so an
# axis-aligned rect stays exactly axis-aligned.
POS_WRITE_TOL = 1e-7          # mm (positions, sizes)
ANG_WRITE_TOL = 1e-8          # rad

# D29 (user, 2026-10-02): a solve that can only be satisfied by collapsing a
# shape is a CONFLICT. The size floors are geometry_2d's own clamp constants
# (one home); see _Adapter.collapses.
DEGEN_EPS = 1e-6


def _seg_collapses(o, n, i: int, j: int) -> bool:
    """D36 (user, 2026-10-02): segment (vertex i, vertex j) was longer than
    ``DEGEN_EPS`` in *o* and is at most that in *n* -- an edge the solve
    shrank to a point is a collapse, so a conflict (an already-degenerate
    segment never counts)."""
    lo = math.hypot(float(o[2 * j]) - float(o[2 * i]),
                    float(o[2 * j + 1]) - float(o[2 * i + 1]))
    ln = math.hypot(float(n[2 * j]) - float(n[2 * i]),
                    float(n[2 * j + 1]) - float(n[2 * i + 1]))
    return ln <= DEGEN_EPS < lo

# §5.3 grip index -> handle name, keyed by to_dict() type (file-format).
# Polyline (i -> v<i>), polygon (0 -> center, i -> v<i-1>, D33) and text /
# block instance (move grip -> ins) are computed by their adapters'
# grip_handle().
GRIP_HANDLES = {
    "draw_line": {0: "p1", 2: "p2"},
    "reference_line": {0: "p1", 2: "p2"},
    "draw_rectangle": {0: "tl", 1: "tm", 2: "tr", 3: "rm", 4: "br",
                       5: "bm", 6: "bl", 7: "lm", 8: "center"},
    "draw_circle": {0: "center"},
    "arc": {0: "center", 1: "start", 2: "end"},
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
        """Per-variable goal weights: 1 (position), ``W_SIZE`` (a size --
        D34), ``ANG_W`` (an angle -- D28)."""
        w = [1.0] * self.nvars(item)
        for i in self.size_floors(item):
            w[i] = W_SIZE
        for i in self.angle_vars(item):
            w[i] = ANG_W
        return w

    def size_floors(self, item) -> dict:
        """D29: ``{local var index: floor}`` for the item's size variables."""
        return {}

    def angle_vars(self, item) -> tuple:
        """Local indices of the item's angle variables (radians)."""
        return ()

    def stiff_vars(self, item) -> tuple:
        """D34: the size + angle variables (everything but positions)."""
        return tuple(self.size_floors(item)) + tuple(self.angle_vars(item))

    def settled(self, item, old, new) -> list:
        """*new* with every variable whose change is within its write
        tolerance (``POS_WRITE_TOL`` mm / ``ANG_WRITE_TOL`` rad) put back to
        its *old* value (VC9 R5): solver noise in an unmoved size / angle --
        D34's stiff pass leaves ~1e-8 -- is never written, so an axis-aligned
        rect keeps angle 0 (and no pivot) and its exact size."""
        ang = set(self.angle_vars(item))
        return [float(a) if abs(float(b) - float(a)) <= (
                    ANG_WRITE_TOL if i in ang else POS_WRITE_TOL) else float(b)
                for i, (a, b) in enumerate(zip(old, new))]

    def changed(self, item, old, new) -> bool:
        """Whether solved *new* differs from *old* by more than the write
        tolerance (``POS_WRITE_TOL`` mm / ``ANG_WRITE_TOL`` rad)."""
        ang = set(self.angle_vars(item))
        return any(abs(float(b) - float(a)) > (ANG_WRITE_TOL if i in ang else POS_WRITE_TOL)
                   for i, (a, b) in enumerate(zip(old, new)))

    def collapses(self, item, old, new) -> bool:
        """D29: whether solved values *new* collapse the shape. A size the
        solve MOVED below its floor (- ``DEGEN_EPS``) does -- write-back would
        clamp it, so the written geometry would not be the solved one; a size
        that was above its floor and lands at it (+ ``DEGEN_EPS``) does too.
        A size the solve left alone never does, even if it already sits below
        the floor (CircleItem / RegularPolygonItem constructors don't clamp)."""
        for i, f in self.size_floors(item).items():
            n, o = float(new[i]), float(old[i])
            moved = abs(n - o) > 1e-9
            if (moved and n < f - DEGEN_EPS) or (n <= f + DEGEN_EPS < o):
                return True
        return False

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

    def collapses(self, it, old, new):
        """D29 + D36: the line shrunk to zero length."""
        return super().collapses(it, old, new) or _seg_collapses(old, new, 0, 1)

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

    def angle_vars(self, it):
        return (4,)

    def size_floors(self, it):
        return {2: RECT_MIN_SIZE, 3: RECT_MIN_SIZE}

    def points(self, it, off):
        idx = tuple(range(off, off + 5))
        return {name: PointExpr(idx=idx, fn=_rect_point_fn(su, sv))
                for name, (su, sv) in _RECT_LOCAL.items()}

    def edges(self, it, off):
        p = self.points(it, off)
        return {e: (p[a], p[b]) for e, (a, b) in _RECT_EDGES.items()}

    def write(self, it, v):
        cx, cy, w, h, th = (float(t) for t in v)
        w, h = max(w, RECT_MIN_SIZE), max(h, RECT_MIN_SIZE)
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
        return {2: CIRCLE_MIN_RADIUS}

    def write(self, it, v):
        it._center = QPointF(float(v[0]), float(v[1]))
        r = float(v[2])
        if r != float(it._radius):
            it.set_radius(r)              # rebuilds the rect about _center (1 mm floor)
        else:
            # Radius untouched: rebuild the rect WITHOUT set_radius's floor, so
            # a sub-floor circle (the ctor doesn't clamp) is written as solved.
            cx, cy = it._center.x(), it._center.y()
            it.setRect(cx - r, cy - r, 2 * r, 2 * r)


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

    def angle_vars(self, it):
        return (3, 4)

    def size_floors(self, it):
        return {2: ARC_MIN_RADIUS}

    def collapses(self, it, old, new):
        """Radius rule, plus the RAW span ``te - ts`` (no mod-2*pi wrap, so a
        sign flip -- 40 deg -> -10 deg, which write-back would turn into a 350
        deg arc -- is caught): outside (0, 2*pi) always collapses; a span that
        lands within ``DEGEN_EPS`` of 0 / 2*pi collapses unless it was there."""
        if super().collapses(it, old, new):
            return True
        tau = 2.0 * math.pi
        dn, do = float(new[4] - new[3]), float(old[4] - old[3])
        if dn < -DEGEN_EPS or dn > tau + DEGEN_EPS:
            return True

        def degen(d):
            return d <= DEGEN_EPS or d >= tau - DEGEN_EPS
        return degen(dn) and not degen(do)

    def points(self, it, off):
        def end(k):
            return PointExpr(idx=(off, off + 1, off + 2, off + k), fn=_arc_point_fn)
        return {"center": raw_point(off, off + 1), "start": end(3), "end": end(4)}

    def write(self, it, v):
        cx, cy, r, ts, te = (float(t) for t in v)
        it._center = QPointF(cx, cy)
        it._radius = max(r, ARC_MIN_RADIUS)
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

    def collapses(self, it, old, new):
        """D29 + D36: any segment (the closing one too) shrunk to zero length."""
        n = len(it._points)
        pairs = [(i, i + 1) for i in range(n - 1)]
        if it.is_closed() and n > 2:
            pairs.append((n - 1, 0))
        return super().collapses(it, old, new) or any(
            _seg_collapses(old, new, i, j) for i, j in pairs)

    def write(self, it, v):
        it._points = [QPointF(float(v[2 * i]), float(v[2 * i + 1]))
                      for i in range(len(it._points))]
        it._rebuild_path()


class _CenterRotAdapter(_Adapter):
    """Polygon (cx cy R rot) / ellipse (cx cy rx ry rot): ``center`` (§5.1).

    ``fields`` are the item attributes after the centre; ``_rotation_deg`` is
    the angle variable (D28 weight), every floored field a size (D34).
    ``floors`` mirror the item's own anti-degeneracy floors.
    """

    def __init__(self, key, fields, floors):
        self.type_key, self._fields, self._floors = key, fields, floors

    def read(self, it):
        vals = [it._center.x(), it._center.y()]
        for f in self._fields:
            v = getattr(it, f)
            vals.append(math.radians(v) if f == "_rotation_deg" else float(v))
        return vals

    def angle_vars(self, it):
        return (2 + self._fields.index("_rotation_deg"),)

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


def _poly_vertex_fn(k: int, n: int, inscribed: bool):
    """Vertex ``k`` of an n-gon over vars (cx, cy, R, rot) -- exactly
    ``RegularPolygonItem.vertices()``: circumradius ``rv = R`` (inscribed) or
    ``R / cos(pi/n)`` (R = apothem), Y-up heading ``rot (+ pi/n when
    circumscribed) + k 2pi/n``, scene point ``c + rv (cos a, -sin a)``."""
    kf = 1.0 if inscribed else 1.0 / math.cos(math.pi / n)
    base = (0.0 if inscribed else math.pi / n) + k * 2.0 * math.pi / n

    def fn(v):
        cx, cy, r, rot = v
        a = rot + base
        c, s = math.cos(a), math.sin(a)
        rv = r * kf
        return (np.array([cx + rv * c, cy - rv * s]),
                np.array([[1.0, 0.0, kf * c, -rv * s], [0.0, 1.0, -kf * s, -rv * c]]))
    return fn


class _PolygonAdapter(_CenterRotAdapter):
    """D33: ``center`` + vertices ``v0..v(n-1)`` and edges ``s<i>`` = ``v<i>``
    -> ``v<i+1>`` (the closing ``s<n-1>`` included), derived from the centre,
    R and rotation; grip 0 -> ``center``, grip i (1..n) -> ``v<i-1>`` (§5.3)."""

    def grip_handle(self, it, index):
        if index == 0:
            return "center"
        return f"v{index - 1}" if 1 <= index <= it._sides else None

    def points(self, it, off):
        n, idx = it._sides, (off, off + 1, off + 2, off + 3)
        out = {"center": raw_point(off, off + 1)}
        for k in range(n):
            out[f"v{k}"] = PointExpr(idx=idx, fn=_poly_vertex_fn(k, n, it._inscribed))
        return out

    def edges(self, it, off):
        p, n = self.points(it, off), it._sides
        return {f"s{k}": (p[f"v{k}"], p[f"v{(k + 1) % n}"]) for k in range(n)}


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
        RegularPolygonItem: _PolygonAdapter(
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
