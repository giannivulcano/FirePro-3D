"""HF1 smoke round (2026-10-18 ruling), slice B: the dialog call sites.

ONE universal colour picker: every site shows the Theme row and No Fill, and
every property it edits honours a ``token:*`` string (resolved per paint,
surface-aware) and ``""`` (draws nothing). Slice B: Roof colour (2D + 3D),
Underlay colour (canvas + paper), title-block Border / Field text / Field
fill (paper), the Fire Suppression visibility swatches.

Ground truth is pixels from a real paint / render, the PDF a real export
writes, or the colour / opacity read from the PyVista actor. Only the modal
dialog is stubbed (``ColourPickerDialog.exec`` for the row guards,
``colour_picker.pick_colour`` to supply the returned value).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QEvent, QModelIndex, QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QMouseEvent, QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog, QStyleOptionGraphicsItem, QStyleOptionViewItem

from firepro3d import colour_picker, theme
from firepro3d.constants import TOKEN_ACCENT, TOKEN_AUTO
# Slice A's helpers and fixtures (picker_spy / force_theme are pytest fixtures).
from tests.test_hf1_universal_picker import (          # noqa: F401
    BG, DARK_INK, LIGHT_INK, _assert_full_picker, _dispose, _pick_returns,
    force_theme, picker_spy)

ACCENT_PAPER = "#2f9e63"


@pytest.fixture(autouse=True)
def _qt_app(qapp):
    """Every guard builds real widgets: a QApplication must exist even when a
    single node is run in isolation."""
    return qapp


# ── Roof ─────────────────────────────────────────────────────────────────────

def _roof_in_scene(ms, colour="#d2b48c"):
    from firepro3d.roof import RoofItem
    r = RoofItem(points=[QPointF(0, 0), QPointF(400, 0), QPointF(400, 300),
                         QPointF(0, 300)], color=colour)
    ms.addItem(r)
    ms._roofs.append(r)
    return r


def _roof_pick(monkeypatch, roof, value):
    """Drive the real caller: RoofItem's edit-dialog path, the dialog's own
    colour button handler supplying *value* through the (stubbed) picker."""
    from firepro3d.roof_dialog import RoofDialog
    seen = _pick_returns(monkeypatch, value)

    def exec_(self):
        self._pick_color()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(RoofDialog, "exec", exec_)
    roof._open_edit_dialog()
    return seen


def _pixels(item, size=120):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor(BG))
    p = QPainter(img)
    p.setWindow(item.boundingRect().toRect())
    item.paint(p, QStyleOptionGraphicsItem(), None)
    p.end()
    return {img.pixelColor(x, y).name() for x in range(size) for y in range(size)}


@pytest.fixture
def ms(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    yield s
    s.deleteLater()
    QTest.qWait(0)


def test_roof_dialog_picker_shows_theme_and_no_fill(qapp, picker_spy):
    from firepro3d.roof_dialog import RoofDialog
    dlg = RoofDialog(None, defaults={"color": "#d2b48c"})
    try:
        dlg._pick_color()
    finally:
        _dispose(dlg)
    _assert_full_picker(picker_spy)


def test_roof_dialog_swatch_shows_token_and_no_fill(qapp, monkeypatch, force_theme):
    from firepro3d.roof_dialog import RoofDialog
    force_theme("dark")
    dlg = RoofDialog(None, defaults={"color": "#d2b48c"})
    try:
        _pick_returns(monkeypatch, TOKEN_ACCENT)
        dlg._pick_color()
        assert dlg.get_params()["color"] == TOKEN_ACCENT
        assert dlg._color_btn.text() == "Accent"
        _pick_returns(monkeypatch, "")
        dlg._pick_color()
        assert dlg.get_params()["color"] == ""
        assert dlg._color_btn.text() == "None"
    finally:
        _dispose(dlg)


@pytest.mark.parametrize("theme_name,ink", [("dark", DARK_INK), ("light", LIGHT_INK)])
def test_roof_2d_token_paints_theme_ink_per_paint(ms, monkeypatch, force_theme,
                                                  theme_name, ink):
    force_theme(theme_name)
    r = _roof_in_scene(ms)
    assert ink not in _pixels(r)                          # control: hex roof
    _roof_pick(monkeypatch, r, TOKEN_AUTO)
    assert r._colour == TOKEN_AUTO                        # stored, not latched
    assert ink in _pixels(r)
    other = LIGHT_INK if theme_name == "dark" else DARK_INK
    force_theme("light" if theme_name == "dark" else "dark")
    assert other in _pixels(r) and ink not in _pixels(r)  # re-resolved per paint


def test_roof_2d_accent_token_paints_theme_accent(ms, monkeypatch, force_theme):
    force_theme("dark")
    r = _roof_in_scene(ms)
    _roof_pick(monkeypatch, r, TOKEN_ACCENT)
    assert theme.detect().accent.lower() in _pixels(r)


def test_roof_2d_no_fill_draws_nothing(ms, monkeypatch):
    r = _roof_in_scene(ms)
    assert _pixels(r) != {BG}                             # control: hex draws
    _roof_pick(monkeypatch, r, "")
    assert r._colour == ""
    assert _pixels(r) == {BG}


def test_roof_colour_round_trips_token_and_no_fill(ms, monkeypatch):
    from firepro3d.roof import RoofItem
    r = _roof_in_scene(ms)
    for v in (TOKEN_AUTO, TOKEN_ACCENT, "", "#123456"):
        _roof_pick(monkeypatch, r, v)
        assert RoofItem.from_dict(r.to_dict())._colour == v
        assert r.get_properties()["Colour"]["value"] == v
        seen = _roof_pick(monkeypatch, r, v)
        assert seen == [v]                  # the reopened dialog seeds the stored value


def test_roof_property_panel_colour_stores_token_and_no_fill(ms):
    r = _roof_in_scene(ms)
    for v in (TOKEN_AUTO, "", "#123456"):
        r.set_property("Colour", v)
        assert r._colour == v


# ── Roof 3D ──────────────────────────────────────────────────────────────────

@pytest.fixture
def real3d(qapp):
    pytest.importorskip("pyvista")
    pytest.importorskip("pyvistaqt")
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_space import Model_Space
    from firepro3d.view_3d import View3D
    s = Model_Space()
    lm = LevelManager()
    s._level_manager = lm
    v = View3D(s, lm, s.scale_manager)
    yield s, v
    v.hide()
    v.cleanup()
    v.deleteLater()
    s.deleteLater()
    QTest.qWait(0)


def _roof_actor(v):
    (actor,) = [a for a in v._actors["roofs"] if a is not None]
    prop = actor.GetProperty()
    return tuple(round(c * 255) for c in prop.GetColor()), prop.GetOpacity()


def _rgb(hex_):
    c = QColor(hex_)
    return (c.red(), c.green(), c.blue())


def test_roof_3d_token_resolves_canvas_ink_and_follows_the_theme(
        real3d, monkeypatch, force_theme):
    s, v = real3d
    force_theme("dark")
    r = _roof_in_scene(s)
    v.rebuild()
    assert _roof_actor(v)[0] != _rgb(DARK_INK)            # control: hex roof
    _roof_pick(monkeypatch, r, TOKEN_AUTO)
    v.rebuild()
    assert _roof_actor(v) == (_rgb(DARK_INK), 1.0)
    # Theme bus: a visible view rebuilds itself when a token roof is in use.
    v.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    v.show()
    QTest.qWait(300)
    force_theme("light")
    theme.theme_bus().changed.emit()
    QTest.qWait(300)
    assert _roof_actor(v) == (_rgb(LIGHT_INK), 1.0)


def test_roof_3d_theme_change_ignores_hex_roofs(real3d, monkeypatch, force_theme):
    s, v = real3d
    _roof_in_scene(s)
    v.rebuild()
    v.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    v.show()
    QTest.qWait(300)
    v._dirty = False
    theme.theme_bus().changed.emit()
    assert v._dirty is False                              # no token: no rebuild


def test_roof_3d_accent_token_resolves_theme_accent(real3d, monkeypatch, force_theme):
    s, v = real3d
    force_theme("dark")
    r = _roof_in_scene(s)
    _roof_pick(monkeypatch, r, TOKEN_ACCENT)
    v.rebuild()
    assert _roof_actor(v) == (_rgb(theme.detect().accent), 1.0)


def test_roof_3d_no_fill_draws_no_surface(real3d, monkeypatch):
    s, v = real3d
    r = _roof_in_scene(s)
    v.rebuild()
    assert _roof_actor(v)[1] == 1.0                       # control: hex draws
    assert [a for a in v._actors["roof_edges"] if a is not None]
    _roof_pick(monkeypatch, r, "")
    v.rebuild()
    assert _roof_actor(v)[1] == 0.0                       # transparent actor
    assert not [a for a in v._actors["roof_edges"] if a is not None]
    assert len(v._actors["roofs"]) == len(v._actors["roof_edges"])   # parallel


# ── Underlay ─────────────────────────────────────────────────────────────────

_LINE = [{"kind": "line", "x1": -400, "y1": 0, "x2": 400, "y2": 0,
          "layer": "A", "width": 1.0}]


def _underlay(ms, colour="#00ff00", layer_colour=None):
    from firepro3d.underlay import Underlay
    rec = Underlay(type="pdf", path="x.pdf", colour=colour)
    if layer_colour is not None:
        rec.layer_overrides["A"] = {"colour": layer_colour}
    g, _ = ms._build_batched_underlay_group(list(_LINE), rec)
    ms.underlays.append((rec, g))
    return rec, g


def _underlay_pixels(group):
    from firepro3d.underlay_freeze import _UnderlayPathItem
    img = QImage(900, 40, QImage.Format.Format_ARGB32)
    img.fill(QColor(BG))
    p = QPainter(img)
    p.setWindow(-450, -20, 900, 40)
    kids = [c for c in group.childItems() if isinstance(c, _UnderlayPathItem)]
    assert kids
    for c in kids:
        c.paint(p, QStyleOptionGraphicsItem(), None)
    p.end()
    return {img.pixelColor(x, y).name() for x in range(900) for y in range(40)}


def _manager_model(ms):
    from firepro3d.underlay_manager_model import UnderlayTreeModel
    return UnderlayTreeModel(ms, theme.DARK, lambda: ["Level 1"])


def _colour_cell_click(model, row_parent=QModelIndex(), row=0):
    from firepro3d.underlay_manager_delegates import ColourDelegate
    from firepro3d.underlay_manager_model import Col
    idx = model.index(row, int(Col.COLOUR), row_parent)
    opt = QStyleOptionViewItem()
    opt.rect = QRect(0, 0, 120, 34)
    ev = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(opt.rect.center()),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    return ColourDelegate(theme.DARK).editorEvent(ev, model, opt, idx)


def test_underlay_picker_shows_theme_and_no_fill(ms, picker_spy):
    _underlay(ms)
    assert _colour_cell_click(_manager_model(ms)) is True
    _assert_full_picker(picker_spy)


def _delegate_swatch(ms, force_theme_name=None):
    from PyQt6.QtGui import QPixmap
    from firepro3d.underlay_manager_delegates import ColourDelegate
    from firepro3d.underlay_manager_model import Col
    model = _manager_model(ms)
    idx = model.index(0, int(Col.COLOUR), QModelIndex())
    opt = QStyleOptionViewItem()
    opt.rect = QRect(0, 0, 120, 34)
    pm = QPixmap(120, 34)
    pm.fill(QColor("#202020"))
    p = QPainter(pm)
    ColourDelegate(theme.DARK).paint(p, opt, idx)
    p.end()
    img = pm.toImage()
    return {img.pixelColor(x, y).name() for x in range(10, 21) for y in range(12, 23)}


def test_underlay_manager_swatch_shows_token_colour_and_no_fill_glyph(
        ms, force_theme):
    force_theme("dark")
    rec, _g = _underlay(ms, colour=TOKEN_AUTO)
    assert DARK_INK in _delegate_swatch(ms)                 # token resolved
    rec.colour = ""
    px = _delegate_swatch(ms)
    assert DARK_INK not in px and "#ffffff" in px           # No-Fill glyph: white
    assert any(_near(c, "#dd2222", 30) for c in px)         # ... and red slash


@pytest.mark.parametrize("theme_name,ink", [("dark", DARK_INK), ("light", LIGHT_INK)])
def test_underlay_token_paints_theme_ink_on_canvas(ms, monkeypatch, force_theme,
                                                   theme_name, ink):
    force_theme(theme_name)
    rec, g = _underlay(ms)
    assert ink not in _underlay_pixels(g)                 # control: hex
    _pick_returns(monkeypatch, TOKEN_AUTO)
    _colour_cell_click(_manager_model(ms))
    assert rec.colour == TOKEN_AUTO                       # stored, not latched
    assert ink in _underlay_pixels(g)
    other = LIGHT_INK if theme_name == "dark" else DARK_INK
    force_theme("light" if theme_name == "dark" else "dark")
    px = _underlay_pixels(g)
    assert other in px and ink not in px                  # re-resolved per paint


def test_underlay_layer_override_token_and_accent(ms, monkeypatch, force_theme):
    force_theme("dark")
    rec, g = _underlay(ms)
    model = _manager_model(ms)
    _pick_returns(monkeypatch, TOKEN_ACCENT)
    # the layer row (child of the underlay row) edits layer_overrides
    _colour_cell_click(model, model.index(0, 0, QModelIndex()), 0)
    assert rec.layer_overrides["A"]["colour"] == TOKEN_ACCENT
    dark_accent = theme.detect().accent.lower()
    assert dark_accent in _underlay_pixels(g)
    force_theme("light")                                   # re-resolved per paint
    px = _underlay_pixels(g)
    assert theme.detect().accent.lower() in px and dark_accent not in px


def test_underlay_no_fill_is_not_drawn(ms, monkeypatch):
    rec, g = _underlay(ms)
    assert "#00ff00" in _underlay_pixels(g)               # control: hex draws
    _pick_returns(monkeypatch, "")
    _colour_cell_click(_manager_model(ms))
    assert rec.colour == ""
    assert _underlay_pixels(g) == {BG}


def test_underlay_built_with_token_or_no_fill_paints_right(ms, force_theme):
    """A rebuild from the stored record (file load / cache) takes the same
    path as an edit: the colour string is resolved per paint."""
    force_theme("dark")
    _rec, g = _underlay(ms, colour=TOKEN_AUTO)
    assert DARK_INK in _underlay_pixels(g)
    force_theme("light")                                   # not latched at build
    px = _underlay_pixels(g)
    assert LIGHT_INK in px and DARK_INK not in px
    _rec2, g2 = _underlay(ms, colour="")
    assert _underlay_pixels(g2) == {BG}


def _paper_pass(ms, mode):
    from firepro3d.paper_display import apply_paper_overrides, save_paper_color_mode
    save_paper_color_mode(mode)
    return apply_paper_overrides(ms, QRectF(-2000, -2000, 4000, 4000),
                                 paper_scale=50.0)


@pytest.mark.parametrize("mode_name,expect", [("FULL_COLOR", "#000000"),
                                              ("BW", "#000000")])
def test_underlay_token_auto_is_black_on_paper(ms, force_theme, mode_name, expect):
    from firepro3d.paper_display import PaperColorMode, restore_model_display
    force_theme("dark")
    _rec, g = _underlay(ms, colour=TOKEN_AUTO)
    saved = _paper_pass(ms, PaperColorMode[mode_name])
    try:
        px = _underlay_pixels(g)
        assert expect in px and DARK_INK not in px
    finally:
        restore_model_display(saved)
    assert DARK_INK in _underlay_pixels(g)                # back on the canvas


def test_underlay_accent_is_light_accent_on_paper_and_black_in_bw(ms, force_theme):
    from firepro3d.paper_display import PaperColorMode, restore_model_display
    force_theme("dark")
    _rec, g = _underlay(ms, colour=TOKEN_ACCENT)
    for mode, want in ((PaperColorMode.FULL_COLOR, ACCENT_PAPER),
                       (PaperColorMode.BW, "#000000")):
        saved = _paper_pass(ms, mode)
        try:
            px = _underlay_pixels(g)
            assert want in px
            assert theme.detect().accent.lower() not in px
        finally:
            restore_model_display(saved)


def test_underlay_no_fill_is_not_drawn_on_paper(ms):
    from firepro3d.paper_display import PaperColorMode, restore_model_display
    _rec, g = _underlay(ms, colour="")
    saved = _paper_pass(ms, PaperColorMode.FULL_COLOR)
    try:
        assert _underlay_pixels(g) == {BG}
    finally:
        restore_model_display(saved)


def test_underlay_paper_pass_keeps_a_valid_pen_for_a_token(ms):
    from firepro3d.paper_display import PaperColorMode, restore_model_display
    from firepro3d.underlay_freeze import _UnderlayPathItem
    _rec, g = _underlay(ms, colour=TOKEN_AUTO)
    saved = _paper_pass(ms, PaperColorMode.FULL_COLOR)
    try:
        kids = [c for c in g.childItems() if isinstance(c, _UnderlayPathItem)]
        assert kids and all(c.pen().color().isValid() for c in kids)
    finally:
        restore_model_display(saved)


# ── Title block (paper) ──────────────────────────────────────────────────────

def _editor(tmp_path, monkeypatch):
    from firepro3d import titleblock_template as tbt
    from firepro3d.titleblock_editor import TitleBlockEditorDialog
    monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
    t = tbt.make_default_template()
    tbt.save_to_library(t)
    dlg = TitleBlockEditorDialog(project_template=None)
    dlg.select_template(t.uuid)
    return dlg


def _paper_scene(tpl):
    from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
    sheet = Sheet.create_default()
    sheet.paper_size = tpl.paper_size
    sheet.orientation = tpl.orientation
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.return_value = None
    ps = PaperScene(sheet, resolver)
    ps.set_template(tpl, {})
    return ps


def _render(scene, src, ppm):
    w, h = max(1, int(src.width() * ppm)), max(1, int(src.height() * ppm))
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, w, h), src)
    p.end()
    return img


def _farthest_from_white(img):
    """The pixel colour furthest from white (the glyph core / stroke colour)."""
    best, bd = QColor("#ffffff"), 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            d = (255 - c.red()) + (255 - c.green()) + (255 - c.blue())
            if d > bd:
                best, bd = c, d
    return best.name()


def _near(got, want, tol=40):
    a, b = QColor(got), QColor(want)
    return (abs(a.red() - b.red()) + abs(a.green() - b.green())
            + abs(a.blue() - b.blue())) <= tol


def _geom(ps, field_name="Project"):
    tb = ps._title_tb
    lay, var = tb._layout, tb._variant
    f = next(x for x in var.fields if x.name == field_name)
    i = lay.cell_field_ids.index(f.id)
    return lay, f, i


def _edge_pixel(ps):
    lay = ps._title_tb._layout
    ar = lay.area_rect
    src = QRectF(ar.left() - 3, ar.center().y() - 3, 6, 6)
    img = _render(ps, src, 10)
    return img.pixelColor(30, 30).name()


def _fill_pixel(ps):
    lay, _f, i = _geom(ps)
    cr = lay.cell_rects[i]
    img = _render(ps, QRectF(cr.right() - 2, cr.bottom() - 2, 1.5, 1.5), 10)
    return img.pixelColor(img.width() // 2, img.height() // 2).name()


def _label_ink(ps):
    lay, _f, i = _geom(ps)
    return _farthest_from_white(_render(ps, lay.cell_label_rects[i], 12))


def _full_colour(monkeypatch):
    from firepro3d import paper_display
    monkeypatch.setattr(paper_display, "load_paper_color_mode",
                        lambda *a, **k: paper_display.PaperColorMode.FULL_COLOR)


def _bw(monkeypatch):
    from firepro3d import paper_display
    monkeypatch.setattr(paper_display, "load_paper_color_mode",
                        lambda *a, **k: paper_display.PaperColorMode.BW)


def test_titleblock_border_picker_shows_theme_and_no_fill(tmp_path, monkeypatch,
                                                          picker_spy):
    dlg = _editor(tmp_path, monkeypatch)
    try:
        dlg._area_border._color_btn.click()
    finally:
        _dispose(dlg)
    _assert_full_picker(picker_spy)


def test_titleblock_field_text_picker_shows_theme_and_no_fill(tmp_path, monkeypatch,
                                                              picker_spy):
    dlg = _editor(tmp_path, monkeypatch)
    try:
        dlg._field_select_row(2)
        dlg._ftext_color_swatch.click()
    finally:
        _dispose(dlg)
    _assert_full_picker(picker_spy)


def test_titleblock_field_fill_picker_shows_theme_and_no_fill(tmp_path, monkeypatch,
                                                              picker_spy):
    dlg = _editor(tmp_path, monkeypatch)
    try:
        dlg._field_select_row(2)
        dlg._ffield_fill_swatch.click()
    finally:
        _dispose(dlg)
    _assert_full_picker(picker_spy)


def _set_border(dlg, value, monkeypatch):
    _pick_returns(monkeypatch, value)
    dlg._area_border._color_btn.click()


def _set_text(dlg, value, monkeypatch):
    dlg._field_select_row(2)
    _pick_returns(monkeypatch, value)
    dlg._ftext_color_swatch.click()


def _set_fill(dlg, value, monkeypatch):
    dlg._field_select_row(2)
    _pick_returns(monkeypatch, value)
    dlg._ffield_fill_swatch.click()


def test_titleblock_border_accent_is_paper_green_and_black_in_bw(
        tmp_path, monkeypatch, force_theme):
    force_theme("dark")
    dlg = _editor(tmp_path, monkeypatch)
    try:
        _set_border(dlg, "#ff0000", monkeypatch)
        _full_colour(monkeypatch)
        ps = _paper_scene(dlg.working)
        assert _near(_edge_pixel(ps), "#ff0000")           # control: hex
        ps.dispose()
        _set_border(dlg, TOKEN_ACCENT, monkeypatch)
        assert dlg.working.layout.area_border.color == TOKEN_ACCENT   # stored
        ps = _paper_scene(dlg.working)
        assert _near(_edge_pixel(ps), ACCENT_PAPER)
        ps.dispose()
        _bw(monkeypatch)
        ps = _paper_scene(dlg.working)
        assert _near(_edge_pixel(ps), "#000000")
        ps.dispose()
    finally:
        _dispose(dlg)


def test_titleblock_border_auto_is_black_not_theme_ink(tmp_path, monkeypatch,
                                                       force_theme):
    force_theme("dark")
    dlg = _editor(tmp_path, monkeypatch)
    try:
        _set_border(dlg, "#ff0000", monkeypatch)
        _set_border(dlg, TOKEN_AUTO, monkeypatch)
        _full_colour(monkeypatch)
        ps = _paper_scene(dlg.working)
        assert _near(_edge_pixel(ps), "#000000")           # not the e6e9ec ink
        ps.dispose()
    finally:
        _dispose(dlg)


def test_titleblock_border_no_fill_draws_no_border(tmp_path, monkeypatch):
    dlg = _editor(tmp_path, monkeypatch)
    try:
        _set_border(dlg, "#ff0000", monkeypatch)
        _full_colour(monkeypatch)
        ps = _paper_scene(dlg.working)
        assert _edge_pixel(ps) != "#ffffff"                # control: drawn
        ps.dispose()
        _set_border(dlg, "", monkeypatch)
        assert dlg.working.layout.area_border.color == ""
        ps = _paper_scene(dlg.working)
        assert _edge_pixel(ps) == "#ffffff"
        ps.dispose()
    finally:
        _dispose(dlg)


def test_titleblock_field_text_token_and_no_fill(tmp_path, monkeypatch, force_theme):
    force_theme("dark")
    dlg = _editor(tmp_path, monkeypatch)
    try:
        _full_colour(monkeypatch)
        _set_text(dlg, "#ff0000", monkeypatch)
        ps = _paper_scene(dlg.working)
        assert _near(_label_ink(ps), "#ff0000")            # control: hex
        ps.dispose()
        _set_text(dlg, TOKEN_ACCENT, monkeypatch)
        assert _geom(_paper_scene(dlg.working))[1].text_color == TOKEN_ACCENT
        ps = _paper_scene(dlg.working)
        assert _near(_label_ink(ps), ACCENT_PAPER)
        ps.dispose()
        _set_text(dlg, TOKEN_AUTO, monkeypatch)
        ps = _paper_scene(dlg.working)
        assert _near(_label_ink(ps), "#000000")            # not near-white ink
        ps.dispose()
        _bw(monkeypatch)
        _set_text(dlg, TOKEN_ACCENT, monkeypatch)
        ps = _paper_scene(dlg.working)
        assert _near(_label_ink(ps), "#000000")
        ps.dispose()
        _full_colour(monkeypatch)
        _set_text(dlg, "", monkeypatch)
        assert _geom(_paper_scene(dlg.working))[1].text_color == ""
        ps = _paper_scene(dlg.working)
        assert _label_ink(ps) == "#ffffff"                 # no glyph drawn
        ps.dispose()
    finally:
        _dispose(dlg)


def test_titleblock_editor_swatches_show_token_colour_and_no_fill(
        tmp_path, monkeypatch, force_theme):
    force_theme("dark")
    dlg = _editor(tmp_path, monkeypatch)
    try:
        _set_fill(dlg, TOKEN_AUTO, monkeypatch)
        sw = dlg._ffield_fill_swatch
        assert sw.grab().toImage().pixelColor(3, 3).name() == DARK_INK
        assert sw.text() == "A" and sw.icon().isNull()
        _set_fill(dlg, "", monkeypatch)
        assert not sw.icon().isNull() and sw.text() == ""    # No-Fill glyph
    finally:
        _dispose(dlg)


def test_titleblock_no_fill_text_and_border_reopen_as_no_fill(tmp_path, monkeypatch):
    """"" is a value, not 'unset': the picker re-opens seeded with "" (not
    black) and the border group reads "" back instead of falling to black."""
    dlg = _editor(tmp_path, monkeypatch)
    try:
        _set_text(dlg, "", monkeypatch)
        seen = _pick_returns(monkeypatch, None)
        dlg._ftext_color_swatch.click()
        assert seen == [""]
        _set_border(dlg, "", monkeypatch)
        assert dlg._area_border.read()["color"] == ""
        assert dlg.working.layout.area_border.color == ""
    finally:
        _dispose(dlg)


def test_titleblock_field_fill_token_and_no_fill(tmp_path, monkeypatch, force_theme):
    force_theme("dark")
    dlg = _editor(tmp_path, monkeypatch)
    try:
        _full_colour(monkeypatch)
        _set_fill(dlg, "#ff0000", monkeypatch)
        ps = _paper_scene(dlg.working)
        assert _fill_pixel(ps) == "#ff0000"                # control: hex
        ps.dispose()
        _set_fill(dlg, TOKEN_ACCENT, monkeypatch)
        ps = _paper_scene(dlg.working)
        assert _fill_pixel(ps) == ACCENT_PAPER
        ps.dispose()
        _set_fill(dlg, TOKEN_AUTO, monkeypatch)
        ps = _paper_scene(dlg.working)
        assert _fill_pixel(ps) == "#000000"                # paper ink, not e6e9ec
        ps.dispose()
        _bw(monkeypatch)
        _set_fill(dlg, TOKEN_ACCENT, monkeypatch)
        ps = _paper_scene(dlg.working)
        assert _fill_pixel(ps) == "#000000"
        ps.dispose()
        _full_colour(monkeypatch)
        _set_fill(dlg, "", monkeypatch)
        ps = _paper_scene(dlg.working)
        assert _fill_pixel(ps) == "#ffffff"
        ps.dispose()
    finally:
        _dispose(dlg)


def test_titleblock_editor_preview_scene_resolves_tokens_as_paper(
        tmp_path, monkeypatch, force_theme):
    """The editor's own preview scene carries ``paints_on_paper``: a token
    border reads paper green there, never the dark-theme ink."""
    force_theme("dark")
    _full_colour(monkeypatch)
    dlg = _editor(tmp_path, monkeypatch)
    try:
        _set_border(dlg, TOKEN_ACCENT, monkeypatch)
        sc = dlg._preview_scene
        (tb,) = [i for i in sc.items() if type(i).__name__ == "TitleBlockTemplateItem"]
        ar = tb._layout.area_rect
        img = _render(sc, QRectF(ar.left() - 3, ar.center().y() - 3, 6, 6), 10)
        assert _near(img.pixelColor(30, 30).name(), ACCENT_PAPER)
    finally:
        _dispose(dlg)


def test_titleblock_pdf_export_border_token_is_paper_green_or_black(
        tmp_path, monkeypatch, force_theme):
    """The real PDF export path (paper pass): an Accent border plots paper
    green in colour, black in B&W."""
    fitz = pytest.importorskip("fitz")
    from firepro3d import paper_export
    from firepro3d.paper_space import Sheet, ViewResolver
    force_theme("dark")
    dlg = _editor(tmp_path, monkeypatch)
    try:
        _set_border(dlg, TOKEN_ACCENT, monkeypatch)
        tpl = dlg.working
        sheet = Sheet.create_default()
        sheet.paper_size, sheet.orientation = tpl.paper_size, tpl.orientation
        resolver = MagicMock(spec=ViewResolver)
        resolver.resolve.return_value = None

        def stroke_colours(name):
            out = tmp_path / name
            paper_export.export_pdf([sheet], resolver, str(out), dpi=72,
                                    template=tpl, project_info={})
            doc = fitz.open(str(out))
            try:
                return {tuple(round(v * 255) for v in d["color"])
                        for d in doc[0].get_drawings() if d.get("color")}
            finally:
                doc.close()
        _full_colour(monkeypatch)
        col = stroke_colours("c.pdf")
        want = tuple(round(v) for v in _rgb(ACCENT_PAPER))
        assert any(max(abs(a - b) for a, b in zip(c, want)) <= 2 for c in col), col
        _bw(monkeypatch)
        bw = stroke_colours("bw.pdf")
        assert not any(max(abs(a - b) for a, b in zip(c, want)) <= 2 for c in bw), bw
    finally:
        _dispose(dlg)


# ── Fire Suppression visibility dialog ───────────────────────────────────────

def _fs_dialog(monkeypatch):
    from firepro3d.fs_visibility_dialog import FSVisibilityDialog
    return FSVisibilityDialog()


def _swatch_corner(btn, dlg):
    dlg.show()
    QTest.qWaitForWindowExposed(dlg)
    return btn.grab().toImage().pixelColor(3, 3).name()


def test_fs_visibility_picker_shows_theme_and_no_fill(qapp, picker_spy):
    dlg = _fs_dialog(None)
    try:
        dlg._pick("Pipe", dlg._rows["Pipe"]["btn"])
    finally:
        _dispose(dlg)
    _assert_full_picker(picker_spy)


def test_fs_visibility_token_and_no_fill_swatch_and_persistence(
        qapp, monkeypatch, force_theme):
    force_theme("dark")
    dlg = _fs_dialog(None)
    try:
        btn = dlg._rows["Pipe"]["btn"]
        _pick_returns(monkeypatch, TOKEN_AUTO)
        dlg._pick("Pipe", btn)
        assert dlg.get_settings()["Pipe"]["color"] == TOKEN_AUTO
        assert _swatch_corner(btn, dlg) == DARK_INK        # token resolved
        dlg.save_settings()
        dlg2 = _fs_dialog(None)
        assert dlg2.get_settings()["Pipe"]["color"] == TOKEN_AUTO
        _dispose(dlg2)
        _pick_returns(monkeypatch, "")
        dlg._pick("Pipe", btn)
        assert dlg.get_settings()["Pipe"]["color"] == ""
        assert btn.text() == "None"
        seen = _pick_returns(monkeypatch, None)
        dlg._pick("Pipe", btn)
        assert seen == [""]                                # "" is a value, not unset
        assert _swatch_corner(btn, dlg) != DARK_INK
        dlg.save_settings()
        dlg3 = _fs_dialog(None)
        assert dlg3.get_settings()["Pipe"]["color"] == ""  # "" survives QSettings
        _dispose(dlg3)
    finally:
        _dispose(dlg)
