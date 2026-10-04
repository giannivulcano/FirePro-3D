"""LT2-4 / LT2-5 / T-canvas / T-paper -- per-op weights on canvas and PDF."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d import paper_display as pd
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from tests.test_lt1_block_paper import (_HALF_LEN, _block_strokes, _export,
                                        _nested, _render_model, _row_run)


def _def(weight, name="W"):
    ln = LineItem(QPointF(-_HALF_LEN, 0), QPointF(_HALF_LEN, 0))
    ln.style["weight"] = weight
    return BlockDefinition.new(name=name, library="L", series="S",
                               primitives=[ln.to_dict()], origin=(0.0, 0.0))


def _scene(weight, nested=False):
    ms = Model_Space()
    d = _def(weight)
    ms.register_block_definition(d)
    top = d
    if nested:
        top = BlockDefinition.new(name="Outer", library="L", series="S",
                                  primitives=[_nested(d.id)], origin=(0.0, 0.0))
        ms.register_block_definition(top)
    ms.place_block_instance(top.id, (0.0, 0.0), level=ms.active_level)
    return ms


def test_compiled_op_carries_weight(qapp):
    ops = _def("Heavy").render_ops()
    assert ops[0].weight == "Heavy"


def test_canvas_by_block_follows_model_blocks_row(qapp):
    pd.set_model_blocks_weight(None)
    try:
        ms = _scene("by_block")
        assert _row_run(_render_model(ms), 320) == 1          # Light -> 1 px
        pd.set_model_blocks_weight("Heavy")
        ms.update()
        assert _row_run(_render_model(ms), 320) >= 2
    finally:
        pd.set_model_blocks_weight(None)


def test_canvas_named_weight_and_thin_lines(qapp):
    ms = _scene("Heavy")
    heavy = _row_run(_render_model(ms), 320)
    assert heavy >= 2
    pd.set_thin_lines(True)
    try:
        assert _row_run(_render_model(ms), 320) == 1
    finally:
        pd.set_thin_lines(False)


@pytest.mark.parametrize("scale", [0.02, 0.01])
@pytest.mark.parametrize("nested", [False, True])
def test_pdf_by_block_and_named(qapp, tmp_path, scale, nested):
    save_paper_color_mode(PaperColorMode.BW)
    blocks_mm = pd.resolve_line_weight_mm(
        pd.load_paper_categories()["Blocks"]["line_weight"])
    for weight, want in (("by_block", blocks_mm),
                         ("Heavy", pd.resolve_line_weight_mm("Heavy"))):
        ms = _scene(weight, nested=nested)
        pdf = _export(tmp_path, ms, scale, f"{weight}_{scale}_{nested}.pdf")
        strokes = _block_strokes(pdf, scale)
        assert strokes, weight
        for w, _rgb in strokes:
            assert w == pytest.approx(want, abs=0.02), (weight, w)
