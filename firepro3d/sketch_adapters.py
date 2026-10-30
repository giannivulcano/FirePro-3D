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

from .constants import MIN_TEXT_WRAP_WIDTH_MM
from .geometry_2d import ARC_MIN_RADIUS, CIRCLE_MIN_RADIUS, RECT_MIN_SIZE
from .sketch_solver import ANG_SCALE, CurveExpr, PointExpr, raw_point, register_point_family

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


def _mid(a: PointExpr, b: PointExpr) -> PointExpr:
    """CS3b: the derived midpoint ``(a + b) / 2`` of two handle exprs -- not a
    solver variable. Its deps are the union of both ends' deps; ``fn`` maps
    the sub-vector ``x[idx]`` onto each end and halves the summed Jacobians."""
    idx = tuple(sorted(set(a.deps) | set(b.deps)))
    col = {d: k for k, d in enumerate(idx)}

    def _end(e, v):
        sel = [col[d] for d in e.deps]
        if e.raw is not None:
            return np.array(v[sel], dtype=float), np.eye(2), sel
        p, dp = e.fn(v[sel])
        return p, dp, sel

    def fn(v):
        pa, da, sa = _end(a, v)
        pb, db, sb = _end(b, v)
        dp = np.zeros((2, len(idx)))
        dp[:, sa] += 0.5 * da
        dp[:, sb] += 0.5 * db
        return 0.5 * (pa + pb), dp
    return PointExpr(idx=idx, fn=fn)


_ROT90 = np.array([[0.0, -1.0], [1.0, 0.0]])


def _offset_point(off: int, end: int, s: float) -> PointExpr:
    """Slice 2 (ruling W1): drawn-line end *end* (0 / 1) of a wall offset by
    *s* along the drawn line's unit normal ``n = (-dy, dx) / L``
    (``WallSegment.normal``). ``s == 0`` is the raw end itself (substitutable).
    ``dn/dd = (R - n u^T) / L`` with ``u = d / L`` and R the +90 deg rotation."""
    if s == 0.0:
        return raw_point(off + 2 * end, off + 2 * end + 1)

    def fn(v):
        x1, y1, x2, y2 = (float(a) for a in v)
        d = np.array([x2 - x1, y2 - y1])
        L = math.hypot(d[0], d[1])
        e = np.array([x1, y1]) if end == 0 else np.array([x2, y2])
        dp = np.zeros((2, 4))
        dp[:, 2 * end:2 * end + 2] = np.eye(2)
        if L <= DEGEN_EPS:                    # no direction: the end itself
            return e, dp
        u = d / L
        n = _ROT90 @ u
        J = (_ROT90 - np.outer(n, u)) / L
        dp[:, 0:2] -= s * J
        dp[:, 2:4] += s * J
        return e + s * n, dp
    return PointExpr(idx=(off, off + 1, off + 2, off + 3), fn=fn)


# §5.3 grip index -> handle name, keyed by to_dict() type (file-format).
# Polyline (i -> v<i>), polygon (0 -> center, i -> v<i-1>, D33) and text /
# block instance (move grip -> ins) are computed by their adapters'
# grip_handle().
GRIP_HANDLES = {
    "draw_line": {0: "p1", 2: "p2"},
    "draw_rectangle": {0: "tl", 1: "tm", 2: "tr", 3: "rm", 4: "br",
                       5: "bm", 6: "bl", 7: "lm", 8: "center"},
    "draw_circle": {0: "center"},
    "arc": {0: "center", 1: "start", 2: "end"},
    "draw_ellipse": {0: "center", 1: "a0", 2: "a1", 3: "b0", 4: "b1"},
}
# CS3c: text grips 0=TL .. 8=Centre (text_item.py grip protocol) carry the
# rectangle's names -- one map.
GRIP_HANDLES["text"] = GRIP_HANDLES["draw_rectangle"]
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
        """Variable count; subclasses answer without a read (D18 drag bar)."""
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

    def curves(self, item, off: int) -> dict:
        """``{name: CurveExpr}`` -- the ``curve`` handle kind (§5.1, CS3:
        circle / arc only; point-on-curve uses the FULL circle)."""
        return {}

    def mid_names(self, item) -> frozenset:
        """CS3b: the point handles that are edge midpoints (pick markers
        paint them as triangles); none by default."""
        return frozenset()

    def handle_kind(self, item, h: str) -> str | None:
        """``"point"`` / ``"edge"`` / ``"curve"`` for handle *h*, or None --
        pure membership, so an adapter with an expensive expression dict can
        answer without building it."""
        if h in self.points(item, 0):
            return "point"
        if h in self.edges(item, 0):
            return "edge"
        if h in self.curves(item, 0):
            return "curve"
        return None

    def circle_curves(self, item) -> frozenset:
        """Names of the ``curves`` handles that are FULL circles (a Smart
        Dimension on one is a diameter, not a radius); none by default."""
        return frozenset()

    def hidden_names(self, item) -> frozenset:
        """CS3c: point handles that stay valid (old records solve) but are
        never offered as pick candidates -- text ``ins``. None by default."""
        return frozenset()

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

    def struct_key(self, item) -> tuple:
        """What a built System's rows depend on besides values (D18 build cache)."""
        return (self.type_key, self.nvars(item))

    def locked(self, item) -> bool:
        """Slice 2 (ruling L1): a locked item is fixed in every solve."""
        return False


class _LineAdapter(_Adapter):
    """vars x1 y1 x2 y2; handles ``p1`` ``p2``, the derived midpoint ``mid``
    (CS3b) + edge ``edge``."""

    def __init__(self, key):
        self.type_key = key

    def nvars(self, it):
        return 4

    def read(self, it):
        return [it._pt1.x(), it._pt1.y(), it._pt2.x(), it._pt2.y()]

    def points(self, it, off):
        p1, p2 = raw_point(off, off + 1), raw_point(off + 2, off + 3)
        return {"p1": p1, "p2": p2, "mid": _mid(p1, p2)}

    def mid_names(self, it):
        return frozenset(("mid",))

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


class _WallAdapter(_LineAdapter):
    """Slice 2 (ruling W1): vars = the drawn line x1 y1 x2 y2 (``_pt1`` /
    ``_pt2``, the grips). Points ``p1`` ``p2`` ``mid`` (true centerline), the
    untrimmed body corners ``p1l`` ``p1r`` ``p2l`` ``p2r`` and the HIDDEN face
    midpoints ``mid_l`` ``mid_r`` (WF1); edges ``edge``
    (centerline), ``face_l``, ``face_r``, ``end1``, ``end2``. Width is not a
    variable (``half_thickness_scene`` is a constant of the build)."""

    def __init__(self):
        super().__init__("wall")

    @staticmethod
    def _offsets(it) -> tuple:
        """(centerline, left face, right face) normal offsets, scene units."""
        from .wall import ALIGN_LEFT, ALIGN_RIGHT
        k = {ALIGN_LEFT: 1.0, ALIGN_RIGHT: -1.0}.get(it._alignment, 0.0)
        ht = it.half_thickness_scene()
        return k * ht, (1.0 + k) * ht, (k - 1.0) * ht

    def points(self, it, off):
        sc, sl, sr = self._offsets(it)
        p1, p2 = _offset_point(off, 0, sc), _offset_point(off, 1, sc)
        p1l, p1r = _offset_point(off, 0, sl), _offset_point(off, 0, sr)
        p2l, p2r = _offset_point(off, 1, sl), _offset_point(off, 1, sr)
        return {"p1": p1, "p2": p2, "mid": _mid(p1, p2),
                "p1l": p1l, "p1r": p1r, "p2l": p2l, "p2r": p2r,
                # WF1 (wall faces design): HIDDEN face midpoints -- never a
                # marker / pick / grip; D81 face dims and the solver resolve
                # them by name.
                "mid_l": _mid(p1l, p2l), "mid_r": _mid(p1r, p2r)}

    def edges(self, it, off):
        p = self.points(it, off)
        return {"edge": (p["p1"], p["p2"]), "face_l": (p["p1l"], p["p2l"]),
                "face_r": (p["p1r"], p["p2r"]), "end1": (p["p1l"], p["p1r"]),
                "end2": (p["p2l"], p["p2r"])}

    def grip_handle(self, it, index):
        return {0: "p1", 1: "p2"}.get(index)

    def pin_vars(self, it, index):
        """Grip 0 / 1 move ``_pt1`` / ``_pt2`` (raw vars, even when ``p1`` /
        ``p2`` are derived); the move and width grips pin the whole wall."""
        return {0: (0, 1), 1: (2, 3)}.get(index, (0, 1, 2, 3))

    def struct_key(self, it):
        return (self.type_key, 4, it._alignment, round(it.half_thickness_scene(), 9))

    def hidden_names(self, it):
        """WF1: the face midpoints stay out of every pick / marker enumeration."""
        return frozenset(("mid_l", "mid_r"))

    def write(self, it, v):
        it._pt1 = QPointF(float(v[0]), float(v[1]))
        it._pt2 = QPointF(float(v[2]), float(v[3]))
        it.invalidate_geometry()       # outline, joins, openings (wall-room-floor s4.5/s6.1)


class _GridlineAdapter(_LineAdapter):
    """Slice 2: vars x1 y1 x2 y2 = origin + far end, derived from
    ``_origin`` / ``_length`` / ``_angle_deg``; handles ``p1`` ``p2`` ``mid``
    ``edge``. Write-back keeps the bubble standoffs; a locked gridline is
    fixed (ruling L1). Hosted blocks (ruling H1): an origin slide along the
    unchanged axis compensates ``along_mm`` (D6, as grip 0 does); a shift or
    rotation lets them ride (``_rebuild_geometry`` -> D5 sync)."""

    def __init__(self):
        super().__init__("gridline")

    def read(self, it):
        far = it._far_point()
        return [it._origin.x(), it._origin.y(), far.x(), far.y()]

    def grip_handle(self, it, index):
        return {0: "p1", 1: "p2"}.get(index)

    def locked(self, it):
        return bool(getattr(it, "_locked", False))

    def struct_key(self, it):
        return (self.type_key, 4, self.locked(it))

    def collapses(self, it, old, new):
        """D29 + the gridline's own 1-unit length floor (``set_length``)."""
        ln = math.hypot(float(new[2]) - float(new[0]), float(new[3]) - float(new[1]))
        return super().collapses(it, old, new) or ln < 1.0 - DEGEN_EPS

    def write(self, it, v):
        if self.locked(it):
            return
        ox, oy, fx, fy = (float(a) for a in v)
        new = QPointF(ox, oy)
        ang = math.degrees(math.atan2(-(fy - oy), fx - ox)) % 360.0
        turn = abs((ang - it._angle_deg + 180.0) % 360.0 - 180.0)
        if turn <= math.degrees(ANG_WRITE_TOL):
            sc = it.scene()
            shift = getattr(sc, "_shift_hosted_along", None) if sc is not None else None
            if shift is not None:
                shift(it, QPointF(it._origin), new)    # H1 / D6: axial part stays put
        else:
            it._angle_deg = ang
        it._origin = new
        it._length = max(1.0, math.hypot(fx - ox, fy - oy))
        it._rebuild_geometry()


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


def _rect_point_batch(V, P):
    """Batched ``_rect_point_fn``: V (k, 5) = cx cy w h th, P (k, 2) = su sv."""
    cx, cy, w, h, th = V.T
    su, sv = P.T
    u, vv = su * w / 2.0, sv * h / 2.0
    c, s = np.cos(th), np.sin(th)
    pts = np.stack([cx + u * c + vv * s, cy - u * s + vv * c], axis=1)
    dp = np.zeros((len(V), 2, 5))
    dp[:, 0, 0] = 1.0
    dp[:, 0, 2] = su / 2.0 * c
    dp[:, 0, 3] = sv / 2.0 * s
    dp[:, 0, 4] = -u * s + vv * c
    dp[:, 1, 1] = 1.0
    dp[:, 1, 2] = -su / 2.0 * s
    dp[:, 1, 3] = sv / 2.0 * c
    dp[:, 1, 4] = -u * c - vv * s
    return pts, dp


register_point_family("rect", _rect_point_batch)


class _RectAdapter(_Adapter):
    """vars cx cy w h th (scene centre; th = Y-up CCW radians). Write-back
    canonicalises the pivot to the centre (pivot=None) — identical scene
    geometry (§5.1)."""

    type_key = "draw_rectangle"

    def nvars(self, it):
        return 5

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
        return {name: PointExpr(idx=idx, fn=_rect_point_fn(su, sv), fam=("rect", (su, sv)))
                for name, (su, sv) in _RECT_LOCAL.items()}

    def edges(self, it, off):
        p = self.points(it, off)
        return {e: (p[a], p[b]) for e, (a, b) in _RECT_EDGES.items()}

    def mid_names(self, it):
        """CS3b: the edge midpoints already exist as §5.3 handles."""
        return frozenset(("tm", "rm", "bm", "lm"))

    def write(self, it, v):
        cx, cy, w, h, th = (float(t) for t in v)
        w, h = max(w, RECT_MIN_SIZE), max(h, RECT_MIN_SIZE)
        it.prepareGeometryChange()
        it.setRect(QRectF(cx - w / 2.0, cy - h / 2.0, w, h))
        deg = math.degrees(th)
        if it._angle != deg or it._pivot is not None:   # D18: setRect already repaints
            it.set_angle(deg, None)


class _CircleAdapter(_Adapter):
    """vars cx cy r; handle ``center``."""

    type_key = "draw_circle"

    def circle_curves(self, item):
        return frozenset(("curve",))

    def nvars(self, it):
        return 3

    def read(self, it):
        return [it._center.x(), it._center.y(), float(it._radius)]

    def points(self, it, off):
        return {"center": raw_point(off, off + 1)}

    def size_floors(self, it):
        return {2: CIRCLE_MIN_RADIUS}

    def curves(self, it, off):
        return {"curve": CurveExpr(center=raw_point(off, off + 1), r=off + 2)}

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

    def nvars(self, it):
        return 5

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

    def curves(self, it, off):
        return {"curve": CurveExpr(center=raw_point(off, off + 1), r=off + 2,
                                   span=(off + 3, off + 4))}

    def write(self, it, v):
        cx, cy, r, ts, te = (float(t) for t in v)
        it._center = QPointF(cx, cy)
        it._radius = max(r, ARC_MIN_RADIUS)
        it._start_deg = math.degrees(ts) % 360.0
        span = math.degrees(te - ts) % 360.0           # keeps span_deg > 0 (§5.1)
        it._span_deg = span if span > 1e-9 else 360.0
        it._rebuild_path()


class _PolylineAdapter(_Adapter):
    """2 vars per vertex; ``v<i>`` + segments ``s<i>`` (closing one if closed)
    + each segment's derived midpoint ``m<i>`` (CS3b)."""

    type_key = "polyline"

    def nvars(self, it):
        return 2 * len(it._points)

    def read(self, it):
        out = []
        for p in it._points:
            out += [p.x(), p.y()]
        return out

    def grip_handle(self, it, index):
        return f"v{index}" if 0 <= index < len(it._points) else None

    def _seg_pairs(self, it):
        """``(i, j)`` vertex pairs of every segment ``s<i>`` (closing one too)."""
        n = len(it._points)
        pairs = [(i, i + 1) for i in range(n - 1)]
        if it.is_closed() and n > 2:
            pairs.append((n - 1, 0))
        return pairs

    def points(self, it, off):
        out = {f"v{i}": raw_point(off + 2 * i, off + 2 * i + 1)
               for i in range(len(it._points))}
        for i, j in self._seg_pairs(it):
            out[f"m{i}"] = _mid(out[f"v{i}"], out[f"v{j}"])
        return out

    def mid_names(self, it):
        return frozenset(f"m{i}" for i, _j in self._seg_pairs(it))

    def edges(self, it, off):
        p = self.points(it, off)
        return {f"s{i}": (p[f"v{i}"], p[f"v{j}"]) for i, j in self._seg_pairs(it)}

    def collapses(self, it, old, new):
        """D29 + D36: any segment (the closing one too) shrunk to zero length."""
        return super().collapses(it, old, new) or any(
            _seg_collapses(old, new, i, j) for i, j in self._seg_pairs(it))

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

    def nvars(self, it):
        return 2 + len(self._fields)

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
    R and rotation; grip 0 -> ``center``, grip i (1..n) -> ``v<i-1>`` (§5.3).
    CS3b: each edge's derived midpoint ``m<i>``."""

    def grip_handle(self, it, index):
        if index == 0:
            return "center"
        return f"v{index - 1}" if 1 <= index <= it._sides else None

    def struct_key(self, it):
        """Vertex rows capture the side count and the inscribed flag."""
        return (self.type_key, it._sides, bool(it._inscribed))

    def points(self, it, off):
        n, idx = it._sides, (off, off + 1, off + 2, off + 3)
        out = {"center": raw_point(off, off + 1)}
        for k in range(n):
            out[f"v{k}"] = PointExpr(idx=idx, fn=_poly_vertex_fn(k, n, it._inscribed))
        for k in range(n):
            out[f"m{k}"] = _mid(out[f"v{k}"], out[f"v{(k + 1) % n}"])
        return out

    def mid_names(self, it):
        return frozenset(f"m{k}" for k in range(it._sides))

    def edges(self, it, off):
        p, n = self.points(it, off), it._sides
        return {f"s{k}": (p[f"v{k}"], p[f"v{(k + 1) % n}"]) for k in range(n)}

    def curves(self, it, off):
        """CS5 D79: the defining circle (R = circumradius, or the apothem when
        circumscribed) -- the polygon R dim's handle; hidden from picks."""
        return {"radius": CurveExpr(center=raw_point(off, off + 1), r=off + 2)}

    def hidden_names(self, it):
        return frozenset(("radius",))


def _ell_axis_fn(which: int, sgn: float):
    """CS5 D70: an ellipse axis end over (cx, cy, rx, ry, rot) -- exactly
    ``EllipseItem._axis_endpoint``: rx along rot (which 0), ry along
    rot + 90° (which 1); *sgn* -1 = the opposite end."""
    def fn(v):
        cx, cy, rx, ry, rot = v
        a = rot + (math.pi / 2.0 if which else 0.0)
        c, s = math.cos(a), math.sin(a)
        r = ry if which else rx
        dp = np.zeros((2, 5))
        dp[0, 0] = dp[1, 1] = 1.0
        dp[0, 2 + which], dp[1, 2 + which] = sgn * c, -sgn * s
        dp[0, 4], dp[1, 4] = -sgn * r * s, -sgn * r * c
        return np.array([cx + sgn * r * c, cy - sgn * r * s]), dp
    return fn


class _EllipseAdapter(_CenterRotAdapter):
    """vars cx cy rx ry rot; ``center`` + derived axis ends ``a0 a1 b0 b1``
    (D70) + hidden curves ``rx`` / ``ry`` (the R1 / R2 dim handles, D79)."""

    _ENDS = {"a0": (0, 1.0), "a1": (0, -1.0), "b0": (1, 1.0), "b1": (1, -1.0)}

    def points(self, it, off):
        idx = tuple(range(off, off + 5))
        out = {"center": raw_point(off, off + 1)}
        for name, (which, sgn) in self._ENDS.items():
            out[name] = PointExpr(idx=idx, fn=_ell_axis_fn(which, sgn))
        return out

    def curves(self, it, off):
        c = raw_point(off, off + 1)
        return {"rx": CurveExpr(center=c, r=off + 2), "ry": CurveExpr(center=c, r=off + 3)}

    def hidden_names(self, it):
        return frozenset(("rx", "ry"))


def _pose_point_fn(u: float, v: float):
    """A nested block's local point (u, v) under its pose vars (x, y, th):
    ``p = (x + u·cosθ + v·sinθ, y − u·sinθ + v·cosθ)`` -- the rectangle
    formula (``_rect_point_fn``) with the local offset baked (NB9)."""
    def fn(w):
        x, y, th = w
        c, s = math.cos(th), math.sin(th)
        return (np.array([x + u * c + v * s, y - u * s + v * c]),
                np.array([[1.0, 0.0, -u * s + v * c],
                          [0.0, 1.0, -u * c - v * s]]))
    return fn


def _pose_point_batch(V, P):
    """Batched ``_pose_point_fn``: V (k, 3) = x y th, P (k, 2) = u v."""
    x, y, th = V.T
    u, v = P.T
    c, s = np.cos(th), np.sin(th)
    pts = np.stack([x + u * c + v * s, y - u * s + v * c], axis=1)
    dp = np.zeros((len(V), 2, 3))
    dp[:, 0, 0] = 1.0
    dp[:, 0, 2] = -u * s + v * c
    dp[:, 1, 1] = 1.0
    dp[:, 1, 2] = -u * c - v * s
    return pts, dp


register_point_family("pose", _pose_point_batch)


class _NestedHandles:
    """A nested instance's handle table in its LOCAL (unrotated) frame:
    ``points[name] = (u, v)``, ``edges[name] = ((u, v), (u, v))``,
    ``curves[name] = ((u, v), r)``, plus the midpoint / hidden name sets."""
    __slots__ = ("points", "edges", "curves", "mids", "hidden", "circles")

    def __init__(self):
        self.points, self.edges, self.curves = {}, {}, {}
        self.mids, self.hidden, self.circles = set(), set(), set()


def _nested_table(inst) -> _NestedHandles:
    """The table of *inst* (NB2/NB3), memoised on (compiled ops identity,
    mirrored, scale) -- the ``snap_primitives`` idiom: a child-definition edit
    recompiles the ops, so the table rebuilds without explicit invalidation.
    Built from the snap stand-ins at the identity-rotation pose (origin
    shift, mirror and scale already baked; rotation is the expression's)."""
    from .block_snap_geometry import posed_primitives
    ops = inst.render_ops()
    mir, s = bool(inst.block_mirrored()), float(inst.block_scale())
    cached = getattr(inst, "_nested_handles_cache", None)
    if cached is not None and cached[0] is ops and cached[1] == mir and cached[2] == s:
        return cached[3]
    t = _NestedHandles()
    prims, origins = posed_primitives(inst.definition(), (0.0, 0.0, 0.0, mir, s), paths=True)
    for path, child in prims:
        ad = adapter_for(child)
        if ad is None:
            continue
        x = np.array(ad.read(child), dtype=float)
        for n, e in ad.points(child, 0).items():
            t.points[f"{path}:{n}"] = tuple(float(c) for c in e.eval(x)[0])
        for n, (a, b) in ad.edges(child, 0).items():
            t.edges[f"{path}:{n}"] = (tuple(float(c) for c in a.eval(x)[0]),
                                      tuple(float(c) for c in b.eval(x)[0]))
        for n, cv in ad.curves(child, 0).items():
            # a child is never a nested instance -- the walker flattens -- so r
            # is always a variable index
            t.curves[f"{path}:{n}"] = (tuple(float(c) for c in cv.center.eval(x)[0]),
                                       float(x[cv.r]))
        t.mids.update(f"{path}:{n}" for n in ad.mid_names(child))
        t.circles.update(f"{path}:{n}" for n in ad.circle_curves(child))
        t.hidden.update(f"{path}:{n}" for n in ad.hidden_names(child))
    for path, (u, v) in origins:
        t.points[f"{path}:ins"] = (float(u), float(v))
    inst._nested_handles_cache = (ops, mir, s, t)
    return t


class _NestedAdapter(_Adapter):
    """Nested block instance: vars x y th (th = Y-up CCW radians, an angle
    var -- NB1); ``ins`` raw + every child handle of the local table posed
    through ``_pose_point_fn`` (NB2/NB3). Mirror and scale are constants."""

    def __init__(self, key):
        self.type_key = key

    def nvars(self, it):
        return 3

    def read(self, it):
        x, y = it.block_pos()
        return [float(x), float(y), math.radians(it.block_rotation())]

    def angle_vars(self, it):
        return (2,)

    def grip_handle(self, it, index):
        return "ins"

    def struct_key(self, it):
        # id(ops) is stable because _nested_handles_cache holds the ops list alive
        return (self.type_key, 3, id(it.render_ops()),
                bool(it.block_mirrored()), float(it.block_scale()))

    @staticmethod
    def _posed(off, uv):
        u, v = uv
        return PointExpr(idx=(off, off + 1, off + 2), fn=_pose_point_fn(u, v),
                         fam=("pose", (u, v)))

    def points(self, it, off):
        out = {"ins": raw_point(off, off + 1)}
        for name, uv in _nested_table(it).points.items():
            out[name] = self._posed(off, uv)
        return out

    def edges(self, it, off):
        return {name: (self._posed(off, a), self._posed(off, b))
                for name, (a, b) in _nested_table(it).edges.items()}

    def curves(self, it, off):
        return {name: CurveExpr(center=self._posed(off, c), r=None, r_const=r)
                for name, (c, r) in _nested_table(it).curves.items()}

    def mid_names(self, it):
        return frozenset(_nested_table(it).mids)

    def hidden_names(self, it):
        return frozenset(_nested_table(it).hidden)

    def circle_curves(self, it):
        return frozenset(_nested_table(it).circles)

    def handle_kind(self, it, h):
        if h == "ins":
            return "point"
        t = _nested_table(it)
        if h in t.points:
            return "point"
        if h in t.edges:
            return "edge"
        if h in t.curves:
            return "curve"
        return None

    def write(self, it, v):
        x, y, th = (float(t) for t in v)
        it.set_block_pos(x, y)
        if abs(th - math.radians(it.block_rotation())) > ANG_WRITE_TOL:
            # round: radians->degrees drift (30 deg -> 29.999999999999996) must
            # not leak into the item on a restore (still inside ANG_WRITE_TOL)
            it.set_block_rotation(round(math.degrees(th), 9))


def _text_point_fn(su, sv, th):
    """``_rect_point_fn`` over cx cy w h with the text's rotation *th* held
    constant (CS3c: rotation is never a variable)."""
    f = _rect_point_fn(su, sv)

    def fn(v):
        p, dp = f(np.append(np.asarray(v, dtype=float), th))
        return p, dp[:, :4]
    return fn


def _text_ins_fn(v):
    """CS3c AC4: legacy ``ins`` == ``pos()`` == centre - (w/2, h/2) -- the
    box rotates about its centre, so pos is unrotated. Exact for the at-rest
    centre pivot (pivot None); a transient explicit pivot is canonicalised to
    None by the first write."""
    cx, cy, w, h = v
    return (np.array([cx - w / 2.0, cy - h / 2.0]),
            np.array([[1.0, 0.0, -0.5, 0.0], [0.0, 1.0, 0.0, -0.5]]))


def _content_height_at(it, w_local: float) -> float:
    """The text's content height (local units) if wrapped at *w_local* --
    laid out on a clone, the item untouched (P4-probed: equals the real
    ``_box_rect_local`` height after ``setTextWidth``)."""
    doc = it.document().clone()
    doc.setTextWidth(w_local)
    return doc.size().height()


class _TextBoxAdapter(_Adapter):
    """CS3c: vars cx cy w h, all SCENE units (box centre; w -> wrap width,
    h -> box height; local box size x ``scale()`` -- 1 in the editor).
    Handles = the rectangle's (``tl``..``center`` + edges) through the text's
    constant rotation, plus the hidden legacy ``ins``. Write-back
    canonicalises the pivot to the centre (identical geometry), like the
    rectangle."""

    type_key = "text"

    def nvars(self, it):
        return 4

    def read(self, it):
        r = it._box_rect_local()
        s = it.scale() or 1.0
        c = it.mapToScene(r.center())
        return [c.x(), c.y(), r.width() * s, r.height() * s]

    def size_floors(self, it):
        return {2: MIN_TEXT_WRAP_WIDTH_MM, 3: 0.0}

    def struct_key(self, it):
        """The rotation is baked into the handle fns (D18 build cache)."""
        return (self.type_key, 4, float(it._angle))

    def points(self, it, off):
        idx = tuple(range(off, off + 4))
        th = math.radians(it._angle)
        out = {name: PointExpr(idx=idx, fn=_text_point_fn(su, sv, th))
               for name, (su, sv) in _RECT_LOCAL.items()}
        out["ins"] = PointExpr(idx=idx, fn=_text_ins_fn)
        return out

    def edges(self, it, off):
        p = self.points(it, off)
        return {e: (p[a], p[b]) for e, (a, b) in _RECT_EDGES.items()}

    def mid_names(self, it):
        return frozenset(("tm", "rm", "bm", "lm"))

    def hidden_names(self, it):
        return frozenset(("ins",))

    def collapses(self, it, old, new):
        """D29 width floor, plus AC3: a solve that changed the size and leaves
        the box shorter than its text re-wrapped at the solved width. Sizes
        are settled first (review I1): solver noise the write would drop
        (an auto-width box sits exactly at its idealWidth, so -1e-8 re-wraps
        a word) is never a collapse."""
        if super().collapses(it, old, new):
            return True
        n = self.settled(it, old, new)
        w, h = n[2], n[3]
        if w == float(old[2]) and h == float(old[3]):
            return False
        s = it.scale() or 1.0
        # An unmoved width re-wraps at the item's own textWidth: w / s can
        # land 1 ulp under it at scale != 1, and Qt truncates to 1/64.
        w_local = it.textWidth() if w == float(old[2]) else w / s
        return _content_height_at(it, w_local) * s > h + DEGEN_EPS

    def write(self, it, v):
        cx, cy, w, h = (float(t) for t in v)
        o = self.read(it)
        s = it.scale() or 1.0
        it.prepareGeometryChange()
        w_moved = abs(w - o[2]) > POS_WRITE_TOL
        h_moved = abs(h - o[3]) > POS_WRITE_TOL
        if w_moved:
            w = max(w, MIN_TEXT_WRAP_WIDTH_MM)
            it.setTextWidth(w / s)
            it._data.wrap_width_mm = w
        else:
            w = o[2]                      # sub-tolerance noise never shifts pos
        if not h_moved:
            h = o[3]
        if w_moved or h_moved:
            # Freeze the solved height (an auto box would otherwise re-fit
            # the re-wrapped content and drift its bottom edge / centre).
            it._data.box_height_mm = h
        if it._pivot is not None:
            it.set_angle(it._angle, None)
        it.setPos(cx - w / 2.0, cy - h / 2.0)
        it.sync_data_from_item()
        it.update()


def _registry():
    from .block_instance import BlockInstance
    from .geometry_2d import (_AXIS_MIN, ArcItem, CircleItem, EllipseItem, LineItem,
                              PolylineItem, RectangleItem,
                              RegularPolygonItem)
    from .gridline import GridlineItem
    from .text_item import TextItem
    from .wall import WallSegment
    return {
        LineItem: _LineAdapter("draw_line"),
        RectangleItem: _RectAdapter(),
        CircleItem: _CircleAdapter(),
        ArcItem: _ArcAdapter(),
        PolylineItem: _PolylineAdapter(),
        RegularPolygonItem: _PolygonAdapter(
            "polygon", ("_radius_mm", "_rotation_deg"), {"_radius_mm": _AXIS_MIN}),
        EllipseItem: _EllipseAdapter(
            "draw_ellipse", ("_rx", "_ry", "_rotation_deg"),
            {"_rx": _AXIS_MIN, "_ry": _AXIS_MIN}),
        TextItem: _TextBoxAdapter(),
        BlockInstance: _NestedAdapter("block_instance"),
        WallSegment: _WallAdapter(),
        GridlineItem: _GridlineAdapter(),
    }


_REG = None


def adapter_for(item):
    """The item's adapter by EXACT type (subclass-safe), or None (spline, other)."""
    global _REG
    if _REG is None:
        _REG = _registry()
    return _REG.get(type(item))
