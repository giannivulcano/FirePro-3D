"""Layout + paint for selection dimension readouts (viewport px).

Pure functions over a view's transform — no knowledge of primitives, so the
gridline/constraint/ALIGN §8 follow-ups can reuse them. Text is painted as
glyph outlines (``QPainterPath.addText`` + ``fillPath``): QTextDocument-based
text renders nothing on the live model canvas (engine==0).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetricsF, QPainter, QPainterPath, QPen

from . import theme as _theme
from .constants import (SELDIM_ARC_LABEL_GAP_PX, SELDIM_ARC_REF_FRAC,
                        SELDIM_ARC_REF_MIN_PX, SELDIM_ARROW_HALF_W_PX,
                        SELDIM_ARROW_PX, SELDIM_DASH, SELDIM_FIT_MARGIN_PX,
                        SELDIM_FONT_PX, SELDIM_LABEL_OFFSET_PX,
                        SELDIM_PICK_PAD_PX)


@dataclass
class ReadoutLayout:
    """A laid-out label (viewport px)."""
    text: str
    center: QPointF
    angle_deg: float          # text baseline rotation, screen degrees (Y-down)
    width: float
    height: float
    fits: bool
    # angular only
    arc_center: QPointF | None = None
    arc_radius_px: float = 0.0
    start_deg: float = 0.0    # Y-up
    span_deg: float = 0.0


def readable_deg(deg: float) -> float:
    """Fold a text angle into (-90, 90] so text never reads upside down."""
    d = (deg + 180.0) % 360.0 - 180.0
    if d > 90.0:
        d -= 180.0
    elif d <= -90.0:
        d += 180.0
    return d


def _text_size(text: str) -> tuple[float, float]:
    fm = QFontMetricsF(_theme.value_font(SELDIM_FONT_PX))
    return fm.horizontalAdvance(text), fm.ascent() + fm.descent()


def _half_extent(nx: float, ny: float, angle_deg: float, w: float, h: float) -> float:
    """Half the label's extent along unit normal (nx, ny)."""
    a = math.radians(angle_deg)
    ux, uy = math.cos(a), math.sin(a)
    return abs(nx * ux + ny * uy) * w / 2 + abs(-nx * uy + ny * ux) * h / 2


def layout_linear(view, spec, text: str) -> ReadoutLayout:
    """Label for a linear spec: segment midpoint, offset
    ``SELDIM_LABEL_OFFSET_PX`` off the line to the side away from
    ``spec.away`` (else screen-up / screen-left), aligned + readable."""
    A = QPointF(view.mapFromScene(spec.a))
    B = QPointF(view.mapFromScene(spec.b))
    dx, dy = B.x() - A.x(), B.y() - A.y()
    seg = math.hypot(dx, dy)
    w, h = _text_size(text)
    mid = QPointF((A.x() + B.x()) / 2, (A.y() + B.y()) / 2)
    if seg < 1e-9:
        return ReadoutLayout(text, mid, 0.0, w, h, False)
    tx, ty = dx / seg, dy / seg
    nx, ny = ty, -tx
    if spec.away is not None:
        aw = QPointF(view.mapFromScene(spec.away))
        if nx * (aw.x() - mid.x()) + ny * (aw.y() - mid.y()) > 0:
            nx, ny = -nx, -ny
    elif ny > 0 or (abs(ny) < 1e-9 and nx > 0):
        nx, ny = -nx, -ny
    ang = readable_deg(math.degrees(math.atan2(ty, tx)))
    dist = SELDIM_LABEL_OFFSET_PX + _half_extent(nx, ny, ang, w, h)
    c = QPointF(mid.x() + nx * dist, mid.y() + ny * dist)
    return ReadoutLayout(text, c, ang, w, h,
                         fits=seg >= w + SELDIM_FIT_MARGIN_PX)


def layout_angular(view, spec, text: str) -> ReadoutLayout:
    """Label for an angular spec: dashed reference arc at
    ``max(SELDIM_ARC_REF_MIN_PX, SELDIM_ARC_REF_FRAC * leg)`` px; label on
    the bisector just outside the arc. Hidden when the arc exceeds the leg."""
    C = QPointF(view.mapFromScene(spec.center))
    probe = QPointF(view.mapFromScene(spec.center + QPointF(1.0, 0.0)))
    px_per_scene = max(math.hypot(probe.x() - C.x(), probe.y() - C.y()), 1e-9)
    leg_px = spec.ref_radius * px_per_scene
    r_px = max(float(SELDIM_ARC_REF_MIN_PX), SELDIM_ARC_REF_FRAC * leg_px)
    w, h = _text_size(text)
    mid = math.radians(spec.start_deg + spec.span_deg / 2.0)
    ux, uy = math.cos(mid), -math.sin(mid)             # Y-up bisector -> screen
    # Text runs along the arc tangent at the bisector: (-uy, ux) on screen.
    ang = readable_deg(math.degrees(math.atan2(ux, -uy)))
    dist = r_px + SELDIM_ARC_LABEL_GAP_PX + _half_extent(ux, uy, ang, w, h)
    c = QPointF(C.x() + ux * dist, C.y() + uy * dist)
    return ReadoutLayout(text, c, ang, w, h, fits=r_px <= leg_px,
                         arc_center=C, arc_radius_px=r_px,
                         start_deg=spec.start_deg, span_deg=spec.span_deg)


def hit_layout(lay: ReadoutLayout, vp_pt: QPointF) -> bool:
    """Whether *vp_pt* lies in the (rotated) label rect, padded."""
    if not lay.fits:
        return False
    a = math.radians(-lay.angle_deg)
    dx, dy = vp_pt.x() - lay.center.x(), vp_pt.y() - lay.center.y()
    x = dx * math.cos(a) - dy * math.sin(a)
    y = dx * math.sin(a) + dy * math.cos(a)
    return (abs(x) <= lay.width / 2 + SELDIM_PICK_PAD_PX
            and abs(y) <= lay.height / 2 + SELDIM_PICK_PAD_PX)


def label_path(lay: ReadoutLayout) -> QPainterPath:
    """The padded label rect as a viewport-px path (for the hover glow)."""
    r = QRectF(-lay.width / 2 - SELDIM_PICK_PAD_PX, -lay.height / 2 - SELDIM_PICK_PAD_PX,
               lay.width + 2 * SELDIM_PICK_PAD_PX, lay.height + 2 * SELDIM_PICK_PAD_PX)
    p = QPainterPath()
    p.addRoundedRect(r, 3, 3)
    from PyQt6.QtGui import QTransform
    t = QTransform()
    t.translate(lay.center.x(), lay.center.y())
    t.rotate(lay.angle_deg)
    return t.map(p)


def _paint_arc(painter: QPainter, lay: ReadoutLayout, color: QColor) -> None:
    C, r = lay.arc_center, lay.arc_radius_px
    rect = QRectF(C.x() - r, C.y() - r, 2 * r, 2 * r)
    pen = QPen(color, 1.0)
    pen.setCosmetic(True)
    pen.setDashPattern([float(d) for d in SELDIM_DASH])
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    arc = QPainterPath()
    arc.arcMoveTo(rect, lay.start_deg)
    arc.arcTo(rect, lay.start_deg, lay.span_deg)
    painter.drawPath(arc)
    # solid arrowheads at both ends, pointing outward along the arc
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    for deg, sgn in ((lay.start_deg, -1.0), (lay.start_deg + lay.span_deg, 1.0)):
        a = math.radians(deg)
        tip = QPointF(C.x() + r * math.cos(a), C.y() - r * math.sin(a))
        # CCW tangent on screen at Y-up angle a is (-sin a, -cos a)
        tx, ty = -math.sin(a) * sgn, -math.cos(a) * sgn
        bx, by = tip.x() - tx * SELDIM_ARROW_PX, tip.y() - ty * SELDIM_ARROW_PX
        nx, ny = -ty * SELDIM_ARROW_HALF_W_PX, tx * SELDIM_ARROW_HALF_W_PX
        head = QPainterPath(tip)
        head.lineTo(bx + nx, by + ny)
        head.lineTo(bx - nx, by - ny)
        head.closeSubpath()
        painter.drawPath(head)


def paint_readout(painter: QPainter, lay: ReadoutLayout, th) -> None:
    """Paint one laid-out readout in viewport px (caller skips unfit ones).

    Text in ``ink``; reference arc + arrowheads in ``muted``.
    """
    painter.save()
    painter.resetTransform()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if lay.arc_center is not None:
        _paint_arc(painter, lay, th.color("muted"))
    font = _theme.value_font(SELDIM_FONT_PX)
    fm = QFontMetricsF(font)
    path = QPainterPath()
    path.addText(QPointF(-lay.width / 2, (fm.ascent() - fm.descent()) / 2), font, lay.text)
    painter.translate(lay.center)
    painter.rotate(lay.angle_deg)
    painter.fillPath(path, th.color("ink"))
    painter.restore()
