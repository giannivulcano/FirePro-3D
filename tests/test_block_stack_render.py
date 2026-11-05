"""Compiled stacking: mask shape, band order, nested clips (D1, D2, D4, D5)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import CircleItem, LineItem
from firepro3d.model_space import Model_Space
from firepro3d.render_op import STROKE, ops_mask
from tests._block_stack_helpers import ink, line_def, rect_def

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
    m = ops_mask(rect_def(sc).render_ops())
    assert m.contains(QPointF(50, 50)) and not m.contains(QPointF(150, 50))


def test_mask_of_two_closed_shapes_is_their_union(sc):
    a, b = rect_def(sc, "A"), rect_def(sc, "B", 40, 40)
    p = _parent(sc, [_rec(a, 0, 0), _rec(b, 300, 0)])
    m = ops_mask(p.render_ops())
    assert m.contains(QPointF(50, 50)) and m.contains(QPointF(320, 20))
    assert not m.contains(QPointF(200, 20))              # not the bounding box


def test_open_geometry_falls_back_to_its_bounding_box(sc):
    d = BlockDefinition.new(name="Vee", library="L", series="", origin=(0.0, 0.0), primitives=[
        LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict(),
        LineItem(QPointF(0, 0), QPointF(0, 100)).to_dict()])
    sc.register_block_definition(d)
    assert ops_mask(d.render_ops()).contains(QPointF(80, 80))


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
