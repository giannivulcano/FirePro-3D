"""G3 print exact + G4-LT3 paper widths -- real PDF export, parsed."""
import fitz
import pytest
from PyQt6.QtCore import QPointF

from tests.test_lt1_block_paper import _export, _VP_X, _VP_Y, _VP_W
from tests.test_lt3_block_paint import _scene
from firepro3d import paper_display as pd
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode

PT = 25.4 / 72.0


def _viewport_hlines(pdf):
    """[(x0_mm, x1_mm, width_mm)] of horizontal stroked lines inside the viewport."""
    doc = fitz.open(str(pdf))
    out = []
    try:
        for d in doc[0].get_drawings():
            if "s" not in (d.get("type") or ""):
                continue
            for it in d["items"]:
                if it[0] != "l":
                    continue
                a, b = it[1], it[2]
                y0, y1 = a.y * PT, b.y * PT
                if abs(y0 - y1) > 0.01 or not (_VP_Y + 1 < y0 < _VP_Y + _VP_W - 1):
                    continue
                xs = sorted((a.x * PT, b.x * PT))
                if _VP_X + 1 < xs[0] and xs[1] < _VP_X + _VP_W - 1:
                    out.append((xs[0], xs[1], d["width"] * PT))
    finally:
        doc.close()
    return out


def _blocks_mm():
    """The paper Blocks category weight in mm, read the way
    paper_display.apply_paper_overrides feeds _apply_block."""
    return pd.resolve_line_weight_mm(pd.load_paper_categories()["Blocks"]["line_weight"])


@pytest.mark.parametrize("scale", [0.02, 0.01])           # 1:50, 1:100
def test_g3_drafting_dashes_print_at_authored_mm(qapp, tmp_path, scale):
    save_paper_color_mode(PaperColorMode.BW)
    pdf = _export(tmp_path, _scene(), scale, f"g3_{scale}.pdf")
    lines = _viewport_hlines(pdf)
    full = [x1 - x0 for x0, x1, _ in lines if 0.5 < x1 - x0]
    inner = full[1:-1]                                  # end dashes may be clipped
    assert inner and all(abs(L - 6.0) <= 0.05 for L in inner), full


def test_g3_model_linetype_scales_with_viewport(qapp, tmp_path):
    # The 1:2 crop is 160 mm wide: a 100 mm line stays inside the viewport.
    save_paper_color_mode(PaperColorMode.BW)
    pdf = _export(tmp_path, _scene(model_size=True, half_len=50.0), 0.5, "g3_model.pdf")
    inner = [x1 - x0 for x0, x1, _ in _viewport_hlines(pdf)][1:-1]
    assert inner and all(abs(L - 3.0) <= 0.05 for L in inner), inner   # 6 mm x 0.5


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("weight", ["Heavy", "by_block"])
def test_g4_paper_widths(qapp, tmp_path, weight, nested):
    save_paper_color_mode(PaperColorMode.BW)
    pdf = _export(tmp_path, _scene(weight=weight, nested=nested), 0.02,
                  f"g4_{weight}_{nested}.pdf")
    lines = _viewport_hlines(pdf)
    exp = pd.resolve_line_weight_mm("Heavy") if weight == "Heavy" else _blocks_mm()
    assert len(lines) > 3                               # dashed, not one stroke
    assert {round(w, 3) for _, _, w in lines} == {round(exp, 3)}


def test_g4_by_linetype_takes_dash_weight_on_paper(qapp, tmp_path):
    save_paper_color_mode(PaperColorMode.BW)
    ms = _scene(weight="by_linetype")
    lt = next(d for d in ms._block_definitions.values() if d.repeat)
    for p in lt.primitives:
        p["style"]["weight"] = "Heavy"
    lt.set_repeat(lt.repeat)                            # version bump -> re-read
    pdf = _export(tmp_path, ms, 0.02, "g4_bylt.pdf")
    lines = _viewport_hlines(pdf)
    assert len(lines) > 3                               # dashed, not one stroke
    assert {round(w, 3) for _, _, w in lines} == {
        round(pd.resolve_line_weight_mm("Heavy"), 3)}


def test_raw_plan_primitive_prints_drafting_dashes_at_authored_mm(qapp, tmp_path):
    """LT3-5 paper pass for a raw (e.g. exploded) primitive on the plan:
    Drafting / viewport scale, never the plan drawing_scale."""
    from firepro3d.geometry_2d import LineItem
    from firepro3d.model_space import Model_Space
    from tests.lt3_support import hidden
    save_paper_color_mode(PaperColorMode.BW)
    ms = Model_Space()
    ms.scale_manager.drawing_scale = 200.0             # must NOT drive the print
    ln = LineItem(QPointF(-1500, 0), QPointF(1500, 0))
    ln.style["linetype"] = hidden(ms)
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    pdf = _export(tmp_path, ms, 0.02, "raw.pdf")
    inner = [x1 - x0 for x0, x1, _ in _viewport_hlines(pdf) if 0.5 < x1 - x0][1:-1]
    assert inner and all(abs(L - 6.0) <= 0.05 for L in inner), inner
