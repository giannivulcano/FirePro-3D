"""Compiled stacking: mask shape, band order, nested clips (D1, D2, D4, D5)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import CircleItem, LineItem, RectangleItem
from firepro3d.constants import MASK_GAP_MM
from firepro3d.model_space import Model_Space
from firepro3d.render_op import STROKE, TEXT, ops_mask
from tests._block_stack_helpers import ink, l_def, line_def, rect_def

VIEW = QRectF(-20, -60, 260, 180)


@pytest.fixture
def sc(qapp):
    s = Model_Space()
    yield s
    s.cleanup()


def _rec(d, x, y, **kw):
    return {"type": "block_instance", "block_id": d.id, "pos": [x, y], "rotation": 0.0, **kw}


def _parent(sc, prims, kind="block"):
    p = BlockDefinition.new(name="P", library="L" if kind == "block" else "",
                            series="", primitives=prims, origin=(0.0, 0.0), kind=kind)
    sc.register_block_definition(p)
    return p


def test_mask_is_the_closed_geometry(sc):
    """Rewritten for amended D2 (silhouette): a closed outline fills, outset by
    at most half the gap width."""
    m = ops_mask(rect_def(sc).render_ops())
    assert m.contains(QPointF(50, 50)) and not m.contains(QPointF(150, 50))
    half = MASK_GAP_MM / 2
    assert m.contains(QPointF(100 + half - 0.1, 50))          # outset, but only by half the gap
    assert not m.contains(QPointF(100 + half + 0.2, 50))
    assert not m.contains(QPointF(-half - 0.2, 50))


def test_mask_of_two_closed_shapes_is_their_union(sc):
    a, b = rect_def(sc, "A"), rect_def(sc, "B", 40, 40)
    p = _parent(sc, [_rec(a, 0, 0), _rec(b, 300, 0)])
    m = ops_mask(p.render_ops())
    assert m.contains(QPointF(50, 50)) and m.contains(QPointF(320, 20))
    assert not m.contains(QPointF(200, 20))              # not the bounding box


def test_open_geometry_has_no_bounding_box_fallback(sc):
    """Rewritten for amended D2: open linework masks its own silhouette, never
    the bounding box; no ink is no mask."""
    d = BlockDefinition.new(name="Vee", library="L", series="", origin=(0.0, 0.0), primitives=[
        LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict(),
        LineItem(QPointF(0, 0), QPointF(0, 100)).to_dict()])
    sc.register_block_definition(d)
    m = ops_mask(d.render_ops())
    assert m.contains(QPointF(50, 0)) and m.contains(QPointF(0, 50))     # the lines themselves
    assert not m.contains(QPointF(80, 80))                               # the bounding box corner
    assert ops_mask([]).isEmpty()


def _text_def(sc, with_rect=False):
    prims = [{"type": "text", "text": "FPT", "x": 150.0, "y": 20.0, "height_mm": 20.0}]
    if with_rect:
        prims.append(RectangleItem(QPointF(0, 0), QPointF(100, 100)).to_dict())
    d = BlockDefinition.new(name="Txt", library="L", series="", origin=(0.0, 0.0),
                            primitives=prims)
    sc.register_block_definition(d)
    return d


def test_text_never_counts_toward_the_mask(sc):
    """A text-only op list, and a definition whose only op is text, mask nothing."""
    d = _text_def(sc)
    ops = d.render_ops()
    assert [op.kind for op in ops] == [TEXT]
    assert ops_mask(ops).isEmpty()
    assert d.silhouette().isEmpty()


def test_text_beside_a_rect_does_not_widen_its_mask(sc):
    d = _text_def(sc, with_rect=True)
    assert TEXT in {op.kind for op in d.render_ops()}
    m = ops_mask(d.render_ops())
    assert m.contains(QPointF(50, 50))
    assert not m.contains(QPointF(150, 30))              # where the glyphs sit
    assert m.boundingRect().right() < 100 + MASK_GAP_MM


def test_a_curved_mask_keeps_its_curve(sc):
    d = BlockDefinition.new(name="C", library="L", series="", origin=(0.0, 0.0),
                            primitives=[CircleItem(QPointF(0, 0), 100.0).to_dict()])
    sc.register_block_definition(d)
    m = ops_mask(d.render_ops())
    assert m.contains(QPointF(70, 70)) and not m.contains(QPointF(72, 72))


def test_own_primitives_compile_after_nested_blocks(sc):
    a = rect_def(sc)
    own = LineItem(QPointF(0, 0), QPointF(10, 0)).to_dict()
    p = _parent(sc, [own, _rec(a, 0, 0)])
    ops = p.render_ops()
    assert ops[-1].path.boundingRect().height() == 0     # the own line paints last
    assert p._op_groups[-1] == 0 and p._op_groups[0] != 0  # joint containers follow the order


def test_nested_order_follows_layer_height_stably(sc):
    a, b, c = line_def(sc, "A", 10), line_def(sc, "B", 20), line_def(sc, "C", 30)
    p = _parent(sc, [_rec(a, 0, 0, layer_height=5), _rec(b, 0, 0), _rec(c, 0, 0)])
    assert [o.path.boundingRect().width() for o in p.render_ops()] == [20, 30, 10]


def test_only_a_lower_nested_block_is_clipped(sc):
    low, top = line_def(sc, "Low"), rect_def(sc, "Top")
    p = _parent(sc, [_rec(top, 50, -50, opaque=True, layer_height=1), _rec(low, 0, 0),
                     LineItem(QPointF(0, 10), QPointF(200, 10)).to_dict()])
    ops = p.render_ops()
    assert ops[0].clip_out is not None and ops[0].clip_out.contains(QPointF(100, 0))
    assert all(o.clip_out is None for o in ops[1:])      # the block above and the parent's line


def test_a_nested_block_is_not_opaque_by_default_in_a_block(sc):
    low, top = line_def(sc, "Low"), rect_def(sc, "Top")
    p = _parent(sc, [_rec(low, 0, 0), _rec(top, 50, -50)])
    assert all(o.clip_out is None for o in p.render_ops())


def test_a_nested_block_is_opaque_by_default_in_a_schematic(sc):
    low, top = line_def(sc, "Low"), rect_def(sc, "Top")
    p = _parent(sc, [_rec(low, 0, 0), _rec(top, 50, -50)], kind="schematic")
    assert p.render_ops()[0].clip_out is not None


def test_a_missing_nested_block_has_no_mask(sc):
    low = line_def(sc, "Low")
    p = _parent(sc, [_rec(low, 0, 0), {"type": "block_instance", "block_id": "gone",
                                       "pos": [0, 0], "rotation": 0.0, "opaque": True}])
    assert p.render_ops()[0].clip_out is None


@pytest.mark.parametrize("mirrored,scale,inside,outside", [
    (True, 1.0, (-100, 0), (100, 0)),
    (False, 2.0, (200, 0), (60, 0)),
])
def test_a_variant_clips_in_the_right_place(sc, mirrored, scale, inside, outside):
    low, top = line_def(sc, "Low"), rect_def(sc, "Top")
    p = _parent(sc, [_rec(low, 0, 0), _rec(top, 50, -50, opaque=True, layer_height=1)])
    clip = p.render_ops_variant(mirrored, scale)[0].clip_out
    assert clip.contains(QPointF(*inside)) and not clip.contains(QPointF(*outside))


def test_ops_of_one_covered_block_share_one_clip_through_a_variant(sc):
    low = BlockDefinition.new(name="Two", library="L", series="", origin=(0.0, 0.0), primitives=[
        LineItem(QPointF(0, 0), QPointF(200, 0)).to_dict(),
        LineItem(QPointF(0, 5), QPointF(200, 5)).to_dict()])
    sc.register_block_definition(low)
    top = rect_def(sc, "Top")
    p = _parent(sc, [_rec(low, 0, 0), _rec(top, 50, -50, opaque=True, layer_height=1)])
    v = p.render_ops_variant(True, 1.0)
    assert v[0].clip_out is v[1].clip_out


def test_plan_placement_hides_the_lower_nested_block_only(sc):
    """AC: lower nested hidden; the parent's line and a plan item stay."""
    low, top = line_def(sc, "Low"), rect_def(sc, "Top")
    under = LineItem(QPointF(0, 20), QPointF(200, 20))
    sc.addItem(under)
    p = _parent(sc, [_rec(low, 0, 0), _rec(top, 50, -50, opaque=True, layer_height=1),
                     LineItem(QPointF(0, 10), QPointF(200, 10)).to_dict()])
    inst = sc.place_block_instance(p.id, (0.0, 0.0))
    assert ink(sc, inst, QRectF(60, -4, 80, 8), VIEW) == 0        # the low line is hidden
    assert ink(sc, inst, QRectF(10, -4, 30, 8), VIEW) > 0         # outside the mask it shows
    assert ink(sc, inst, QRectF(60, 6, 80, 8), VIEW) > 0          # the parent's own line
    assert ink(sc, under, QRectF(60, 16, 80, 8), VIEW) > 0        # the plan item


def test_clipped_ops_paint_through_the_linetype_loop_too(sc):
    low, top = line_def(sc, "Low"), rect_def(sc, "Top")
    p = _parent(sc, [_rec(low, 0, 0), _rec(top, 50, -50, opaque=True, layer_height=1)])
    i = sc.place_block_instance(p.id, (0.0, 0.0))
    calls = []
    orig = i._paint_plain_ops
    i._paint_plain_ops = lambda *a, **k: calls.append(1) or orig(*a, **k)
    i._linetype_ids = lambda ops: frozenset({"x"})       # forces the linetype branch
    i._lt_ref_cache = None
    assert ink(sc, i, QRectF(10, -4, 30, 8), VIEW) > 0
    assert ink(sc, i, QRectF(60, -2, 30, 4), VIEW) == 0
    assert not calls


def _count_masks(monkeypatch):
    import firepro3d.render_op as ro
    calls = []
    orig = ro.ops_mask
    monkeypatch.setattr(ro, "ops_mask", lambda ops: calls.append(1) or orig(ops))
    return calls


def test_the_bottom_run_builds_no_mask(sc, monkeypatch):
    low, top = line_def(sc, "Low"), rect_def(sc, "Top")
    p = _parent(sc, [_rec(low, 0, 0), _rec(top, 50, -50)], kind="schematic")
    calls = _count_masks(monkeypatch)
    ops = p.render_ops()
    assert len(calls) == 1                                   # the upper block's only
    assert ops[0].clip_out is not None and ops[0].clip_out.contains(QPointF(100, 0))
    assert ops[1].clip_out is None


def test_a_single_nested_record_builds_no_mask(sc, monkeypatch):
    top = rect_def(sc, "Top")
    p = _parent(sc, [_rec(top, 50, -50)], kind="schematic")
    calls = _count_masks(monkeypatch)
    ops = p.render_ops()
    assert not calls
    assert all(o.clip_out is None for o in ops)


def test_a_fixed_size_covered_run_survives_a_render_at_another_zoom(qapp):
    """The cover clip's kept frame must hold what the painter's own scale
    paints, not the frame sized at the view's zoom (annotative Fixed size)."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor, QImage, QPainter
    from firepro3d.geometry_2d import RectangleItem
    ms = Model_Space(scene_role="plan")
    try:
        ln = LineItem(QPointF(-3, 2), QPointF(3, 2))
        ln.style["colour"] = "#ffffff"
        low = BlockDefinition.new(name="Low", library="L", series="S", origin=(0.0, 0.0),
                                  primitives=[ln.to_dict()])
        top = BlockDefinition.new(name="Top", library="L", series="S", origin=(0.0, 0.0),
                                  primitives=[RectangleItem(QPointF(-1, 1), QPointF(1, 3)).to_dict()])
        ms.register_block_definition(low)
        ms.register_block_definition(top)
        par = BlockDefinition.new(name="P", library="L", series="S", origin=(0.0, 0.0),
                                  primitives=[_rec(low, 0, 0),
                                              _rec(top, 0, 0, opaque=True, layer_height=1)])
        par.scale_mode = "annotative"
        par.annotative_screen = "fixed"
        ms.register_block_definition(par)
        ms.place_block_instance(par.id, (0.0, 0.0), level=ms.active_level)
        px, scale = 400, 0.25
        w = px / scale
        img = QImage(px, px, QImage.Format.Format_RGB32)
        img.fill(0xFF101010)
        p = QPainter(img)
        ms.render(p, QRectF(0, 0, px, px), QRectF(-w / 2, -w / 2, w, w),
                  Qt.AspectRatioMode.IgnoreAspectRatio)
        p.end()
        c = px // 2
        ink = [x for y in range(c + 10, c + 16) for x in range(c + 9, c + 16)
               if QColor(img.pixel(x, y)).lightness() > 80]
        assert ink                      # outside the mask (6 px) and the view-zoom frame
    finally:
        ms.cleanup()


def test_a_nested_l_shape_hides_its_arm_and_not_its_corner(sc):
    """Compiled path: the L sits at (150, -50), so its arm is x 150..190,
    y -50..50 and its bounding box corner x 190..250, y -10..50 holds the low
    line, which stays drawn. (An L left unposed would sit at x 0..100.)"""
    low, top = line_def(sc, "Low", 300.0), l_def(sc)
    p = _parent(sc, [_rec(low, 0, 0), _rec(top, 150, -50, opaque=True, layer_height=1)])
    inst = sc.place_block_instance(p.id, (0.0, 0.0))
    view = QRectF(-20, -60, 300, 180)
    assert ink(sc, inst, QRectF(155, -4, 30, 8), view) == 0
    assert ink(sc, inst, QRectF(200, -4, 40, 8), view) > 0


def test_a_mirrored_variant_of_an_l_shape_clips_its_mirrored_arm(sc):
    low, top = line_def(sc, "Low"), l_def(sc)
    p = _parent(sc, [_rec(low, 0, 0), _rec(top, 150, -50, opaque=True, layer_height=1)])
    clip = p.render_ops_variant(True, 1.0)[0].clip_out        # the arm x 150..190 becomes -190..-150
    assert clip.contains(QPointF(-170, 0)) and not clip.contains(QPointF(-220, 0))


def test_the_silhouette_is_traced_once_per_definition(sc, monkeypatch):
    d = l_def(sc)
    calls = _count_masks(monkeypatch)
    a = sc.place_block_instance(d.id, (0.0, 0.0))
    b = sc.place_block_instance(d.id, (300.0, 0.0))
    c = sc.place_block_instance(d.id, (0.0, 300.0))
    b.set_block_mirrored(True)
    c.set_block_scale(2.0)
    for i in (a, b, c):
        i.opaque_mask()
    a.set_block_pos(10.0, 10.0)
    a.opaque_mask()
    assert len(calls) == 1
    assert b.opaque_mask().contains(QPointF(280, 50)) and not b.opaque_mask().contains(QPointF(230, 70))
    assert c.opaque_mask().contains(QPointF(40, 450)) and not c.opaque_mask().contains(QPointF(150, 450))
