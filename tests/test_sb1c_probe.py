"""SB1c D13 (P4): RenderOp.mapped scales geometry and text, never the pen."""
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem


def _defn():
    ln = LineItem(QPointF(-3.0, 0.0), QPointF(3.0, 0.0))
    txt = {"type": "text", "text": "H", "x": 0.0, "y": -6.0, "height_mm": 3.0}
    return BlockDefinition.new(name="A", library="L", series="S",
                               primitives=[ln.to_dict(), txt], origin=(0.0, 0.0))


def test_variant_scales_path_and_text_not_pen(qapp):
    d = _defn()
    base = d.render_ops()
    var = d.render_ops_variant(False, 100.0)
    for b, v in zip(base, var):
        bw = b.path.boundingRect().width()
        assert abs(v.path.boundingRect().width() - 100.0 * bw) < 1e-6 * max(1.0, bw)
        if b.pen is not None:
            assert v.pen.widthF() == b.pen.widthF()
