"""Pick-point region finder (HF4).

Design: ``docs/superpowers/specs/2026-10-20-hf4-pick-region-design.md`` §1.
Pure geometry -- depends on Qt value types and the 2D item constructors only,
never on a scene or a view. ``Arrangement.build`` flattens the drawn paths of
the candidate items (``halo.halo_scene_path``) into tagged segments, splits
them at every crossing, welds vertices within ``CHAIN_WELD_MM``, prunes
dangling edges (recording the open ends) and links half-edges; ``face_at``
walks the tightest-left-turn cycle around a point; ``rebuild`` turns a face
back into exact pieces for ``FilledRegionItem.from_pieces``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPainterPath

from .constants import (CHAIN_MIN_LOOP_AREA_MM2, CHAIN_WELD_MM,
                        REGION_FINDER_BUCKETS, REGION_FINDER_NUDGE_MM,
                        REGION_FINDER_SAGITTA_MM)
from .geometry_2d import bezier_sub
from .geometry_intersect import line_line_intersection
from .halo import halo_scene_path

_EPS = 1e-9


@dataclass(frozen=True)
class Tag:
    """Which drawn path element a flattened segment came from.

    Attributes:
        item: The source 2D item (or a posed block stand-in).
        elem: Index of the ``LineTo`` / ``CurveTo`` element in the item's
            ``halo_scene_path`` that drew it.
        kind: ``"line"`` or ``"curve"``.
        bez: The cubic's four ``(x, y)`` control points for ``"curve"``.
        t0: Parameter of the segment's start along the element.
        t1: Parameter of its end (``t1 < t0`` once a walk traverses it backwards).
    """
    item: object
    elem: int
    kind: str
    bez: tuple | None
    t0: float
    t1: float


@dataclass
class Piece:
    """One flattened straight segment in scene coordinates with its tag."""
    x0: float
    y0: float
    x1: float
    y1: float
    tag: Tag

    def sub(self, u0: float, u1: float) -> "Piece":
        """The part ``[u0, u1]`` of this segment, tag parameters interpolated."""
        dx, dy = self.x1 - self.x0, self.y1 - self.y0
        dt = self.tag.t1 - self.tag.t0
        t = self.tag
        return Piece(self.x0 + dx * u0, self.y0 + dy * u0,
                     self.x0 + dx * u1, self.y0 + dy * u1,
                     Tag(t.item, t.elem, t.kind, t.bez, t.t0 + dt * u0, t.t0 + dt * u1))

    def reversed(self) -> "Piece":
        t = self.tag
        return Piece(self.x1, self.y1, self.x0, self.y0,
                     Tag(t.item, t.elem, t.kind, t.bez, t.t1, t.t0))

    def bbox(self) -> tuple:
        return (min(self.x0, self.x1), min(self.y0, self.y1),
                max(self.x0, self.x1), max(self.y0, self.y1))


# ── 1. Flatten ──────────────────────────────────────────────────────────────

def _bez_pt(b, t):
    u = 1.0 - t
    return (u**3 * b[0][0] + 3*u*u*t * b[1][0] + 3*u*t*t * b[2][0] + t**3 * b[3][0],
            u**3 * b[0][1] + 3*u*u*t * b[1][1] + 3*u*t*t * b[2][1] + t**3 * b[3][1])


def _flat_enough(b, sagitta: float) -> bool:
    """Control points within *sagitta* of the chord -> one segment suffices."""
    (x0, y0), (x3, y3) = b[0], b[3]
    dx, dy = x3 - x0, y3 - y0
    L = math.hypot(dx, dy)
    for x, y in (b[1], b[2]):
        d = (math.hypot(x - x0, y - y0) if L < 1e-12
             else abs((x - x0) * dy - (y - y0) * dx) / L)
        if d > sagitta:
            return False
    return True


def _window_hits(win: tuple, x0, y0, x1, y1) -> bool:
    wx0, wy0, wx1, wy1 = win
    return not (max(x0, x1) < wx0 or min(x0, x1) > wx1
                or max(y0, y1) < wy0 or min(y0, y1) > wy1)


def _emit_seg(out: list, win: tuple, p, q, tag: Tag) -> None:
    if math.hypot(q[0] - p[0], q[1] - p[1]) < _EPS:
        return
    if _window_hits(win, p[0], p[1], q[0], q[1]):
        out.append(Piece(p[0], p[1], q[0], q[1], tag))


def _flatten_cubic(out, win, item, elem, b, t0=0.0, t1=1.0, depth=0) -> None:
    piece = bezier_sub(b, t0, t1)
    if depth >= 16 or _flat_enough(piece, REGION_FINDER_SAGITTA_MM):
        _emit_seg(out, win, piece[0], piece[3], Tag(item, elem, "curve", b, t0, t1))
        return
    tm = (t0 + t1) / 2
    _flatten_cubic(out, win, item, elem, b, t0, tm, depth + 1)
    _flatten_cubic(out, win, item, elem, b, tm, t1, depth + 1)


def _flatten(items, window: QRectF) -> list[Piece]:
    """Tagged straight segments of every item's drawn path inside *window*.

    ``MoveTo``/``LineTo`` -> one segment; ``CurveTo`` (cubic; what circles,
    arcs, ellipses and splines draw) -> adaptive subdivision at
    ``REGION_FINDER_SAGITTA_MM``. Segments wholly outside the window (padded
    by the weld tolerance) are dropped.
    """
    pad = CHAIN_WELD_MM
    win = (window.left() - pad, window.top() - pad, window.right() + pad, window.bottom() + pad)
    out: list[Piece] = []
    Move = QPainterPath.ElementType.MoveToElement
    Line = QPainterPath.ElementType.LineToElement
    Curve = QPainterPath.ElementType.CurveToElement
    for item in items:
        path = halo_scene_path(item)
        n = path.elementCount()
        prev = None
        i = 0
        while i < n:
            e = path.elementAt(i)
            if e.type == Move:
                prev = (e.x, e.y)
                i += 1
            elif e.type == Line:
                cur = (e.x, e.y)
                if prev is not None:
                    _emit_seg(out, win, prev, cur, Tag(item, i, "line", None, 0.0, 1.0))
                prev = cur
                i += 1
            elif e.type == Curve and i + 2 < n and prev is not None:
                d1, d2 = path.elementAt(i + 1), path.elementAt(i + 2)
                b = (prev, (e.x, e.y), (d1.x, d1.y), (d2.x, d2.y))
                _flatten_cubic(out, win, item, i, b)
                prev = b[3]
                i += 3
            else:
                i += 1
    return out


# ── 2. Split at crossings ───────────────────────────────────────────────────

def _param_on(p: Piece, q: QPointF) -> float:
    dx, dy = p.x1 - p.x0, p.y1 - p.y0
    L2 = dx * dx + dy * dy
    if L2 < _EPS:
        return 0.0
    return ((q.x() - p.x0) * dx + (q.y() - p.y0) * dy) / L2


def _bucket_grid(pieces: list[Piece], window: QRectF):
    """``{(bx, by): [piece index, ...]}`` over a REGION_FINDER_BUCKETS² grid."""
    B = REGION_FINDER_BUCKETS
    w = max(window.width(), 1e-6) / B
    h = max(window.height(), 1e-6) / B
    ox, oy = window.left(), window.top()
    grid: dict = {}
    for idx, p in enumerate(pieces):
        x0, y0, x1, y1 = p.bbox()
        bx0 = max(0, min(B - 1, int((x0 - ox) // w)))
        bx1 = max(0, min(B - 1, int((x1 - ox) // w)))
        by0 = max(0, min(B - 1, int((y0 - oy) // h)))
        by1 = max(0, min(B - 1, int((y1 - oy) // h)))
        for bx in range(bx0, bx1 + 1):
            for by in range(by0, by1 + 1):
                grid.setdefault((bx, by), []).append(idx)
    return grid


def _split_all(pieces: list[Piece], window: QRectF) -> list[Piece]:
    """Cut every piece at each crossing with another piece (tags interpolated)."""
    grid = _bucket_grid(pieces, window)
    cuts: list[list[float]] = [[] for _ in pieces]
    seen: set = set()
    boxes = [p.bbox() for p in pieces]
    for members in grid.values():
        for a in range(len(members)):
            i = members[a]
            bi = boxes[i]
            for b in range(a + 1, len(members)):
                j = members[b]
                key = (i, j) if i < j else (j, i)
                if key in seen:
                    continue
                seen.add(key)
                bj = boxes[j]
                if bi[2] < bj[0] or bj[2] < bi[0] or bi[3] < bj[1] or bj[3] < bi[1]:
                    continue
                pi, pj = pieces[i], pieces[j]
                q = line_line_intersection(QPointF(pi.x0, pi.y0), QPointF(pi.x1, pi.y1),
                                           QPointF(pj.x0, pj.y0), QPointF(pj.x1, pj.y1))
                if q is None:
                    continue
                cuts[i].append(_param_on(pi, q))
                cuts[j].append(_param_on(pj, q))
    out: list[Piece] = []
    for p, ts in zip(pieces, cuts):
        params = sorted(t for t in ts if _EPS < t < 1.0 - _EPS)
        prev = 0.0
        for t in params + [1.0]:
            if t - prev > _EPS:
                out.append(p.sub(prev, t))
                prev = t
    return out


# ── 3. Weld ─────────────────────────────────────────────────────────────────

class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, k: int) -> int:
        while self.parent[k] != k:
            self.parent[k] = self.parent[self.parent[k]]
            k = self.parent[k]
        return k

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _seg_point_dist(px, py, x0, y0, x1, y1):
    """(distance, parameter) of the closest point on segment (x0,y0)-(x1,y1)."""
    dx, dy = x1 - x0, y1 - y0
    L2 = dx * dx + dy * dy
    if L2 < _EPS:
        return math.hypot(px - x0, py - y0), 0.0
    t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / L2))
    return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy)), t


def _weld(pieces: list[Piece], tol: float):
    """Vertices merged within *tol* (union-find on a grid), then T-gaps closed.

    Returns ``(verts, edges)`` with ``verts = [(x, y), ...]`` and
    ``edges = [[u, v, piece], ...]`` (``u != v``; duplicate edges between the
    same two vertices with the same midpoint collapse to one).
    """
    pts = []
    for p in pieces:
        pts.append((p.x0, p.y0))
        pts.append((p.x1, p.y1))
    uf = _UnionFind(len(pts))
    cell = max(tol, 1e-6)
    grid: dict = {}
    for k, (x, y) in enumerate(pts):
        grid.setdefault((math.floor(x / cell), math.floor(y / cell)), []).append(k)
    for k, (x, y) in enumerate(pts):
        cx, cy = math.floor(x / cell), math.floor(y / cell)
        for ddx in (-1, 0, 1):
            for ddy in (-1, 0, 1):
                for m in grid.get((cx + ddx, cy + ddy), ()):
                    if m > k and math.hypot(pts[m][0] - x, pts[m][1] - y) <= tol:
                        uf.union(k, m)
    vid: dict = {}
    verts: list = []
    for k in range(len(pts)):
        r = uf.find(k)
        if r not in vid:
            vid[r] = len(verts)
            verts.append(pts[r])
    edges: list = []
    for n, p in enumerate(pieces):
        u, v = vid[uf.find(2 * n)], vid[uf.find(2 * n + 1)]
        if u != v:
            edges.append([u, v, p])
    # T-gap: a degree-1 vertex within tol of an edge interior splits that edge.
    deg = [0] * len(verts)
    for u, v, _ in edges:
        deg[u] += 1
        deg[v] += 1
    for vi in [i for i in range(len(verts)) if deg[i] == 1]:
        x, y = verts[vi]
        best = None
        for ei, (u, v, p) in enumerate(edges):
            if u == vi or v == vi:
                continue
            d, t = _seg_point_dist(x, y, verts[u][0], verts[u][1], verts[v][0], verts[v][1])
            if d <= tol and _EPS < t < 1.0 - _EPS and (best is None or d < best[0]):
                best = (d, t, ei)
        if best is None:
            continue
        _, t, ei = best
        u, v, p = edges[ei]
        verts[vi] = (verts[u][0] + t * (verts[v][0] - verts[u][0]),
                     verts[u][1] + t * (verts[v][1] - verts[u][1]))
        edges[ei] = [u, vi, p.sub(0.0, t)]
        edges.append([vi, v, p.sub(t, 1.0)])
        deg[vi] += 2
    # Collapse duplicate edges (coincident lines): same vertex pair, same midpoint.
    seen: dict = {}
    out: list = []
    for u, v, p in edges:
        key = (min(u, v), max(u, v), round((p.x0 + p.x1) / 2, 3), round((p.y0 + p.y1) / 2, 3))
        if key in seen:
            continue
        seen[key] = True
        out.append([u, v, p])
    return verts, out


# ── 4. Prune ────────────────────────────────────────────────────────────────

def _prune(verts, edges):
    """Remove dangling edges iteratively. Returns ``(edges, open_ends)`` where
    the open ends are the positions of the vertices that were degree-1 BEFORE
    pruning (the true loose ends, not the cascade)."""
    deg = [0] * len(verts)
    adj: list = [[] for _ in verts]
    for ei, (u, v, _) in enumerate(edges):
        deg[u] += 1
        deg[v] += 1
        adj[u].append(ei)
        adj[v].append(ei)
    tips = [i for i in range(len(verts)) if deg[i] == 1]
    open_ends = [QPointF(verts[i][0], verts[i][1]) for i in tips]
    alive = [True] * len(edges)
    stack = list(tips)
    while stack:
        vi = stack.pop()
        if deg[vi] != 1:
            continue
        for ei in adj[vi]:
            if not alive[ei]:
                continue
            alive[ei] = False
            u, v, _ = edges[ei]
            other = v if u == vi else u
            deg[vi] -= 1
            deg[other] -= 1
            if deg[other] == 1:
                stack.append(other)
    return [e for e, a in zip(edges, alive) if a], open_ends


# ── 5. Half-edges + faces ───────────────────────────────────────────────────

def _signed_area(pts) -> float:
    s = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return s / 2.0


@dataclass
class Face:
    """A bounded face: its outer cycle, one-level islands, and a fill path."""
    outer: list          # list[Piece] in walk order (oriented)
    islands: list        # list[list[Piece]]
    path: QPainterPath   # OddEven: outer + islands (flattened)
    area: float          # |area| of the outer cycle, mm²


class Arrangement:
    """The planar arrangement of the candidates inside one window."""

    def __init__(self, verts, edges, open_ends):
        self._verts = verts
        self._edges = edges            # [[u, v, piece], ...]
        self._open_ends = open_ends    # [QPointF, ...]
        n = len(edges)
        # half-edge h: origin/target vertices; h = 2*ei (u->v) or 2*ei+1 (v->u)
        self._origin = [0] * (2 * n)
        self._target = [0] * (2 * n)
        outgoing: list = [[] for _ in verts]
        for ei, (u, v, _) in enumerate(edges):
            self._origin[2 * ei], self._target[2 * ei] = u, v
            self._origin[2 * ei + 1], self._target[2 * ei + 1] = v, u
            outgoing[u].append(2 * ei)
            outgoing[v].append(2 * ei + 1)
        angle = [0.0] * (2 * n)
        for h in range(2 * n):
            ox, oy = verts[self._origin[h]]
            tx, ty = verts[self._target[h]]
            angle[h] = math.atan2(ty - oy, tx - ox)
        for lst in outgoing:
            lst.sort(key=lambda h: angle[h])
        # next(h): at the target vertex, the outgoing half-edge that is the
        # cyclic predecessor (clockwise neighbour) of twin(h) -> left face.
        self._next = [0] * (2 * n)
        for h in range(2 * n):
            twin = h ^ 1
            lst = outgoing[self._target[h]]
            k = lst.index(twin)
            self._next[h] = lst[k - 1] if len(lst) > 1 else twin
        # all bounded cycles, enumerated once for island lookup
        self._cycles: list = []      # [(frozenset(half-edges), pts, area)]
        visited = [False] * (2 * n)
        for h0 in range(2 * n):
            if visited[h0]:
                continue
            cyc = self._walk(h0)
            if cyc is None:
                visited[h0] = True
                continue
            for h in cyc:
                visited[h] = True
            pts = [verts[self._origin[h]] for h in cyc]
            area = _signed_area(pts)
            if area > 0:
                self._cycles.append((frozenset(cyc), pts, area, cyc))

    # -- construction ------------------------------------------------------
    @classmethod
    def build(cls, candidates, window: QRectF) -> "Arrangement":
        """Flatten, split, weld, prune and link the *candidates* inside *window*."""
        pieces = _split_all(_flatten(candidates, window), window)
        verts, edges = _weld(pieces, CHAIN_WELD_MM)
        edges, open_ends = _prune(verts, edges)
        return cls(verts, edges, open_ends)

    # -- queries -----------------------------------------------------------
    def _walk(self, h0: int):
        cyc = [h0]
        h = h0
        for _ in range(2 * len(self._edges) + 2):
            h = self._next[h]
            if h == h0:
                return cyc
            cyc.append(h)
        return None

    def _piece_of(self, h: int) -> Piece:
        p = self._edges[h >> 1][2]
        return p if (h & 1) == 0 else p.reversed()

    def _ray_start(self, pt: QPointF):
        """Half-edge of the nearest edge crossed by the +X ray from *pt*, on
        *pt*'s side (left of the half-edge), or None."""
        px, py = pt.x(), pt.y()
        best = None
        for ei, (u, v, _) in enumerate(self._edges):
            ax, ay = self._verts[u]
            bx, by = self._verts[v]
            if (ay > py) == (by > py):
                continue
            x = ax + (py - ay) * (bx - ax) / (by - ay)
            if x > px and (best is None or x - px < best[0]):
                best = (x - px, ei, ax, ay, bx, by)
        if best is None:
            return None
        _, ei, ax, ay, bx, by = best
        cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
        return 2 * ei if cross > 0 else 2 * ei + 1

    def _sample_inside(self, cyc) -> QPointF:
        """A point just inside a positive-area cycle: first edge midpoint pushed
        to its left."""
        h = cyc[0]
        ax, ay = self._verts[self._origin[h]]
        bx, by = self._verts[self._target[h]]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1.0
        return QPointF((ax + bx) / 2 - dy / L * 0.05, (ay + by) / 2 + dx / L * 0.05)

    def _islands(self, outer_set, outer_path: QPainterPath) -> list:
        inside = [(s, pts, area, cyc) for (s, pts, area, cyc) in self._cycles
                  if s != outer_set and outer_path.contains(self._sample_inside(cyc))]
        paths = []
        for _, pts, _, _ in inside:
            p = QPainterPath(QPointF(*pts[0]))
            for x, y in pts[1:]:
                p.lineTo(x, y)
            p.closeSubpath()
            paths.append(p)
        out = []
        for i, (s, pts, area, cyc) in enumerate(inside):
            sample = self._sample_inside(cyc)
            if any(j != i and paths[j].contains(sample) for j in range(len(inside))):
                continue       # nested deeper than one level
            out.append([self._piece_of(h) for h in cyc])
        return out

    def face_at(self, pt: QPointF):
        """The bounded face containing *pt*, or None (open space / leak)."""
        h0 = self._ray_start(pt)
        if h0 is None:
            return None
        cyc = self._walk(h0)
        if cyc is None:
            return None
        pts = [self._verts[self._origin[h]] for h in cyc]
        area = _signed_area(pts)
        if area <= 0 or area < CHAIN_MIN_LOOP_AREA_MM2:
            return None
        outer_path = QPainterPath(QPointF(*pts[0]))
        for x, y in pts[1:]:
            outer_path.lineTo(x, y)
        outer_path.closeSubpath()
        islands = self._islands(frozenset(cyc), outer_path)
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        path.addPath(outer_path)
        for isl in islands:
            sub = QPainterPath(QPointF(isl[0].x0, isl[0].y0))
            for p in isl[1:]:
                sub.lineTo(p.x0, p.y0)
            sub.closeSubpath()
            path.addPath(sub)
        return Face([self._piece_of(h) for h in cyc], islands, path, area)

    def nearest_open_end(self, pt: QPointF):
        """The pruned loose end nearest *pt*, or None when nothing was pruned."""
        if not self._open_ends:
            return None
        return min(self._open_ends,
                   key=lambda e: math.hypot(e.x() - pt.x(), e.y() - pt.y()))

    def nudge(self, pt: QPointF, motion: QPointF) -> QPointF:
        """*pt* pushed ``REGION_FINDER_NUDGE_MM`` off a nearby edge, toward the
        side the cursor came from (opposite *motion*); unchanged when no edge
        is within the nudge distance or the motion is zero."""
        mx, my = motion.x(), motion.y()
        if math.hypot(mx, my) < _EPS:
            return QPointF(pt)
        best = None
        for u, v, _ in self._edges:
            ax, ay = self._verts[u]
            bx, by = self._verts[v]
            d, _t = _seg_point_dist(pt.x(), pt.y(), ax, ay, bx, by)
            if d <= REGION_FINDER_NUDGE_MM and (best is None or d < best[0]):
                best = (d, ax, ay, bx, by)
        if best is None:
            return QPointF(pt)
        _, ax, ay, bx, by = best
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L, dx / L                      # a unit normal of the edge
        side = 1.0 if (nx * -mx + ny * -my) >= 0 else -1.0
        return QPointF(pt.x() + side * nx * REGION_FINDER_NUDGE_MM,
                       pt.y() + side * ny * REGION_FINDER_NUDGE_MM)

