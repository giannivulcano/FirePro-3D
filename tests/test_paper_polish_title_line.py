"""Paper polish AC5: the title line's end grip, its stored length, and the one
reset. BOX: the box's right edge is x = 130, the line runs on y = 114.5, the
block origin defaults to x = 34."""
import pytest
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMenu

from firepro3d import paper_space
from firepro3d.manip_handle import GripHandle
from firepro3d.paper_space import SheetViewData, ViewportProperties
from tests._sb4d_helpers import dispose, plan_scene
from tests._sb4f_helpers import BOX, place

X, Y, W, H = BOX
ORIGIN_X = X + 4.0
LINE_Y = Y + H + 4.5


@pytest.fixture
def rig(qapp, real_system_library):
    ms, sec, det, tabs = plan_scene()
    yield ms, sec, det
    dispose(ms, sec, tabs)


def _select(view, ps, vp, zoom=6.0):
    """Zoomed in: the line grip sits 4.5 mm below the box's corner handle, so the
    two hit areas overlap at sheet fit."""
    view.show()
    QTest.qWaitForWindowExposed(view)
    view.resetTransform()
    view.scale(zoom, zoom)
    vp.setSelected(True)
    QApplication.processEvents()
    return ps._manipulator


def _grips(m):
    return [h for h in m._active_handles() if isinstance(h, GripHandle)]


def _shown(m):
    return [h for h in m._host_pool if h.isVisible() and isinstance(h.handle, GripHandle)]


def rendered_line_end(ps, y=LINE_Y, start=ORIGIN_X + 6.0, px=10):
    """Scene x where the ink along *y* stops, read from pixels. Clears the
    selection first: a grip painted at the line end would read as ink."""
    ps.clearSelection()
    QApplication.processEvents()
    rect = QRectF(start, y - 0.2, 400.0, 0.4)
    w, h = int(rect.width() * px), int(rect.height() * px)
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    ps.render(p, QRectF(0, 0, w, h), rect, Qt.AspectRatioMode.IgnoreAspectRatio)
    p.end()
    for x in range(w):
        if QColor(img.pixel(x, h // 2)).lightness() > 128:
            return start + x / px
    return start + w / px


def _drag(view, vp, dx_px=60, dy_px=24, steps=4):
    start = vp.grip_points()[1]
    view.centerOn(start)
    QApplication.processEvents()
    pt = view.mapFromScene(start)
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=pt)
    for i in range(1, steps + 1):
        QTest.mouseMove(view.viewport(), pt + QPoint(dx_px * i // steps, dy_px * i // steps))
        QApplication.processEvents()
    return pt + QPoint(dx_px, dy_px)


def test_two_round_grips_with_the_second_at_the_line_end(rig):
    view, ps, vp = place(*rig)
    m = _select(view, ps, vp)
    grips = _grips(m)
    assert len(grips) == 2 and all(g.circular for g in grips)
    assert grips[1].scene_position(m._rect) == QPointF(X + W, LINE_Y)
    assert rendered_line_end(ps) == pytest.approx(X + W, abs=0.2)


def test_drag_changes_length_only_in_one_undo_step(rig):
    view, ps, vp = place(*rig)
    _select(view, ps, vp)
    count = ps.undo_stack.count()
    end = _drag(view, vp)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    QApplication.processEvents()
    got = view.mapToScene(end)
    assert vp.data.title_line_mm == pytest.approx(got.x() - ORIGIN_X, abs=1e-6)
    assert vp.data.title_offset == (0.0, 0.0)         # x only: the title did not move
    assert (vp.data.x, vp.data.y, vp.data.w, vp.data.h) == BOX
    assert rendered_line_end(ps) == pytest.approx(got.x(), abs=0.2)
    assert ps.undo_stack.count() == count + 1
    ps.undo_stack.undo()
    assert vp.data.title_line_mm == 0.0
    assert rendered_line_end(ps) == pytest.approx(X + W, abs=0.2)


def test_esc_restores_the_automatic_line(rig):
    view, ps, vp = place(*rig)
    m = _select(view, ps, vp)
    count = ps.undo_stack.count()
    end = _drag(view, vp)
    assert vp.data.title_line_mm != 0.0
    m.cancel_drag()
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    QApplication.processEvents()
    assert vp.data.title_line_mm == 0.0
    assert ps.undo_stack.count() == count


def test_an_undragged_line_follows_the_box(rig):
    view, ps, vp = place(*rig)
    vp.manip_scale(1.5, 1.0, QPointF(X, Y))
    assert rendered_line_end(ps) == pytest.approx(X + 150.0, abs=0.2)


def test_a_stored_length_survives_resize_title_move_rescale_and_save(rig):
    view, ps, vp = place(*rig)
    vp.apply_grip(1, QPointF(ORIGIN_X + 60.0, LINE_Y))
    assert vp.data.title_line_mm == pytest.approx(60.0)
    vp.manip_scale(1.5, 1.0, QPointF(X, Y))
    # 0.25: the 0.3 mm pen's square cap ends the ink 0.15 mm past the stored end
    # and the read is 0.1 mm granular, so 94.2 sits on the 0.2 bound.
    assert rendered_line_end(ps) == pytest.approx(ORIGIN_X + 60.0, abs=0.25)
    vp.apply_grip(0, QPointF(ORIGIN_X + 10.0, LINE_Y + 20.0))
    assert vp.grip_points()[1] == QPointF(ORIGIN_X + 70.0, LINE_Y + 20.0)
    moved = rendered_line_end(ps, y=LINE_Y + 20.0, start=ORIGIN_X + 16.0)
    assert moved == pytest.approx(ORIGIN_X + 70.0, abs=0.25)
    ps.commit_viewport_edit(vp, scale=0.01)
    assert vp.data.title_line_mm == pytest.approx(60.0)
    assert SheetViewData.from_dict(vp.data.to_dict()).title_line_mm == pytest.approx(60.0)


def test_a_drag_stops_short_of_the_bubble(rig):
    view, ps, vp = place(*rig)
    vp.apply_grip(1, QPointF(0.0, 0.0))
    assert vp.data.title_line_mm == pytest.approx(3.0 + 1.0)    # bubble radius + the minimum


def test_a_record_without_the_key_loads_automatic():
    rec = SheetViewData("plan", "L", "T", 0.0, 0.0, 0.0, 10.0, 10.0).to_dict()
    del rec["title_line_mm"]
    assert SheetViewData.from_dict(rec).title_line_mm == 0.0


def test_panel_reset_restores_position_and_line_in_one_step(rig):
    view, ps, vp = place(*rig)
    vp.apply_grip(0, QPointF(200.0, 150.0))
    vp.apply_grip(1, QPointF(260.0, 150.0))
    off, line = vp.data.title_offset, vp.data.title_line_mm
    row = ViewportProperties(ps, vp).get_properties()["Title Position"]
    assert row["value"] == "Reset Title"
    count = ps.undo_stack.count()
    row["callback"]()
    assert vp.data.title_offset == (0.0, 0.0) and vp.data.title_line_mm == 0.0
    assert ps.undo_stack.count() == count + 1
    assert rendered_line_end(ps) == pytest.approx(X + W, abs=0.2)
    ps.undo_stack.undo()
    assert vp.data.title_offset == off and vp.data.title_line_mm == line


def test_context_menu_reset_restores_both(rig, monkeypatch):
    class _Menu(QMenu):
        def exec(self, *a):
            return next(x for x in self.actions() if x.text() == "Reset Title")
    monkeypatch.setattr(paper_space, "QMenu", _Menu)

    class _Ev:
        def screenPos(self):
            return QPoint(0, 0)
    view, ps, vp = place(*rig)
    vp.apply_grip(1, QPointF(ORIGIN_X + 60.0, LINE_Y))
    vp.contextMenuEvent(_Ev())
    assert vp.data.title_line_mm == 0.0


def test_a_hidden_title_has_no_line_grip(rig):
    view, ps, vp = place(*rig)
    m = _select(view, ps, vp)
    assert len(_shown(m)) == 2
    ps.commit_viewport_edit(vp, show_title=False)
    assert _grips(m) == [] and _shown(m) == []


def test_no_line_means_no_line_grip_and_no_stale_index(rig):
    view, ps, vp = place(*rig)
    m = _select(view, ps, vp)
    lab = vp._title_label
    lab._line_span = lambda: None
    lab.refresh()
    assert len(vp.grip_points()) == 2                 # index 1 stays valid for a live host
    assert len(_grips(m)) == 1
    m._reflow_live()
