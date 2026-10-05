"""LT3 H3-e -- stroke ops carry pieces + linetype; nested ops map them."""
import pytest
from PyQt6.QtCore import QPointF
from firepro3d import path_walk as pw
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.model_space import Model_Space
from firepro3d.render_op import STROKE


def _def(ms, lt="continuous", origin=(10.0, 0.0)):
    ln = LineItem(QPointF(10, 0), QPointF(40, 0))
    ln.style["linetype"] = lt
    d = BlockDefinition.new(name="D", library="L", series="S",
                            primitives=[ln.to_dict()], origin=origin)
    ms.register_block_definition(d)
    return d


def test_stroke_op_has_origin_relative_pieces_and_linetype(qapp):
    ms = Model_Space()
    d = _def(ms, lt="abc")
    (op,) = [o for o in d.render_ops() if o.kind == STROKE]
    assert op.linetype == "abc"
    assert op.pieces == (pw.Seg(0.0, 0.0, 30.0, 0.0),)
    assert (op.origin.x(), op.origin.y()) == (0.0, 0.0)      # phase anchor


def test_nested_op_maps_pieces_and_anchor(qapp):
    ms = Model_Space()
    inner = _def(ms, lt="abc")
    outer = BlockDefinition.new(
        name="O", library="L", series="S", origin=(0.0, 0.0),
        primitives=[{"type": "block_instance", "block_id": inner.id,
                     "pos": [100, 50], "rotation": 90.0}])
    ms.register_block_definition(outer)
    (op,) = [o for o in outer.render_ops() if o.kind == STROKE]
    seg = op.pieces[0]
    assert (seg.x0, seg.y0) == pytest.approx((100.0, 50.0))
    assert (seg.x1, seg.y1) == pytest.approx((100.0, 20.0))     # Y-up CCW 90 → up
    assert (op.origin.x(), op.origin.y()) == pytest.approx((100.0, 50.0))


def test_rotated_rect_pieces_trace_the_compiled_path(qapp):
    """Pieces land exactly where the op's path draws (same map as the path)."""
    ms = Model_Space()
    rect = RectangleItem(QPointF(0, 0), QPointF(50, 20))
    rect.set_angle(30.0)
    d = BlockDefinition.new(name="R", library="L", series="S",
                            primitives=[rect.to_dict()], origin=(7.0, -3.0))
    ms.register_block_definition(d)
    (op,) = [o for o in d.render_ops() if o.kind == STROKE]
    path_pts = [(op.path.elementAt(i).x, op.path.elementAt(i).y)
                for i in range(4)]
    piece_pts = [(s.x0, s.y0) for s in op.pieces]
    assert len(op.pieces) == 4
    for (px, py), (qx, qy) in zip(piece_pts, path_pts):
        assert (px, py) == pytest.approx((qx, qy), abs=1e-9)
