"""Smart Dimension graphics -- parametric-constraint-system.md D60-D66 (CS4b).

Pure viewport-px layout of a linear dim (witness lines, dim line,
terminators, value label), its pick test and the signed-offset math, plus the
terminator: the End Types end named by the ``dimension/terminator`` setting
(default ``Arrow``) drawn at ``DIM_TERM_PX_PER_MM``, else a built-in 3:1
triangle (D61). The angular selection readouts' arc arrows draw through
:func:`paint_terminator` too.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, replace

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPainterPath, QPen

from .constants import (DIM_AUTO_OFFSET_PX, DIM_FIT_PAD_PX, DIM_SHORT_LEADER_PX,
                        DIM_TERM_FALLBACK_MM, DIM_TERM_PX_PER_MM,
                        DIM_TERMINATOR_DEFAULT, DIM_TERMINATOR_KEY,
                        DIM_TEXT_GAP_PX, DIM_WITNESS_EXT_PX, DIM_WITNESS_GAP_PX)
from .readout_paint import (ReadoutLayout, _half_extent, _text_size, _to_vp,
                            hit_layout, label_path, readable_deg)
from .theme import M

_EPS = 1e-12


def unit_normal(a, b):
    """Scene unit normal ``n = (-dy, dx) / |d|`` of a->b (D62), or None when
    a == b."""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    L = math.hypot(dx, dy)
    if L < _EPS:
        return None
    return (-dy / L, dx / L)


def signed_offset(a, b, p) -> float:
    """Signed scene distance of *p* from the line a->b along :func:`unit_normal`."""
    n = unit_normal(a, b)
    if n is None:
        return 0.0
    return (p.x() - a.x()) * n[0] + (p.y() - a.y()) * n[1]


def offset_of(label):
    """The stored mm offset of a dim's ``label`` record, or None = auto (D62)."""
    if isinstance(label, dict):
        v = label.get("offset")
        if (isinstance(v, (int, float)) and not isinstance(v, bool)
                and math.isfinite(v)):
            return float(v)
    return None


def with_offset(label, off) -> dict:
    """*label* (any other keys kept) with ``offset`` = *off* mm."""
    out = dict(label) if isinstance(label, dict) else {}
    out["offset"] = float(off)
    return out


@dataclass
class DimGraphic:
    """One laid-out dim in viewport px.

    Attributes:
        a, b: Dim-line ends (at the measured points' offset).
        witness: ``[(start, end)]`` witness segments (none at offset 0).
        segments: Dim-line segments to stroke (the stubs too when outside).
        terms: ``[(tip, (ux, uy))]`` -- terminator tip + outward unit vector.
        label: The value text layout.
        inside: Terminators + text fit between the witness lines (D66).
    """
    a: QPointF
    b: QPointF
    witness: list
    segments: list
    terms: list
    label: ReadoutLayout
    inside: bool


def layout_dim(view, a, b, offset, text, away=None, tlen=7.5) -> DimGraphic:
    """Lay out a linear dim of scene points *a*, *b* in *view*'s viewport px.

    Args:
        view: The painting view (its viewport transform maps scene -> px).
        a, b: The measured scene points (``ConstraintController.dim_ends``).
        offset: Stored signed mm offset (D62), or None = auto.
        text: The value text.
        away: Auto offset only -- go to the side away from this scene point.
        tlen: Terminator length in px (:func:`terminator_length_px`).
    """
    A0, B0 = _to_vp(view, a), _to_vp(view, b)
    w, h = _text_size(text)
    n = unit_normal(a, b)
    if n is None:
        lay = ReadoutLayout(text, A0, 0.0, w, h, False)
        return DimGraphic(A0, B0, [], [], [], lay, False)
    tip = _to_vp(view, QPointF(a.x() + n[0], a.y() + n[1]))
    vx, vy = tip.x() - A0.x(), tip.y() - A0.y()
    s = max(math.hypot(vx, vy), _EPS)                      # px per scene unit
    vx, vy = vx / s, vy / s
    if offset is None:                                     # D62 auto
        side = 0.0
        if away is not None:
            m = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
            dot = (away.x() - m.x()) * n[0] + (away.y() - m.y()) * n[1]
            if abs(dot) > 1e-9:
                side = -1.0 if dot > 0 else 1.0
        if side == 0.0:                                    # screen-up / screen-left
            side = -1.0 if (vy > 0 or (abs(vy) < 1e-9 and vx > 0)) else 1.0
        d_px = side * DIM_AUTO_OFFSET_PX
    else:
        d_px = offset * s
    A = QPointF(A0.x() + vx * d_px, A0.y() + vy * d_px)
    B = QPointF(B0.x() + vx * d_px, B0.y() + vy * d_px)
    sgn = 1.0 if d_px >= 0 else -1.0
    ox, oy = vx * sgn, vy * sgn                            # away from the geometry
    witness = []
    # D66: no witness lines at offset 0 -- nor whenever the dim line sits
    # within the witness gap, where a witness would be shorter than its gap.
    if abs(d_px) > DIM_WITNESS_GAP_PX:
        for P0 in (A0, B0):
            witness.append((
                QPointF(P0.x() + ox * DIM_WITNESS_GAP_PX, P0.y() + oy * DIM_WITNESS_GAP_PX),
                QPointF(P0.x() + vx * d_px + ox * DIM_WITNESS_EXT_PX,
                        P0.y() + vy * d_px + oy * DIM_WITNESS_EXT_PX)))
    dx, dy = B.x() - A.x(), B.y() - A.y()
    L = math.hypot(dx, dy)
    tx, ty = dx / L, dy / L
    ang = readable_deg(math.degrees(math.atan2(ty, tx)))
    inside = L >= w + 2.0 * tlen + DIM_FIT_PAD_PX
    if inside:
        segments = [(A, B)]
        terms = [(A, (-tx, -ty)), (B, (tx, ty))]
        dist = DIM_TEXT_GAP_PX + _half_extent(ox, oy, ang, w, h)
        c = QPointF((A.x() + B.x()) / 2 + ox * dist, (A.y() + B.y()) / 2 + oy * dist)
    else:
        S = DIM_SHORT_LEADER_PX
        segments = [(QPointF(A.x() - tx * S, A.y() - ty * S), A), (A, B),
                    (B, QPointF(B.x() + tx * S, B.y() + ty * S))]
        terms = [(A, (tx, ty)), (B, (-tx, -ty))]
        k = S + DIM_TEXT_GAP_PX + w / 2.0
        c = QPointF(B.x() + tx * k, B.y() + ty * k)
    return DimGraphic(A, B, witness, segments, terms,
                      ReadoutLayout(text, c, ang, w, h, inside), inside)


def _seg_dist(p, a, b) -> float:
    ax, ay, bx, by = a.x(), a.y(), b.x(), b.y()
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = (0.0 if L2 < _EPS
         else max(0.0, min(1.0, ((p.x() - ax) * dx + (p.y() - ay) * dy) / L2)))
    return math.hypot(p.x() - (ax + t * dx), p.y() - (ay + t * dy))


def hit_dim(g: DimGraphic, vp_pt, tol=None) -> bool:
    """D64: *vp_pt* on the label (padded), the dim line or a terminator --
    never a witness line."""
    tol = M.CONSTRAINT_PICK_EDGE_TOL_PX if tol is None else tol
    p = QPointF(vp_pt)
    if hit_layout(replace(g.label, fits=True), p):
        return True
    return any(_seg_dist(p, s, e) <= tol for s, e in g.segments)


def bounds(g: DimGraphic, reach: float = 7.5) -> QRectF:
    """Viewport bounds of every part of *g* (repaint region); *reach* =
    :func:`terminator_reach_px` -- how far a terminator spreads from its tip."""
    out = label_path(g.label).boundingRect()
    pts = [g.a, g.b] + [q for seg in g.witness + g.segments for q in seg]
    r = reach + 1.0                                   # + the 1 px stroke
    for q in pts:
        out = out.united(QRectF(q.x() - r, q.y() - r, 2 * r, 2 * r))
    return out


# -- D61 terminator -----------------------------------------------------------

_TERM_CACHE: dict = {}          # path -> (mtime, EndDef | None)


def terminator_name() -> str:
    """D61: the End Types end name in the ``dimension/terminator`` setting."""
    try:
        from PyQt6.QtCore import QSettings
        v = QSettings("GV", "FirePro3D").value(DIM_TERMINATOR_KEY,
                                               DIM_TERMINATOR_DEFAULT, type=str)
        return (v or "").strip() or DIM_TERMINATOR_DEFAULT
    except Exception:
        return DIM_TERMINATOR_DEFAULT


def terminator_def():
    """The ``EndDef`` of the End Types end named by :func:`terminator_name`,
    or None (missing / unreadable / not an end) -- the caller then draws the
    built-in triangle (D61). Cached per file mtime."""
    from .block_library import load_block_file
    from .capabilities import _folder_ends
    from .end_render import EndDef
    name = terminator_name()
    path = next((p for n, _bid, p in _folder_ends() if n == name), None)
    if not path:
        return None
    try:
        mt = os.path.getmtime(path)
    except OSError:
        return None
    hit = _TERM_CACHE.get(path)
    if hit is not None and hit[0] == mt:
        return hit[1]
    ed = EndDef.from_block(load_block_file(path))
    ed = ed if ed is not None and ed.ops else None
    _TERM_CACHE[path] = (mt, ed)
    return ed


def terminator_length_px(ed) -> float:
    """How far a terminator reaches back from its tip, px (D66 fit rule)."""
    if ed is None:
        return DIM_TERM_FALLBACK_MM[0] * DIM_TERM_PX_PER_MM
    return max(-ed.bounds[0], ed.bounds[2], 0.0) * DIM_TERM_PX_PER_MM


def terminator_reach_px(ed) -> float:
    """How far a terminator spreads from its tip in any direction, px (the
    repaint pad -- a wide end reaches further sideways than back)."""
    if ed is None:
        L, W = DIM_TERM_FALLBACK_MM
        return max(L, W / 2.0) * DIM_TERM_PX_PER_MM
    return max(abs(v) for v in ed.bounds) * DIM_TERM_PX_PER_MM


_MISSING = object()


def _snap(v: float, dpr: float) -> float:
    """*v* (logical px) moved to its device pixel's centre."""
    return (math.floor(v * dpr) + 0.5) / dpr


def _crisp_seg(s, e, dpr: float):
    """An axis-aligned segment with its cross coordinate on a device pixel
    centre, so a 1 px line covers whole pixels instead of two half-tone rows
    (the glyph-box half-px inset idiom); diagonals are left alone (they are
    anti-aliased anyway, and per-end snapping would tilt short ones)."""
    if abs(e.y() - s.y()) < 1e-6:
        y = _snap(s.y(), dpr)
        return QPointF(s.x(), y), QPointF(e.x(), y)
    if abs(e.x() - s.x()) < 1e-6:
        x = _snap(s.x(), dpr)
        return QPointF(x, s.y()), QPointF(x, e.y())
    return s, e


def _crisp_tip(tip, outward, dpr: float) -> QPointF:
    """A terminator tip snapped like the axis-aligned dim line it sits on."""
    ux, uy = outward
    if abs(uy) < 1e-6:
        return QPointF(tip.x(), _snap(tip.y(), dpr))
    if abs(ux) < 1e-6:
        return QPointF(_snap(tip.x(), dpr), tip.y())
    return QPointF(tip)


def _dpr(painter) -> float:
    try:
        return float(painter.device().devicePixelRatioF()) or 1.0
    except Exception:
        return 1.0


def paint_terminator(painter, tip, outward, colour, ed=_MISSING) -> None:
    """One terminator at viewport *tip*, +X along unit *outward* (D61)."""
    if ed is _MISSING:
        ed = terminator_def()
    k = DIM_TERM_PX_PER_MM
    pen = QPen(colour, 1.0)
    pen.setCosmetic(True)
    if ed is not None:
        from .end_render import paint_end_at
        paint_end_at(painter, ed, QPointF(tip), outward, k, pen)
        return
    L, W = DIM_TERM_FALLBACK_MM
    ux, uy = outward
    nx, ny = -uy, ux
    bx, by = tip.x() - ux * L * k, tip.y() - uy * L * k
    hw = W * k / 2.0
    path = QPainterPath(QPointF(tip))
    path.lineTo(bx + nx * hw, by + ny * hw)
    path.lineTo(bx - nx * hw, by - ny * hw)
    path.closeSubpath()
    painter.fillPath(path, colour)


def paint_dim(painter, g: DimGraphic, colour, th, ed=_MISSING) -> None:
    """D60: witness lines, dim line, terminators, then the text -- all in
    *colour* (viewport px; the painter is reset)."""
    from PyQt6.QtGui import QPainter
    from .readout_paint import paint_readout
    if ed is _MISSING:
        ed = terminator_def()
    dpr = _dpr(painter)
    painter.save()
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(colour, 1.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for s, e in g.witness + g.segments:
            painter.drawLine(*_crisp_seg(s, e, dpr))
        for tip, u in g.terms:
            paint_terminator(painter, _crisp_tip(tip, u, dpr), u, colour, ed)
    finally:
        painter.restore()
    paint_readout(painter, g.label, th, color=colour)
