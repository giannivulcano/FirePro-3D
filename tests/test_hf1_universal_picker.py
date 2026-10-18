"""HF1 smoke round (2026-10-18 ruling): ONE universal colour picker.

Every picker call site shows every row (Theme: Automatic / Accent, No Fill,
Standard / Recents / custom) and every property it edits honours a
``token:*`` string (resolved per paint, paper-aware) and ``""`` (draws
nothing). Slice A: 2D geometry fill / stroke, text fill, Display Manager
(category / instance / Section / paper tab), Graphic Override.

Ground truth is the paint result (pixels from a real ``paint``, the pen / brush
actually used), reached through the real caller methods; only the modal
dialog itself is stubbed (``ColourPickerDialog.exec`` / ``pick_colour``).
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog, QStyleOptionGraphicsItem

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from firepro3d import colour_picker, snap_engine, theme
from firepro3d.constants import TOKEN_ACCENT, TOKEN_AUTO
from firepro3d.geometry_2d import LineItem, RectangleItem
from main import MainWindow
from tests._mainwindow_helpers import dispose_main_window

DARK_INK, LIGHT_INK = "#e6e9ec", "#1c2024"
BG = "#808080"


@pytest.fixture
def force_theme(monkeypatch):
    def _set(name):
        monkeypatch.setattr(theme, "theme_preference", lambda: name)
    return _set


@pytest.fixture
def picker_spy(monkeypatch):
    """Stub the modal: record what the real dialog offers, then cancel."""
    seen = []

    def exec_(self):
        seen.append({
            "theme": [c.value for c in self._theme_row_chips],
            "standard": [c.value for c in self._standard_row_chips],
            "initial": self.current_value(),
        })
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(colour_picker.ColourPickerDialog, "exec", exec_)
    return seen


def _pick_returns(monkeypatch, value):
    """pick_colour returns *value*; ``seen`` records the initial it was given."""
    seen = []

    def fake(initial, parent=None, context="", **_retired):
        seen.append(initial)
        return value
    monkeypatch.setattr(colour_picker, "pick_colour", fake)
    return seen


def _pixels(item, size=120):
    """Set of colour names from really painting *item* over a grey backdrop."""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor(BG))
    p = QPainter(img)
    p.setWindow(item.boundingRect().toRect())
    item.paint(p, QStyleOptionGraphicsItem(), None)
    p.end()
    return {img.pixelColor(x, y).name() for x in range(size) for y in range(size)}


def _solid_rect(scene, stroke="#00ff00"):
    r = RectangleItem(QPointF(0, 0), QPointF(500, 300))
    scene.addItem(r)
    if hasattr(scene, "_draw_rects"):
        scene._draw_rects.append(r)    # as the draw tool registers it (DM categories)
    r.fill_type = "solid"
    r.fill_opacity = 1.0            # exact fill colour, not a blend
    r.style["colour"] = stroke      # a stroke colour distinct from every fill
    return r


def _dispose(w):
    from PyQt6 import sip
    if not sip.isdeleted(w):
        w.hide()
        w.deleteLater()
    from PyQt6.QtWidgets import QApplication
    QApplication.processEvents()


# ── Picker shows every row at every (former opt-out) site ────────────────────

def _assert_full_picker(seen):
    assert len(seen) == 1, "the real caller must open the picker once"
    assert seen[0]["theme"] == [TOKEN_AUTO, TOKEN_ACCENT]
    assert seen[0]["standard"][-1] == "", "No Fill chip ends the Standard row"


def test_dm_section_dialog_picker_shows_theme_and_no_fill(qapp, picker_spy):
    from firepro3d.display_manager import SectionPatternDialog
    dlg = SectionPatternDialog("#666666", "diagonal", 1.0)
    try:
        dlg._pick_color()
    finally:
        _dispose(dlg)
    _assert_full_picker(picker_spy)


@pytest.mark.parametrize("prop", ["color", "fill"])
def test_dm_category_pick_shows_theme_and_no_fill(qapp, picker_spy, prop):
    from firepro3d.display_manager import DisplayManager, _CATEGORIES
    from firepro3d.model_space import Model_Space
    dm = DisplayManager(Model_Space())
    try:
        key = next(c["key"] for c in _CATEGORIES if c["fill"])
        dm._pick_category_prop(key, prop)
    finally:
        _dispose(dm)
    _assert_full_picker(picker_spy)


def test_dm_paper_tab_pick_shows_theme_and_no_fill(qapp, picker_spy):
    from firepro3d.display_manager import DisplayManager
    from firepro3d.model_space import Model_Space
    dm = DisplayManager(Model_Space())
    try:
        dm._on_paper_color_clicked(next(iter(dm._paper_cat_data)), "color")
    finally:
        _dispose(dm)
    _assert_full_picker(picker_spy)


def test_property_panel_swatch_picker_shows_theme_and_no_fill(qapp, picker_spy):
    """A 2D-geometry Colour swatch (formerly the only token-enabled kind) and
    a text Fill Color swatch (formerly the only No-Fill kind) both open the
    one full picker."""
    from firepro3d.property_manager import PropertyManager
    from firepro3d.text_item import TextAnnotationData, TextItem
    from firepro3d.ui_kit import Swatch
    pm = PropertyManager()
    try:
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        pm.show_properties(line)
        sw = next(s for s in pm.findChildren(Swatch) if s._context == "Colour")
        QTest.mouseClick(sw._chip, Qt.MouseButton.LeftButton)
        _assert_full_picker(picker_spy)
        picker_spy.clear()
        pm.show_properties(TextItem(TextAnnotationData(text="A", fill_color="")))
        sw = next(s for s in pm.findChildren(Swatch) if s._context == "Font Color")
        QTest.mouseClick(sw._chip, Qt.MouseButton.LeftButton)
        _assert_full_picker(picker_spy)
    finally:
        _dispose(pm)


# ── MainWindow entries: 2D geometry Fill, Graphic Override ──────────────────

@pytest.fixture(scope="module")
def _mw_singleton(qapp):
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    dispose_main_window(win)
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


@pytest.fixture
def mw(_mw_singleton, qapp):
    yield _mw_singleton
    _mw_singleton.scene.clearSelection()
    qapp.processEvents()
    for it in list(_mw_singleton.scene.items()):
        if isinstance(it, (RectangleItem, LineItem)):
            _mw_singleton.scene.removeItem(it)
    _mw_singleton.scene._draw_rects[:] = []
    qapp.processEvents()


def _fill_button(mw, qapp):
    from PyQt6.QtWidgets import QToolButton
    tb = mw.ribbon._tab_bar
    tabs = [tb.tabText(i) for i in range(tb.count())]
    page = mw.ribbon._stack.widget(tabs.index("Modify | Rectangle"))
    return next(b for b in page.findChildren(QToolButton)
                if b.toolTip() == "Override the fill colour")


def _click_fill(mw, qapp, rect):
    rect.setSelected(True)
    qapp.processEvents()
    _fill_button(mw, qapp).click()
    qapp.processEvents()


def test_main_fill_pick_shows_theme_and_no_fill(mw, qapp, picker_spy):
    _click_fill(mw, qapp, _solid_rect(mw.scene))
    _assert_full_picker(picker_spy)


def test_graphic_override_pick_shows_theme_and_no_fill(mw, qapp, picker_spy):
    r = _solid_rect(mw.scene)
    r.setSelected(True)
    mw._graphic_override_fill()
    _assert_full_picker(picker_spy)
    picker_spy.clear()
    mw._graphic_override_stroke()
    _assert_full_picker(picker_spy)


# ── 2D geometry fill: token / "" ─────────────────────────────────────────────

@pytest.mark.parametrize("theme_name,ink", [("dark", DARK_INK), ("light", LIGHT_INK)])
def test_2d_fill_token_paints_theme_ink_on_canvas(mw, qapp, monkeypatch,
                                                  force_theme, theme_name, ink):
    force_theme(theme_name)
    r = _solid_rect(mw.scene)
    _pick_returns(monkeypatch, TOKEN_AUTO)
    _click_fill(mw, qapp, r)
    assert r._display_fill_color == TOKEN_AUTO              # stored, not latched
    assert ink in _pixels(r)
    force_theme("light" if theme_name == "dark" else "dark")
    other = LIGHT_INK if theme_name == "dark" else DARK_INK
    assert other in _pixels(r)                               # re-resolved per paint


def test_2d_fill_token_paints_black_on_full_colour_paper(mw, qapp, monkeypatch,
                                                         force_theme):
    from firepro3d.paper_display import (PaperColorMode, apply_paper_overrides,
                                         restore_model_display,
                                         save_paper_color_mode)
    force_theme("dark")
    r = _solid_rect(mw.scene)
    _pick_returns(monkeypatch, TOKEN_AUTO)
    _click_fill(mw, qapp, r)
    assert DARK_INK in _pixels(r)
    save_paper_color_mode(PaperColorMode.FULL_COLOR)
    saved = apply_paper_overrides(mw.scene, QRectF(-5000, -5000, 10000, 10000))
    try:
        px = _pixels(r)
        assert "#000000" in px and DARK_INK not in px
    finally:
        restore_model_display(saved)
    assert DARK_INK in _pixels(r)


def test_2d_fill_no_fill_draws_nothing_and_survives_round_trip(mw, qapp, monkeypatch):
    from firepro3d.geometry_2d import RectangleItem as R
    r = _solid_rect(mw.scene)
    # control: an unset fill paints the default grey, a hex paints itself
    assert "#888888" in _pixels(r)
    _pick_returns(monkeypatch, "#ff0000")
    _click_fill(mw, qapp, r)
    assert "#ff0000" in _pixels(r)
    _pick_returns(monkeypatch, "")
    _click_fill(mw, qapp, r)
    assert r._display_fill_color == ""                       # not None, not grey
    px = _pixels(r)
    assert px <= {BG, "#00ff00"}, px          # only backdrop + the green stroke
    d = r.to_dict()
    assert d["fill"]["color"] == ""
    again = R.from_dict(d)
    assert again._display_fill_color == ""


def test_2d_fill_panel_value_keeps_no_fill(mw, qapp):
    r = _solid_rect(mw.scene)
    r._display_fill_color = ""
    assert r.get_properties()["Fill Colour"]["value"] == ""


# ── 2D geometry stroke: "" ───────────────────────────────────────────────────

def test_2d_stroke_no_stroke_draws_nothing(qapp, monkeypatch, force_theme):
    from firepro3d.model_space import Model_Space
    from firepro3d.property_manager import PropertyManager
    from firepro3d.ui_kit import Swatch
    from PyQt6.QtCore import Qt
    force_theme("dark")
    scene = Model_Space()
    r = RectangleItem(QPointF(0, 0), QPointF(500, 300))
    scene.addItem(r)
    r.style["colour"] = "#ff0000"
    assert "#ff0000" in _pixels(r)                           # control: stroke shows
    pm = PropertyManager()
    try:
        pm.show_properties(r)
        sw = next(s for s in pm.findChildren(Swatch) if s._context == "Colour")
        _pick_returns(monkeypatch, "")
        QTest.mouseClick(sw._chip, Qt.MouseButton.LeftButton)
    finally:
        _dispose(pm)
    assert r.style["colour"] == ""                           # not coerced to Automatic
    px = _pixels(r)
    assert px == {BG}, px                                    # nothing drawn at all
    again = RectangleItem.from_dict(r.to_dict())
    assert again.style["colour"] == ""


# ── Text fill: token / "" ────────────────────────────────────────────────────

@pytest.mark.parametrize("theme_name,ink", [("dark", DARK_INK), ("light", LIGHT_INK)])
def test_text_fill_token_paints_theme_ink(qapp, monkeypatch, force_theme,
                                          theme_name, ink):
    from firepro3d.property_manager import PropertyManager
    from firepro3d.text_item import TextAnnotationData, TextItem
    from firepro3d.ui_kit import Swatch
    from PyQt6.QtCore import Qt
    force_theme(theme_name)
    item = TextItem(TextAnnotationData(text="A", height_mm=4.0, fill_opacity=100.0,
                                       color="#00ff00"))     # glyphs off the ink colour
    pm = PropertyManager()
    try:
        pm.show_properties(item)
        sw = next(s for s in pm.findChildren(Swatch) if s._context == "Fill Color")
        _pick_returns(monkeypatch, TOKEN_AUTO)
        QTest.mouseClick(sw._chip, Qt.MouseButton.LeftButton)
    finally:
        _dispose(pm)
    assert item._data.fill_color == TOKEN_AUTO
    assert ink in _pixels(item)


@pytest.mark.parametrize("token,expected", [(TOKEN_AUTO, "#000000"),
                                            (TOKEN_ACCENT, "#2f9e63")])
def test_text_fill_token_resolves_for_paper_scene(qapp, force_theme, monkeypatch,
                                                  token, expected):
    from unittest.mock import MagicMock
    from firepro3d import paper_display
    from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
    from firepro3d.text_item import TextAnnotationData
    force_theme("dark")
    monkeypatch.setattr(paper_display, "load_paper_color_mode",
                        lambda *a, **k: paper_display.PaperColorMode.FULL_COLOR)
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.return_value = None
    ps = PaperScene(Sheet.create_default(), resolver)
    t = ps.add_annotation(TextAnnotationData(text="A", height_mm=4.0,
                                             color="#00ff00",
                                             fill_color=token,
                                             fill_opacity=100.0))
    px = _pixels(t)
    assert expected in px and DARK_INK not in px


# ── Display Manager ──────────────────────────────────────────────────────────

def _grid_scene():
    from firepro3d.gridline import GridlineItem
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="1")
    ms.addItem(gl)
    return ms, gl


@pytest.mark.parametrize("value,alpha", [("", 0), ("#ff0000", 255)])
def test_dm_category_fill_no_fill_vs_hex_reaches_the_brush(qapp, monkeypatch,
                                                           value, alpha):
    from firepro3d.display_manager import DisplayManager
    ms, gl = _grid_scene()
    _pick_returns(monkeypatch, value)
    dm = DisplayManager(ms)
    try:
        dm._pick_category_prop("Grid Line", "fill")
        assert dm._read_category_settings("Grid Line")["fill"] == value
        brush = gl.bubble1.brush()
        assert brush.color().alpha() == alpha
        if value:
            assert brush.color().name() == value
    finally:
        _dispose(dm)


def test_dm_category_fill_token_resolves_for_the_brush(qapp, monkeypatch, force_theme):
    from firepro3d.display_manager import DisplayManager
    force_theme("dark")
    ms, gl = _grid_scene()
    _pick_returns(monkeypatch, TOKEN_AUTO)
    dm = DisplayManager(ms)
    try:
        dm._pick_category_prop("Grid Line", "fill")
        assert gl.bubble1.brush().color().name() == DARK_INK
        assert dm._read_category_settings("Grid Line")["fill"] == TOKEN_AUTO
    finally:
        _dispose(dm)


def test_dm_no_fill_persists_and_is_not_inherit(qapp, monkeypatch):
    from PyQt6.QtCore import QSettings
    from firepro3d.display_manager import (DisplayManager, _CATEGORY_MAP,
                                           _read_category_from_settings)
    ms, gl = _grid_scene()
    _pick_returns(monkeypatch, "")
    dm = DisplayManager(ms)
    try:
        dm._pick_category_prop("Grid Line", "fill")
        dm.accept()
    finally:
        _dispose(dm)
    # persisted as "" and read back as "" -- never the factory fill (inherit)
    assert _read_category_from_settings("Grid Line")["fill"] == ""
    assert _CATEGORY_MAP["Grid Line"]["fill"] not in ("", None)
    QSettings("GV", "FirePro3D").remove("display/Grid Line/fill")


def test_dm_instance_state_no_fill_vs_unset(qapp):
    """A per-item No Fill is read back as "" (shown as None); an unset item
    inherits the category default -- the two never collapse."""
    from firepro3d.display_manager import DisplayManager, _CATEGORY_MAP
    from firepro3d.model_space import Model_Space
    from firepro3d.room import Room
    ms = Model_Space()
    room = Room([QPointF(0, 0), QPointF(2000, 0), QPointF(2000, 2000), QPointF(0, 2000)])
    ms.addItem(room)
    dm = DisplayManager(ms)
    try:
        room._display_fill_color = ""
        assert dm._read_item_display_state(room, "Room")["fill"] == ""
        room._display_fill_color = None
        assert (dm._read_item_display_state(room, "Room")["fill"]
                == _CATEGORY_MAP["Room"]["fill"])
    finally:
        _dispose(dm)


def test_dm_swatch_looks(qapp, force_theme):
    from PyQt6.QtWidgets import QPushButton
    from firepro3d.display_manager import _apply_swatch_look
    force_theme("light")
    t = theme.detect()
    b = QPushButton()
    _apply_swatch_look(b, "", t)
    assert b.text() == "None" and "transparent" in b.styleSheet()
    _apply_swatch_look(b, TOKEN_ACCENT, t)
    assert b.text() == "Accent" and t.accent.lower() in b.styleSheet().lower()
    _dispose(b)


def test_dm_section_token_and_no_fill_render_in_the_dialog(qapp, monkeypatch,
                                                           force_theme):
    from firepro3d.display_manager import SectionPatternDialog
    force_theme("light")
    dlg = SectionPatternDialog("#666666", "diagonal", 1.0)
    try:
        _pick_returns(monkeypatch, TOKEN_ACCENT)
        dlg._pick_color()
        assert dlg.get_result()[0] == TOKEN_ACCENT
        img = dlg._preview.pixmap().toImage()
        accent = theme.detect().accent.lower()
        names = {img.pixelColor(x, y).name() for x in range(img.width())
                 for y in range(img.height()) if img.pixelColor(x, y).alpha() == 255}
        assert accent in names, (accent, names)
        _pick_returns(monkeypatch, "")
        dlg._pick_color()
        assert dlg.get_result()[0] == ""
        img = dlg._preview.pixmap().toImage()
        assert all(img.pixelColor(x, y).alpha() == 0 or img.pixelColor(x, y).name() == "#2b2b2b"
                   for x in range(img.width()) for y in range(img.height()))
        assert dlg._color_btn.text() == "None"
    finally:
        _dispose(dlg)


def test_dm_svg_tint_fill_token_and_no_fill(qapp, force_theme, tmp_path):
    from firepro3d import display_manager as dm
    force_theme("light")
    svg = tmp_path / "s.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" '
                   'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">'
                   '<g inkscape:groupmode="layer"><rect width="1" '
                   'height="1"/></g></svg>', encoding="utf-8")
    tok = bytes(dm._recolor_svg_bytes(str(svg), "#ff0000", TOKEN_AUTO)).decode().lower()
    assert "fill:" + LIGHT_INK in tok and "token" not in tok
    none = bytes(dm._recolor_svg_bytes(str(svg), "#ff0000", "")).decode().lower()
    assert "fill:none" in none


def _paper_pass_colours(scene, gl):
    """(grid colour, bubble pen colour) a gridline really draws with during a
    paper pass."""
    from firepro3d.paper_display import apply_paper_overrides, restore_model_display
    saved = apply_paper_overrides(scene, QRectF(-5000, -5000, 10000, 10000))
    try:
        return QColor(gl._grid_color), gl.bubble1.pen().color()
    finally:
        restore_model_display(saved)


@pytest.mark.parametrize("value,name,alpha", [(TOKEN_ACCENT, "#2f9e63", 255),
                                              ("", None, 0)])
def test_dm_paper_tab_colour_reaches_the_paper_pen(qapp, monkeypatch, force_theme,
                                                   value, name, alpha):
    from firepro3d.display_manager import DisplayManager
    from firepro3d.model_space import Model_Space
    from firepro3d.paper_display import PaperColorMode
    force_theme("dark")
    ms, gl = _grid_scene()
    _pick_returns(monkeypatch, value)
    dm = DisplayManager(ms)
    try:
        dm._on_paper_color_clicked("Grid Line", "color")
    finally:
        _dispose(dm)
    from firepro3d.paper_display import load_paper_color_mode
    assert load_paper_color_mode() is PaperColorMode.CUSTOM
    grid, bubble_pen = _paper_pass_colours(ms, gl)
    assert grid.alpha() == alpha and bubble_pen.alpha() == alpha
    if name:
        assert grid.name() == name and bubble_pen.name() == name


# ── Graphic Override (token / "") ────────────────────────────────────────────

@pytest.mark.parametrize("theme_name,ink", [("dark", DARK_INK), ("light", LIGHT_INK)])
def test_graphic_override_fill_token_paints_ink(mw, qapp, monkeypatch, force_theme,
                                                theme_name, ink):
    force_theme(theme_name)
    r = _solid_rect(mw.scene)
    r._display_overrides["color"] = "#00ff00"   # keep the stroke off the ink colour
    r.setSelected(True)
    qapp.processEvents()
    _pick_returns(monkeypatch, TOKEN_AUTO)
    mw._graphic_override_fill()
    assert r._display_overrides["fill"] == TOKEN_AUTO
    assert r._display_fill_color == TOKEN_AUTO
    assert ink in _pixels(r)


def test_graphic_override_fill_no_fill_draws_nothing(mw, qapp, monkeypatch):
    r = _solid_rect(mw.scene)
    r._display_overrides["color"] = "#00ff00"   # keep the stroke off the ink colour
    r.setSelected(True)
    qapp.processEvents()
    assert "#888888" in _pixels(r)
    _pick_returns(monkeypatch, "")
    mw._graphic_override_fill()
    assert r._display_overrides["fill"] == ""
    assert _pixels(r) <= {BG, "#00ff00"}


def test_graphic_override_stroke_no_stroke_draws_nothing(mw, qapp, monkeypatch):
    r = RectangleItem(QPointF(0, 0), QPointF(500, 300))
    mw.scene.addItem(r)
    mw.scene._draw_rects.append(r)
    r.style["colour"] = "#ff0000"
    r.setSelected(True)
    qapp.processEvents()
    assert "#ff0000" in _pixels(r)
    _pick_returns(monkeypatch, "")
    mw._graphic_override_stroke()
    assert r._display_overrides["color"] == ""
    r.setSelected(False)       # a selected rect also draws its corner guides
    assert _pixels(r) == {BG}


def test_pick_colour_has_no_opt_out_flags(qapp, monkeypatch):
    """The retired allow_none / allow_tokens kwargs are gone (slice B): the
    one picker takes (initial, parent, context) and always shows every row."""
    import inspect
    assert list(inspect.signature(colour_picker.pick_colour).parameters) == [
        "initial", "parent", "context"]
    seen = []

    def exec_(self):
        seen.append(bool(self._theme_row_chips) and self._standard_row_chips[-1].value == "")
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(colour_picker.ColourPickerDialog, "exec", exec_)
    assert colour_picker.pick_colour("#112233", None, "x") is None
    assert seen == [True]


# ── Font colour: "" ──────────────────────────────────────────────────────────

def test_text_font_colour_no_colour_draws_no_glyphs(qapp, monkeypatch, force_theme):
    from firepro3d.font_group import FontGroupController
    from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
    from firepro3d.text_item import TextAnnotationData, TextItem
    from unittest.mock import MagicMock
    force_theme("dark")
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.return_value = None
    ps = PaperScene(Sheet.create_default(), resolver)
    item = ps.add_annotation(TextAnnotationData(text="AB", height_mm=6.0,
                                                color="#ff0000"))
    assert "#ff0000" in _pixels(item)                     # control: the glyphs draw
    c = FontGroupController(get_targets=lambda: [item])
    _pick_returns(monkeypatch, "")
    c._pick_color()
    assert item.data.color == ""
    assert _pixels(item) == {BG}
