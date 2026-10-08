"""LT5 P4 probe -- a cosmetic pen keeps its px width under the end frame.

Design C: ``end_render.paint_ends`` draws each end's ops under
``translate(attach) . rotate(outward) . scale(k) [. scale(1, -1)]`` and
strokes them with the line's pen; a cosmetic canvas pen must stay its px
width whatever k / mirror, while a non-cosmetic (paper) pen scales by k.
Ratifies "cosmetic widths survive the scale" (P4, plan step 1) by measuring
rasterised ink: lit pixels / drawn length = the stroke's device width.
"""
import numpy as np
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen

_LEN_PX = 100.0               # drawn length in device px (any k)


def _draw(rot, k, mirrored, cosmetic, width, as_path):
    img = QImage(240, 240, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    p.translate(120.0, 120.0)
    p.rotate(rot)
    p.scale(k, k)
    if mirrored:
        p.scale(1.0, -1.0)
    pen = QPen(QColor("#ffffff"))
    pen.setWidthF(width)
    pen.setCosmetic(cosmetic)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    p.setPen(pen)
    half = _LEN_PX / 2.0 / k
    a, b = QPointF(-half, 0.0), QPointF(half, 0.0)
    if as_path:
        path = QPainterPath(a)
        path.lineTo(b)
        p.drawPath(path)
    else:
        p.drawLine(a, b)
    p.end()
    return img


def _width_px(img):
    """Lit pixels / drawn length = the stroke's device width (px)."""
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    a = np.frombuffer(bytes(ptr), np.uint32).reshape(img.height(), img.width())
    return int(((a & 0xFFFFFF) != 0).sum()) / _LEN_PX


@pytest.mark.parametrize("as_path", [False, True])
@pytest.mark.parametrize("mirrored", [False, True])
@pytest.mark.parametrize("k", [0.05, 5.0])
@pytest.mark.parametrize("rot", [0.0, 30.0, 90.0, 217.0])
def test_cosmetic_width_survives_the_end_frame(qapp, rot, k, mirrored, as_path):
    w = _width_px(_draw(rot, k, mirrored, True, 3.0, as_path))
    assert 2.5 <= w <= 3.6, w


@pytest.mark.parametrize("mirrored", [False, True])
@pytest.mark.parametrize("rot", [0.0, 30.0, 217.0])
def test_non_cosmetic_width_scales_with_k(qapp, rot, mirrored):
    w = _width_px(_draw(rot, 5.0, mirrored, False, 3.0, True))
    assert abs(w - 15.0) <= 1.5, w
