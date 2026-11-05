"""Top-level stacking in a block_editor scene (D1, D4, D8)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QImage, QPainter

from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests._block_stack_helpers import ink, line_def, rect_def

VIEW = QRectF(-20, -60, 260, 180)
OVER = QRectF(60, -4, 80, 8)      # inside the top block
BESIDE = QRectF(10, -4, 30, 8)    # outside it


@pytest.fixture
def be(qapp):
    s = Model_Space(scene_role="block_editor")
    s.opaque_blocks = True
    yield s
    s.cleanup()


def _pair(be):
    a = be.place_block_instance(line_def(be, "A").id, (0.0, 0.0))
    b = be.place_block_instance(rect_def(be, "B").id, (50.0, -50.0))
    return a, b


def test_the_upper_block_hides_the_lower(be):
    a, b = _pair(be)
    assert ink(be, a, BESIDE, VIEW) > 0
    assert ink(be, a, OVER, VIEW) == 0


def test_raising_the_lower_block_reverses_it(be):
    a, b = _pair(be)
    a.set_layer_height(1)
    assert ink(be, a, OVER, VIEW) > 0


def test_opaque_off_shows_through(be):
    a, b = _pair(be)
    b.set_opaque(False)
    assert ink(be, a, OVER, VIEW) > 0


def test_a_line_crossing_a_block_stays_visible(be):
    a, b = _pair(be)
    line = LineItem(QPointF(0, 20), QPointF(200, 20))
    be.addItem(line)
    assert ink(be, line, QRectF(60, 16, 80, 8), VIEW) > 0


def test_moving_the_upper_block_updates_the_cover(be):
    a, b = _pair(be)
    assert ink(be, a, OVER, VIEW) == 0
    b.set_block_pos(50.0, 300.0)
    assert ink(be, a, OVER, VIEW) > 0


def test_a_hidden_upper_block_hides_nothing(be):
    a, b = _pair(be)
    b.setVisible(False)
    assert ink(be, a, OVER, VIEW) > 0


def test_a_plan_scene_never_clips_blocks(qapp):
    sc = Model_Space()
    sc.opaque_blocks = True
    a, b = _pair(sc)
    a.setZValue(0)
    b.setZValue(1)
    assert ink(sc, a, OVER, VIEW) > 0
    sc.cleanup()


def test_an_opaque_interior_is_a_hit(be):
    a, b = _pair(be)
    centre = QPointF(100, 0)
    assert b.halo_area_path().contains(centre)
    assert b.shape().contains(centre)
    b.set_opaque(False)
    assert not b.halo_area_path().contains(centre)
    assert not b.shape().contains(centre)


def test_a_covered_block_keeps_its_ink_in_a_render_at_another_zoom(be):
    """The cover clip's kept frame must hold what the painter's own scale
    paints, not the frame sized at the view's zoom: a screen-width stroke is
    far wider than the item's rect when rendered zoomed out (as a second view
    or print does). Annotative Fixed size cannot show it here, because the
    editor scenes do not scale annotative blocks."""
    from PyQt6.QtCore import Qt
    a = be.place_block_instance(line_def(be, "A", 4000.0).id, (0.0, 0.0))
    b = be.place_block_instance(rect_def(be, "B", 1000.0, 1000.0).id, (1500.0, -500.0))
    px, w = 200, 10000.0

    def shot():
        img = QImage(px, px, QImage.Format.Format_RGB32)
        img.fill(0xFF101010)
        p = QPainter(img)
        be.render(p, QRectF(0, 0, px, px), QRectF(-1000, -w / 2, w, w),
                  Qt.AspectRatioMode.IgnoreAspectRatio)
        p.end()
        return img

    def line_ink():
        with_a = shot()
        a.setVisible(False)
        without = shot()
        a.setVisible(True)
        return sum(1 for y in range(px) for x in range(45)       # left of the cover
                   if with_a.pixel(x, y) != without.pixel(x, y))

    covered = line_ink()
    b.setVisible(False)
    uncovered = line_ink()
    assert uncovered > 0
    assert covered == uncovered