"""Linetype expansion renderer (linetypes.md LT3, H3-c; concept LD-A / LD3).

One renderer for raw primitives (Block Editor) and compiled block ops (plan
canvas, viewports, PDF). Expansion is explicit geometry in the pieces' own
frame — never a QPen dash pattern (width-multiple units collapse). Continuous
strokes never reach this module's expansion (``paint_stroke`` returns False and
the caller draws its unchanged plain stroke).
"""
from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPainterPath, QPen

from . import hatch_render as _hr
from . import paper_display as _pd
from . import path_walk as pw
from . import stroke_style as _ss
from .constants import (LINETYPE_AXIS_TOL_MM, LINETYPE_CACHE_MAX,
                        LINETYPE_DEF_CACHE_MAX, LINETYPE_DOT_MM, LINETYPE_LOD_MIN_PERIOD_PX,
                        LINETYPE_MAX_PERIODS, LINETYPE_WINDOW_MIN_PERIODS,
                        UNDERLAY_MM_TO_PX_HINT)


def axis_role(p1, p2, length: float):
    """LT3-3 role of one unit Line (origin-relative points).

    Returns:
        ``("dash", start, length)`` (clamped to ``[0, length]``),
        ``("dot", x)`` (a zero-length axis Line inside the frame), or None
        (off-axis, wholly outside, or a clamped sliver -- never a dot).
    """
    (x1, y1), (x2, y2) = p1, p2
    tol = LINETYPE_AXIS_TOL_MM
    if abs(y1) > tol or abs(y2) > tol:
        return None
    a, b = sorted((x1, x2))
    if b - a <= tol:
        if -tol <= a <= length + tol:
            return ("dot", round(min(max(a, 0.0), length), 9))
        return None
    a, b = max(a, 0.0), min(b, length)
    if b - a <= tol:
        return None
    return ("dash", round(a, 9), round(b - a, 9))


@dataclass(frozen=True)
class LinetypeDef:
    """A repeat block read per LT3-3 (definition-local mm)."""
    block_id: str
    version: int
    period: float
    dashes: tuple          # ((start, length), ...)
    dots: tuple            # (pos, ...)
    dash_weight: str | None
    size: str              # "drafting" | "model"
    screen: str = "scale"  # "fixed" | "scale" (LTS-1)

    # (id, version, origin) -> (primitives list, LinetypeDef | None); LRU,
    # LINETYPE_DEF_CACHE_MAX. Origin is in the key: the origin setter moves
    # the unit without a bump. The held primitives list is a hit only when it
    # *is* the definition's list (two copies sharing id + version read apart);
    # holding the ref keeps its identity from being recycled (the
    # ``hatch_render._lattice`` idiom).
    _CACHE = OrderedDict()

    @classmethod
    def from_block(cls, defn) -> "LinetypeDef | None":
        """Read *defn*'s unit; None when it is not a well-formed linetype."""
        rep = getattr(defn, "repeat", None)
        if not rep:
            return None
        ox, oy = defn.origin
        key = (defn.id, defn.version, (ox, oy))
        hit = cls._CACHE.get(key)
        if hit is not None and hit[0] is defn.primitives:
            cls._CACHE.move_to_end(key)
            return hit[1]
        length = float(rep["length"])
        dashes, dots, weights = [], [], []
        for prim in defn.primitives:
            if prim.get("type") != "draw_line":
                continue
            (x1, y1), (x2, y2) = prim["pt1"], prim["pt2"]
            role = axis_role((x1 - ox, y1 - oy), (x2 - ox, y2 - oy), length)
            if role is None:
                continue
            if role[0] == "dot":
                dots.append(role[1])
                continue
            dashes.append((role[1], role[2]))
            w = (prim.get("style") or {}).get("weight")
            if _ss.is_named_weight(w):
                weights.append(w)
        if not (0.0 < length < math.inf) or (not dashes and not dots):
            res = None
        else:
            dash_weight = None
            if weights:
                dash_weight = max(weights, key=_pd.resolve_line_weight_mm)
            res = cls(defn.id, defn.version, length, tuple(sorted(dashes)),
                      tuple(sorted(dots)), dash_weight, rep["size"],
                      rep.get("screen", "scale"))
        cls._CACHE[key] = (defn.primitives, res)
        cls._CACHE.move_to_end(key)
        while len(cls._CACHE) > LINETYPE_DEF_CACHE_MAX:
            cls._CACHE.popitem(last=False)
        return res


_EXPAND: OrderedDict = OrderedDict()


def view_window(painter):
    """The painter's visible area (painter coords) as a snapped key, or None.

    Snapped outward to a power-of-two grid whose cell is half the next 2^n
    at or above the view's larger side, plus one cell of margin, so a pan
    inside a cell keeps one expansion-cache key (LTS-8: pans stay cached)
    while the window stays ~2-3x the view, not 4-6x (perf ruling 2026-10-06).
    """
    area = _hr._visible_area(painter, QRectF(-1e15, -1e15, 2e15, 2e15))
    if area.isEmpty() or not _hr._finite_rect(area):
        return None
    cell = 0.5 * 2.0 ** math.ceil(math.log2(max(area.width(), area.height(), 1e-9)))
    return ((math.floor(area.left() / cell) - 1) * cell,
            (math.floor(area.top() / cell) - 1) * cell,
            (math.ceil(area.right() / cell) + 1) * cell,
            (math.ceil(area.bottom() / cell) + 1) * cell)


def visible_spans(p, window, min_span: float) -> list:
    """Arc-length spans [(s0, s1)] of canonical piece *p* inside *window*.

    *window* = (x0, y0, x1, y1). A Seg clips exactly (Liang-Barsky); other
    pieces bisect in arc length, dropping halves whose control box misses
    the window, down to *min_span*. Spans are merged and sorted.
    """
    x0, y0, x1, y1 = window
    L = pw.length(p)
    if isinstance(p, pw.Seg):
        dx, dy = p.x1 - p.x0, p.y1 - p.y0
        t0, t1 = 0.0, 1.0
        for q, r in ((-dx, p.x0 - x0), (dx, x1 - p.x0),
                     (-dy, p.y0 - y0), (dy, y1 - p.y0)):
            if abs(q) < 1e-12:
                if r < 0:
                    return []
                continue
            t = r / q
            if q < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return []
        return [(t0 * L, t1 * L)]
    out = []

    def _rec(a, b):
        r = pw.to_path((pw.split(p, a, b),)).controlPointRect()
        if r.right() < x0 or r.left() > x1 or r.bottom() < y0 or r.top() > y1:
            return
        if b - a <= min_span:
            out.append((a, b))
            return
        m = 0.5 * (a + b)
        _rec(a, m)
        _rec(m, b)

    _rec(0.0, L)
    merged = []
    for a, b in out:
        if merged and a <= merged[-1][1] + 1e-9:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def expand(pieces, lt: LinetypeDef, factor: float, anchor: tuple,
           window=None):
    """``(dash_path, dot_path)`` for *pieces* in *lt* scaled by *factor*.

    Cached on (pieces, the *lt* reading itself, factor, anchor, window) --
    keyed on the frozen reading's value, so a re-read that differs (e.g. a
    moved origin without a version bump) never hits a stale expansion.
    Returns the same tuple object on a hit: the paths are shared cached
    objects and must be treated as read-only. *window* is a ``view_window``
    key: pieces longer than ``LINETYPE_WINDOW_MIN_PERIODS`` periods expand
    only inside it (LTS-8); when no piece qualifies it leaves the cache key.
    """
    if not period_ok(lt, factor):
        return QPainterPath(), QPainterPath()   # never walk a bad period
    period = lt.period * factor
    if window is not None and not any(
            pw.length(q) / period > LINETYPE_WINDOW_MIN_PERIODS for q in pieces):
        window = None                         # nothing windowed: one key per pan
    key = (tuple(pieces), lt, round(factor, 9),
           (round(anchor[0], 6), round(anchor[1], 6)), window)
    hit = _EXPAND.get(key)
    if hit is not None:
        _EXPAND.move_to_end(key)
        return hit
    dashes = [(s * factor, n * factor) for s, n in lt.dashes]
    dots = [d * factor for d in lt.dots]
    dash_path, dot_path = QPainterPath(), QPainterPath()
    # Canonical pieces, arcs / ellipse arcs broken at 0° (rhythm restarts there).
    for p in (q for raw in pieces for q in pw.split_at_zero(raw)):
        L = pw.length(p)
        if L <= 1e-9:
            continue
        if window is not None and L / period > LINETYPE_WINDOW_MIN_PERIODS:
            spans = visible_spans(p, window,
                                  max(window[2] - window[0], window[3] - window[1]))
        else:
            spans = ((0.0, L),)
        ph = pw.phase0(p, anchor)
        seg = isinstance(p, pw.Seg)
        k_done = None                         # never re-draw a unit across spans
        for s_lo, s_hi in spans:
            if (s_hi - s_lo) / period > LINETYPE_MAX_PERIODS:
                pw.append(dash_path, p if (s_lo, s_hi) == (0.0, L)
                          else pw.split(p, s_lo, s_hi))   # safety cap: continuous
                continue
            k = math.floor((ph + s_lo) / period)
            if k_done is not None:
                k = max(k, k_done)
            if seg:
                k = _walk_seg(p, L, ph, period, k, s_hi, dashes, dots,
                              dash_path, dot_path)
                k_done = k
                continue
            while k * period - ph < s_hi:
                base = k * period - ph                   # s of this unit's start
                for st, ln in dashes:
                    a, b = max(base + st, 0.0), min(base + st + ln, L)
                    if b - a > 1e-9:
                        pw.append(dash_path, pw.split(p, a, b))
                for d in dots:
                    s = base + d
                    if -1e-9 <= s <= L + 1e-9:
                        q = pw.point_at(p, min(max(s, 0.0), L))
                        dot_path.moveTo(q)
                        dot_path.lineTo(q.x() + LINETYPE_DOT_MM, q.y())
                k += 1
            k_done = k
    res = (dash_path, dot_path)
    _EXPAND[key] = res
    while len(_EXPAND) > LINETYPE_CACHE_MAX:
        _EXPAND.popitem(last=False)
    return res


def _walk_seg(p, L, ph, period, k, s_hi, dashes, dots, dash_path, dot_path):
    """The unit walk of ``expand`` for a straight piece (LTS-8 perf).

    Same dashes / dots as the generic walk (``pw.split`` / ``pw.point_at`` on
    a Seg are linear interpolation), computed inline -- no per-dash piece
    objects or type dispatch. Returns the next unit index.
    """
    x0, y0 = p.x0, p.y0
    dx, dy = p.x1 - x0, p.y1 - y0
    move, line = dash_path.moveTo, dash_path.lineTo
    while k * period - ph < s_hi:
        base = k * period - ph                   # s of this unit's start
        for st, ln in dashes:
            a, b = max(base + st, 0.0), min(base + st + ln, L)
            if b - a > 1e-9:
                fa, fb = a / L, b / L
                move(x0 + dx * fa, y0 + dy * fa)
                line(x0 + dx * fb, y0 + dy * fb)
        for d in dots:
            s = base + d
            if -1e-9 <= s <= L + 1e-9:
                f = min(max(s, 0.0), L) / L
                qx, qy = x0 + dx * f, y0 + dy * f
                dot_path.moveTo(qx, qy)
                dot_path.lineTo(qx + LINETYPE_DOT_MM, qy)
        k += 1
    return k


def paint_stroke(painter, pieces, lt, pen: QPen, *, factor: float,
                 anchor: tuple, fixed: bool = False) -> bool:
    """Draw *pieces* dashed in *lt* with *pen* (LT3 one paint entry).

    Returns False -- nothing drawn -- when there is no linetype, no pieces, a
    non-positive / non-finite scaled period, or (screen only, ``_lod_ok``) the on-screen period is below
    ``LINETYPE_LOD_MIN_PERIOD_PX``; the caller then draws its unchanged plain
    stroke. Paper passes always expand. *fixed* is True for a Fixed linetype
    on a model canvas (``fixed_on_canvas``): a stroke shorter than one period
    then also returns False, so it draws solid (LTS-7).
    """
    if lt is None or not pieces or not period_ok(lt, factor):
        return False
    if not _lod_ok(painter, lt.period * factor):
        return False
    win = None
    if fixed:
        n = periods_on(pieces, lt, factor)
        if n < 1.0:
            return False                  # LTS-7: shorter than one period -> solid
        if n > LINETYPE_WINDOW_MIN_PERIODS:
            win = view_window(painter)    # LTS-8 delta 1: expand near the view only
    dash, dot = expand(pieces, lt, factor, anchor, window=win)
    painter.save()
    try:
        draw_expansion(painter, dash, dot, QPen(pen))
    finally:
        painter.restore()
    return True


def draw_expansion(painter, dash: QPainterPath, dot: QPainterPath,
                   pen: QPen) -> None:
    """Stroke an ``expand`` result: dashes flat-capped, dots round-capped.

    The low-level half of ``paint_stroke`` for callers that already decided
    period / LOD and hold the expansion (``BlockInstance.paint``). Leaves
    the painter's pen and brush changed -- the caller brackets it with
    ``save`` / ``restore`` -- and sets *pen*'s cap style (pass a copy).
    """
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(dash)
    if not dot.isEmpty():
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawPath(dot)


def period_ok(lt: LinetypeDef, factor: float) -> bool:
    """True when the scaled period is positive and finite (else no dashes:
    a zero / negative / NaN / inf length factor would not terminate or
    would draw nothing)."""
    period = lt.period * factor
    return period > 0.0 and math.isfinite(period)


def periods_on(pieces, lt, factor: float) -> float:
    """How many scaled periods *pieces* span (LTS-7 / LTS-8 tests)."""
    return pw.total_length(pieces) / (lt.period * factor)


_FIXED_ROLES = ("plan", "block_editor")      # model canvases (LTS-2)


def fixed_on_canvas(lt, *, paper_scale, role) -> bool:
    """True when *lt* holds a constant screen length here (LTS-1 / LTS-2).

    A Fixed linetype on a model canvas -- plan (detail views share its
    scene) or the Block Editor. Never on a paper pass, a sheet or a viewport:
    paper / PDF stay true mm.
    """
    return (getattr(lt, "screen", "scale") == "fixed" and not paper_scale
            and role in _FIXED_ROLES and not _pd.paper_pass_active())


def length_factor(lt, *, paper_scale, role, drawing_scale,
                  device_scale=None) -> float:
    """Definition mm -> painter units for *lt* (LT3-5, LTS-3).

    A Fixed linetype on a model canvas (``fixed_on_canvas``) -> its printed
    mm x ``UNDERLAY_MM_TO_PX_HINT`` px, divided by *device_scale* (device px
    per painter unit -- the caller passes this paint's). Otherwise: Model
    size -> 1; a paper pass (*paper_scale* set) -> 1 / scale; the plan canvas
    (*role* ``"plan"``) -> the drawing scale; anything else (Block Editor, no
    scene) -> 1 (real size).
    """
    if fixed_on_canvas(lt, paper_scale=paper_scale, role=role):
        # LTS-3: printed mm x the D-L14 mm->px hint, back into painter units.
        printed = 1.0 if lt.size != "model" else 1.0 / (drawing_scale or 1.0)
        return printed * UNDERLAY_MM_TO_PX_HINT / max(device_scale or 0.0, 1e-12)
    if lt.size == "model":
        return 1.0
    if paper_scale:
        return 1.0 / paper_scale
    if role == "plan":
        return float(drawing_scale) if drawing_scale is not None else 1.0
    return 1.0


def _lod_ok(painter, period: float) -> bool:
    """Screen-only LOD (D-L21): paper/PDF passes always expand."""
    if _pd.paper_pass_active():
        return True
    return lod_ok_at(period, _hr._device_scale(painter))


def lod_ok_at(period: float, device_scale: float) -> bool:
    """The screen LOD test (D-L21) for a period at a known device scale
    (device px per painter unit); callers handle the paper-pass bypass."""
    return period * device_scale >= LINETYPE_LOD_MIN_PERIOD_PX


def mid_point(pieces) -> QPointF | None:
    """Point at half the total length (missing-linetype badge anchor)."""
    return pw.point_at_total(pieces, pw.total_length(pieces) / 2.0) if pieces else None


# Missing-glyph geometry (mockup option A) in mockup units: authored on a
# 12-unit grid, scaled to LINETYPE_BADGE_PX. The glyph's farthest point from
# its anchor is _BADGE_REACH units (triangle apex / base corners); the bounds
# pad adds _BADGE_AA_PX of antialiasing fringe. One home for both.
_BADGE_GRID = 12.0
_BADGE_REACH = 7.0
_BADGE_AA_PX = 1.0


def _badge_unit() -> float:
    """Device px per mockup unit at the current ``LINETYPE_BADGE_PX``."""
    from . import constants
    return constants.LINETYPE_BADGE_PX / _BADGE_GRID


def badge_pad_px() -> float:
    """Device-px half-extent the missing glyph needs around its anchor: the
    bounds pad of an item that may draw it (the glyph's reach + AA fringe)."""
    return _BADGE_REACH * _badge_unit() + _BADGE_AA_PX


def sync_missing_tooltip(item, missing_id) -> None:
    """Name *missing_id* in *item*'s own tooltip (LT3-10); restore the
    previous tooltip once it resolves again. Only writes on a change."""
    cur = getattr(item, "_lt_tip_id", None)
    if cur == missing_id:
        return
    if missing_id:
        if cur is None:
            item._lt_tip_prev = item.toolTip()
        item.setToolTip(f"Missing linetype: {missing_id} — drawn Continuous")
    else:
        item.setToolTip(getattr(item, "_lt_tip_prev", ""))
    item._lt_tip_id = missing_id


def paint_missing_badge(painter, at: QPointF) -> None:
    """Canvas-only missing-linetype glyph at item point *at* (LT3-10).

    Approved mockup option A (2026-10-04): a filled amber (theme ``warn``)
    triangle with a white '!' drawn as geometry (no font dependency), in
    device space at a fixed ``LINETYPE_BADGE_PX`` size. Callers skip it
    during a paper pass (``paper_display.paper_pass_active``).
    """
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QColor, QPainter, QPolygonF
    from . import theme
    c = painter.transform().map(at)
    k = _badge_unit()                            # mockup geometry: 12-unit grid
    r = _BADGE_REACH * k
    painter.save()
    painter.resetTransform()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(theme.detect().warn))
    painter.drawPolygon(QPolygonF([QPointF(c.x(), c.y() - r),
                                   QPointF(c.x() + r, c.y() + 5 * k),
                                   QPointF(c.x() - r, c.y() + 5 * k)]))
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(QRectF(c.x() - 0.9 * k, c.y() - 2.6 * k,
                                   1.8 * k, 4.6 * k), 0.6 * k, 0.6 * k)
    painter.drawEllipse(QPointF(c.x(), c.y() + 3.7 * k), 1.0 * k, 1.0 * k)
    painter.restore()
