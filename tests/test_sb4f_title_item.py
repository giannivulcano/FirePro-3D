"""SB4f AC1-AC3, AC6 hit half: the title child paints the block and the line,
hides cleanly, and passes the viewport's mouse behaviour through."""
import pytest
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QContextMenuEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMenu

from firepro3d import paper_space
from firepro3d.block_definition import BlockDefinition
from tests._sb4d_helpers import dispose, head_def, plan_scene
from tests._sb4f_helpers import BOX, dark_px, place

X, Y, W, H = BOX
STRIP = QRectF(X, Y + H + 0.6, W, 8.5)      # raw: below the box, past its border pen
LINE_Y = Y + H + 4.5                        # raw: VIEW_TITLE_ORIGIN_Y_MM below the box


@pytest.fixture
def rig(qapp, real_system_library):
    ms, sec, det, tabs = plan_scene()
    yield ms, sec, det
    dispose(ms, sec, tabs)


def test_block_paints_below_the_box_and_box_is_the_bounds(rig):
    _v, ps, vp = place(*rig)
    assert vp._title_label.paints()
    assert dark_px(ps, STRIP) > 0
    assert vp.boundingRect() == QRectF(0.0, 0.0, W, H)


def test_hidden_paints_nothing_and_undo_brings_it_back(rig):
    _v, ps, vp = place(*rig)
    ps.commit_viewport_edit(vp, show_title=False)
    assert not vp._title_label.isVisible()
    assert dark_px(ps, STRIP) == 0
    assert vp.boundingRect() == QRectF(0.0, 0.0, W, H)
    ps.undo_stack.undo()
    assert vp._title_label.isVisible()
    assert dark_px(ps, STRIP) > 0


def test_placeholder_hides_the_title(rig):
    _v, ps, vp = place(*rig)
    vp.data.source_view_name = "gone"
    vp.refresh_source()
    assert vp._placeholder and not vp._title_label.isVisible()


def test_line_runs_from_the_outline_to_the_box_edge(rig):
    _v, ps, vp = place(*rig)
    lab = vp._title_label
    lab.boundingRect()
    assert lab._line == pytest.approx((3.0, W - 4.0), abs=0.05)   # raw: seed r 3, origin x 4
    assert dark_px(ps, QRectF(X + W - 10.0, LINE_Y - 0.3, 9.0, 0.6)) > 0
    assert dark_px(ps, QRectF(X + W + 1.0, LINE_Y - 0.3, 9.0, 0.6)) == 0


def test_line_follows_a_resize_and_the_title_stays_at_lower_left(rig):
    _v, _ps, vp = place(*rig)
    vp.manip_scale(1.5, 1.25, QPointF(X, Y))
    lab = vp._title_label
    lab.boundingRect()
    assert lab._line == pytest.approx((3.0, 1.5 * W - 4.0), abs=0.05)
    assert lab.pos() == QPointF(4.0, 1.25 * H + 4.5)


def test_line_follows_a_restyled_block(rig):
    ms, sec, det = rig
    _v, ps, vp = place(ms, sec, det)
    head_def(ms, "View Title", shape="square")    # half side 4
    vp._sync_title()
    lab = vp._title_label
    lab.boundingRect()
    assert lab._line == pytest.approx((4.0, W - 4.0), abs=0.05)


def test_line_is_box_width_when_the_title_sits_elsewhere(rig):
    _v, _ps, vp = place(*rig)
    vp.data.title_offset = (W + 10.0, -60.0)      # beside the box
    vp._sync_title()
    lab = vp._title_label
    lab.boundingRect()
    assert lab._line == pytest.approx((3.0, 3.0 + W), abs=0.05)


def test_line_is_box_width_when_the_outline_passes_the_box_right_edge(rig):
    _v, _ps, vp = place(*rig)
    vp.data.title_offset = (W, 0.0)               # still below, past the right edge
    vp._sync_title()
    lab = vp._title_label
    lab.boundingRect()
    assert lab._line == pytest.approx((3.0, 3.0 + W), abs=0.05)


def test_title_edit_reshapes_and_a_long_title_runs_past_the_box(rig):
    _v, ps, vp = place(*rig)
    lab = vp._title_label
    assert lab.boundingRect().right() + lab.pos().x() < W + 3.0
    ps.commit_viewport_edit(vp, title="X" * 80)    # D6: not clipped at the box edge
    assert lab.boundingRect().right() + lab.pos().x() > W + 10.0


def test_a_block_with_no_closed_outline_does_not_recurse(rig):
    ms, sec, det = rig
    _v, _ps, vp = place(ms, sec, det)
    d = BlockDefinition.new(name="TestOpenTitle", library="", series="", origin=(0.0, 0.0),
                            primitives=[{"type": "draw_line", "pt1": [-3.0, 0.0],
                                         "pt2": [3.0, 0.0]}])
    d.scale_mode = "annotative"
    d.host_category = "View Title"
    ms.register_block_definition(d)
    ms.annotation_defaults["View Title"] = d.id
    vp._sync_title()
    assert not vp._title_label.boundingRect().isEmpty()


def _shown(view, ps, scene_pt):
    view.show()
    QTest.qWaitForWindowExposed(view)
    view.centerOn(scene_pt)
    QApplication.processEvents()
    return view.mapFromScene(scene_pt)


def test_click_on_the_title_selects_the_viewport(rig):
    view, ps, vp = place(*rig)
    pt = _shown(view, ps, QPointF(X + 60.0, LINE_Y))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=pt)
    QApplication.processEvents()
    assert vp.isSelected()


def test_drag_on_the_title_moves_the_viewport_as_one_undo_step(rig):
    view, ps, vp = place(*rig)
    pt = _shown(view, ps, QPointF(X + 60.0, LINE_Y))
    count = ps.undo_stack.count()
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=pt)
    for i in range(1, 6):
        QTest.mouseMove(view.viewport(), pt + QPoint(i * 6, i * 4))
        QApplication.processEvents()
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=pt + QPoint(30, 20))
    QApplication.processEvents()
    moved = view.mapToScene(pt + QPoint(30, 20)) - view.mapToScene(pt)
    assert vp.data.x == pytest.approx(X + moved.x(), abs=1e-6)
    assert vp.data.y == pytest.approx(Y + moved.y(), abs=1e-6)
    assert ps.undo_stack.count() == count + 1


def test_double_click_on_the_title_navigates(rig):
    view, ps, vp = place(*rig)
    pt = _shown(view, ps, QPointF(X + 60.0, LINE_Y))
    seen = []
    vp.navigate_requested.connect(lambda t, n: seen.append((t, n)))
    QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, pos=pt)
    QApplication.processEvents()
    assert seen == [("plan", "Plan: Level 1")]


def test_right_click_on_the_title_opens_the_viewport_menu(rig, monkeypatch):
    seen = []

    class _Menu(QMenu):
        def exec(self, *a):
            seen.append([x.text() for x in self.actions()])
            return None
    monkeypatch.setattr(paper_space, "QMenu", _Menu)
    view, ps, _vp = place(*rig)
    pt = _shown(view, ps, QPointF(X + 60.0, LINE_Y))
    ev = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, pt,
                           view.viewport().mapToGlobal(pt),
                           Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()
    assert seen and "Go to View" in seen[0]
