"""LT1-2 -- block linework plots at the paper "Blocks" weight/colour (L33).

linetypes.md LT1-1 / LT1-2 / H5 / H6. Real PDF export through
``paper_export.export_pdf`` (transient PaperScene -> apply_paper_overrides ->
render -> restore). Helper idioms copied from tests/test_underlay_display.py
(``_sheet_with_viewports`` / ``_mock_resolver``), not imported.
"""
from unittest.mock import MagicMock

import fitz
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d import paper_display as pd
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode

# A4 sheet, one 80 mm-square viewport at (65, 30); crop centred on model (0,0)
# and sized 80 mm / scale so the viewport stays 80 mm at every scale.
_VP_X, _VP_Y, _VP_W = 65.0, 30.0, 80.0
_HALF_LEN = 1500.0                      # block line runs x = -1500 .. +1500
_TEXT_X, _TEXT_Y, _TEXT_H = -500.0, -1000.0, 400.0   # block text glyph (model)


def _crop(scale):
    half = _VP_W / 2.0 / scale
    return QRectF(-half, -half, 2 * half, 2 * half)


def _line_def(name, colour="#ffffff", extra=()):
    ln = LineItem(QPointF(-_HALF_LEN, 0), QPointF(_HALF_LEN, 0))
    pen = ln.pen()
    pen.setColor(QColor(colour))
    pen.setWidthF(3.0)                  # authored px -- must be ignored on paper
    ln.setPen(pen)
    return BlockDefinition.new(name=name, library="L", series="S",
                               primitives=[ln.to_dict(), *extra],
                               origin=(0.0, 0.0))


def _nested(block_id):
    return {"type": "block_instance", "block_id": block_id,
            "pos": [0, 0], "rotation": 0.0}


def _text_prim():
    """A white block text glyph well clear of the line (model y=-1000)."""
    from firepro3d.text_item import TextAnnotationData, TextItem
    return TextItem(TextAnnotationData(text="H", x=_TEXT_X, y=_TEXT_Y,
                                       height_mm=_TEXT_H,
                                       color="#ffffff")).to_dict()


def _scene_with_blocks(nested=False, text=False):
    ms = Model_Space()
    if nested:
        c = _line_def("C")
        b = BlockDefinition.new(name="B", library="L", series="S",
                                primitives=[_nested(c.id)], origin=(0.0, 0.0))
        a = BlockDefinition.new(name="A", library="L", series="S",
                                primitives=[_nested(b.id)], origin=(0.0, 0.0))
        for d in (c, b, a):
            ms.register_block_definition(d)
        ms.place_block_instance(a.id, (0.0, 0.0), level=ms.active_level)
    else:
        d = _line_def("P", extra=[_text_prim()] if text else ())
        ms.register_block_definition(d)
        ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
    return ms


def _export(tmp_path, ms, scale, name):
    from firepro3d import paper_export
    from firepro3d.paper_space import Sheet, SheetViewData, ViewResolver
    sheet = Sheet.create_default()
    sheet.paper_size = "A4"             # programmatic title block
    sheet.sheet_views = [SheetViewData("plan", "Plan: Level 1", "P", scale,
                                       _VP_X, _VP_Y, _VP_W, _VP_W)]
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.side_effect = lambda vt, vn: (ms, QRectF(_crop(scale)))
    out = tmp_path / name
    paper_export.export_pdf([sheet], resolver, str(out), dpi=300)
    return out


def _block_strokes(pdf, scale):
    """(width_mm, rgb) of every stroke that IS the block's line.

    Selected by geometry only (never by width or colour): a horizontal stroke
    strictly inside the viewport box whose x-extent matches the block line's
    expected paper extent (centre 105 mm, half-length 1500 mm x scale). The
    viewport border (80 mm tall) and the title rule (below the box) fall out.
    """
    pt = 25.4 / 72.0                    # PDF points -> mm
    cx = _VP_X + _VP_W / 2.0
    half = _HALF_LEN * scale
    doc = fitz.open(str(pdf))
    try:
        res = []
        for d in doc[0].get_drawings():
            if "s" not in (d.get("type") or ""):
                continue
            r = d["rect"]
            x0, y0, x1, y1 = (v * pt for v in (r.x0, r.y0, r.x1, r.y1))
            if (y1 - y0 < 0.5 and _VP_Y + 1 < y0 and y1 < _VP_Y + _VP_W - 1
                    and abs(x0 - (cx - half)) < 1.0
                    and abs(x1 - (cx + half)) < 1.0):
                res.append((d["width"] * pt, d.get("color")))
        return res
    finally:
        doc.close()


@pytest.mark.parametrize("thin", [False, True])           # LT1-8: never plots
@pytest.mark.parametrize("scale", [0.02, 0.01])          # 1:50 and 1:100
def test_block_plots_at_blocks_weight(qapp, tmp_path, scale, thin):
    save_paper_color_mode(PaperColorMode.BW)
    pd.set_thin_lines(thin)
    strokes = _block_strokes(
        _export(tmp_path, _scene_with_blocks(), scale, "b.pdf"), scale)
    assert len(strokes) == 1, strokes
    assert abs(strokes[0][0] - 0.18) < 0.02, strokes     # factory "Light"


def test_nested_block_follows_category_weight_change(qapp, tmp_path):
    save_paper_color_mode(PaperColorMode.BW)
    cats = pd.load_paper_categories()
    cats["Blocks"]["line_weight"] = "Heavy"
    pd.save_paper_categories(cats)
    strokes = _block_strokes(
        _export(tmp_path, _scene_with_blocks(nested=True), 0.02, "n.pdf"), 0.02)
    assert len(strokes) == 1, strokes
    assert abs(strokes[0][0] - 0.35) < 0.02, strokes


def test_white_block_plots_black_in_bw_authored_in_full_color(qapp, tmp_path):
    save_paper_color_mode(PaperColorMode.BW)
    bw = _block_strokes(
        _export(tmp_path, _scene_with_blocks(), 0.02, "bw.pdf"), 0.02)
    assert len(bw) == 1 and bw[0][1] == (0.0, 0.0, 0.0), bw
    save_paper_color_mode(PaperColorMode.FULL_COLOR)
    fc = _block_strokes(
        _export(tmp_path, _scene_with_blocks(), 0.02, "fc.pdf"), 0.02)
    assert len(fc) == 1 and fc[0][1] == (1.0, 1.0, 1.0), fc
    assert abs(fc[0][0] - 0.18) < 0.02, fc                # weight in every mode


def test_selected_block_plots_authored_colour_in_full_color(qapp, tmp_path):
    """Selection is canvas feedback: a selected block plots authored on paper."""
    save_paper_color_mode(PaperColorMode.FULL_COLOR)
    ms = _scene_with_blocks()
    inst = ms._block_instances[0]
    assert inst.flags() & inst.GraphicsItemFlag.ItemIsSelectable
    inst.setSelected(True)
    assert inst.isSelected()
    fc = _block_strokes(_export(tmp_path, ms, 0.02, "sel.pdf"), 0.02)
    assert len(fc) == 1 and fc[0][1] == (1.0, 1.0, 1.0), fc
    assert inst.isSelected()                       # pass did not deselect


def _text_fills(pdf):
    """Fill colours of drawings inside the block text's paper box.

    Selected by position only: fill-type drawings whose rect lies inside the
    viewport, clear of its full-box background, and away from the block
    line's row (y = 70 mm) -- the text glyph sits 20 mm off that row.
    """
    pt = 25.4 / 72.0
    line_y = _VP_Y + _VP_W / 2.0
    doc = fitz.open(str(pdf))
    try:
        res = []
        for d in doc[0].get_drawings():
            if "f" not in (d.get("type") or ""):
                continue
            r = d["rect"]
            x0, y0, x1, y1 = (v * pt for v in (r.x0, r.y0, r.x1, r.y1))
            if (_VP_X + 1 < x0 and x1 < _VP_X + _VP_W - 1
                    and _VP_Y + 1 < y0 and y1 < _VP_Y + _VP_W - 1
                    and (y1 < line_y - 5 or y0 > line_y + 5)):
                res.append(d.get("fill"))
        return res
    finally:
        doc.close()


def test_block_text_plots_black_in_bw(qapp, tmp_path):
    """LT1-2: B&W forces the category colour onto TEXT ops too."""
    save_paper_color_mode(PaperColorMode.BW)
    fills = _text_fills(_export(tmp_path, _scene_with_blocks(text=True),
                                0.02, "t.pdf"))
    assert fills, "block text glyph not found in PDF"
    assert all(f == (0.0, 0.0, 0.0) for f in fills), fills
    save_paper_color_mode(PaperColorMode.FULL_COLOR)       # authored white kept
    fc = _text_fills(_export(tmp_path, _scene_with_blocks(text=True),
                             0.02, "tf.pdf"))
    assert fc and all(f == (1.0, 1.0, 1.0) for f in fc), fc


def test_custom_mode_forces_category_colour(qapp, tmp_path):
    save_paper_color_mode(PaperColorMode.CUSTOM)
    cats = pd.load_paper_categories()
    cats["Blocks"]["color"] = "#ff0000"
    pd.save_paper_categories(cats)
    st = _block_strokes(
        _export(tmp_path, _scene_with_blocks(), 0.02, "c.pdf"), 0.02)
    assert len(st) == 1 and st[0][1] == (1.0, 0.0, 0.0), st


def test_model_render_restored_after_paper_pass(qapp):
    ms = _scene_with_blocks()
    inst = ms._block_instances[0]
    saved = pd.apply_paper_overrides(ms, _crop(0.02), paper_scale=0.02)
    assert inst._paper_pen_width is not None
    pd.restore_model_display(saved)
    assert inst._paper_pen_width is None and inst._paper_pen_color is None


def test_paper_tab_has_blocks_row_under_drafting(qapp):
    """H6: the Paper tab row source (_PS_GROUPS) shows Blocks with weight /
    colour / visibility / opacity live and fill / section disabled."""
    from firepro3d.display_manager import DisplayManager
    save_paper_color_mode(PaperColorMode.CUSTOM)
    dlg = DisplayManager(Model_Space())
    try:
        row = dlg._paper_cat_data["Blocks"]
        assert row["tree_item"].parent().text(0) == "Drafting"
        for w in ("vis", "color_btn", "lw_combo", "opacity"):
            assert row[w].isEnabled(), w
        assert not row["fill_btn"].isEnabled()
        assert not row["section_btn"].isEnabled()
        # MW-4/MW-5: factory 0.18 mm -> "Thinnest" (was "Light"); "Thin" is a
        # live row of the new factory table (was "Heavy").
        assert row["lw_combo"].currentText() == "Thinnest"
        row["lw_combo"].setCurrentText("Thin")
        assert pd.load_paper_categories()["Blocks"]["line_weight"] == "Thin"
    finally:
        dlg.close()


def test_placement_ghost_never_plots(qapp):
    """A ghost-flagged BlockInstance is hidden for the pass, restored after."""
    ms = _scene_with_blocks()
    ms._place_block_id = ms._block_instances[0].block_id
    ms._place_block_make_ghost()
    g = ms._place_block_ghost
    assert g is not None and g.isVisible()
    saved = pd.apply_paper_overrides(ms, _crop(0.02), paper_scale=0.02)
    try:
        assert not g.isVisible()
        assert g.opacity() == 0.5 and g._paper_pen_width is None
        assert ms._block_instances[0]._paper_pen_width is not None
    finally:
        pd.restore_model_display(saved)
    assert g.isVisible() and g.opacity() == 0.5
    ms._place_block_drop_ghost()


def _render_model(ms):
    """Model-canvas render of the crop at 0.1 px/mm (no paper pass)."""
    img = QImage(400, 400, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, 400, 400), _crop(0.1))
    p.end()
    return img


def _row_run(img, x):
    """Height of the lit run in column x (the line's on-screen thickness)."""
    return sum(1 for y in range(img.height())
               if QColor(img.pixel(x, y)).lightness() > 128)


def test_model_canvas_block_render_unchanged(qapp):
    """LT2-4: canvas blocks draw By Block at the Model Blocks weight (Light = 1 px); a paper pass leaves no trace."""
    ms = _scene_with_blocks()
    inst = ms._block_instances[0]
    assert inst._paper_pen_width is None and inst._paper_pen_color is None
    before = _render_model(ms)
    # By Block at the factory Model Blocks weight "Light" -> 1 cosmetic px at
    # any zoom; the authored 3 px pen width is ignored (paper weight would be
    # 0.18 mm = 0.018 px here and colour black).
    # Column x=320 is clear of the origin cross at the crop centre (x=200).
    assert _row_run(before, 320) == 1
    saved = pd.apply_paper_overrides(ms, _crop(0.02), paper_scale=0.02)
    pd.restore_model_display(saved)
    assert _render_model(ms) == before
