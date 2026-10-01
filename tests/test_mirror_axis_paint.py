"""DD3: the Flip / Mirror axis paint — an infinite accent dash-dot axis plus a
HALO glow on the SINGLE source segment — and the ghost transforms.

Pixel ground truth on a real shown Model_View (scale 1, 800x600, centred on
the origin): pixels on the axis line far beyond the source segment are
background before and painted after; the glow is beside the segment but not
beside the axis beyond it.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from firepro3d.axis_picker import pick_axis
from firepro3d.cad_math import CAD_Math
from firepro3d.geometry_2d import ReferenceLineItem
from firepro3d.transform_ghost import reflect_transform, scale_transform
from tests._snap_polish_helpers import close_view, make_view


def _grab(view):
    view.viewport().update()
    QApplication.processEvents()
    return view.viewport().grab().toImage()


def _px(view, img, spt):
    vp = view.mapFromScene(spt)
    return QColor(img.pixel(vp.x(), vp.y()))


def test_axis_dash_dot_and_single_segment_glow(qapp):
    view, scene = make_view(scale=1.0)
    try:
        rl = ReferenceLineItem(QPointF(200, -50), QPointF(200, 50))
        scene.addItem(rl)
        scene._reference_lines.append(rl)
        img0 = _grab(view)
        bg = _px(view, img0, QPointF(300, -200))
        scene._mirror_axis = pick_axis(scene, QPointF(202, 0), 10.0)
        assert scene._mirror_axis is not None and scene._mirror_axis.source is rl
        img1 = _grab(view)
        on_axis = [QPointF(200, y) for y in range(-280, -100)]
        assert sum(_px(view, img0, p) != bg for p in on_axis) == 0
        assert sum(_px(view, img1, p) != bg for p in on_axis) >= 60   # [RED]
        assert _px(view, img0, QPointF(203, 0)) == bg
        assert _px(view, img1, QPointF(203, 0)) != bg                 # [RED] glow
        assert _px(view, img1, QPointF(203, -200)) == bg   # glow is the segment only
    finally:
        scene._mirror_axis = None
        close_view(view, scene)


AXES = [(QPointF(0, 0), QPointF(0, -100)), (QPointF(300, 0), QPointF(400, -100)),
        (QPointF(-50, 30), QPointF(80, 170))]
SAMPLES = [QPointF(0, 0), QPointF(100, -50), QPointF(-30, 70), QPointF(250, 5)]


@pytest.mark.parametrize("axis", range(len(AXES)))
def test_reflect_transform_is_the_mirror_map(axis):
    p1, p2 = AXES[axis]
    t = reflect_transform(p1, p2)
    for p in SAMPLES:
        got, exp = t.map(p), CAD_Math.mirror_point(p, p1, p2)
        assert got.x() == pytest.approx(exp.x(), abs=1e-9)           # [RED]
        assert got.y() == pytest.approx(exp.y(), abs=1e-9)


def test_scale_transform_is_the_uniform_scale_map():
    base = QPointF(50, 80)
    t = scale_transform(base, 1.5)
    for p in SAMPLES:
        got, exp = t.map(p), CAD_Math.scale_point(p, base, 1.5)
        assert got.x() == pytest.approx(exp.x(), abs=1e-9)
        assert got.y() == pytest.approx(exp.y(), abs=1e-9)
