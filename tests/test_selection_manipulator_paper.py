"""Parity tests: SheetViewport resize via the SelectionManipulator (Task 7).

The paper scene adopts the model-scene SelectionManipulator. These tests prove
the manipulator-driven resize path reproduces the RETIRED
``SheetViewport._apply_grip_resize`` crop×scale semantics EXACTLY, keeps scale
fixed, produces one undo entry per gesture, and moves on paper via
``manip_translate``.

Ground-truth numbers were captured from the OLD ``_apply_grip_resize`` before it
was retired (see the module docstring in git history / the task report) and are
asserted here as literals so a future drift is caught.
"""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsRectItem
from PyQt6.QtCore import QRectF, QPointF

from firepro3d.paper_space import PaperScene, Sheet, SheetViewData
from firepro3d.manip_math import HandleRole
from tests.test_paper_viewport_crop import _resolver


def _make_scene(qapp):
    """A real PaperScene + one plan viewport bound to a real source scene.

    Source extent is (0,0,1000,500) but the QGraphicsRectItem's 0.5mm pen halo
    makes the seeded full-extent crop (-0.5,-0.5,1001,501); scale 0.1 → the
    on-paper size seeds at 100.1 x 50.1.
    """
    model = QGraphicsScene()
    model.addItem(QGraphicsRectItem(QRectF(0, 0, 1000, 500)))
    sheet = Sheet.create_default()
    data = SheetViewData("plan", "Level 1", "PLAN", 0.1, 0, 0, 0, 0)
    scene = PaperScene(sheet, _resolver(model))
    vp = scene.add_viewport(data)
    return scene, vp, data


# --------------------------------------------------------------------------- #
#  manip_scale reproduces the retired _apply_grip_resize numbers
# --------------------------------------------------------------------------- #

def test_viewport_manip_scale_matches_old_apply_grip_resize(qapp):
    """manip_scale for a BR-corner resize == the OLD _apply_grip_resize numbers.

    OLD ground truth (captured from _apply_grip_resize(BR, (+30,+20)) on the
    same fixture, before retirement):
        x=0, y=0, w=130.1, h=70.1, crop=(-0.5,-0.5,1301,701)
    The manipulator resizes about the corner opposite the dragged handle, so a
    BR drag anchors the TL corner at the on-paper (x, y). new_w/new_h grow by
    the same +30/+20 paper mm the old delta produced.
    """
    scene, vp, data = _make_scene(qapp)
    x0, y0, w0, h0 = data.x, data.y, data.w, data.h
    # BR drag by (+30, +20) paper mm → factors about the TL anchor.
    fx = (w0 + 30.0) / w0
    fy = (h0 + 20.0) / h0
    anchor = QPointF(x0, y0)      # TL corner (opposite the dragged BR handle)
    vp.manip_scale(fx, fy, anchor)

    cr = data.crop_rect
    assert data.x == pytest.approx(0.0, abs=1e-6)
    assert data.y == pytest.approx(0.0, abs=1e-6)
    assert data.w == pytest.approx(130.1, abs=1e-4)
    assert data.h == pytest.approx(70.1, abs=1e-4)
    assert (cr.x(), cr.y(), cr.width(), cr.height()) == pytest.approx(
        (-0.5, -0.5, 1301.0, 701.0), abs=1e-3)


def test_viewport_manip_scale_tl_matches_old(qapp):
    """manip_scale for a TL-corner resize == OLD _apply_grip_resize(TL,(+10,+5)).

    OLD ground truth: x=10, y=5, w=90.1, h=45.1, crop=(99.5,49.5,901,451).
    A TL drag anchors the BR corner on paper; x/y shift so the BR stays put.
    """
    scene, vp, data = _make_scene(qapp)
    x0, y0, w0, h0 = data.x, data.y, data.w, data.h
    # TL drag by (+10, +5): the TL edge moves in, shrinking on-paper size by
    # (10, 5); anchor is the BR corner (x0+w0, y0+h0).
    fx = (w0 - 10.0) / w0
    fy = (h0 - 5.0) / h0
    anchor = QPointF(x0 + w0, y0 + h0)
    vp.manip_scale(fx, fy, anchor)

    cr = data.crop_rect
    assert data.x == pytest.approx(10.0, abs=1e-4)
    assert data.y == pytest.approx(5.0, abs=1e-4)
    assert data.w == pytest.approx(90.1, abs=1e-4)
    assert data.h == pytest.approx(45.1, abs=1e-4)
    assert (cr.x(), cr.y(), cr.width(), cr.height()) == pytest.approx(
        (99.5, 49.5, 901.0, 451.0), abs=1e-3)


def test_viewport_resize_crop_at_fixed_scale(qapp):
    """A corner resize changes crop_rect, leaves scale UNCHANGED, and keeps the
    on-paper size == crop × scale invariant."""
    scene, vp, data = _make_scene(qapp)
    scale_before = data.scale
    crop_w_before = data.crop_rect.width()
    x0, y0, w0, h0 = data.x, data.y, data.w, data.h

    fx = (w0 + 30.0) / w0
    vp.manip_scale(fx, 1.0, QPointF(x0, y0))

    assert data.scale == scale_before                      # scale untouched
    assert data.crop_rect.width() == pytest.approx(crop_w_before + 300, abs=1.0)
    assert data.w == pytest.approx(data.crop_rect.width() * data.scale, abs=1e-4)
    assert data.h == pytest.approx(data.crop_rect.height() * data.scale, abs=1e-4)


# --------------------------------------------------------------------------- #
#  One undo per gesture via the paper commit hook (macro)
# --------------------------------------------------------------------------- #

def test_viewport_resize_one_geometry_command(qapp):
    """A full manipulator resize gesture pushes exactly one undo entry, and undo
    restores geometry exactly."""
    scene, vp, data = _make_scene(qapp)
    manip = scene._manipulator
    vp.setSelected(True)

    def _flat_geom(d):
        cr = d.crop_rect
        return (d.x, d.y, d.w, d.h,
                cr.x(), cr.y(), cr.width(), cr.height())

    before = _flat_geom(data)
    idx_before = scene.undo_stack.index()

    # Drive a released-drag resize through the manipulator's internal lifecycle
    # exactly like a handle press→move→release.
    manip.rebake()
    r0 = QRectF(manip._rect)
    anchor_scene = r0.topLeft()
    start = r0.bottomRight()
    manip._begin("resize", start, QPointF(0, 0), HandleRole.BOTTOM_RIGHT)
    from PyQt6.QtCore import Qt
    manip._moved = True
    manip._last_factors = ((r0.width() + 30.0) / r0.width(),
                           (r0.height() + 20.0) / r0.height())
    manip._finish(QPointF(start.x() + 30, start.y() + 20),
                  Qt.KeyboardModifier.NoModifier)

    assert scene.undo_stack.index() == idx_before + 1, "exactly one undo entry"
    assert data.w == pytest.approx(130.1, abs=1e-3)

    scene.undo_stack.undo()
    assert _flat_geom(data) == pytest.approx(before, abs=1e-4)


# --------------------------------------------------------------------------- #
#  manip_translate moves on paper
# --------------------------------------------------------------------------- #

def test_viewport_move_translates_on_paper(qapp):
    """manip_translate shifts the viewport's on-paper x/y."""
    scene, vp, data = _make_scene(qapp)
    x0, y0 = data.x, data.y
    vp.manip_translate(15.0, -7.0)
    assert data.x == pytest.approx(x0 + 15.0, abs=1e-6)
    assert data.y == pytest.approx(y0 - 7.0, abs=1e-6)
    # The Qt item position tracks the data (mirrors the retired move path).
    assert vp.pos().x() == pytest.approx(x0 + 15.0, abs=1e-6)
    assert vp.pos().y() == pytest.approx(y0 - 7.0, abs=1e-6)


def test_viewport_move_gesture_one_undo_entry(qapp):
    """A full manipulator MOVE gesture (press→move→release) translates the
    viewport, pushes exactly one undo entry (macro), and undo restores it."""
    from PyQt6.QtWidgets import QGraphicsView
    from PyQt6.QtCore import Qt
    from firepro3d.manip_math import move_delta
    scene, vp, data = _make_scene(qapp)
    _view = QGraphicsView(scene)      # manipulator needs a live view
    vp.setSelected(True)
    manip = scene._manipulator
    manip.rebake()
    assert vp in manip.selection_items()
    x0, y0 = data.x, data.y
    idx0 = scene.undo_stack.index()

    c = manip._rect.center()
    manip._begin("move", c, QPointF(0, 0))
    manip._moved = True
    manip._apply(move_delta(c, QPointF(c.x() + 25, c.y() - 10), ortho=False))
    manip._finish(QPointF(c.x() + 25, c.y() - 10), Qt.KeyboardModifier.NoModifier)

    assert data.x == pytest.approx(x0 + 25, abs=1e-6)
    assert data.y == pytest.approx(y0 - 10, abs=1e-6)
    assert scene.undo_stack.index() == idx0 + 1
    scene.undo_stack.undo()
    assert data.x == pytest.approx(x0, abs=1e-6)
    assert data.y == pytest.approx(y0, abs=1e-6)


def test_viewport_manip_bounds_is_on_paper_rect(qapp):
    """manip_bounds() is the on-paper (x, y, w, h) rect."""
    scene, vp, data = _make_scene(qapp)
    b = vp.manip_bounds()
    assert (b.x(), b.y(), b.width(), b.height()) == pytest.approx(
        (data.x, data.y, data.w, data.h), abs=1e-6)


def test_detail_viewport_has_no_scale_capability(qapp):
    """A detail viewport's extent is marker-owned: no manip_scale handles."""
    from firepro3d.selection_manipulator import item_capabilities
    model = QGraphicsScene()
    from tests.test_paper_viewport_crop import _FakeMarker
    markers = {"D1": _FakeMarker(QRectF(0, 0, 100, 100))}
    sheet = Sheet.create_default()
    data = SheetViewData("detail", "D1", "DET", 0.2, 0, 0, 0, 0)
    scene = PaperScene(sheet, _resolver(model, markers))
    vp = scene.add_viewport(data)
    assert "scale" not in item_capabilities(vp)
    # Paper viewports never rotate in v1.
    assert "rotate" not in item_capabilities(vp)
