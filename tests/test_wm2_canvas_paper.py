"""WM2 G1-G5 -- placement Weight / Linetype on canvas pixels + parsed PDF."""
import fitz
import pytest

from firepro3d import paper_display as pd
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from firepro3d.stroke_style import canvas_px
from tests.lt3_support import make_linetype
from tests.test_lt1_block_paper import _block_strokes, _export, _render_model
from tests.test_lt2_canvas_paper import _run_near
from tests.wm2_support import COL, ROWS, SPRINKLER, scene_with, sprinkler_def


def _runs(ms):
    img = _render_model(ms)
    return {c: _run_near(img, COL, r) for c, r in ROWS.items()}


def _lit_cols(ms, comp):
    img = _render_model(ms)
    from PyQt6.QtGui import QColor
    r = ROWS[comp]
    return sum(1 for x in range(img.width())
               if any(QColor(img.pixel(x, y)).lightness() > 128
                      for y in range(r - 3, r + 4)))


def test_g1_as_authored(qapp):
    d = sprinkler_def()
    ms, _ = scene_with([d], d.id)
    runs = _runs(ms)
    for comp, (_y, w) in SPRINKLER.items():
        assert runs[comp] == round(canvas_px(w)), comp
    assert len({runs[c] for c in runs}) == 3         # composition: distinct


def test_g2_weight_named_replaces_all(qapp):
    d = sprinkler_def()
    ms, _ = scene_with([d], d.id, {"weight": "Thick"})
    assert set(_runs(ms).values()) == {round(canvas_px("Thick"))}


def test_g3_by_category_canvas_is_model_blocks(qapp):
    d = sprinkler_def()
    pd.set_model_blocks_weight("Thickest")
    try:
        ms, _ = scene_with([d], d.id, {"weight": "by_category"})
        assert set(_runs(ms).values()) == {round(canvas_px("Thickest"))}
    finally:
        pd.set_model_blocks_weight(None)


def test_g4_linetype_hidden_dashes_every_component(qapp):
    # real mm: visible at 0.5 px/mm (Drafting would scale by drawing_scale, LT3-5)
    lt = make_linetype(length=900.0, dashes=((0.0, 600.0),), size="model")
    d = sprinkler_def()
    plain, _ = scene_with([lt, d], d.id)
    dashed, _ = scene_with([lt, d], d.id, {"linetype": lt.id})
    for comp in ROWS:
        assert _lit_cols(dashed, comp) < 0.85 * _lit_cols(plain, comp), comp


def test_g5_by_linetype_takes_override_dash_weight(qapp):
    lt = make_linetype(length=900.0, dashes=((0.0, 600.0),), weight="Thickest",
                       size="model")
    d = sprinkler_def(weights={"cross": "by_linetype"})
    ms, _ = scene_with([lt, d], d.id, {"linetype": lt.id})
    img = _render_model(ms)
    # first dash of the cross row spans x in [0, 300) px at col 220 (model +40)
    assert _run_near(img, 220, ROWS["cross"]) == round(canvas_px("Thickest"))


@pytest.mark.parametrize("scale", [0.02, 0.01])
def test_g1_g2_g3_pdf(qapp, tmp_path, scale):
    save_paper_color_mode(PaperColorMode.BW)
    d = sprinkler_def()
    ms, _ = scene_with([d], d.id)
    got = sorted(round(w, 3) for w, _c in _block_strokes(
        _export(tmp_path, ms, scale, "a.pdf"), scale))
    want = sorted(round(pd.resolve_line_weight_mm(w), 3)
                  for _y, w in SPRINKLER.values())
    assert got == want                                   # G1 As Authored
    ms2, _ = scene_with([d], d.id, {"weight": "Thick"})
    got2 = {round(w, 3) for w, _c in _block_strokes(
        _export(tmp_path, ms2, scale, "b.pdf"), scale)}
    assert got2 == {round(pd.resolve_line_weight_mm("Thick"), 3)}   # G2
    ms3, _ = scene_with([d], d.id, {"weight": "by_category"})
    cat = pd.load_paper_categories()["Blocks"]["line_weight"]
    got3 = {round(w, 3) for w, _c in _block_strokes(
        _export(tmp_path, ms3, scale, "c.pdf"), scale)}
    assert got3 == {round(pd.resolve_line_weight_mm(cat), 3)}       # G3 paper


def _pdf_dash_rows(pdf):
    """Horizontal line-segment count per page row (y rounded to 0.1 pt)."""
    pt = 25.4 / 72.0
    rows = {}
    doc = fitz.open(str(pdf))
    try:
        for dr in doc[0].get_drawings():
            for it in dr.get("items", []):
                if it[0] == "l" and abs(it[1].y - it[2].y) * pt < 0.1:
                    y = round(it[1].y, 1)
                    rows[y] = rows.get(y, 0) + 1
        return rows
    finally:
        doc.close()


def test_g4_pdf_has_dashes(qapp, tmp_path):
    save_paper_color_mode(PaperColorMode.BW)
    lt = make_linetype(length=9.0, dashes=((0.0, 6.0),))
    d = sprinkler_def()
    plain, _ = scene_with([lt, d], d.id)
    dashed, _ = scene_with([lt, d], d.id, {"linetype": lt.id})
    r0 = _pdf_dash_rows(_export(tmp_path, plain, 0.02, "p.pdf"))
    r1 = _pdf_dash_rows(_export(tmp_path, dashed, 0.02, "d.pdf"))
    # 60 paper mm per row / 9 mm period -> ~7 dashes on each of the three
    # component rows; As Authored draws each row as one continuous segment.
    split = [y for y in r1 if r1[y] >= 5 and r0.get(y) == 1]
    assert len(split) == 3, (r0, r1)
