"""Display management & view assignment (spec §16) — pens, visibility, DM tab."""
from __future__ import annotations

from unittest.mock import MagicMock

import fitz  # PyMuPDF — already a project dependency
import pytest
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QGraphicsPathItem

from firepro3d import paper_display as pd
from firepro3d.constants import UNDERLAY_LINE_WIDTH_PX, UNDERLAY_MM_TO_PX_HINT
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space, underlay_layer_pen
from firepro3d.paper_display import (apply_paper_overrides,
                                     restore_model_display, PaperColorMode,
                                     save_paper_color_mode)
from firepro3d.underlay import Underlay


@pytest.fixture(autouse=True)
def _factory_line_weights(monkeypatch):
    """Isolate weight-dependent tests from live QSettings (paper/line_weights).

    underlay_layer_pen -> resolve_line_weight_mm -> load_line_weights reads the
    developer's real QSettings; pin the module global to factory defaults
    (same idiom as tests/test_gridline_paper_scale.py::paper_env).
    """
    monkeypatch.setattr(pd, "load_line_weights",
                        lambda settings=None: list(pd.FACTORY_LINE_WEIGHTS))


def _geoms(layers=("A-WALL", "A-DOOR")):
    """Minimal stroked geometry dicts, one line per layer."""
    return [{"kind": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 100,
             "layer": ln} for ln in layers]


def _record(**kw):
    kw.setdefault("type", "dxf")
    kw.setdefault("path", "x.dxf")
    return Underlay(**kw)


class TestUnderlayLayerPen:
    def test_default_matches_today(self, qapp):
        pen = underlay_layer_pen(_record(), "A-WALL")
        assert pen.isCosmetic()
        assert pen.widthF() == pytest.approx(UNDERLAY_LINE_WIDTH_PX)
        assert pen.color().name() == "#c0c0c0"

    def test_layer_colour_override(self, qapp):
        rec = _record(layer_overrides={"A-WALL": {"colour": "#ff0000"}})
        assert underlay_layer_pen(rec, "A-WALL").color().name() == "#ff0000"
        assert underlay_layer_pen(rec, "A-DOOR").color().name() == "#c0c0c0"

    def test_named_weight_hint_width(self, qapp):
        # "Medium" is a factory weight = 0.25mm -> 0.25 * 6.0 = 1.5px
        rec = _record(line_weight_name="Medium")
        pen = underlay_layer_pen(rec, "A-WALL")
        assert pen.isCosmetic()  # NEVER zoom-scales (spec §3.4 invariant)
        assert pen.widthF() == pytest.approx(0.25 * UNDERLAY_MM_TO_PX_HINT)


class TestBuilderPerLayerPens:
    def test_builder_uses_per_layer_pens(self, qapp):
        scene = Model_Space()
        rec = _record(layer_overrides={"A-WALL": {"colour": "#ff0000"}})
        group, layers = scene._build_batched_underlay_group(_geoms(), rec)
        assert sorted(layers) == ["A-DOOR", "A-WALL"]
        by_layer = {c.data(1): c for c in group.childItems()
                    if isinstance(c, QGraphicsPathItem)}
        assert by_layer["A-WALL"].pen().color().name() == "#ff0000"
        assert by_layer["A-DOOR"].pen().color().name() == "#c0c0c0"
        for c in by_layer.values():
            assert c.pen().isCosmetic()


class TestPdfRecordColourSeam:
    """Reloaded PDF vector underlays must keep today's gray pen (§16.2 D4).

    Old project files predate PDF ``colour`` serialization (pre-§16.6
    to_dict omitted it), so from_dict must default PDFs to the dataclass
    default "#c0c0c0" — the colour the PDF vector path always rendered
    with — not the DXF legacy "#ffffff".
    """

    def test_pdf_from_dict_colour_defaults_to_gray(self):
        u = Underlay.from_dict({"type": "pdf", "path": "plans/sheet.pdf"})
        assert u.colour == "#c0c0c0"

    def test_dxf_from_dict_colour_keeps_legacy_white(self):
        u = Underlay.from_dict({"type": "dxf", "path": "old.dxf"})
        assert u.colour == "#ffffff"


class TestRepenUnderlay:
    def test_repen_swaps_pens_in_place(self, qapp):
        scene = Model_Space()
        rec = _record()
        group, _ = scene._build_batched_underlay_group(_geoms(), rec)
        scene.underlays.append((rec, group))
        child = next(c for c in group.childItems()
                     if c.data(1) == "A-WALL")
        assert child.pen().color().name() == "#c0c0c0"
        rec.layer_overrides["A-WALL"] = {"colour": "#00ff00"}
        scene.repen_underlay(rec)
        # same item object, new pen — no rebuild
        assert child.pen().color().name() == "#00ff00"

    def test_repen_applies_opacity(self, qapp):
        scene = Model_Space()
        rec = _record(opacity=0.4)
        group, _ = scene._build_batched_underlay_group(_geoms(), rec)
        scene.underlays.append((rec, group))
        scene.repen_underlay(rec)
        assert group.opacity() == pytest.approx(0.4)


class TestLayerHiddenChokePoint:
    def test_hide_and_show_layer(self, qapp):
        scene = Model_Space()
        rec = _record()
        group, _ = scene._build_batched_underlay_group(_geoms(), rec)
        scene.underlays.append((rec, group))
        fired = []
        scene.underlaysChanged.connect(lambda: fired.append(1))
        scene.set_underlay_layer_hidden(rec, group, "A-WALL", True)
        assert "A-WALL" in rec.hidden_layers
        assert all(not c.isVisible() for c in group.childItems()
                   if c.data(1) == "A-WALL")
        scene.set_underlay_layer_hidden(rec, group, "A-WALL", False)
        assert "A-WALL" not in rec.hidden_layers
        assert all(c.isVisible() for c in group.childItems()
                   if c.data(1) == "A-WALL")
        assert len(fired) == 2

    def test_noop_does_not_emit(self, qapp):
        scene = Model_Space()
        rec = _record()
        group, _ = scene._build_batched_underlay_group(_geoms(), rec)
        fired = []
        scene.underlaysChanged.connect(lambda: fired.append(1))
        scene.set_underlay_layer_hidden(rec, group, "A-WALL", False)  # already shown
        assert fired == []


class TestLevelsVisibility:
    """§16.x: underlay visibility is governed by the levels list."""

    def _scene_with_underlay(self, qapp, levels=("Level 1",)):
        scene = Model_Space()
        lm = LevelManager()
        # Ensure "Level 1" and "Level 2" exist in the LevelManager
        # (default LevelManager already has "Level 1"; add "Level 2")
        if not any(l.name == "Level 2" for l in lm._levels):
            from firepro3d.level_manager import Level
            lm._levels.append(Level("Level 2", elevation=3000.0))
        rec = _record()
        rec.levels = list(levels)
        group, _ = scene._build_batched_underlay_group(_geoms(), rec)
        scene.underlays.append((rec, group))
        return scene, rec, group, lm

    def test_levels_list_matches_active(self, qapp):
        """levels=["Level 1","Level 2"] → visible when active is "Level 1"."""
        scene, rec, group, lm = self._scene_with_underlay(
            qapp, levels=["Level 1", "Level 2"])
        lm.apply_to_scene(scene, "Level 1")
        assert group.isVisible()

    def test_levels_list_not_matching_active(self, qapp):
        """levels=["Level 2"] → hidden when active is "Level 1"."""
        scene, rec, group, lm = self._scene_with_underlay(
            qapp, levels=["Level 2"])
        lm.apply_to_scene(scene, "Level 1")
        assert not group.isVisible()

    def test_levels_star_always_visible(self, qapp):
        """levels=["*"] → visible regardless of active level."""
        scene, rec, group, lm = self._scene_with_underlay(
            qapp, levels=["*"])
        lm.apply_to_scene(scene, "Level 1")
        assert group.isVisible()

    def test_levels_empty_always_hidden(self, qapp):
        """levels=[] → hidden (no level assigned)."""
        scene, rec, group, lm = self._scene_with_underlay(
            qapp, levels=[])
        lm.apply_to_scene(scene, "Level 1")
        assert not group.isVisible()


class TestLevelRenameRemap:
    """§16.7: renaming a level remaps the underlay levels list; delete strips the removed name."""

    def _find_name_row(self, widget, text):
        for row in range(widget.table.rowCount()):
            it = widget.table.item(row, 0)
            if it is not None and it.text() == text:
                return row
        raise AssertionError(f"no level row named {text!r}")

    def _rename(self, lm, scene, old, new):
        from firepro3d.level_widget import LevelWidget
        widget = LevelWidget(lm, scene)
        row = self._find_name_row(widget, old)
        widget.table.item(row, 0).setText(new)  # drives _on_item_changed
        widget.deleteLater()

    def test_rename_remaps_level_assignment(self, qapp):
        # a level-specific underlay must follow its level's rename, not orphan
        scene = Model_Space()
        rec = _record()
        rec.levels = ["Level 1"]
        group, _ = scene._build_batched_underlay_group(_geoms(), rec)
        scene.underlays.append((rec, group))
        lm = LevelManager()

        self._rename(lm, scene, "Level 1", "Level 5")

        assert rec.levels == ["Level 5"]
        # still shown on the (renamed) level it belongs to
        lm.apply_to_scene(scene, "Level 5")
        assert group.isVisible()

    def test_delete_strips_level_from_underlays(self, qapp):
        # deleting a level removes it from every underlay's levels list
        from firepro3d.level_manager import Level
        from firepro3d.level_widget import LevelWidget
        scene = Model_Space()
        lm = LevelManager()
        if not any(l.name == "Level 2" for l in lm._levels):
            lm._levels.append(Level("Level 2", elevation=3000.0))
        rec = _record()
        rec.levels = ["Level 1", "Level 2"]
        group, _ = scene._build_batched_underlay_group(_geoms(), rec)
        scene.underlays.append((rec, group))

        # Drive the real delete path via LevelWidget
        widget = LevelWidget(lm, scene)
        row = self._find_name_row(widget, "Level 1")
        widget.table.setCurrentCell(row, 0)
        # Bypass the themed_confirm confirmation dialog
        import firepro3d.level_widget as _lw
        from unittest.mock import patch
        with patch.object(_lw, "themed_confirm", return_value=True):
            widget._delete_level()
        widget.deleteLater()

        assert rec.levels == ["Level 2"]


@pytest.fixture(scope="module")
def _main_window_singleton(qapp):
    """Module-scoped MainWindow shared by tab-switch tests (VTK-heavy).

    Same idiom as tests/test_ribbon_draft_tab.py: pre-import View3D,
    save/restore snap_engine.SNAP_TOLERANCE_PX (MainWindow overwrites it
    from QSettings), and clear _modified before close so teardown never
    hits the unsaved-changes prompt.  Imports are inside the fixture so
    the lightweight tests above don't pay the View3D import cost.
    """
    from PyQt6.QtTest import QTest
    from firepro3d import snap_engine
    import main as _main_module
    from firepro3d.view_3d import View3D  # heavy import, required before MainWindow()
    _main_module.View3D = View3D
    from main import MainWindow

    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    win._modified = False
    win.close()
    win.deleteLater()
    qapp.processEvents()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


@pytest.fixture
def main_window(_main_window_singleton):
    return _main_window_singleton


class TestTabSwitchVisibility:
    def test_detail_activation_sets_detail_view_key(self, main_window,
                                                    monkeypatch):
        """Slot-level by necessity: the pure-key assertion is the target.

        _apply_detail_level's key format is not reachable through a widget
        without building a real detail marker; stub get_marker with a minimal
        fake and assert the ``detail:<name>`` key lands on the scene.
        """
        win = main_window
        scene = win.scene

        class _FakeMarker:
            level_name = scene.active_level
            view_height = None
            view_depth = None

        prior_key = scene.active_view_key
        monkeypatch.setattr(win.detail_manager, "get_marker",
                            lambda name: _FakeMarker())
        try:
            win._apply_detail_level("Riser")
            assert scene.active_view_key == "detail:Riser"
        finally:
            scene.active_view_key = prior_key


@pytest.fixture(autouse=True)
def _restore_color_mode():
    prior = pd.load_paper_color_mode()
    yield
    save_paper_color_mode(prior)


def _paper_scene_setup(qapp, **rec_kw):
    scene = Model_Space()
    rec = _record(**rec_kw)
    group, _ = scene._build_batched_underlay_group(_geoms(), rec)
    scene.underlays.append((rec, group))
    rect = QRectF(-500, -500, 2000, 2000)
    return scene, rec, group, rect


class TestPaperUnderlayStage:
    def test_bw_mode_blackens_strokes_and_restores(self, qapp):
        scene, rec, group, rect = _paper_scene_setup(qapp)
        save_paper_color_mode(PaperColorMode.BW)
        child = next(c for c in group.childItems() if c.data(1) == "A-WALL")
        before = child.pen().color().name()
        saved = apply_paper_overrides(scene, rect, paper_scale=0.02,
                                      source_view_key="plan:Plan: Level 1")
        assert child.pen().color().name() == "#000000"
        restore_model_display(saved)
        assert child.pen().color().name() == before

    def test_full_color_keeps_authored_colours(self, qapp):
        scene, rec, group, rect = _paper_scene_setup(
            qapp, layer_overrides={"A-WALL": {"colour": "#ff0000"}})
        save_paper_color_mode(PaperColorMode.FULL_COLOR)
        child = next(c for c in group.childItems() if c.data(1) == "A-WALL")
        saved = apply_paper_overrides(scene, rect, paper_scale=0.02,
                                      source_view_key="plan:x")
        assert child.pen().color().name() == "#ff0000"
        restore_model_display(saved)

    def test_custom_mode_keeps_authored_colours(self, qapp):
        """Spec D6: black ONLY in BW — Custom keeps authored colours too."""
        scene, rec, group, rect = _paper_scene_setup(
            qapp, layer_overrides={"A-WALL": {"colour": "#ff0000"}})
        save_paper_color_mode(PaperColorMode.CUSTOM)
        child = next(c for c in group.childItems() if c.data(1) == "A-WALL")
        saved = apply_paper_overrides(scene, rect, paper_scale=0.02,
                                      source_view_key="plan:x")
        assert child.pen().color().name() == "#ff0000"
        restore_model_display(saved)

    def test_named_weight_true_mm_pen(self, qapp):
        scene, rec, group, rect = _paper_scene_setup(
            qapp, line_weight_name="Heavy")     # factory 0.35mm
        save_paper_color_mode(PaperColorMode.BW)
        child = next(c for c in group.childItems() if c.data(1) == "A-WALL")
        paper_scale = 0.02
        saved = apply_paper_overrides(scene, rect, paper_scale=paper_scale,
                                      source_view_key="plan:x")
        assert not child.pen().isCosmetic()
        assert child.pen().widthF() == pytest.approx(0.35 / paper_scale)
        restore_model_display(saved)
        assert child.pen().isCosmetic()      # screen pen back

    def test_no_weight_keeps_cosmetic_hairline(self, qapp):
        scene, rec, group, rect = _paper_scene_setup(qapp)
        child = next(c for c in group.childItems() if c.data(1) == "A-WALL")
        saved = apply_paper_overrides(scene, rect, paper_scale=0.02,
                                      source_view_key="plan:x")
        assert child.pen().isCosmetic()
        assert child.pen().widthF() == pytest.approx(UNDERLAY_LINE_WIDTH_PX)
        restore_model_display(saved)

    def test_model_hidden_group_stays_hidden(self, qapp):
        """A group hidden by the model-side pass is left alone (§16.5)."""
        scene, rec, group, rect = _paper_scene_setup(qapp)
        group.setVisible(False)
        saved = apply_paper_overrides(scene, rect, paper_scale=0.02,
                                      source_view_key="plan:x")
        assert not group.isVisible()
        restore_model_display(saved)
        assert not group.isVisible()


# ─────────────────────────────────────────────────────────────────────────────
# §16.10 acceptance — viewport-pixel + PDF-export parity through REAL rendering
# Idioms (fixture geometry, _render_paper, _dark_run_width, fitz sampling)
# copied from tests/test_gridline_paper_scale.py — not imported (private test
# helpers stay private to their module).
# ─────────────────────────────────────────────────────────────────────────────

PX_PER_MM = 8            # viewport-render density (matches gridline suite)
_RASTER_DPI = 300        # fitz raster density for PDF measurements
_EXPORT_DPI = 300        # QPdfWriter resolution

# A4 portrait sheet, 80mm-square viewport(s), crop centered on model (0,0):
# S = 80mm / 4000mm = 1:50 (paper_scale 0.02).
_VP_W = 80.0
_VP_A_X, _VP_A_Y = 65.0, 30.0    # center (105, 70)
_VP_B_X, _VP_B_Y = 65.0, 130.0   # center (105, 170)
_CROP = QRectF(-2000.0, -2000.0, 4000.0, 4000.0)
_SCALE = 0.02

# Deterministic, generous strokes: one vertical line through the crop center
# (thickness measured as a horizontal dark run — the gridline-suite idiom),
# plus (test 2 only) a big text glyph left of it, baseline at model (0,-1000)
# → paper y = 50mm, well clear of the line row (y = 70mm) and borders.
_VLINE = {"kind": "line", "x1": 0, "y1": -1500, "x2": 0, "y2": 1500,
          "layer": "A-WALL"}
_TEXT = {"kind": "text", "text": "X", "x": -800, "y": -1000, "size": 300,
         "layer": "A-WALL"}


def _sheet_with_viewports(view_defs):
    """A4 sheet with 80mm-square viewports; view_defs = (type, name, x, y)."""
    from firepro3d.paper_space import Sheet, SheetViewData
    sheet = Sheet.create_default()
    sheet.paper_size = "A4"  # programmatic title block — no DXF artwork load
    sheet.sheet_views = [
        SheetViewData(vt, vn, vn, _SCALE, x, y, _VP_W, _VP_W)
        for (vt, vn, x, y) in view_defs]
    return sheet


def _mock_resolver(scene):
    """Every view resolves to the same model scene + the fixed square crop.

    Same MagicMock(spec=ViewResolver) pattern as the gridline suite's
    two_scale_sheet fixture — the source_view_key under test is built from
    SheetViewData (type:name), not from the resolver, so a shared crop is
    exactly what isolates the per-view exclusion path.
    """
    from firepro3d.paper_space import ViewResolver
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.side_effect = lambda vt, vn: (scene, QRectF(_CROP))
    return resolver


# ── PDF-export parity (fitz sampling idiom from the gridline suite) ──────────

def _pdf_pixmap(pdf_path):
    """Rasterize page 1 at _RASTER_DPI; return (pixmap, px_per_mm)."""
    doc = fitz.open(str(pdf_path))
    try:
        page = doc[0]
        pm = page.get_pixmap(dpi=_RASTER_DPI)
        page_w_mm = page.rect.width / 72 * 25.4   # PDF points → mm
        return pm, pm.width / page_w_mm
    finally:
        doc.close()


def _pm_lightness(buf, pm, x, y):
    off = y * pm.stride + x * pm.n
    r, g, b = buf[off], buf[off + 1], buf[off + 2]
    return (max(r, g, b) + min(r, g, b)) // 2


def _pm_min_lightness(pm, ppm, x0_mm, y0_mm, x1_mm, y1_mm):
    """Darkest pixel in a paper-mm region (255 = nothing drawn)."""
    buf = pm.samples          # copy the pixmap buffer ONCE — not per pixel
    lo = 255
    for y in range(int(y0_mm * ppm), int(y1_mm * ppm)):
        for x in range(int(x0_mm * ppm), int(x1_mm * ppm)):
            lo = min(lo, _pm_lightness(buf, pm, x, y))
    return lo


def _pm_dark_run(pm, y_px, x0, x1):
    """Widest contiguous run of dark pixels on row y between x0..x1."""
    buf = pm.samples          # copy the pixmap buffer ONCE — not per pixel
    best = run = 0
    for x in range(x0, min(x1, pm.width)):
        if _pm_lightness(buf, pm, x, y_px) < 200:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def _export_single_viewport_pdf(tmp_path, geoms, name, **rec_kw):
    """Model scene + underlay → single-viewport A4 sheet → export_pdf.

    Returns (out_path, record, group). The viewport is VP-A (center 105,70).
    """
    from firepro3d import paper_export
    scene = Model_Space()
    rec = _record(**rec_kw)
    group, _ = scene._build_batched_underlay_group(
        [dict(g) for g in geoms], rec)
    scene.underlays.append((rec, group))
    sheet = _sheet_with_viewports([("plan", "Plan: Level 1", _VP_A_X, _VP_A_Y)])
    out = tmp_path / name
    paper_export.export_pdf([sheet], _mock_resolver(scene), str(out),
                            dpi=_EXPORT_DPI)
    return out, rec, group


def _measure_stroke_mm(pdf_path):
    """Stroke thickness of the vertical center line, in paper mm.

    Scans the row through the viewport center (y = 70mm), strictly inside
    the viewport (2mm border guard) — the gridline-suite dark-run idiom.
    """
    pm, ppm = _pdf_pixmap(pdf_path)
    row = int((_VP_A_Y + _VP_W / 2) * ppm)
    x0 = int((_VP_A_X + 2) * ppm)
    x1 = int((_VP_A_X + _VP_W - 2) * ppm)
    return _pm_dark_run(pm, row, x0, x1) / ppm


class TestExportUnderlayParity:
    def test_export_bw_underlay_black(self, qapp, tmp_path):
        """BW export blackens underlay strokes AND text fills; model restored."""
        save_paper_color_mode(PaperColorMode.BW)
        out, rec, group = _export_single_viewport_pdf(
            tmp_path, [_VLINE, _TEXT], "bw.pdf",
            line_weight_name="Very Heavy")   # 0.50mm — unambiguous sampling
        pm, ppm = _pdf_pixmap(out)
        # Stroke: near-black core at the line location (105, 70)±2mm.
        # A retained-gray pen (#c0c0c0, lightness 192) can never dip below
        # ~180 — lightness < 60 is exclusive to a blackened stroke.
        assert _pm_min_lightness(pm, ppm, 103, 68, 107, 72) < 60
        # Text batch: glyph "X" (size 300 ≈ 6mm cap on paper), baseline at
        # paper (89, 50) — scan a generous box over the glyph.
        assert _pm_min_lightness(pm, ppm, 86, 40, 101, 50.5) < 60
        # Model pens/brushes restored after export (screen look untouched).
        stroke = next(c for c in group.childItems()
                      if isinstance(c, QGraphicsPathItem)
                      and c.pen().style() != Qt.PenStyle.NoPen)
        text = next(c for c in group.childItems()
                    if isinstance(c, QGraphicsPathItem)
                    and c.pen().style() == Qt.PenStyle.NoPen)
        assert stroke.pen().isCosmetic()
        assert stroke.pen().color().name() == "#c0c0c0"
        assert stroke.pen().widthF() == pytest.approx(
            0.50 * UNDERLAY_MM_TO_PX_HINT)   # screen hint pen back
        assert text.brush().color().name() == "#c0c0c0"

    def test_export_weight_true_mm(self, qapp, tmp_path):
        """Named weight "Heavy" measures ≈0.35mm on the exported page."""
        save_paper_color_mode(PaperColorMode.BW)
        out, _, _ = _export_single_viewport_pdf(
            tmp_path, [_VLINE], "heavy.pdf", line_weight_name="Heavy")
        measured_mm = _measure_stroke_mm(out)
        # ±2 raster px — the gridline suite's viewport-measurement tolerance
        # expressed at the fitz density (2 / 11.81 ≈ 0.17mm).
        assert measured_mm == pytest.approx(0.35, abs=2 / (_RASTER_DPI / 25.4))

    def test_export_no_weight_hairline_baseline(self, qapp, tmp_path):
        """No named weight → cosmetic hairline, NOT promoted to a mm pen.

        A cosmetic UNDERLAY_LINE_WIDTH_PX pen is 1.5 device px at the export
        DPI → 1.5 raster px at the (equal) raster DPI; allow +2px AA fringe
        (the same slack the gridline suite gives its Very Light stroke).
        """
        save_paper_color_mode(PaperColorMode.BW)
        out, _, _ = _export_single_viewport_pdf(tmp_path, [_VLINE], "hair.pdf")
        pm, ppm = _pdf_pixmap(out)
        row = int((_VP_A_Y + _VP_W / 2) * ppm)
        x0 = int((_VP_A_X + 2) * ppm)
        x1 = int((_VP_A_X + _VP_W - 2) * ppm)
        width_px = _pm_dark_run(pm, row, x0, x1)
        hairline_px = UNDERLAY_LINE_WIDTH_PX * _RASTER_DPI / _EXPORT_DPI
        assert 1 <= width_px <= hairline_px + 2



# ──────────────────────────────────────────────────────────────────────────────
# §16.6 — PDF underlay colour persistence
# ──────────────────────────────────────────────────────────────────────────────


class TestPdfColourPersistence:
    def test_pdf_colour_round_trips(self):
        rec = _record(type="pdf", path="x.pdf", colour="#123456")
        assert Underlay.from_dict(rec.to_dict()).colour == "#123456"
