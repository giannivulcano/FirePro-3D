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
from firepro3d.geometry_2d import LineItem, RectangleItem
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
    """The source is a RECTANGLE edge, so "the single source segment" and
    "the whole parent shape" are told apart: the picked (left) edge glows,
    the rect's other edges do not."""
    view, scene = make_view(scale=1.0)
    try:
        rect = RectangleItem(QPointF(200, -50), QPointF(350, 50))
        scene.addItem(rect)
        scene._draw_rects.append(rect)
        img0 = _grab(view)
        bg = _px(view, img0, QPointF(300, -200))
        scene._mirror_axis = pick_axis(scene, QPointF(202, 0), 10.0)
        assert scene._mirror_axis is not None and scene._mirror_axis.source is rect
        assert {round(scene._mirror_axis.p1.x(), 6),
                round(scene._mirror_axis.p2.x(), 6)} == {200.0}   # the left edge
        img1 = _grab(view)
        on_axis = [QPointF(200, y) for y in range(-280, -100)]
        assert sum(_px(view, img0, p) != bg for p in on_axis) == 0
        assert sum(_px(view, img1, p) != bg for p in on_axis) >= 60   # [RED]
        assert _px(view, img0, QPointF(203, 0)) == bg
        assert _px(view, img1, QPointF(203, 0)) != bg                 # [RED] glow
        assert _px(view, img1, QPointF(203, -200)) == bg   # glow is the segment only
        # ...and not the parent shape: no glow beside the rect's other edges.
        for other in (QPointF(353, 0), QPointF(275, -53), QPointF(275, 53)):
            assert _px(view, img0, other) == bg
            assert _px(view, img1, other) == bg                       # [RED] I2
    finally:
        scene._mirror_axis = None
        close_view(view, scene)


def test_degenerate_axis_threshold_matches_the_commit_path(qapp):
    """M1: a segment the commit path treats as degenerate
    (``geometry_2d._degenerate_axis``, length² < 1e-12) is never offered as
    an axis, and its ghost transform is the identity — the same no-op
    ``manip_reflect`` performs on commit."""
    from firepro3d.model_space import Model_Space
    scene = Model_Space(scene_role="block_editor")
    try:
        p1, p2 = QPointF(0, 0), QPointF(5e-7, 0)       # 0.5 µm: l² = 2.5e-13
        sliver = LineItem(p1, p2)
        scene.addItem(sliver)
        scene._draw_lines.append(sliver)
        assert pick_axis(scene, QPointF(0, 2), 10.0) is None          # [RED]
        assert reflect_transform(p1, p2).isIdentity()                 # [RED]
        target = LineItem(QPointF(10, 20), QPointF(30, 40))
        before = [QPointF(p) for p in target.grip_points()]
        target.manip_reflect(p1, p2)                                  # commit
        assert [(p.x(), p.y()) for p in target.grip_points()] == \
            [(p.x(), p.y()) for p in before]
    finally:
        scene.cleanup()


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
