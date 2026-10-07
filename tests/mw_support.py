"""Shared MW pixel helpers: a shown Block Editor view + row counting."""
import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication


def grab(v):
    """Repaint + grab *v*'s viewport. Skips the calling test off DPR 1: the
    exact (n full, 0 partial) row asserts need logical pixel boundaries to
    be device pixel boundaries."""
    v.viewport().repaint()
    QApplication.processEvents()
    img = v.viewport().grab().toImage()
    if img.devicePixelRatio() != 1.0:
        pytest.skip(f"MW pixel guards are DPR-1 only (DPR {img.devicePixelRatio()})")
    return img, img.devicePixelRatio()


def dist(a: QColor, b: QColor) -> int:
    return abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue())


def boundary_y(v, y_near: float) -> float:
    """A scene y near *y_near* that maps exactly onto a device pixel boundary."""
    dy = v.viewportTransform().map(QPointF(0.0, y_near)).y()
    s = v.viewportTransform().m22()
    return y_near - (dy - math.floor(dy)) / s


def column_profile(img, dpr, x_dev: int, y_dev: float, span: int = 8):
    """[(row, QColor)] for device rows around *y_dev* at column *x_dev*."""
    c = int(math.floor(y_dev))
    return [(r, img.pixelColor(int(x_dev * dpr), int(r * dpr)))
            for r in range(c - span, c + span + 1)]


def rows(profile, ink: QColor, bg: QColor):
    """(full, partial): rows at the ink colour and rows neither ink nor bg."""
    full = sum(1 for _r, c in profile if dist(c, ink) <= 30)
    partial = sum(1 for _r, c in profile
                  if dist(c, ink) > 30 and dist(c, bg) > 30)
    return full, partial


def boundary_x(v, x_near: float) -> float:
    """A scene x near *x_near* that maps exactly onto a device pixel boundary."""
    dx = v.viewportTransform().map(QPointF(x_near, 0.0)).x()
    s = v.viewportTransform().m11()
    return x_near - (dx - math.floor(dx)) / s


def row_profile(img, dpr, x_dev: float, y_dev: int, span: int = 8):
    """[(col, QColor)] for device columns around *x_dev* at row *y_dev*."""
    c = int(math.floor(x_dev))
    return [(k, img.pixelColor(int(k * dpr), int(y_dev * dpr)))
            for k in range(c - span, c + span + 1)]


def blend_spread(c: QColor, bg: QColor, ink: QColor, min_sep: int = 40):
    """How far *c* is from a pure ``bg + a (ink - bg)`` blend: the spread of
    the per-channel alphas (channels where ink and bg differ by > *min_sep*),
    or None when no channel separates them. ~0 = only ink and background on
    the pixel (an anti-aliased fringe of the ink colour); large = another
    colour (e.g. the item's own) shows through."""
    ch = [(c.red(), bg.red(), ink.red()), (c.green(), bg.green(), ink.green()),
          (c.blue(), bg.blue(), ink.blue())]
    alphas = [(cv - b) / (f - b) for cv, b, f in ch if abs(f - b) > min_sep]
    return (max(alphas) - min(alphas)) if alphas else None
