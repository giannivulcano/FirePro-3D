"""SB4f AC6: the round title grip beside the resize set, one undo step per
drag, Esc cancels, reset from the panel and the context menu."""
import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMenu

from firepro3d import paper_space
from firepro3d.manip_handle import GripHandle, ResizeHandle
from firepro3d.paper_space import ViewportProperties
from tests._sb4d_helpers import dispose, plan_scene
from tests._sb4f_helpers import BOX, place

X, Y, W, H = BOX


@pytest.fixture
def rig(qapp, real_system_library):
    ms, sec, det, tabs = plan_scene()
    yield ms, sec, det
    dispose(ms, sec, tabs)


def _select(view, ps, vp):
    view.show()
    QTest.qWaitForWindowExposed(view)
    vp.setSelected(True)
    QApplication.processEvents()
    return ps._manipulator


def _grips(m):
    return [h for h in m._active_handles() if isinstance(h, GripHandle)]


@pytest.mark.parametrize("kind,resizable", [("plan", True), ("detail", False)])
def test_round_grip_sits_on_the_title_and_the_resize_set_stays(rig, kind, resizable):
    view, ps, vp = place(*rig, kind)
    m = _select(view, ps, vp)
    grips = _grips(m)
    assert len(grips) == 1 and grips[0].circular
    want = QPointF(X + 4.0, Y + H + 4.5)      # raw: the default spot
    assert grips[0].scene_position(m._rect) == want
    resize = [h for h in m._active_handles() if isinstance(h, ResizeHandle)]
    assert bool([h for h in resize if h.visible(m)]) is resizable


def test_hidden_title_has_no_grip_at_once(rig):
    view, ps, vp = place(*rig)
    m = _select(view, ps, vp)
    ps.commit_viewport_edit(vp, show_title=False)
    assert _grips(m) == []
    ps.undo_stack.undo()
    assert len(_grips(m)) == 1


def _drag_grip(view, vp, steps=5):
    start = vp.mapToScene(vp._title_label.pos())
    view.centerOn(start)
    QApplication.processEvents()
    pt = view.mapFromScene(start)
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=pt)
    for i in range(1, steps + 1):
        QTest.mouseMove(view.viewport(), pt + QPoint(i * 6, i * 4))
        QApplication.processEvents()
    return pt, pt + QPoint(steps * 6, steps * 4)


def test_drag_moves_only_the_title_in_one_undo_step(rig):
    view, ps, vp = place(*rig)
    _select(view, ps, vp)
    count = ps.undo_stack.count()
    _pt, end = _drag_grip(view, vp)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    QApplication.processEvents()
    got = view.mapToScene(end)                 # the grip follows the cursor, not a delta
    assert vp.data.title_offset == pytest.approx(
        (got.x() - (X + 4.0), got.y() - (Y + H + 4.5)), abs=1e-6)
    assert (vp.data.x, vp.data.y, vp.data.w, vp.data.h) == BOX
    assert ps.undo_stack.count() == count + 1
    ps.undo_stack.undo()
    assert vp.data.title_offset == (0.0, 0.0)
    assert vp._title_label.pos() == QPointF(4.0, H + 4.5)


def test_cancelled_drag_restores_and_pushes_nothing(rig):
    view, ps, vp = place(*rig)
    m = _select(view, ps, vp)
    count = ps.undo_stack.count()
    _pt, end = _drag_grip(view, vp)
    assert vp.data.title_offset != (0.0, 0.0)
    m.cancel_drag()
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    QApplication.processEvents()
    assert vp.data.title_offset == pytest.approx((0.0, 0.0), abs=1e-9)
    assert ps.undo_stack.count() == count


def test_offset_survives_a_viewport_move(rig):
    view, ps, vp = place(*rig)
    vp.apply_grip(0, QPointF(200.0, 150.0))
    off = vp.data.title_offset
    vp.manip_translate(10.0, 5.0)
    assert vp.data.title_offset == off


def test_panel_reset_is_one_undo_step(rig):
    view, ps, vp = place(*rig)
    vp.apply_grip(0, QPointF(200.0, 150.0))
    off = vp.data.title_offset
    ViewportProperties(ps, vp).get_properties()["Title Position"]["callback"]()
    assert vp.data.title_offset == (0.0, 0.0)
    assert vp._title_label.pos() == QPointF(4.0, H + 4.5)
    ps.undo_stack.undo()
    assert vp.data.title_offset == off


def test_context_menu_reset(rig, monkeypatch):
    class _Menu(QMenu):
        def exec(self, *a):
            return next(x for x in self.actions() if x.text() == "Reset Title Position")
    monkeypatch.setattr(paper_space, "QMenu", _Menu)

    class _Ev:
        def screenPos(self):
            return QPoint(0, 0)
    view, ps, vp = place(*rig)
    vp.apply_grip(0, QPointF(200.0, 150.0))
    vp.contextMenuEvent(_Ev())
    assert vp.data.title_offset == (0.0, 0.0)
