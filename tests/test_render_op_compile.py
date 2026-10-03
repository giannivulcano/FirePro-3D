"""RenderOp compile contract (hatch HD4a): typed ops replace (pen, brush, path)."""
from PyQt6.QtCore import QPointF
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem, RectangleItem
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
    r.fill_type = "hatch"
    r.fill_pattern = "diagonal"
    r._display_fill_color = "#ff0000"
    ops = _defn([r.to_dict()]).render_ops()
    assert [o.kind for o in ops] == [PATTERN, STROKE]
    pat = ops[0]
    assert pat.tile_ref == "builtin-hatch-diagonal"
    assert pat.colour == "#ff0000"
    assert pat.origin == QPointF(0, 0)
    assert pat.path.boundingRect().width() == 100


def test_solid_rect_emits_fill_op_with_alpha(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    r.fill_type = "solid"
    r.fill_opacity = 0.5
    r._display_fill_color = "#00ff00"
    ops = _defn([r.to_dict()]).render_ops()
    assert [o.kind for o in ops] == [FILL, STROKE]
    assert ops[0].alpha == 128 and ops[0].colour == "#00ff00"


def _hatched_rect():
    r = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    r.fill_type = "hatch"
    r.fill_pattern = "diagonal"
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
