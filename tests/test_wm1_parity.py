"""WM1 G1/G2 -- legacy by_block primitives load as By Linetype with
pixel-identical canvas and PDF output (linetypes.md WM-9), except a linetype
id + by_block, which draws at the dash weight (user ruling D1)."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d import paper_display as pd
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from tests.lt3_support import make_linetype
from tests.test_lt1_block_paper import (_HALF_LEN, _block_strokes, _export,
                                        _render_model, _row_run)
from tests.test_lt2_canvas_paper import _EDITOR_ROW, _run_near


def _legacy_prim(linetype="continuous"):
    d = LineItem(QPointF(-_HALF_LEN, 0), QPointF(_HALF_LEN, 0)).to_dict()
    d["style"]["weight"] = "by_block"            # what LT2/LT3 files hold
    d["style"]["linetype"] = linetype
    return d


def _placed(prim, extra=()):
    """Place a definition loaded through ``BlockDefinition.from_dict`` (the
    .fpd / .fpdb path) from a raw dict whose primitive still says by_block."""
    ms = Model_Space()
    for d in extra:
        ms.register_block_definition(d)
    raw = BlockDefinition.new(name="W", library="L", series="S",
                              primitives=[prim], origin=(0.0, 0.0)).to_dict()
    raw["primitives"][0]["style"]["weight"] = "by_block"   # survive to_dict
    raw["primitives"][0]["style"]["linetype"] = prim["style"]["linetype"]
    d = BlockDefinition.from_dict(raw)
    ms.register_block_definition(d)
    ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
    return ms, d


def _max_run(img, cols=range(300, 341)):
    """Thickest lit run over a band of columns (a dashed line has gaps)."""
    return max(_row_run(img, x) for x in cols)


def test_definition_load_migrates_by_block(qapp):
    _ms, d = _placed(_legacy_prim())
    st = d.primitives[0]["style"]
    assert st["weight"] == "by_linetype" and st["linetype"] == "continuous"


def test_canvas_parity_follows_model_blocks_row(qapp):
    pd.set_model_blocks_weight(None)
    try:
        ms, _d = _placed(_legacy_prim())
        assert _row_run(_render_model(ms), 320) == 1        # Light, as before
        pd.set_model_blocks_weight("Heavy")
        ms.update()
        assert _row_run(_render_model(ms), 320) >= 2        # still follows the row
    finally:
        pd.set_model_blocks_weight(None)


@pytest.mark.parametrize("scale", [0.02, 0.01])
def test_pdf_parity_paper_blocks_weight(qapp, tmp_path, scale):
    save_paper_color_mode(PaperColorMode.BW)
    want = pd.resolve_line_weight_mm(
        pd.load_paper_categories()["Blocks"]["line_weight"])
    ms, _d = _placed(_legacy_prim())
    strokes = _block_strokes(_export(tmp_path, ms, scale, f"p{scale}.pdf"), scale)
    assert strokes
    for w, _rgb in strokes:
        assert w == pytest.approx(want, abs=0.02)


def test_raw_editor_item_from_dict_parity(qapp):
    pd.set_model_blocks_weight(None)
    pd.set_thin_lines(False)
    try:
        d = LineItem(QPointF(-_HALF_LEN, -200.0),
                     QPointF(_HALF_LEN, -200.0)).to_dict()
        d["style"]["weight"] = "by_block"
        ln = LineItem.from_dict(d)                   # the .fpd item load entry
        assert ln.style["weight"] == "by_linetype"
        ms = Model_Space(scene_role="block_editor")
        ms.addItem(ln); ms._draw_lines.append(ln)
        assert _run_near(_render_model(ms), 320, _EDITOR_ROW) == 1
    finally:
        pd.set_model_blocks_weight(None)


def test_edge_linetype_plus_by_block_takes_dash_weight(qapp):
    pd.set_model_blocks_weight(None)                         # Blocks = Light (1 px)
    lt = make_linetype(weight="Heavy")                       # dashes drawn Heavy
    ms, d = _placed(_legacy_prim(linetype=lt.id), extra=(lt,))
    assert d.primitives[0]["style"]["weight"] == "by_linetype"
    assert _max_run(_render_model(ms)) >= 2                  # Heavy dashes now
