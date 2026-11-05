"""Top-level stacking in a block_editor scene (D1, D4, D8)."""
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QImage, QPainter, QTransform

from firepro3d.filled_region import FilledRegionItem
from firepro3d.geometry_2d import (ArcItem, CircleItem, LineItem, PolylineItem,
                                   RectangleItem)
from firepro3d.model_space import Model_Space
from tests._block_stack_helpers import ink, l_def, line_def, lines_def, rect_def, render

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


@pytest.fixture
def ordinary(qapp):
    s = Model_Space(scene_role="block_editor")      # opaque_blocks stays False: not a schematic
    yield s
    s.cleanup()


def test_a_line_crossing_an_opaque_block_stays_visible_in_an_ordinary_editor(ordinary):
    """D5 for ordinary blocks: an Opaque block hides only the blocks below it.
    (A schematic hides loose lines too; see the schematic tests below.)"""
    a, b = _pair(ordinary)
    b.set_opaque(True)
    assert ink(ordinary, a, OVER, VIEW) == 0                  # the block really is opaque
    line = LineItem(QPointF(0, 20), QPointF(200, 20))
    ordinary.addItem(line)
    assert ink(ordinary, line, QRectF(60, 16, 80, 8), VIEW) > 0


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


# -- The mask is the block's silhouette (amended D2): its outline traced from
#    connected linework, not the closed shapes or the bounding box. The covered
#    extents are worked out by hand from the geometry. ------------------------

def _sq(x0, y0, x1, y1):
    return [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
            ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]


def _under(be, upper_def, at, line=200.0, **kw):
    """A's horizontal line along y = 0, and the upper block placed at *at*."""
    a = be.place_block_instance(line_def(be, "A", line).id, (0.0, 0.0))
    b = be.place_block_instance(upper_def.id, at)
    return a, b


def test_an_outline_of_four_separate_lines_masks_its_interior(be):
    a, b = _under(be, lines_def(be, "Box", _sq(0, 0, 100, 100)), (50.0, -50.0))
    assert ink(be, a, QRectF(60, -4, 80, 8), VIEW) == 0       # inside the outline
    assert ink(be, a, BESIDE, VIEW) > 0                       # left of it


def test_a_lower_blocks_ink_in_the_corner_of_an_l_shape_stays_drawn(be):
    """The smoke bug. The L's arms are x 50..150, y -50..-10 and x 50..90,
    y -50..50; its bounding box corner is x 90..150, y -10..50, and A's line
    runs through it at y 0."""
    a, b = _under(be, l_def(be), (50.0, -50.0))
    assert ink(be, a, QRectF(55, -4, 30, 8), VIEW) == 0       # under the vertical arm
    assert ink(be, a, QRectF(100, -4, 40, 8), VIEW) > 0       # the empty corner: drawn
    assert ink(be, a, BESIDE, VIEW) > 0


def test_a_gap_of_six_tenths_mm_in_an_outline_still_fills(be):
    segs = _sq(0, 0, 100, 100)[:3] + [((0, 0), (0, 99.4))]    # the left side stops 0.6 short
    a, b = _under(be, lines_def(be, "Gap", segs), (50.0, -50.0))
    assert ink(be, a, QRectF(60, -4, 80, 8), VIEW) == 0


def test_two_disjoint_pieces_each_mask_and_the_space_between_does_not(be):
    segs = _sq(0, 50, 40, 90) + _sq(100, 50, 140, 90)         # x 50..90 and 150..190, y -20..20
    a, b = _under(be, lines_def(be, "Two", segs), (50.0, -70.0))
    assert ink(be, a, QRectF(55, -4, 30, 8), VIEW) == 0
    assert ink(be, a, QRectF(155, -4, 30, 8), VIEW) == 0
    assert ink(be, a, QRectF(100, -4, 40, 8), VIEW) > 0       # between them: drawn


def test_a_closed_ring_with_a_hole_stays_opaque_in_the_hole(be):
    d = lines_def(be, "Ring", [], rects=[(0, 0, 100, 100), (30, 30, 70, 70)])
    a, b = _under(be, d, (50.0, -50.0))                       # the hole is x 80..120, y -20..20
    assert ink(be, a, QRectF(85, -4, 30, 8), VIEW) == 0
    assert ink(be, a, BESIDE, VIEW) > 0


def test_the_halo_area_of_an_l_shape_misses_its_empty_corner(be):
    a, b = _under(be, l_def(be), (50.0, -50.0))
    assert b.halo_area_path().contains(QPointF(70, 0))        # the vertical arm
    assert not b.halo_area_path().contains(QPointF(120, 20))  # the empty corner


def test_a_mirrored_l_shape_masks_its_mirrored_arm(be):
    """At x=150 and mirrored the arms are x 50..150, y -50..-10 and x 110..150,
    y -50..50; the empty corner is x 50..110, y -10..50."""
    a, b = _under(be, l_def(be), (150.0, -50.0))
    render(be, VIEW)
    b.set_block_mirrored(True)
    assert ink(be, a, QRectF(115, -4, 30, 8), VIEW) == 0      # under the mirrored arm
    assert ink(be, a, QRectF(60, -4, 40, 8), VIEW) > 0        # the mirrored corner: drawn


def test_a_scaled_l_shape_masks_its_scaled_arm(be):
    """At (50, -120) and scaled 2x the arms are x 50..250, y -120..-40 and
    x 50..130, y -120..80; the empty corner is x 130..250, y -40..80."""
    a = be.place_block_instance(line_def(be, "A", 300.0).id, (0.0, 0.0))
    b = be.place_block_instance(l_def(be).id, (50.0, -120.0))
    render(be, WIDE)
    b.set_block_scale(2.0)
    assert ink(be, a, QRectF(60, -4, 60, 8), WIDE) == 0       # under the scaled arm
    assert ink(be, a, QRectF(150, -4, 60, 8), WIDE) > 0       # the scaled corner: drawn


# -- A schematic: an opaque block hides the loose lines, arcs, rectangles,
#    circles and polylines under it (D4, amended 2026-11-05) ------------------
#    The square block B covers x 50..150, y -50..50 (its mask is outset by half
#    MASK_GAP_MM); every extent below is worked out by hand from that.

def _arc():
    return ArcItem(QPointF(0, 0), 100.0, 0.0, 270.0)           # a circle's three quarters


def _polyline():
    pl = PolylineItem(QPointF(0, 20))
    pl.append_point(QPointF(100, 20))
    pl.append_point(QPointF(200, 20))
    pl.finalize()
    return pl


# kind -> (item, a region inside the block it crosses, a region outside it)
LOOSE = {
    "line": (lambda: LineItem(QPointF(0, 20), QPointF(200, 20)),
             QRectF(60, 16, 80, 8), QRectF(160, 16, 30, 8)),
    "polyline": (_polyline, QRectF(60, 16, 80, 8), QRectF(160, 16, 30, 8)),
    "rectangle": (lambda: RectangleItem(QPointF(20, 20), QPointF(180, 90)),
                  QRectF(60, 16, 80, 8), QRectF(60, 86, 80, 8)),
    "circle": (lambda: CircleItem(QPointF(0, 0), 100.0),
               QRectF(96, -4, 8, 8), QRectF(-4, 96, 8, 8)),
    "arc": (_arc, QRectF(96, -4, 8, 8), QRectF(-4, 96, 8, 8)),
}


def _loose(be, kind):
    make, inside, outside = LOOSE[kind]
    item = make()
    be.addItem(item)
    return item, inside, outside


@pytest.mark.parametrize("kind", sorted(LOOSE))
def test_an_opaque_block_hides_a_loose_primitive_under_it_in_a_schematic(be, kind):
    a, b = _pair(be)
    item, inside, outside = _loose(be, kind)
    assert ink(be, item, outside, VIEW) > 0                   # it is drawn where nothing covers it
    assert ink(be, item, inside, VIEW) == 0                   # and gone under the block


@pytest.mark.parametrize("kind", sorted(LOOSE))
def test_opaque_off_shows_a_loose_primitive_again(be, kind):
    a, b = _pair(be)
    item, inside, _outside = _loose(be, kind)
    b.set_opaque(False)
    assert ink(be, item, inside, VIEW) > 0


def test_a_loose_line_has_ink_right_up_to_the_silhouette(be):
    """The block's right edge is x 150; its mask reaches 150.5."""
    a, b = _pair(be)
    line = LineItem(QPointF(0, 20), QPointF(200, 20))
    be.addItem(line)
    assert ink(be, line, QRectF(151.5, 16, 3, 8), VIEW) > 0
    assert ink(be, line, QRectF(146, 16, 3, 8), VIEW) == 0


def test_a_loose_line_shows_in_the_empty_corner_of_an_l_shaped_block(be):
    """The L's arms are x 50..150, y -50..-10 and x 50..90, y -50..50; the
    bounding box corner x 90..150, y -10..50 is empty and the line runs
    through it at y 20."""
    be.place_block_instance(l_def(be).id, (50.0, -50.0))
    line = LineItem(QPointF(0, 20), QPointF(200, 20))
    be.addItem(line)
    assert ink(be, line, QRectF(55, 16, 30, 8), VIEW) == 0    # under the vertical arm
    assert ink(be, line, QRectF(100, 16, 40, 8), VIEW) > 0    # the corner: drawn


def test_moving_the_block_moves_the_gap_in_a_loose_line(be):
    a, b = _pair(be)
    line = LineItem(QPointF(0, 20), QPointF(300, 20))
    be.addItem(line)
    assert ink(be, line, QRectF(60, 16, 40, 8), VIEW) == 0
    b.set_block_pos(150.0, -50.0)                             # now x 150..250
    assert ink(be, line, QRectF(60, 16, 40, 8), VIEW) > 0
    assert ink(be, line, QRectF(170, 16, 40, 8), VIEW) == 0


def test_a_loose_line_moved_by_set_pos_is_hidden_where_it_now_is(be):
    """Drawn at x 0..200 and moved to x 100..300, y 20: ``pos`` is not the
    identity, so the cover must be mapped into the item's frame (unmapped, the
    cut would land at scene x 150..250 and hide the wrong stretch)."""
    a, b = _pair(be)
    line = LineItem(QPointF(0, -10), QPointF(200, -10))
    be.addItem(line)
    line.setPos(100.0, 30.0)
    assert ink(be, line, QRectF(110, 16, 30, 8), VIEW) == 0   # inside the block
    assert ink(be, line, QRectF(160, 16, 30, 8), VIEW) > 0    # past its edge


def test_a_rotated_loose_line_is_hidden_where_it_now_is(be):
    """From (100, -80), turned 90 degrees: the vertical x 100, y -80..120."""
    a, b = _pair(be)
    line = LineItem(QPointF(0, 0), QPointF(200, 0))
    be.addItem(line)
    line.setPos(100.0, -80.0)
    line.setRotation(90.0)
    assert ink(be, line, QRectF(96, -4, 8, 8), VIEW) == 0     # through the block
    assert ink(be, line, QRectF(96, 70, 8, 8), VIEW) > 0      # below it
    assert ink(be, line, QRectF(96, -58, 8, 6), VIEW) > 0     # above it


def _text(x=100.0, y=0.0):
    from firepro3d.text_item import TextAnnotationData, TextItem
    return TextItem(TextAnnotationData(text="HOSE", x=x, y=y, height_mm=30.0))


def _region():
    return FilledRegionItem.from_pieces([[CircleItem(QPointF(100, 0), 20.0)]])


@pytest.mark.parametrize("make", [_text, _region], ids=["text", "filled_region"])
def test_text_and_a_filled_region_stay_drawn_under_an_opaque_block(be, make):
    a, b = _pair(be)
    item = make()
    be.addItem(item)
    assert ink(be, item, QRectF(85, -15, 30, 30), VIEW) > 0


def _pick(be, p):
    return be.halo_candidates_at(QPointF(*p), 6.0, QTransform())


def test_a_click_on_the_hidden_part_of_a_line_picks_the_block(be):
    a, b = _pair(be)
    line = LineItem(QPointF(0, 20), QPointF(200, 20))
    be.addItem(line)
    hit = _pick(be, (100, 20))                                # under the block
    assert b in hit and line not in hit
    assert line in _pick(be, (175, 20))                       # beside it: the line


@pytest.mark.parametrize("make", [_text, _region], ids=["text", "filled_region"])
def test_text_and_a_filled_region_stay_clickable_under_an_opaque_block(be, make):
    a, b = _pair(be)
    item = make()
    be.addItem(item)
    assert item in _pick(be, (100, 0))


def test_a_rubber_band_still_takes_the_hidden_line(be):
    """D8 governs clicks; a band across the covered region selects as before."""
    a, b = _pair(be)
    line = LineItem(QPointF(0, 20), QPointF(200, 20))
    be.addItem(line)
    assert line in be.rubber_band_hits(QRectF(90, 10, 20, 20), True)


def test_object_snap_still_finds_the_end_of_a_hidden_line(qapp):
    from tests._snap_polish_helpers import close_view, make_view
    view, sc = make_view(role="block_editor", scale=1.0, mode=None)
    try:
        sc.opaque_blocks = True
        _pair(sc)
        line = LineItem(QPointF(0, 20), QPointF(100, 20))      # ends under the block
        sc.addItem(line)
        r = sc._snap_engine.find(QPointF(101, 21), sc, view.transform())
        assert r is not None and r.snap_type == "endpoint"
        assert (round(r.point.x(), 3), round(r.point.y(), 3)) == (100.0, 20.0)
    finally:
        close_view(view, sc)
