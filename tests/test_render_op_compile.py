"""RenderOp compile contract (hatch HD4a): typed ops replace (pen, brush, path)."""
from PyQt6.QtCore import QPointF
from firepro3d.block_definition import BlockDefinition
from firepro3d.fill_layers import BackgroundLayer, FillLayers, PatternLayer
from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.hatch_patterns import canonical_ref
from firepro3d.render_op import RenderOp, STROKE, FILL, PATTERN


def _defn(prims):
    return BlockDefinition.new(name="T", library="L", series="S",
                               primitives=prims, origin=(0.0, 0.0))


def test_line_compiles_to_one_stroke_op(qapp):
    ops = _defn([LineItem(QPointF(0, 0), QPointF(10, 0)).to_dict()]).render_ops()
    assert len(ops) == 1 and isinstance(ops[0], RenderOp)
    assert ops[0].kind == STROKE and ops[0].pen is not None
    assert ops[0].path.boundingRect().width() == 10


def test_hatched_rect_emits_pattern_op_before_stroke(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    r.fill_layers = FillLayers(pattern=PatternLayer(
        canonical_ref("diagonal"), "#ff0000", 0.45, 1.0))
    ops = _defn([r.to_dict()]).render_ops()
    assert [o.kind for o in ops] == [PATTERN, STROKE]
    pat = ops[0]
    assert pat.tile_ref == "builtin-hatch-diagonal"
    assert pat.colour == "#ff0000"
    assert pat.origin == QPointF(0, 0)
    assert pat.path.boundingRect().width() == 100


def test_solid_rect_emits_fill_op_with_alpha(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    r.fill_layers = FillLayers(background=BackgroundLayer("#00ff00", 0.5))
    ops = _defn([r.to_dict()]).render_ops()
    assert [o.kind for o in ops] == [FILL, STROKE]
    assert ops[0].alpha == 128 and ops[0].colour == "#00ff00"


def _hatched_rect():
    r = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    r.fill_layers = FillLayers(pattern=PatternLayer(
        canonical_ref("diagonal"), "#888888", 0.45, 1.0))
    return r


def test_pattern_op_with_nonzero_definition_origin(qapp):
    d = BlockDefinition.new(name="T", library="L", series="S",
                            primitives=[_hatched_rect().to_dict()],
                            origin=(10.0, 20.0))
    pat = [o for o in d.render_ops() if o.kind == PATTERN][0]
    assert pat.origin == QPointF(-10, -20)
    b = pat.path.boundingRect()
    assert (b.left(), b.top(), b.width(), b.height()) == (-10, -20, 100, 50)


def test_pattern_op_through_nested_pose(qapp):
    from firepro3d.model_space import Model_Space
    sc = Model_Space()
    inner = _defn([_hatched_rect().to_dict()])
    sc.register_block_definition(inner)
    host = _defn([{"type": "block_instance", "block_id": inner.id,
                   "pos": [100.0, 0.0], "rotation": 90.0}])
    sc.register_block_definition(host)
    pat = [o for o in host.render_ops() if o.kind == PATTERN][0]
    assert pat.origin == QPointF(100, 0)          # nested pose maps (0,0)
    b = pat.path.boundingRect()
    assert (round(b.width(), 6), round(b.height(), 6)) == (50, 100)  # rotated


def test_pattern_frame_composes_nested_rotation_and_drops_scale(qapp):
    from PyQt6.QtGui import QPainterPath
    from firepro3d.block_pose import pose_matrix
    from firepro3d.render_op import orient_part
    op = RenderOp(PATTERN, QPainterPath(), tile_ref="x")
    assert op.pattern_frame is None
    m = op.mapped(pose_matrix(0, 0, 90.0, False, 3.0)).mapped(
        pose_matrix(0, 0, 30.0, False, 2.0))
    want = orient_part(pose_matrix(0, 0, 120.0))
    assert all(abs(a - b) < 1e-9 for a, b in zip(m.pattern_frame, want))


def test_pattern_frame_keeps_reflection(qapp):
    from PyQt6.QtGui import QPainterPath
    from firepro3d.block_pose import pose_matrix
    op = RenderOp(PATTERN, QPainterPath(), tile_ref="x")
    f = op.mapped(pose_matrix(0, 0, 0.0, True, 2.0)).pattern_frame
    assert all(abs(a - b) < 1e-9 for a, b in zip(f, (-1.0, 0.0, 0.0, 1.0)))


def test_non_pattern_ops_carry_no_frame(qapp):
    from PyQt6.QtGui import QPainterPath
    from firepro3d.block_pose import pose_matrix
    op = RenderOp(FILL, QPainterPath())
    assert op.mapped(pose_matrix(0, 0, 45.0)).pattern_frame is None


def _prim_with_fill(fill):
    d = RectangleItem(QPointF(0, 0), QPointF(100, 50)).to_dict()
    d["fill"] = fill
    return d


def test_two_layer_record_emits_fill_then_pattern_with_scale(qapp):
    ops = _defn([_prim_with_fill({
        "background": {"color": "#0000ff", "opacity": 0.25},
        "pattern": {"ref": "builtin-hatch-diagonal", "color": "#00ff00",
                    "opacity": 0.5, "scale": 2.5}})]).render_ops()
    assert [o.kind for o in ops] == [FILL, PATTERN, STROKE]
    bg, pat = ops[0], ops[1]
    assert (bg.colour, bg.alpha) == ("#0000ff", 64)
    assert (pat.colour, pat.alpha, pat.scale) == ("#00ff00", 128, 2.5)
    assert pat.tile_ref == "builtin-hatch-diagonal" and pat.origin == QPointF(0, 0)
    assert bg.path.boundingRect() == pat.path.boundingRect()


def test_pattern_only_record_emits_pattern_op(qapp):
    ops = _defn([_prim_with_fill({"pattern": {"ref": "abc"}})]).render_ops()
    assert [o.kind for o in ops] == [PATTERN, STROKE]
    assert ops[0].colour == "token:auto" and ops[0].alpha == 255


def test_legacy_hatch_record_reads_ref_from_record_not_item(qapp):
    ops = _defn([_prim_with_fill({"type": "hatch", "pattern": "diagonal",
                                  "color": "#ff0000", "opacity": 0.45})]).render_ops()
    assert [o.kind for o in ops] == [PATTERN, STROKE]
    assert ops[0].tile_ref == "builtin-hatch-diagonal" and ops[0].alpha == 115


def test_prim_refs_and_fill_ref_read_both_record_shapes(qapp):
    from firepro3d.block_registry import prim_refs
    from firepro3d.hatch_patterns import _fill_ref
    new = _prim_with_fill({"pattern": {"ref": "tile-x"}})
    old = _prim_with_fill({"type": "hatch", "pattern": "diagonal"})
    assert "tile-x" in prim_refs([new]) and "builtin-hatch-diagonal" in prim_refs([old])
    assert _fill_ref(new) == "tile-x" and _fill_ref(old) == "builtin-hatch-diagonal"
