"""G5 (AC9, AC6 hover): Room-mode hover through posted mouse moves on a shown view.
Assertions: the preview tuple (path, open_end, enclosed, covered, tone), the painted tint's
red-minus-green shift (amber warn > 0, green ok < 0 for both theme variants: dark ok #6FBE93 /
warn #D9A24A, light ok #2f9e63 / warn #b46500 -- theme.py), and a viewport repaint."""
import pytest
from PyQt6.QtCore import QEvent, QObject, QPointF
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.constants import REGION_FINDER_DEBOUNCE_MS
from tests._room_detect_helpers import (add_wall, click_room, frame, rect_walls, room_view,
                                        settle, wall_tool)
from tests._snap_polish_helpers import close_view, move

# Pixel sample in the left bay (x 100..2900, y 100..3900): 400 mm off the faces (the 1.5 px
# preview outline) and ~1580 mm from the bay's vertex mean (1500, 2000), where a placed room's
# tag sits -- at 0.1 px/mm that is 40 px / 158 px away.
SAMPLE = QPointF(500, 500)


class _Paints(QObject):
    """Counts Paint events delivered to *widget* from now on."""
    def __init__(self, widget):
        super().__init__()
        self.n = 0
        widget.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Paint:
            self.n += 1
        return False


def _px(view, scene_pt):
    img = view.grab().toImage()
    vp = view.viewportTransform().map(scene_pt)
    vo = view.viewport().mapTo(view, vp.toPoint())
    return QColor(img.pixel(vo.x(), vo.y()))


def _shift(before, after):
    """Red-minus-green change of a 25 % tint: > 0 amber (warn), < 0 green (ok)."""
    return (after.red() - before.red()) - (after.green() - before.green())


@pytest.fixture
def tee(qapp):
    view, scene = room_view()
    rect_walls(scene, 0, 0, 6000, 4000)
    wall_tool(scene, (3000, 0), (3000, 4000))
    scene.set_mode("room")
    frame(view, QPointF(3000, 2000), 0.1)
    yield view, scene
    close_view(view, scene)


def test_hover_placeable_face_is_ok_green_and_repaints(tee):
    view, scene = tee
    _px(view, SAMPLE)                                    # discard the first-paint grab
    before = _px(view, SAMPLE)
    paints = _Paints(view.viewport())
    move(view, QPointF(1500, 2500))
    assert paints.n > 0
    path, open_end, enclosed, covered, tone = scene._pick_region_preview
    assert enclosed and not covered and open_end is None and tone == "ok"
    assert path.contains(SAMPLE) and not path.contains(QPointF(4500, 2000))
    QApplication.processEvents()
    assert _shift(before, _px(view, SAMPLE)) < 0


def test_hover_existing_room_is_warn_amber(tee):
    view, scene = tee
    click_room(view, QPointF(1500, 2000))
    assert len(scene._rooms) == 1 and scene._pick_region_preview is None   # premise; cleared on press
    frame(view, QPointF(3000, 2000), 0.1)
    _px(view, SAMPLE)
    before = _px(view, SAMPLE)                           # room fill, no overlay
    move(view, QPointF(1500, 2500))
    path, open_end, enclosed, covered, tone = scene._pick_region_preview
    assert enclosed and tone == "warn" and path.contains(SAMPLE)
    QApplication.processEvents()
    assert _shift(before, _px(view, SAMPLE)) > 0


def test_slow_scene_hover_debounces_then_repaints(tee):
    view, scene = tee
    move(view, QPointF(1500, 2500))
    assert scene._pick_region_preview[4] == "ok" and scene._room_arr is not None   # premise: built
    scene._room_slow = True                              # premise: last build was slow (D-A25)
    move(view, QPointF(4500, 2500))
    assert scene._pick_region_preview[0].contains(QPointF(1500, 2500))            # not yet re-run
    paints = _Paints(view.viewport())
    QTest.qWait(REGION_FINDER_DEBOUNCE_MS + 200)
    assert scene._pick_region_preview[0].contains(QPointF(4500, 2500))
    assert paints.n > 0


def test_hover_in_wall_shows_nothing(tee):
    view, scene = tee
    move(view, QPointF(1500, 2500))
    move(view, QPointF(3000, 0))                          # bottom wall centreline: inside its body
    assert scene._pick_region_preview is None


def test_hover_open_marks_nearest_free_end(qapp):
    """Gap 1 (D-R6): U (0,4000)->(0,0)->(6000,0)->(6000,4000) via the wall tool;
    free-end caps centred on (0,4000) and (6000,4000); from (1000,2000) the nearer is (0,4000)."""
    view, scene = room_view()
    try:
        for p1, p2 in (((0, 4000), (0, 0)), ((0, 0), (6000, 0)), ((6000, 0), (6000, 4000))):
            wall_tool(scene, p1, p2)
        scene.set_mode("room")
        frame(view, QPointF(3000, 2000), 0.1)
        move(view, QPointF(1000, 2000))
        path, open_end, enclosed, covered, tone = scene._pick_region_preview
        assert path is None and not enclosed and not covered and tone is None
        assert (open_end.x(), open_end.y()) == pytest.approx((0.0, 4000.0), abs=1e-6)
    finally:
        close_view(view, scene)


def test_hover_gap_marks_open_end(qapp):
    """AC6 / Gap 1: right wall starts 5 mm above the bottom face (y = 105); caps: right wall
    (5900,105)-(6100,105) -> (6000,105); bottom wall end (6000,-100)-(6000,100) -> (6000,0).
    From (3000,2000): |(3000,-1895)| = 3548.5 < |(3000,-2000)| = 3605.6 -> (6000, 105)."""
    view, scene = room_view()
    try:
        add_wall(scene, (0, 0), (6000, 0))
        add_wall(scene, (6000, 105), (6000, 4000))
        add_wall(scene, (6000, 4000), (0, 4000))
        add_wall(scene, (0, 4000), (0, 0))
        settle(scene)
        scene.set_mode("room")
        frame(view, QPointF(3000, 2000), 0.1)
        move(view, QPointF(3000, 2000))
        path, open_end, enclosed, covered, tone = scene._pick_region_preview
        assert path is None and not enclosed
        assert (open_end.x(), open_end.y()) == pytest.approx((6000.0, 105.0), abs=1e-6)
    finally:
        close_view(view, scene)
