"""LT1-8 -- THIN pill: global Thin Lines, persisted, never affects paper (T6).

linetypes.md LT1-8 / H10. MainWindow tests drive the real footer pill; the
paper-parity guards export real PDFs (``paper_export.export_pdf`` ->
apply_paper_overrides -> render -> restore) with Thin Lines off and on and
compare every stroke width inside the viewport.
"""
from unittest.mock import MagicMock

import fitz
import pytest
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtWidgets import QGraphicsPathItem

import main as _main_module
from firepro3d.view_3d import View3D          # heavy import required before MainWindow
_main_module.View3D = View3D                  # inject lazy global (test_halo_pill idiom)
from main import MainWindow

from firepro3d import paper_display as pd
from firepro3d.model_space import Model_Space, underlay_layer_pen
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from firepro3d.underlay import Underlay


@pytest.fixture
def main_window(qapp):
    w = MainWindow()
    yield w
    w.close()


# ── Footer pill + persistence ────────────────────────────────────────────────

def test_thin_pill_drives_mapping_and_persists(main_window):
    w = main_window
    assert w.footer.thin_pill.toolTip()
    assert pd.thin_lines() is False
    w.footer.thin_pill.click()                     # drive the widget
    assert pd.thin_lines() is True
    assert w.settings.value("view/thin_lines", False, type=bool) is True
    rec = Underlay(type="dxf", path="x.dxf", line_weight_name="Very Heavy")
    assert underlay_layer_pen(rec, "0").widthF() == 1.0
    w.footer.thin_pill.click()
    assert pd.thin_lines() is False
    assert w.settings.value("view/thin_lines", True, type=bool) is False
    # MW-6/MW-8: old "Very Heavy" -> its 0.50 mm row -> Auto 4 px (was 3.0)
    assert underlay_layer_pen(rec, "0").widthF() == pytest.approx(4.0)


def test_thin_lines_restored_on_startup(qapp):
    from PyQt6.QtCore import QSettings
    QSettings("GV", "FirePro3D").setValue("view/thin_lines", True)
    w = MainWindow()
    try:
        assert pd.thin_lines() is True
        assert w.footer.thin_pill.isChecked()
    finally:
        w.close()


_LINE = {"kind": "line", "x1": 0, "y1": -1500, "x2": 0, "y2": 1500,
         "layer": "A-WALL"}


def _stroke_widths(group):
    return [c.pen().widthF() for c in group.childItems()
            if isinstance(c, QGraphicsPathItem)
            and c.pen().style() != Qt.PenStyle.NoPen]


def test_pill_repens_live_underlay(main_window):
    """The BAKED pen of a real underlay in the live scene follows the pill."""
    w = main_window
    rec = Underlay(type="dxf", path="x.dxf", line_weight_name="Very Heavy")
    group, _ = w.scene._build_batched_underlay_group([dict(_LINE)], rec)
    w.scene.underlays.append((rec, group))
    on_screen = pd.canvas_weight_px(pd.resolve_line_weight_mm("Very Heavy"))
    assert _stroke_widths(group) == [pytest.approx(on_screen)]
    assert on_screen > 1.0
    w.footer.thin_pill.click()
    assert _stroke_widths(group) == [1.0]
    w.footer.thin_pill.click()
    assert _stroke_widths(group) == [pytest.approx(on_screen)]


# ── Paper parity: Thin Lines never plots ─────────────────────────────────────

_VP_X, _VP_Y, _VP_W = 65.0, 30.0, 80.0
_SCALE = 0.02
_HALF = _VP_W / 2.0 / _SCALE


def _export(tmp_path, ms, name):
    from firepro3d import paper_export
    from firepro3d.paper_space import Sheet, SheetViewData, ViewResolver
    sheet = Sheet.create_default()
    sheet.paper_size = "A4"             # programmatic title block
    sheet.sheet_views = [SheetViewData("plan", "Plan: Level 1", "P", _SCALE,
                                       _VP_X, _VP_Y, _VP_W, _VP_W)]
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.side_effect = lambda vt, vn: (
        ms, QRectF(-_HALF, -_HALF, 2 * _HALF, 2 * _HALF))
    out = tmp_path / name
    paper_export.export_pdf([sheet], resolver, str(out), dpi=300)
    return out


def _vp_stroke_widths(pdf):
    """Sorted paper-mm widths of every stroke strictly inside the viewport
    box (the viewport border and the title block fall outside it)."""
    pt = 25.4 / 72.0
    doc = fitz.open(str(pdf))
    try:
        res = []
        for d in doc[0].get_drawings():
            if "s" not in (d.get("type") or ""):
                continue
            r = d["rect"]
            x0, y0, x1, y1 = (v * pt for v in (r.x0, r.y0, r.x1, r.y1))
            if (_VP_X + 1 < x0 and x1 < _VP_X + _VP_W - 1
                    and _VP_Y + 1 < y0 and y1 < _VP_Y + _VP_W - 1):
                res.append(round(d["width"] * pt, 3))
        return sorted(res)
    finally:
        doc.close()


def _parity(tmp_path, ms, refresh=lambda: None):
    """Export with Thin Lines off, then on (re-baking via *refresh*)."""
    save_paper_color_mode(PaperColorMode.BW)
    off = _vp_stroke_widths(_export(tmp_path, ms, "off.pdf"))
    pd.set_thin_lines(True)
    refresh()
    on = _vp_stroke_widths(_export(tmp_path, ms, "on.pdf"))
    assert off, "no stroke found inside the viewport"
    return off, on


def _underlay_scene(geoms, **rec_kw):
    ms = Model_Space()
    rec = Underlay(**rec_kw)
    group, _ = ms._build_batched_underlay_group([dict(g) for g in geoms], rec)
    ms.underlays.append((rec, group))
    return ms, rec, group


def test_weighted_underlay_paper_parity(qapp, tmp_path):
    ms, rec, group = _underlay_scene([_LINE], type="dxf", path="x.dxf",
                                     line_weight_name="Very Heavy")
    off, on = _parity(tmp_path, ms, lambda: ms.repen_underlay(rec))
    assert _stroke_widths(group) == [1.0]           # canvas went thin
    assert on == pytest.approx(off, abs=0.01)


def test_unweighted_pdf_underlay_paper_parity(qapp, tmp_path):
    """Unweighted PDF layer: the source-width cosmetic pen plots as-is, so a
    Thin-Lines 1 px bake would reach paper without the paper-pass restore."""
    geom = {"kind": "path_points", "layer": "PDF Vectors",
            "points": [(0, -1500), (0, 1500)], "closed": False, "width": 3.0}
    ms, rec, group = _underlay_scene([geom], type="pdf", path="x.pdf")
    from firepro3d.model_space import _pdf_width_to_px
    wide = _pdf_width_to_px(3.0)
    assert _stroke_widths(group) == [pytest.approx(wide)] and wide > 1.5
    off, on = _parity(tmp_path, ms, lambda: ms.repen_underlay(rec))
    assert _stroke_widths(group) == [1.0]           # canvas thin, restored
    assert on == pytest.approx(off, abs=0.01)


def test_model_text_border_unthinned_during_paper_pass(qapp):
    """A model-surface text border (cosmetic canvas pen, resolved at PAINT
    time) paints its real width while a paper pass is live, thin otherwise.

    Pass-level, not a PDF export: a model-plan TextItem inside a viewport crop
    currently aborts the paper pass (pre-existing: ``TextItem.data`` property
    shadows ``QGraphicsItem.data`` -> apply_paper_overrides' origin check
    raises). The pixels are painted by the real TextItem.paint under the real
    apply_paper_overrides / restore_model_display bracket.
    """
    from tests.test_lt1_canvas_mapping import (_border_thickness_px,
                                               _left_border_run)
    normal = _left_border_run(_border_thickness_px("Very Heavy"))   # 3 px
    assert normal >= 3
    pd.set_thin_lines(True)
    assert _left_border_run(_border_thickness_px("Very Heavy")) <= 2
    ms, _rec, _group = _underlay_scene([_LINE], type="dxf", path="x.dxf")
    saved = pd.apply_paper_overrides(ms, QRectF(-2000, -2000, 4000, 4000),
                                     paper_scale=_SCALE)
    try:
        during = _left_border_run(_border_thickness_px("Very Heavy"))
    finally:
        pd.restore_model_display(saved)
    assert during == normal                         # paper sees no Thin Lines
    assert _left_border_run(_border_thickness_px("Very Heavy")) <= 2
    assert pd.thin_lines_active() is True           # suspension lifted


def test_unbalanced_suspension_warns(qapp, caplog):
    """A restore that would drive the suspension counter negative logs it."""
    import logging
    saved = pd.apply_paper_overrides(Model_Space(), QRectF(0, 0, 10, 10))
    pd._THIN_SUSPEND = 0                     # simulate an unbalanced counter
    with caplog.at_level(logging.WARNING, logger="firepro3d.paper_display"):
        pd.restore_model_display(saved)
    assert pd._THIN_SUSPEND == 0
    assert any("unbalanced" in r.getMessage() for r in caplog.records)
