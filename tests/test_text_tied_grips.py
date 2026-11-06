"""Tied text box grips (notes design N1 to N5, guard G1): real mouse events through a
shown block editor view. The fixture rebuilds the shape of the recorded Blue Stair case:
a box corner tied to a line end inside a small constrained network."""
import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.constraint_controller import CONFLICT_STATUS
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.scale_manager import ScaleManager
from firepro3d.text_item import TextAnnotationData, TextItem
from tests._note_helpers import mouse
from tests.conftest import _DropOsPointerInput

NB = Qt.MouseButton.NoButton
GRIP_TL, GRIP_TM, GRIP_TR, GRIP_RM, GRIP_BR, GRIP_BM, GRIP_BL, GRIP_LM = range(8)


@pytest.fixture
def block_view(qapp):
    """A shown block editor canvas at 1:1, snap off."""
    scene = Model_Space(scene_role="block_editor")
    scene.scale_manager = ScaleManager()
    scene.setSceneRect(-5000, -5000, 10000, 10000)
    view = Model_View(scene)
    view.resize(900, 700)
    view._os_pointer_filter = _DropOsPointerInput(view)
    view.viewport().installEventFilter(view._os_pointer_filter)
    view.installEventFilter(view._os_pointer_filter)
    view.show()
    QTest.qWaitForWindowExposed(view)
    view.resetTransform()
    view.centerOn(0, 0)
    scene.set_mode("select")
    scene._snap_enabled = False
    QApplication.processEvents()
    yield view, scene
    scene.clearSelection()
    scene.cleanup()
    view.close()
    view.deleteLater()
    QApplication.processEvents()


def _box(scene, text="UP", w=120.0, h=60.0, x=-60.0, y=-30.0, **kw):
    item = TextItem(TextAnnotationData(text=text, x=x, y=y, height_mm=10.0,
                                       wrap_width_mm=w, box_height_mm=h, valign="M", **kw))
    scene.addItem(item)
    scene._texts.append(item)
    QApplication.processEvents()
    return item


def _pin(scene, item, handle):
    assert scene.constraint_ctl.add("coincident",
                                    [{"uid": item._uid, "h": handle}, {"ref": "origin"}])


def _line(scene, a, b):
    ln = LineItem(a, b)
    scene.addItem(ln)
    scene._draw_lines.append(ln)
    return ln


def _tie_into_network(scene, item):
    """Three lines chained by their ends and held horizontal or vertical, with the box's
    bottom-left corner on the first line's start: the recorded case's shape."""
    ctl = scene.constraint_ctl
    bl = item.grip_points()[GRIP_BL]
    a = _line(scene, QPointF(bl), QPointF(bl.x() - 140.0, bl.y()))
    b = _line(scene, QPointF(bl.x() - 140.0, bl.y()), QPointF(bl.x() - 140.0, bl.y() + 90.0))
    c = _line(scene, QPointF(bl.x() - 140.0, bl.y() + 90.0), QPointF(bl.x(), bl.y() + 90.0))
    assert ctl.add("horizontal", [{"uid": a._uid, "h": "edge"}])
    assert ctl.add("vertical", [{"uid": b._uid, "h": "edge"}])
    assert ctl.add("horizontal", [{"uid": c._uid, "h": "edge"}])
    assert ctl.add("coincident", [{"uid": a._uid, "h": "p2"}, {"uid": b._uid, "h": "p1"}])
    assert ctl.add("coincident", [{"uid": b._uid, "h": "p2"}, {"uid": c._uid, "h": "p1"}])
    assert ctl.add("coincident", [{"uid": c._uid, "h": "p2"}, {"ref": "origin"}])
    for ln in (a, b, c):
        assert ctl.add("dim_distance", [{"uid": ln._uid, "h": "edge"}])
    assert ctl.add("coincident", [{"uid": item._uid, "h": "bl"}, {"uid": a._uid, "h": "p1"}])
    QApplication.processEvents()
    return a


def _drag(view, scene, item, grip, delta, frames=12):
    """Select *item*, press its grip, walk the cursor, release. Returns the status lines."""
    lines = []
    scene.constraint_ctl._status = lines.append
    scene.clearSelection()
    item.setSelected(True)
    QApplication.processEvents()
    start = QPointF(item.grip_points()[grip])
    mouse(view, QEvent.Type.MouseMove, start, buttons=NB, button=NB)
    mouse(view, QEvent.Type.MouseButtonPress, start)
    for i in range(1, frames + 1):
        p = QPointF(start.x() + delta[0] * i / frames, start.y() + delta[1] * i / frames)
        mouse(view, QEvent.Type.MouseMove, p, button=NB)
    mouse(view, QEvent.Type.MouseButtonRelease, p, buttons=NB)
    return lines


def _size(item):
    r = item.manip_bounds()
    return r.width(), r.height()


@pytest.mark.parametrize("delta, want", [
    ((30.0, 0.0), 180.0),                  # N1: the design's own example
    ((-30.0, 0.0), 60.0),
])
def test_centre_pin_grows_both_sides_with_the_grip_on_the_cursor(block_view, delta, want):
    view, scene = block_view
    item = _box(scene)
    _pin(scene, item, "center")
    start = QPointF(item.grip_points()[GRIP_RM])
    assert _drag(view, scene, item, GRIP_RM, delta) == []
    assert _size(item)[0] == pytest.approx(want, abs=0.05)
    got = item.grip_points()[GRIP_RM]
    assert got.x() == pytest.approx(start.x() + delta[0], abs=0.05)
    assert item.grip_points()[8].x() == pytest.approx(0.0, abs=1e-6)


def test_centre_pin_height_grip_reaches_the_cursor(block_view):
    view, scene = block_view
    item = _box(scene)
    _pin(scene, item, "center")
    assert _drag(view, scene, item, GRIP_BM, (0.0, 25.0)) == []
    assert _size(item)[1] == pytest.approx(110.0, abs=0.05)


def test_corner_grip_reaches_both_axes_under_a_centre_pin(block_view):
    view, scene = block_view
    item = _box(scene)
    _pin(scene, item, "center")
    assert _drag(view, scene, item, GRIP_BR, (30.0, 25.0)) == []
    assert _size(item) == pytest.approx((180.0, 110.0), abs=0.05)


@pytest.mark.parametrize("handle, grip, delta, axis, want", [
    ("bm", GRIP_RM, (30.0, 0.0), 0, 180.0),
    ("lm", GRIP_BM, (0.0, 25.0), 1, 110.0),
])
def test_an_edge_pin_reaches_on_the_axis_it_does_not_hold(block_view, handle, grip, delta,
                                                          axis, want):
    view, scene = block_view
    item = _box(scene)
    _pin(scene, item, handle)
    assert _drag(view, scene, item, grip, delta) == []
    assert _size(item)[axis] == pytest.approx(want, abs=0.05)


def test_a_rotated_box_reaches_along_its_own_axes(block_view):
    view, scene = block_view
    view.scale(4.0, 4.0)                   # the posted cursor lands on whole pixels
    item = _box(scene)
    item.set_angle(30.0, None)
    _pin(scene, item, "center")
    a, b = item.grip_points()[GRIP_LM], item.grip_points()[GRIP_RM]
    ux, uy = (b.x() - a.x()) / 120.0, (b.y() - a.y()) / 120.0
    assert _drag(view, scene, item, GRIP_RM, (30.0 * ux, 30.0 * uy)) == []
    a, b = item.grip_points()[GRIP_LM], item.grip_points()[GRIP_RM]
    assert ((b.x() - a.x()) ** 2 + (b.y() - a.y()) ** 2) ** 0.5 == pytest.approx(180.0, abs=0.3)


def test_a_grip_on_the_pinned_point_stays_put(block_view):
    view, scene = block_view
    item = _box(scene)
    _pin(scene, item, "rm")
    before = _size(item)
    _drag(view, scene, item, GRIP_RM, (30.0, 0.0))
    assert _size(item) == pytest.approx(before, abs=1e-6)


@pytest.mark.parametrize("grip, delta", [
    (GRIP_TM, (0.0, 80.0)),                # past the text: the recorded refusal
    (GRIP_TM, (0.0, 20.0)),
    (GRIP_TR, (-40.0, 20.0)),
    (GRIP_TR, (60.0, -40.0)),
    (GRIP_RM, (-30.0, 0.0)),
    (GRIP_RM, (50.0, 0.0)),
])
def test_a_tied_box_resizes_with_no_refusal_and_its_tie_holds(block_view, grip, delta):
    view, scene = block_view
    item = _box(scene)
    line = _tie_into_network(scene, item)
    tied = QPointF(item.grip_points()[GRIP_BL])
    lines = _drag(view, scene, item, grip, delta)
    assert CONFLICT_STATUS not in lines
    now = item.grip_points()[GRIP_BL]
    assert (now.x(), now.y()) == pytest.approx((tied.x(), tied.y()), abs=1e-3)
    p1 = line.grip_points()[0]
    assert (p1.x(), p1.y()) == pytest.approx((tied.x(), tied.y()), abs=1e-3)


def test_a_tied_box_stops_at_its_text_height_silently(block_view):
    view, scene = block_view
    item = _box(scene)
    _tie_into_network(scene, item)
    content = item._content_height_mm()
    assert content < 60.0
    assert _drag(view, scene, item, GRIP_TM, (0.0, 80.0)) == []
    assert _size(item)[1] == pytest.approx(content, abs=0.05)


def test_a_tied_box_width_stops_where_the_text_fits_the_height(block_view):
    view, scene = block_view
    item = _box(scene, text="WORD WORD", w=120.0, h=0.0)
    one_line = item._content_height_mm()
    _tie_into_network(scene, item)
    box_h = _size(item)[1]
    assert box_h == pytest.approx(one_line, abs=0.05)
    assert _drag(view, scene, item, GRIP_RM, (-110.0, 0.0)) == []
    assert _size(item)[1] == pytest.approx(box_h, abs=0.05)           # never two lines
    assert item._content_height_mm() == pytest.approx(one_line, abs=0.05)
    w = _size(item)[0]
    assert w < 120.0                                                   # it did narrow
    # One step narrower really does break the line: this is the stopping width.
    from firepro3d.sketch_adapters import _content_height_at
    s = item.scale() or 1.0
    assert _content_height_at(item, (w - 1.0) / s) * s > one_line + 0.5


def test_a_tied_wrap_off_box_narrows_without_refusal(block_view):
    view, scene = block_view
    item = _box(scene, text="WORD WORD", w=120.0, h=0.0)
    item.set_property("Wrap", False)
    QApplication.processEvents()
    _tie_into_network(scene, item)
    assert CONFLICT_STATUS not in _drag(view, scene, item, GRIP_RM, (-5.0, 0.0))


def test_a_tied_box_refuses_a_move_only_when_the_tie_holds_it(block_view):
    """N5: a real conflict still reports: the centre pinned to the origin holds the box."""
    view, scene = block_view
    item = _box(scene)
    _pin(scene, item, "center")
    before = item.grip_points()[8]
    _drag(view, scene, item, 8, (40.0, 30.0))
    after = item.grip_points()[8]
    assert (after.x(), after.y()) == pytest.approx((before.x(), before.y()), abs=1e-3)


def test_an_untied_box_keeps_its_far_edge_past_its_text(block_view):
    """N3: the silent slide. Top grip past the text: the bottom edge never moves."""
    view, scene = block_view
    item = _box(scene)
    bottom = item.manip_bounds().bottom()
    content = item._content_height_mm()
    assert _drag(view, scene, item, GRIP_TM, (0.0, 80.0)) == []
    r = item.manip_bounds()
    assert r.bottom() == pytest.approx(bottom, abs=0.05)
    assert r.height() == pytest.approx(content, abs=0.05)


def test_an_untied_box_grows_in_height_when_narrowed(block_view):
    """N4's last line: untied keeps today's reflow, the box grows."""
    view, scene = block_view
    item = _box(scene, text="WORD WORD", w=120.0, h=0.0)
    one_line = _size(item)[1]
    assert _drag(view, scene, item, GRIP_RM, (-90.0, 0.0)) == []
    assert _size(item)[1] > one_line + 1.0


def test_an_untied_box_stops_at_the_minimum_width_with_its_left_edge_fixed(block_view):
    view, scene = block_view
    item = _box(scene)
    left = item.manip_bounds().left()
    _drag(view, scene, item, GRIP_RM, (-300.0, 0.0))
    r = item.manip_bounds()
    assert r.left() == pytest.approx(left, abs=0.05)
    from firepro3d.constants import MIN_TEXT_WRAP_WIDTH_MM
    assert r.width() == pytest.approx(MIN_TEXT_WRAP_WIDTH_MM, abs=0.05)


def test_a_disabled_tie_does_not_stop_the_box(block_view):
    """Review of N4: only a tie that holds the box stops it. A suppressed one holds nothing."""
    view, scene = block_view
    item = _box(scene, text="WORD WORD", w=120.0, h=0.0)
    ctl = scene.constraint_ctl
    _pin(scene, item, "bl")
    for c in ctl.constraints_on(item):
        ctl.set_enabled(c.id, False)
    one_line = _size(item)[1]
    assert _drag(view, scene, item, GRIP_RM, (-90.0, 0.0)) == []
    assert _size(item)[1] > one_line + 1.0


def test_a_zero_height_box_axis_falls_back_to_the_plain_apply(block_view):
    """Review of N2: a box side with no length has no axis to measure along, so the reach
    keeps the plain apply instead of dividing by zero in a Qt event, which aborts."""
    from firepro3d.manip_handle import ReachGripHandle
    assert ReachGripHandle._box_axes([QPointF(5.0, 5.0)] * 8) is None
    view, scene = block_view
    item = _box(scene, text="", w=120.0, h=0.0, cell_padding_mm=0.0)
    item.set_property("Wrap", False)
    QApplication.processEvents()
    _pin(scene, item, "center")
    _drag(view, scene, item, GRIP_BM, (0.0, 20.0))
    QApplication.processEvents()
    assert item.scene() is scene
