"""Chain closure for Filled Regions (HF3 design section 2, rulings R3/R4/R5).

Pure geometry: shape objects in, ordered loops out. No scene access. The
pieces' endpoints are read from their scene path (``pointAtPercent``), one
rule for every class; direction is resolved at path build (``loop_path``).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath

from .constants import CHAIN_GAP_REPORT_FACTOR, CHAIN_MIN_LOOP_AREA_MM2, CHAIN_WELD_MM

NO_CANDIDATES = "Select closed shapes or curves that form a closed outline"


@dataclass
class ChainResult:
    """``loops``: outer loop first (largest |area|), each an ordered piece
    list; ``reason``: None on success, else the status string (R5)."""
    loops: list = field(default_factory=list)
    reason: str | None = None


def scene_path(piece) -> QPainterPath:
    """The piece's geometry in scene coordinates (parentless pieces: own pos/rotation)."""
    # Lazy: block_definition imports the primitive classes (and, from Task 2 on,
    # filled_region, which imports this module) -- a top-level import would cycle.
    from .block_definition import _local_path
    return piece.mapToScene(_local_path(piece))


def _is_closed(piece) -> bool:
    fn = getattr(piece, "is_closed", None)
    return True if fn is None else bool(fn())      # Rect/Circle/Ellipse/Polygon: closed


def _ends(piece) -> tuple[QPointF, QPointF]:
    p = scene_path(piece)
    return p.pointAtPercent(0.0), p.pointAtPercent(1.0)


def _dist(a: QPointF, b: QPointF) -> float:
    return ((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2) ** 0.5


def loop_path(loop: list) -> QPainterPath:
    """One closed subpath from *loop*'s pieces in chain order; a piece whose
    start does not meet the previous end is reversed (``toReversed``)."""
    out = QPainterPath()
    if not loop:
        return out
    if len(loop) == 1 and _is_closed(loop[0]):
        out.addPath(scene_path(loop[0]))
        return out
    cur = scene_path(loop[0])
    if len(loop) > 1:
        nxt0, nxt1 = _ends(loop[1])
        # orient the first piece so its END meets the second piece
        if min(_dist(cur.pointAtPercent(0.0), nxt0), _dist(cur.pointAtPercent(0.0), nxt1)) < \
           min(_dist(cur.pointAtPercent(1.0), nxt0), _dist(cur.pointAtPercent(1.0), nxt1)):
            cur = cur.toReversed()
    out.addPath(cur)
    for piece in loop[1:]:
        p = scene_path(piece)
        tail = out.currentPosition()
        if _dist(p.pointAtPercent(0.0), tail) > _dist(p.pointAtPercent(1.0), tail):
            p = p.toReversed()
        out.connectPath(p)
    out.closeSubpath()
    return out


def loop_area(path: QPainterPath) -> float:
    """|area| of *path*'s fill polygon (shoelace)."""
    poly = path.toFillPolygon()
    n = poly.size()
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        s += a.x() * b.y() - b.x() * a.y()
    return abs(s) / 2.0


def close_loops(pieces, tol: float = CHAIN_WELD_MM) -> ChainResult:
    """Greedy head/tail chaining of the open pieces into closed loops; every
    closed piece is a loop by itself. Any leftover open end fails the whole
    call (no partial region).
    """
    pieces = list(pieces)
    if not pieces:
        return ChainResult(reason=NO_CANDIDATES)
    loops: list[list] = [[p] for p in pieces if _is_closed(p)]
    open_pieces = [p for p in pieces if not _is_closed(p)]
    ends = {id(p): _ends(p) for p in open_pieces}
    unused = list(open_pieces)
    stuck: list[list] = []
    while unused:
        first = unused.pop(0)
        chain = [first]
        head, tail = ends[id(first)]
        grown = True
        while grown:
            grown = False
            for p in list(unused):
                a, b = ends[id(p)]
                if _dist(tail, a) <= tol:
                    chain.append(p); tail = b; unused.remove(p); grown = True; break
                if _dist(tail, b) <= tol:
                    chain.append(p); tail = a; unused.remove(p); grown = True; break
                if _dist(head, b) <= tol:
                    chain.insert(0, p); head = a; unused.remove(p); grown = True; break
                if _dist(head, a) <= tol:
                    chain.insert(0, p); head = b; unused.remove(p); grown = True; break
        if _dist(head, tail) <= tol and loop_area(loop_path(chain)) > CHAIN_MIN_LOOP_AREA_MM2:
            loops.append(chain)
        else:
            stuck.append((chain, head, tail))     # head/tail tracked live (orientation-safe)
    if stuck:
        # (point, owning single-piece chain index or None): a lone piece's own two
        # ends are not a "gap" (its length), so those pairs are skipped.
        free = [(pt, k if len(ch) == 1 else None)
                for k, (ch, h, t) in enumerate(stuck) for pt in (h, t)]
        best = None
        for i in range(len(free)):
            for j in range(i + 1, len(free)):
                if free[i][1] is not None and free[i][1] == free[j][1]:
                    continue
                d = _dist(free[i][0], free[j][0])
                if d > tol and (best is None or d < best[0]):
                    best = (d, free[i][0])
        if best is not None and best[0] < CHAIN_GAP_REPORT_FACTOR * tol:
            d, at = best
            return ChainResult(reason=f"Not enclosed -- gap of {d:.1f} mm at "
                                      f"({at.x():.0f}, {at.y():.0f})")
        n = sum(len(ch) for ch, _h, _t in stuck)
        return ChainResult(reason=f"Not enclosed -- {n} curve(s) have an open end")
    loops.sort(key=lambda lp: loop_area(loop_path(lp)), reverse=True)
    return ChainResult(loops=loops)
