"""Live crop resize of sheet viewports (bug: held-preview stretch).

Ground truth: source rect (0,0,1000,500) with a 0.5 mm pen halo seeds the crop
(-0.5,-0.5,1001,501); at scale 0.1 the box is 100.1 x 50.1 (see
tests/test_selection_manipulator_paper._make_scene).  A BR drag of (+30,+20)
gives box 130.1 x 70.1 -> crop 1301 x 701 (= box / 0.1).
"""
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsScene

from firepro3d.manip_math import HandleRole
from firepro3d.paper_space import PaperScene, Sheet, SheetViewData
from tests.test_selection_manipulator_paper import _make_scene, _text_scene
from tests.test_paper_viewport_crop import _resolver

NO = Qt.KeyboardModifier.NoModifier


def _geom(d):
    cr = d.crop_rect
    return (d.x, d.y, d.w, d.h, cr.x(), cr.y(), cr.width(), cr.height())


def _press(scene, item, role):
    m = scene._manipulator
    item.setSelected(True)
    m.rebake()
    r0 = QRectF(m._rect)
    start = {HandleRole.BOTTOM_RIGHT: r0.bottomRight(),
             HandleRole.TOP_LEFT: r0.topLeft()}[role]
    m._begin_handle(m._rigid[role], start, QPointF(0, 0))
    return m, start


def _drag(m, start, dx, dy):
    p = QPointF(start.x() + dx, start.y() + dy)
    m._update(p, NO, QPointF(300, 200))
    return p


def test_crop_updates_live_mid_drag_without_stretch(qapp):
    scene, vp, data = _make_scene(qapp)
    m, start = _press(scene, vp, HandleRole.BOTTOM_RIGHT)
    with patch.object(vp, "update", wraps=vp.update) as up:
        _drag(m, start, 30, 20)
        assert up.call_count >= 1, "a live frame must repaint the viewport"
    assert vp.transform().isIdentity(), "no held stretch on the viewport"
    assert _geom(data) == pytest.approx(
        (0, 0, 130.1, 70.1, -0.5, -0.5, 1301, 701), abs=1e-3)
    f = m.mapRectToScene(m._rect)
    assert (f.x(), f.y(), f.width(), f.height()) == pytest.approx(
        (0, 0, 130.1, 70.1), abs=1e-3), "frame follows the live box"
    # A second frame resets to rest first (no accumulation): +10,+5 from rest.
    _drag(m, start, 10, 5)
    assert _geom(data) == pytest.approx(
        (0, 0, 110.1, 55.1, -0.5, -0.5, 1101, 551), abs=1e-3)


def test_tl_live_drag_keeps_bottom_right_pinned(qapp):
    scene, vp, data = _make_scene(qapp)
    m, start = _press(scene, vp, HandleRole.TOP_LEFT)
    _drag(m, start, -10, -5)
    assert vp.transform().isIdentity()
    # right edge 100.1 / bottom 50.1 stay put on paper
    assert (data.x, data.y, data.w, data.h) == pytest.approx(
        (-10, -5, 110.1, 55.1), abs=1e-3)
    assert vp.pos().x() == pytest.approx(-10, abs=1e-3)


def test_live_release_one_undo_and_exact_undo(qapp):
    scene, vp, data = _make_scene(qapp)
    before = _geom(data)
    idx = scene.undo_stack.index()
    m, start = _press(scene, vp, HandleRole.BOTTOM_RIGHT)
    p = _drag(m, start, 30, 20)
    m._finish(p, NO)
    assert scene.undo_stack.index() == idx + 1, "exactly one undo entry"
    assert _geom(data) == pytest.approx(
        (0, 0, 130.1, 70.1, -0.5, -0.5, 1301, 701), abs=1e-3)
    assert vp.transform().isIdentity()
    scene.undo_stack.undo()
    assert _geom(data) == pytest.approx(before, abs=1e-6)


def test_live_esc_restores_exactly_no_undo(qapp):
    scene, vp, data = _make_scene(qapp)
    before = _geom(data)
    idx = scene.undo_stack.index()
    m, start = _press(scene, vp, HandleRole.BOTTOM_RIGHT)
    _drag(m, start, 30, 20)
    m.cancel_drag()
    assert _geom(data) == before
    assert vp.transform().isIdentity()
    assert scene.undo_stack.index() == idx


def test_nts_viewport_resizes_live(qapp):
    model = QGraphicsScene()
    model.addItem(QGraphicsRectItem(QRectF(0, 0, 1000, 500)))
    data = SheetViewData("plan", "Level 1", "PLAN", 0.0, 0, 0, 100, 50)
    scene = PaperScene(Sheet.create_default(), _resolver(model))
    vp = scene.add_viewport(data)
    m, start = _press(scene, vp, HandleRole.BOTTOM_RIGHT)
    _drag(m, start, 20, 10)
    assert vp.transform().isIdentity()
    assert (data.w, data.h) == pytest.approx((120, 60), abs=1e-6)


def test_non_opt_in_item_keeps_held_preview(qapp):
    """Narrowness guard: a paper TextItem (no MANIP_LIVE_RESIZE) still
    previews under the held transform and bakes on release."""
    scene, item, data = _text_scene(qapp)
    m, start = _press(scene, item, HandleRole.BOTTOM_RIGHT)
    w0 = data.wrap_width_mm
    _drag(m, start, 20, 15)
    assert m._live is None
    assert not item.transform().isIdentity()
    assert data.wrap_width_mm == w0
    m.cancel_drag()
