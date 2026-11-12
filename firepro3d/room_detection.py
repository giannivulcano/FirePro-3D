"""Room detection on wall bodies (room-detection rework design §1).

The HF4 region finder is the one closed-region engine: every candidate wall
contributes the edges of its joined plan body (``outline_geometry().body``:
mitres, wedges, tee copes) as tagged pieces; ``Arrangement.from_pieces``
splits, welds, prunes and links them; :func:`detect` turns the face around a
click into an outer ring plus clean hole rings. Openings never cut a body, so a
door never opens a room (Q8).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPainterPath, QPolygonF

from .constants import (REGION_FINDER_ISLAND_SAMPLE_MM, ROOM_DETECT_WINDOW_PAD_MM,
                        ROOM_SAME_FACE_AREA_TOL, ROOM_SAMPLE_INSET_MM)
from .floor_cut import signed_area
from .region_finder import Arrangement, Piece, Tag
from .wall_outline import cluster_union

_ODD_EVEN = Qt.FillRule.OddEvenFill

#: Status-bar text per refusal reason (design §3 step 1).
REFUSAL_TEXT = {
    "in_wall": "Click inside a room, not on a wall",
    "open": "Not enclosed \u2014 no closed wall boundary at the click point",
}


@dataclass
class RoomFace:
    """A placeable room: outer ring and hole rings (scene coords), net area,
    and the click it was detected from (its interior sample point)."""
    outer: list
    holes: list
    area_mm2: float
    sample: QPointF


@dataclass
class Refusal:
    """No room at the click. ``reason`` is ``"in_wall"`` or ``"open"``;
    ``open_end`` marks the nearest loose wall end of an open click, or None."""
    reason: str
    open_end: QPointF | None = None


# ── Ring helpers ───────────────────────────────────────────────────────────

def ring_area(ring) -> float:
    """Unsigned shoelace area of a ring of QPointF (no closing duplicate)."""
    return abs(signed_area(ring)) if len(ring) >= 3 else 0.0


def ring_contains(ring, pt: QPointF) -> bool:
    """True when *pt* lies inside the polygon *ring* (odd-even)."""
    return len(ring) >= 3 and QPolygonF(ring).containsPoint(pt, _ODD_EVEN)


def edge_sample(ring, inside) -> QPointF | None:
    """The first edge midpoint of *ring* pushed ``ROOM_SAMPLE_INSET_MM`` to the
    side where ``inside(q)`` holds; None when no edge has such a side."""
    n = len(ring)
    k = ROOM_SAMPLE_INSET_MM
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        dx, dy = b.x() - a.x(), b.y() - a.y()
        length = math.hypot(dx, dy)
        if length < 1e-9:
            continue
        mx, my = (a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0
        for s in (1.0, -1.0):
            q = QPointF(mx - s * dy / length * k, my + s * dx / length * k)
            if inside(q):
                return q
    return None


def ring_sample(ring) -> QPointF | None:
    """A point inside *ring*: its vertex mean when inside, else :func:`edge_sample`."""
    n = len(ring)
    if n < 3:
        return None
    mean = QPointF(sum(p.x() for p in ring) / n, sum(p.y() for p in ring) / n)
    if ring_contains(ring, mean):
        return mean
    return edge_sample(ring, lambda q: ring_contains(ring, q))


def same_ring(a, b) -> bool:
    """Same-face test (design §3.2): areas within ``ROOM_SAME_FACE_AREA_TOL``
    of *b*'s and each ring contains the other's sample point."""
    area_a, area_b = ring_area(a), ring_area(b)
    if area_b <= 0.0 or abs(area_a - area_b) > ROOM_SAME_FACE_AREA_TOL * area_b:
        return False
    sa, sb = ring_sample(a), ring_sample(b)
    return (sa is not None and sb is not None
            and ring_contains(b, sa) and ring_contains(a, sb))


def face_contains(face: RoomFace, pt: QPointF) -> bool:
    """True when *pt* is inside the face's outer ring and in none of its holes."""
    return ring_contains(face.outer, pt) and not any(ring_contains(h, pt) for h in face.holes)


def room_path_of(face: RoomFace) -> QPainterPath:
    """Odd-even path of a detected face: the outer ring plus every hole (§4 preview)."""
    path = QPainterPath()
    path.setFillRule(_ODD_EVEN)
    for ring in [face.outer] + list(face.holes):
        path.addPolygon(QPolygonF(ring))
        path.closeSubpath()
    return path


# ── Arrangement over wall bodies ───────────────────────────────────────────

def wall_pieces(walls) -> tuple:
    """``(pieces, window)``: tagged edges of every wall's joined plan body, and
    the bodies' united bounds padded by ``ROOM_DETECT_WINDOW_PAD_MM`` (§1.3)."""
    pieces: list = []
    bounds = QRectF()
    for w in walls:
        body = w.outline_geometry().body
        bounds = bounds.united(body.boundingRect())
        n = body.count()
        for i in range(n):
            a, b = body.at(i), body.at((i + 1) % n)
            if math.hypot(b.x() - a.x(), b.y() - a.y()) > 1e-9:
                pieces.append(Piece(a.x(), a.y(), b.x(), b.y(),
                                    Tag(w, i, "line", None, 0.0, 1.0)))
    pad = ROOM_DETECT_WINDOW_PAD_MM
    return pieces, bounds.adjusted(-pad, -pad, pad, pad)


def build_arrangement(walls) -> Arrangement | None:
    """The planar arrangement of *walls*' bodies; None with no walls."""
    if not walls:
        return None
    pieces, window = wall_pieces(walls)
    return Arrangement.from_pieces(pieces, window)


def nearest_open_end(walls, arr, pt: QPointF) -> QPointF | None:
    """The loose wall end nearest *pt* (Gap 1 / D-R6): the arrangement's pruned
    end, else the midpoint of the nearest free-end cap (``WallOutline.caps``)
    -- wall bodies are closed loops, so the prune alone never records one
    (plan probe P4-1)."""
    if arr is not None:
        end = arr.nearest_open_end(pt)
        if end is not None:
            return end
    best = None
    for w in walls:
        for a, b in w.outline_geometry().caps:
            m = QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)
            d = math.hypot(m.x() - pt.x(), m.y() - pt.y())
            if best is None or d < best[0]:
                best = (d, m)
    return None if best is None else best[1]


def _in_body(walls, pt: QPointF) -> bool:
    return any(w.outline_geometry().body.containsPoint(pt, _ODD_EVEN) for w in walls)


def _face_sample(face) -> QPointF:
    """A point just inside a region-finder face: its first outer piece's
    midpoint pushed ``REGION_FINDER_ISLAND_SAMPLE_MM`` to the left (face side)."""
    p = face.outer[0]
    dx, dy = p.x1 - p.x0, p.y1 - p.y0
    length = math.hypot(dx, dy) or 1.0
    k = REGION_FINDER_ISLAND_SAMPLE_MM
    return QPointF((p.x0 + p.x1) / 2.0 - dy / length * k,
                   (p.y0 + p.y1) / 2.0 + dx / length * k)


def _hole_rings(face) -> list:
    """One clean ring per island cluster (design §1.4 step 5): island cycles
    sharing a wall join one cluster (union-find on ``tag.item``); the cluster's
    bodies are unioned and the outer ring of each connected part is a hole."""
    islands = face.islands
    if not islands:
        return []
    parent = list(range(len(islands)))

    def find(k: int) -> int:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    owner: dict = {}
    for i, cyc in enumerate(islands):
        for p in cyc:
            key = id(p.tag.item)
            if key in owner:
                ra, rb = find(owner[key]), find(i)
                if ra != rb:
                    parent[rb] = ra
            else:
                owner[key] = i
    clusters: dict = {}
    for i, cyc in enumerate(islands):
        members = clusters.setdefault(find(i), {})
        for p in cyc:
            members[id(p.tag.item)] = p.tag.item
    rings: list = []
    for members in clusters.values():
        union = cluster_union([w.outline_geometry().body for w in members.values()])
        cands = []
        for poly in union.toSubpathPolygons():
            pts = [QPointF(poly.at(k)) for k in range(poly.count())]
            if len(pts) > 1 and pts[0] == pts[-1]:
                pts = pts[:-1]
            if len(pts) >= 3:
                cands.append((ring_area(pts), pts))
        cands.sort(key=lambda c: -c[0])
        kept: list = []
        for _a, pts in cands:
            s = ring_sample(pts)
            if s is not None and any(ring_contains(k, s) for k in kept):
                continue                # an inner ring of the union (the island's own room)
            kept.append(pts)
        rings.extend(kept)
    return rings


def detect(walls, click: QPointF, arr: Arrangement | None = None):
    """The room a Room-mode click at *click* would create (design §1.4).

    Args:
        walls: Candidate walls (``Model_Space._room_walls``).
        click: Scene point.
        arr: A prebuilt ``build_arrangement(walls)`` (the Room-mode cache), or None.

    Returns:
        :class:`RoomFace`, or :class:`Refusal` ``("in_wall")`` / ``("open", end)``.
    """
    if _in_body(walls, click):
        return Refusal("in_wall")
    if arr is None:
        arr = build_arrangement(walls)
    if arr is None:
        return Refusal("open", None)
    face = arr.face_at(click)
    if face is None:
        return Refusal("open", nearest_open_end(walls, arr, click))
    if _in_body(walls, _face_sample(face)):
        return Refusal("in_wall")       # a wall-body fragment (overlap sliver)
    outer = [QPointF(p.x0, p.y0) for p in face.outer]
    holes = _hole_rings(face)
    area = ring_area(outer) - sum(ring_area(h) for h in holes)
    return RoomFace(outer, holes, area, QPointF(click))
