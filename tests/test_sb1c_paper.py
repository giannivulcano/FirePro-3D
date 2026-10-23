"""SB1c G3 / G-real -- annotative blocks plot at authored mm on every sheet
viewport (real PDF export); real-size blocks keep plotting at model x scale.
Export idiom copied from tests/test_lt1_block_paper.py (not imported)."""
from unittest.mock import MagicMock

import fitz
import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode

_VP_X, _VP_Y, _VP_W = 65.0, 30.0, 80.0
HALF = 3.0


def _crop(scale):
    if not scale:                                    # NTS: fit = 80 / 2000
        return QRectF(-1000.0, -1000.0, 2000.0, 2000.0)
    half = _VP_W / 2.0 / scale
    return QRectF(-half, -half, 2 * half, 2 * half)


def _scene(mode="annotative", half=HALF, text=False):
    ms = Model_Space()
    ln = LineItem(QPointF(-half, 0.0), QPointF(half, 0.0))
    prims = [ln.to_dict()]
    if text:
        prims.append({"type": "text", "text": "H", "x": 0.0, "y": -6.0, "height_mm": 3.0})
    d = BlockDefinition.new(name="A", library="L", series="S",
                            primitives=prims, origin=(0.0, 0.0))
    d.scale_mode = mode
    ms.register_block_definition(d)
    ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
    return ms


def _export(tmp_path, ms, scale, name):
    from firepro3d import paper_export
    from firepro3d.paper_space import Sheet, SheetViewData, ViewResolver
    sheet = Sheet.create_default()
    sheet.paper_size = "A4"
    sheet.sheet_views = [SheetViewData("plan", "Plan: Level 1", "P", scale,
                                       _VP_X, _VP_Y, _VP_W, _VP_W)]
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.side_effect = lambda vt, vn: (ms, QRectF(_crop(scale)))
    out = tmp_path / name
    paper_export.export_pdf([sheet], resolver, str(out), dpi=300)
    return out


def _inside(r):
    pt = 25.4 / 72.0
    x0, y0, x1, y1 = (v * pt for v in (r.x0, r.y0, r.x1, r.y1))
    ok = (_VP_X + 1 < x0 and x1 < _VP_X + _VP_W - 1
          and _VP_Y + 1 < y0 and y1 < _VP_Y + _VP_W - 1)
    return ok, (x0, y0, x1, y1)


def _h_stroke_widths(pdf):
    """x-extent (mm) of every horizontal stroke strictly inside the viewport."""
    doc = fitz.open(str(pdf))
    try:
        out = []
        for d in doc[0].get_drawings():
            if "s" not in (d.get("type") or ""):
                continue
            ok, (x0, y0, x1, y1) = _inside(d["rect"])
            if ok and y1 - y0 < 0.5:
                out.append(x1 - x0)
        return out
    finally:
        doc.close()


def _text_height(pdf):
    """Height (mm) of the union of fill drawings strictly inside the viewport
    and smaller than 20 mm (the text glyph; the viewport fill falls out)."""
    doc = fitz.open(str(pdf))
    try:
        ys = []
        for d in doc[0].get_drawings():
            if "f" not in (d.get("type") or ""):
                continue
            ok, (x0, y0, x1, y1) = _inside(d["rect"])
            if ok and x1 - x0 < 20 and y1 - y0 < 20:
                ys += [y0, y1]
        return (max(ys) - min(ys)) if ys else 0.0
    finally:
        doc.close()


@pytest.mark.parametrize("scale", [0.02, 0.005, 0.0])       # 1:50, 1:200, NTS
def test_g3_annotative_plots_authored_mm(qapp, tmp_path, scale):
    save_paper_color_mode(PaperColorMode.BW)
    ms = _scene()
    widths = _h_stroke_widths(_export(tmp_path, ms, scale, "a.pdf"))
    assert len(widths) == 1, widths
    assert abs(widths[0] - 2 * HALF) < 0.3, widths
    assert ms._block_instances[0]._paper_scale is None          # restored


def test_g3_text_same_printed_size_across_viewports(qapp, tmp_path):
    save_paper_color_mode(PaperColorMode.BW)
    hs = [_text_height(_export(tmp_path, _scene(text=True), s, f"t{i}.pdf"))
          for i, s in enumerate((0.02, 0.005, 0.0))]
    assert all(1.0 < h < 4.5 for h in hs), hs                  # printed mm, not model mm
    assert max(hs) - min(hs) < 0.1, hs


def test_g_real_size_unchanged(qapp, tmp_path):
    save_paper_color_mode(PaperColorMode.BW)
    w50 = _h_stroke_widths(_export(tmp_path, _scene("real_size", half=1500.0), 0.02, "r50.pdf"))
    w200 = _h_stroke_widths(_export(tmp_path, _scene("real_size", half=1500.0), 0.005, "r200.pdf"))
    assert len(w50) == 1 and abs(w50[0] - 60.0) < 0.5, w50       # 3000 mm x 1:50
    assert len(w200) == 1 and abs(w200[0] - 15.0) < 0.5, w200    # 3000 mm x 1:200
