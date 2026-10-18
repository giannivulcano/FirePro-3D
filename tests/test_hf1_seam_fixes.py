"""HF1 VC9 seam-fix round guards (I1 elevation, I2/I4 latched DM consumers,
I3 per-instance overrides, M3 copy/paste/undo round-trip)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, QSettings
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QGraphicsView

from firepro3d import theme
from firepro3d.constants import TOKEN_AUTO


@pytest.fixture
def force_theme(monkeypatch):
    def _set(name):
        monkeypatch.setattr(theme, "theme_preference", lambda: name)
    return _set


def _view_pixels(scene, rect):
    """Every opaque non-background colour on a shown view of *scene*."""
    v = QGraphicsView(scene)
    v.resize(500, 300)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.fitInView(rect)
    v.viewport().repaint()
    img = v.viewport().grab().toImage()
    bg = img.pixelColor(2, 2).name()
    out = {img.pixelColor(x, y).name()
           for x in range(img.width()) for y in range(img.height())} - {bg}
    v.close()
    return out


def _floor_slab(ms):
    from firepro3d.floor_slab import FloorSlab
    slab = FloorSlab(points=[QPointF(0, 0), QPointF(4000, 0),
                             QPointF(4000, 4000), QPointF(0, 4000)])
    slab._top_mode = "absolute"
    slab._top_abs_z_mm = 3000.0
    slab._bottom_mode = "absolute"
    slab._bottom_abs_z_mm = 2000.0
    ms.addItem(slab)
    ms._floor_slabs.append(slab)
    return slab


def _token_floor_dm():
    s = QSettings("GV", "FirePro3D")        # conftest-isolated
    s.setValue("display/Floor/color", TOKEN_AUTO)
    s.setValue("display/Floor/fill", TOKEN_AUTO)
    s.setValue("display/Floor/opacity", 100)


# ── I1: elevation views resolve token DM colours ────────────────────────────

@pytest.mark.parametrize("name,ink", [("dark", "#e6e9ec"), ("light", "#1c2024")])
def test_i1_elevation_token_category_paints_theme_ink(
        qapp, force_theme, elevation_scene_for, name, ink):
    force_theme(name)
    _token_floor_dm()
    ms, elev = elevation_scene_for("north")
    _floor_slab(ms)
    elev.rebuild()
    px = _view_pixels(elev, QRectF(-500, -3500, 5000, 2000))
    assert ink in px, sorted(px)[:8]
    assert "#000000" not in px


def test_i1_elevation_flips_on_live_theme_switch(qapp, force_theme):
    from firepro3d.view_3d import View3D  # noqa: F401 -- heavy import before MainWindow
    import main as _main_module
    _main_module.View3D = View3D
    from main import MainWindow
    from tests._mainwindow_helpers import dispose_main_window
    force_theme("dark")
    prev_qss = qapp.styleSheet()
    _token_floor_dm()
    win = MainWindow()
    try:
        win.show()
        QTest.qWaitForWindowExposed(win)
        _floor_slab(win.scene)
        win.elevation_manager.open_elevation("north")
        elev = win.elevation_manager.get_scene("north")
        elev.rebuild()
        rect = QRectF(-500, -3500, 5000, 2000)
        assert "#e6e9ec" in _view_pixels(elev, rect)
        force_theme("light")
        win._apply_theme()
        px = _view_pixels(elev, rect)
        assert "#1c2024" in px and "#e6e9ec" not in px
        assert elev.backgroundBrush().color().name() == QColor(theme.LIGHT.canvas_bg).name()
        assert elev._edge_color.name() == "#000000"      # was #d0d0d0 on dark
    finally:
        dispose_main_window(win)
        qapp.setStyleSheet(prev_qss)


# ── I2: latched DM consumers on Full Colour paper ───────────────────────────

def _plot_colours(pdf):
    """(stroke rgbs, fill rgbs) of every drawing inside the sample viewport."""
    import fitz
    from tests.test_lt1_block_paper import _VP_W, _VP_X, _VP_Y
    pt = 25.4 / 72.0
    strokes, fills = set(), set()
    doc = fitz.open(str(pdf))
    try:
        for d in doc[0].get_drawings():
            r = d["rect"]
            x0, y0, x1, y1 = (v * pt for v in (r.x0, r.y0, r.x1, r.y1))
            if not (_VP_X + 1 < x0 and x1 < _VP_X + _VP_W - 1
                    and _VP_Y + 1 < y0 and y1 < _VP_Y + _VP_W - 1):
                continue                    # viewport frame / title block
            t = d.get("type") or ""
            if "s" in t and d.get("color") is not None:
                strokes.add(tuple(round(c, 2) for c in d["color"]))
            if "f" in t and d.get("fill") is not None:
                fills.add(tuple(round(c, 2) for c in d["fill"]))
    finally:
        doc.close()
    return strokes, fills


def _gridline_and_sprinkler_scene(colour):
    from firepro3d.display_manager import (
        _apply_to_scene_items, _read_category_from_settings)
    from firepro3d.gridline import GridlineItem
    from firepro3d.model_space import Model_Space
    s = QSettings("GV", "FirePro3D")
    for key in ("Grid Line", "Sprinkler"):
        s.setValue(f"display/{key}/color", colour)
    ms = Model_Space()
    gl = GridlineItem(QPointF(-1200, 500), QPointF(1200, 500), label="A")
    ms._gridlines.append(gl)
    ms.addItem(gl)
    n = ms.add_node(0, -800)
    ms.add_sprinkler(n)
    for key in ("Grid Line", "Sprinkler"):
        _apply_to_scene_items(ms, key, _read_category_from_settings(key))
    return ms, gl, n.sprinkler


@pytest.mark.parametrize("colour,rgb", [
    (TOKEN_AUTO, (0.0, 0.0, 0.0)),
    ("token:accent", (0.18, 0.62, 0.39)),
], ids=["auto", "accent"])
def test_i2_latched_dm_categories_plot_paper_colour_on_full_colour(
        qapp, tmp_path, force_theme, colour, rgb):
    """A gridline and a sprinkler symbol whose category is Automatic/Accent
    latch the CANVAS colour; the Full Colour pass must re-resolve them."""
    from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
    from tests.test_lt1_block_paper import _export
    force_theme("dark")                       # canvas ink #e6e9ec / accent #63be8b
    save_paper_color_mode(PaperColorMode.FULL_COLOR)
    ms, gl, spr = _gridline_and_sprinkler_scene(colour)
    canvas_grid = gl._grid_color.name()
    pdf = _export(tmp_path, ms, 0.02, "i2.pdf")
    strokes, fills = _plot_colours(pdf)
    canvas = {(0.9, 0.91, 0.93), (0.39, 0.75, 0.55)}      # dark-theme ink / accent
    assert strokes & {rgb}, (strokes, fills)              # gridline + symbol
    assert not (strokes | fills) & canvas, (strokes, fills)
    assert gl._grid_color.name() == canvas_grid           # model colour restored
    # The sprinkler SVG plots as a raster: sample the pixels around it
    # (paper x 105 mm, y 54 mm -- model (0, -800) at 1:50).
    import fitz
    mm = 72.0 / 25.4
    doc = fitz.open(str(pdf))
    try:
        pm = doc[0].get_pixmap(dpi=200, clip=fitz.Rect(
            95 * mm, 44 * mm, 115 * mm, 64 * mm))
    finally:
        doc.close()
    want = tuple(round(v * 255) for v in rgb)
    hits = sum(1 for x in range(pm.width) for y in range(pm.height)
               if all(abs(a - b) <= 10 for a, b in zip(pm.pixel(x, y), want)))
    assert hits > 100, hits       # canvas ink / accent would leave ~0 solid hits
    for canvas_rgb in ((0xe6, 0xe9, 0xec), (0x63, 0xbe, 0x8b)):   # dark-theme ink / accent
        stale = sum(1 for x in range(pm.width) for y in range(pm.height)
                    if all(abs(a - b) <= 3 for a, b in zip(pm.pixel(x, y), canvas_rgb)))
        assert stale < 20, (canvas_rgb, stale)    # latched canvas tint would be ~1400


# ── I3: per-instance token override under a hex category ────────────────────

def test_i3_token_override_under_hex_category_relatches_on_theme_switch(
        qapp, force_theme):
    from firepro3d.display_manager import (
        _apply_vals_to_item, _read_category_from_settings, refresh_token_latched)
    from firepro3d.gridline import GridlineItem
    from firepro3d.model_space import Model_Space
    force_theme("dark")
    QSettings("GV", "FirePro3D").setValue("display/Grid Line/color", "#ff0000")
    ms = Model_Space()
    gl = GridlineItem(QPointF(-1200, 0), QPointF(1200, 0), label="A")
    ms._gridlines.append(gl)
    ms.addItem(gl)
    gl._display_overrides = {"color": TOKEN_AUTO}      # per-instance override
    vals = _read_category_from_settings("Grid Line")
    assert vals["color"] == "#ff0000"                  # category stays hex
    _apply_vals_to_item(gl, vals, respect_overrides=True)
    rect = QRectF(-1500, -300, 3000, 600)
    assert "#e6e9ec" in _view_pixels(ms, rect)
    force_theme("light")
    refresh_token_latched(ms)                          # what the theme bus runs
    px = _view_pixels(ms, rect)
    assert "#1c2024" in px and "#e6e9ec" not in px


# ── I4: live switch flips latched DM consumers (gridline pen, sprinkler tint) ─

def test_i4_live_switch_flips_latched_gridline_and_sprinkler(qapp, force_theme):
    from firepro3d.display_manager import (
        _apply_to_scene_items, _read_category_from_settings)
    from firepro3d.gridline import GridlineItem
    from firepro3d.view_3d import View3D  # noqa: F401 -- heavy import before MainWindow
    import main as _main_module
    _main_module.View3D = View3D
    from main import MainWindow
    from tests._mainwindow_helpers import dispose_main_window
    force_theme("dark")
    prev_qss = qapp.styleSheet()        # _apply_theme restyles the whole app
    s = QSettings("GV", "FirePro3D")
    for key in ("Grid Line", "Sprinkler"):
        s.setValue(f"display/{key}/color", TOKEN_AUTO)
    win = MainWindow()
    try:
        win.show()
        QTest.qWaitForWindowExposed(win)
        ms = win.scene
        gl = GridlineItem(QPointF(-1200, 2000), QPointF(1200, 2000), label="A")
        ms._gridlines.append(gl)
        ms.addItem(gl)
        n = ms.add_node(0, -2000)
        ms.add_sprinkler(n)
        for key in ("Grid Line", "Sprinkler"):
            _apply_to_scene_items(ms, key, _read_category_from_settings(key))
        grid_rect = QRectF(-1500, 1700, 3000, 600)
        spr_rect = QRectF(-400, -2400, 800, 800)
        assert "#e6e9ec" in _view_pixels(ms, grid_rect)
        assert "#e6e9ec" in _view_pixels(ms, spr_rect)
        force_theme("light")
        win._apply_theme()                       # the real switch entry point
        gpx = _view_pixels(ms, grid_rect)
        assert "#1c2024" in gpx and "#e6e9ec" not in gpx
        spx = _view_pixels(ms, spr_rect)
        assert "#1c2024" in spx and "#e6e9ec" not in spx
    finally:
        dispose_main_window(win)
        qapp.setStyleSheet(prev_qss)     # a light QSS left behind poisons later pixel tests


# ── M1: text-tool preview rectangle follows the theme ───────────────────────

@pytest.mark.parametrize("name,ink", [("dark", "#e6e9ec"), ("light", "#1c2024")])
def test_m1_text_tool_preview_pen_is_theme_ink(qapp, force_theme, name, ink):
    from firepro3d.model_space import Model_Space
    force_theme(name)
    ms = Model_Space()
    ms._press_text(None, QPointF(0, 0), QPointF(0, 0), None, None, None)  # 1st click
    assert ms._text_preview is not None
    assert ms._text_preview.pen().color().name() == ink


# ── M3: token colour survives copy -> paste -> undo -> redo (regression guard) ─

def _stored_colour(item):
    d = getattr(item, "_data", None)
    return d.color if d is not None and hasattr(d, "color") else item.style["colour"]


@pytest.mark.parametrize("name", ["line", "text"])
def test_m3_token_colour_survives_copy_paste_undo_redo(qapp, force_theme, name):
    """Pure regression guard of already-correct behaviour (no RED proof)."""
    import json
    from PyQt6.QtWidgets import QApplication
    from tests._modify_tools_helpers import add_primitive
    from tests._snap_polish_helpers import click, close_view, make_view, move
    force_theme("dark")
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, name)
        assert _stored_colour(item) == TOKEN_AUTO             # the HF1 default
        scene._modify_ctl.start("copy")
        click(view, QPointF(0, 0))
        clip = QApplication.clipboard().text()
        assert TOKEN_AUTO in clip and "#e6e9ec" not in clip   # token, not resolved
        assert json.loads(clip)["items"]
        assert scene._modify_ctl.start("paste") is True
        move(view, QPointF(400, 300))
        click(view, QPointF(400, 300))
        lst = getattr(scene, attr)
        assert len(lst) == 2 and _stored_colour(lst[-1]) == TOKEN_AUTO
        scene.undo()
        assert len(getattr(scene, attr)) == 1
        scene.redo()
        lst = getattr(scene, attr)
        assert len(lst) == 2
        assert all(_stored_colour(i) == TOKEN_AUTO for i in lst)
        force_theme("light")                  # and it still resolves per paint
        from firepro3d.colour_tokens import resolve_colour
        assert resolve_colour(_stored_colour(lst[-1]), item=lst[-1]).name() == "#1c2024"
    finally:
        close_view(view, scene)


# ── I-B / VC9 round 2: fitting + marker paper-pass tint hand-off ────────────

def _fitting_scene(colour):
    """Model_Space with one pipe; the end nodes' fittings carry *colour*."""
    from firepro3d.display_manager import (
        _apply_to_scene_items, _read_category_from_settings)
    from firepro3d.model_space import Model_Space
    from firepro3d.pipe import Pipe
    QSettings("GV", "FirePro3D").setValue("display/Fitting/color", colour)
    ms = Model_Space()
    n1, n2 = ms.add_node(0, 0), ms.add_node(1000, 0)
    p = Pipe(n1, n2)
    ms.addItem(p)
    ms.sprinkler_system.add_pipe(p)
    for n in (n1, n2):
        n.fitting.type = n.fitting.determine_type(n.pipes)
        n.fitting.update()
    _apply_to_scene_items(ms, "Fitting", _read_category_from_settings("Fitting"))
    fits = [n.fitting for n in (n1, n2) if n.fitting.symbol is not None]
    assert fits and fits[0].symbol.isVisible()
    return ms, fits


@pytest.fixture
def tint_spy(monkeypatch):
    """Record every SVG recolour hex and every ``_set_svg_tint`` call."""
    from firepro3d import display_manager as dm
    rec = {"hex": [], "calls": 0}
    orig_rc, orig_tint = dm._recolor_svg_bytes, dm._set_svg_tint

    def rc(path, color=None, fill=None):
        rec["hex"].append(color)
        return orig_rc(path, color, fill)

    def tint(*a, **k):
        rec["calls"] += 1
        return orig_tint(*a, **k)
    monkeypatch.setattr(dm, "_recolor_svg_bytes", rc)
    monkeypatch.setattr(dm, "_set_svg_tint", tint)
    return rec


def _pass(ms, mode):
    from firepro3d.paper_display import (
        apply_paper_overrides, restore_model_display, save_paper_color_mode)
    save_paper_color_mode(mode)
    saved = apply_paper_overrides(ms, QRectF(-5000, -5000, 10000, 10000))
    return saved, restore_model_display


def test_ib_token_fitting_full_colour_paper_then_canvas(qapp, force_theme, tint_spy):
    from firepro3d.paper_display import PaperColorMode
    force_theme("dark")
    ms, fits = _fitting_scene(TOKEN_AUTO)
    tint_spy["hex"].clear()
    saved, restore = _pass(ms, PaperColorMode.FULL_COLOR)
    assert tint_spy["hex"] and set(tint_spy["hex"]) == {"#000000"}   # paper ink
    tint_spy["hex"].clear()
    restore(saved)
    assert set(tint_spy["hex"]) == {"#e6e9ec"}                       # canvas ink back
    assert all(f._display_color == TOKEN_AUTO for f in fits)


def test_ib_bw_pass_restores_fitting_canvas_tint(qapp, force_theme, tint_spy):
    from firepro3d.paper_display import PaperColorMode
    force_theme("dark")
    ms, fits = _fitting_scene(TOKEN_AUTO)
    saved, restore = _pass(ms, PaperColorMode.BW)
    tint_spy["hex"].clear()
    restore(saved)
    assert set(tint_spy["hex"]) == {"#e6e9ec"}       # symbol back to canvas ink


def test_ib_hex_fitting_restore_does_not_retint(qapp, force_theme, tint_spy):
    from firepro3d.paper_display import PaperColorMode
    force_theme("dark")
    ms, fits = _fitting_scene("#ff0000")
    before = [f._display_color for f in fits]
    saved, restore = _pass(ms, PaperColorMode.FULL_COLOR)
    tint_spy["calls"] = 0
    restore(saved)
    assert tint_spy["calls"] == 0
    assert [f._display_color for f in fits] == before == ["#ff0000"] * len(fits)


def _detail_marker_scene(colour):
    from firepro3d.display_manager import _apply_detail_marker
    from firepro3d.detail_view import DetailMarker
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    m = DetailMarker("D1", QRectF(0, 0, 400, 300))
    ms.addItem(m)
    _apply_detail_marker(m, colour, 1.0, 100, True, None)
    return ms, m


def test_id_detail_marker_token_full_colour_paper_then_canvas(qapp, force_theme):
    from firepro3d.paper_display import PaperColorMode
    force_theme("dark")
    QSettings("GV", "FirePro3D").setValue("display/Detail Marker/color", TOKEN_AUTO)
    ms, m = _detail_marker_scene(TOKEN_AUTO)
    canvas_tag, canvas_pen = m._tag_color.name(), m.pen().color().name()
    assert canvas_tag == "#e6e9ec"
    saved, restore = _pass(ms, PaperColorMode.FULL_COLOR)
    assert m._tag_color.name() == "#000000" and m.pen().color().name() == "#000000"
    restore(saved)
    assert m._tag_color.name() == canvas_tag and m.pen().color().name() == canvas_pen


def test_id_elevation_marker_never_plots_on_paper(qapp, force_theme):
    """ViewMarkerArrow is PAPER_EXCLUDED (hidden for the pass), so its
    ``_apply_marker`` token branch is unreachable; pin that and the restore."""
    from firepro3d.paper_display import PaperColorMode
    from firepro3d.view_marker import ViewMarkerArrow
    from firepro3d.model_space import Model_Space
    force_theme("dark")
    ms = Model_Space()
    m = ViewMarkerArrow("north")
    ms.addItem(m)
    before = m._marker_color.name()
    saved, restore = _pass(ms, PaperColorMode.FULL_COLOR)
    assert not m.isVisible() and m._marker_color.name() == before
    restore(saved)
    assert m.isVisible() and m._marker_color.name() == before
