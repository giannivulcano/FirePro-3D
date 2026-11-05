"""Top-level stacking in a block_editor scene (D1, D4, D8)."""
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QImage, QPainter

from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests._block_stack_helpers import ink, line_def, rect_def, render

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

# -- The scene's opaque-block order is cached; every route that changes it
#    must show in ink after a first paint has built it. ----------------------

def _prime(be, a):
    """Paint once so the cached order exists before the change under test.
    Not ``ink``: that hides and shows the block, which itself drops the order."""
    render(be, VIEW)


def test_a_deleted_then_restored_upper_block_hides_again(be):
    from firepro3d.block_instance import BlockInstance
    a, b = _pair(be)
    _prime(be, a)
    be.push_undo_state()
    be.delete_items([b])
    assert ink(be, a, OVER, VIEW) > 0              # gone: nothing hides it
    be.undo()
    low = next(i for i in be.items()
               if isinstance(i, BlockInstance) and i.definition().name == "A")
    assert ink(be, low, OVER, VIEW) == 0           # restored: hides again


def test_hiding_the_upper_block_after_a_paint_shows_the_lower(be):
    a, b = _pair(be)
    _prime(be, a)
    b.setVisible(False)
    assert ink(be, a, OVER, VIEW) > 0


def test_opaque_off_after_a_paint_shows_the_lower(be):
    a, b = _pair(be)
    _prime(be, a)
    b.set_opaque(False)
    assert ink(be, a, OVER, VIEW) > 0


def test_a_layer_height_swap_after_a_paint_reverses_the_order(be):
    a, b = _pair(be)
    _prime(be, a)
    a.set_layer_height(1)
    assert ink(be, a, OVER, VIEW) > 0


def test_a_removed_upper_block_after_a_paint_shows_the_lower(be):
    a, b = _pair(be)
    _prime(be, a)
    be.removeItem(b)
    assert ink(be, a, OVER, VIEW) > 0


def test_raising_a_block_reorders_two_opaque_blocks_after_a_paint(be):
    lo = be.place_block_instance(rect_def(be, "Lo", 100.0, 100.0).id, (0.0, 0.0))
    hi = be.place_block_instance(rect_def(be, "Hi", 100.0, 100.0).id, (30.0, 0.0))
    _prime(be, lo)
    lo.set_layer_height(1)                       # lo now over hi
    view = QRectF(-20, -20, 170, 140)
    assert ink(be, hi, QRectF(26, 20, 8, 60), view) == 0
    assert ink(be, lo, QRectF(96, 20, 8, 60), view) > 0


def test_a_block_added_above_after_a_paint_hides_the_lower(be):
    a = be.place_block_instance(line_def(be, "A").id, (0.0, 0.0))
    _prime(be, a)
    be.place_block_instance(rect_def(be, "B").id, (50.0, -50.0))
    assert ink(be, a, OVER, VIEW) == 0


def test_a_scene_default_flip_after_a_paint_takes_effect(be):
    a, b = _pair(be)
    _prime(be, a)
    be.opaque_blocks = False
    assert ink(be, a, OVER, VIEW) > 0


def test_equal_height_opaque_blocks_the_later_placed_one_hides_the_earlier(be):
    lo = be.place_block_instance(rect_def(be, "Lo", 100.0, 100.0).id, (0.0, 0.0))
    hi = be.place_block_instance(rect_def(be, "Hi", 100.0, 100.0).id, (30.0, 0.0))
    assert lo.zValue() == hi.zValue()
    # Qt's own painting order: the first placed is under the second.
    assert [i for i in be.items(Qt.SortOrder.AscendingOrder) if i in (lo, hi)] == [lo, hi]
    view = QRectF(-20, -20, 170, 140)
    lo_edge = QRectF(96, 20, 8, 60)     # lo's right edge, inside hi
    hi_edge = QRectF(26, 20, 8, 60)     # hi's left edge, inside lo
    assert ink(be, lo, lo_edge, view) == 0
    assert ink(be, hi, hi_edge, view) > 0


def test_a_plain_editor_paint_never_queries_the_scene(qapp):
    s = Model_Space(scene_role="block_editor")        # opaque_blocks stays False
    try:
        a = s.place_block_instance(line_def(s, "A").id, (0.0, 0.0))
        s.place_block_instance(rect_def(s, "B").id, (50.0, -50.0))
        calls = []
        real = s.items
        s.items = lambda *args, **kw: (calls.append(1), real(*args, **kw))[1]
        render(s, VIEW)
        del s.items
        assert not calls
    finally:
        s.cleanup()


# -- A posed upper block: the cover is its mirrored / scaled outline, not the
#    definition's. The covered extents below are worked out by hand from the
#    definition's geometry (nothing here reads ``opaque_mask``). ---------------

WIDE = QRectF(-20, -120, 440, 240)


def test_a_mirrored_upper_block_covers_its_mirrored_side(be):
    """B is a 100 x 60 rectangle from its corner. Placed at x=150 and mirrored
    (local x -> -x) it spans x 50..150, y -30..30; unmirrored it would span
    150..250. A's line runs x 0..400 at y 0. Primed with a paint first.
    RED: ``paint`` skips ``_cover_above``."""
    a = be.place_block_instance(line_def(be, "A", 400.0).id, (0.0, 0.0))
    b = be.place_block_instance(rect_def(be, "B", 100.0, 60.0).id, (150.0, -30.0))
    render(be, WIDE)
    b.set_block_mirrored(True)
    assert ink(be, a, QRectF(70, -4, 60, 8), WIDE) == 0      # inside 50..150
    assert ink(be, a, QRectF(170, -4, 60, 8), WIDE) > 0      # where an unmirrored B would be
    assert ink(be, a, QRectF(10, -4, 30, 8), WIDE) > 0       # left of B


def test_a_scaled_upper_block_covers_its_scaled_size(be):
    """B is a 100 x 100 rectangle from its corner. Placed at (100, -100) and
    scaled 2x it spans x 100..300, y -100..100; unscaled it would span
    100..200. A's line runs x 0..400 at y 0. Primed with a paint first.
    RED: ``paint`` skips ``_cover_above``."""
    a = be.place_block_instance(line_def(be, "A", 400.0).id, (0.0, 0.0))
    b = be.place_block_instance(rect_def(be, "B", 100.0, 100.0).id, (100.0, -100.0))
    render(be, WIDE)
    b.set_block_scale(2.0)
    assert ink(be, a, QRectF(220, -4, 60, 8), WIDE) == 0     # inside 100..300, past the unscaled 200
    assert ink(be, a, QRectF(320, -4, 60, 8), WIDE) > 0      # right of B
    assert ink(be, a, QRectF(10, -4, 60, 8), WIDE) > 0       # left of B
