"""Pipe symbols of a section view: geometry only, no scene state.

The plan SVGs are hard-coded white (riser_passthrough.svg, elbow_down.svg), so a
section redraws their geometry as paths in the pipe's colour
(section-view-subsystem s5). Both share a 20-unit viewBox.
"""
from __future__ import annotations

import math
from bisect import bisect_left, bisect_right

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath

SVG_VIEW = 20.0
SVG_RADIUS = 9.2852659        # circle radius in both SVGs
GAP_DEG = 90.0                # elbow_down.svg's arc leaves 90 degrees open


def radius_of(size: float) -> float:
    """Ink radius of a symbol drawn at *size* (the viewBox side)."""
    return SVG_RADIUS * size / SVG_VIEW


def cut_symbol_path(cx: float, cy: float, size: float) -> QPainterPath:
    """Circle + S curve (riser_passthrough.svg) centred on (cx, cy)."""
    k = size / SVG_VIEW

    def pt(x: float, y: float) -> QPointF:
        return QPointF(cx + (x - 10.0) * k, cy + (y - 10.0) * k)

    path = QPainterPath()
    r = radius_of(size)
    path.addEllipse(QPointF(cx, cy), r, r)
    path.moveTo(pt(10.0, 1.0))
    path.cubicTo(pt(9.99322, 1.054255), pt(4.9643808, 6.3732865), pt(10.0, 10.0))
    path.cubicTo(pt(14.766864, 13.433153), pt(10.0, 19.0), pt(10.0, 19.0))
    return path


def end_on_path(cx: float, cy: float, size: float, ux: float, uy: float) -> QPainterPath:
    """The "C" (elbow_down.svg): a circle whose gap faces scene direction (ux, uy)."""
    r = radius_of(size)
    rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
    start = math.degrees(math.atan2(-uy, ux)) + GAP_DEG / 2.0   # Qt angles run y-up
    path = QPainterPath()
    path.arcMoveTo(rect, start)
    path.arcTo(rect, start, 360.0 - GAP_DEG)
    return path


def kept_spans(p1, p2, d1, d2, circles, hs, r_max):
    """Parameter spans of the line p1->p2 left after trimming at symbols.

    *circles* = ``(h, v, r, d)`` sorted by h, *hs* their h values, *r_max* the
    largest r. A symbol trims the line only where the line is at or behind it
    (its d at the point nearest the centre >= the symbol's d, so a pipe joined
    at the symbol trims whichever way it heads): a line passing in front draws
    over. None = untouched.
    """
    lo = min(p1[0], p2[0]) - r_max
    hi = max(p1[0], p2[0]) + r_max
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    l2 = dx * dx + dy * dy
    if l2 <= 0.0:
        return None
    gaps = []
    for h, v, r, d in circles[bisect_left(hs, lo):bisect_right(hs, hi)]:
        fx, fy = p1[0] - h, p1[1] - v
        b = fx * dx + fy * dy
        disc = b * b - l2 * (fx * fx + fy * fy - r * r)
        if disc <= 0.0:
            continue
        s = math.sqrt(disc)
        t0, t1 = max((-b - s) / l2, 0.0), min((-b + s) / l2, 1.0)
        if t1 <= t0:
            continue
        nearest = min(max(-b / l2, 0.0), 1.0)
        if d1 + nearest * (d2 - d1) < d - 1e-6:
            continue                                   # passes in front
        gaps.append((t0, t1))
    if not gaps:
        return None
    kept, t = [], 0.0
    for a, b in sorted(gaps):
        if a > t:
            kept.append((t, a))
        t = max(t, b)
    if t < 1.0:
        kept.append((t, 1.0))
    return kept
