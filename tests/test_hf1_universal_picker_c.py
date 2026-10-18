"""HF1 smoke round (2026-10-18 ruling), slice C: the model item classes, the
Graphic Override clear, legacy data and the placement / paper-pass hand-offs.

ONE universal colour picker: every property a picker edits honours a
``token:*`` string (resolved per paint, surface-aware) and ``""`` (draws
nothing). Ground truth is pixels from a real paint, the PDF a real export
writes, or values read back from the real DM / loader paths. Only modal
dialogs are stubbed.
"""
from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog

from firepro3d import theme
from firepro3d.constants import TOKEN_ACCENT, TOKEN_AUTO
from firepro3d.geometry_2d import RectangleItem
# Slice A / B helpers and fixtures (mw / force_theme are pytest fixtures).
from tests.test_hf1_universal_picker import (          # noqa: F401
    BG, DARK_INK, LIGHT_INK, _dispose, _mw_singleton, _pick_returns, _pixels,
    _solid_rect, force_theme, mw, picker_spy)

ACCENT_PAPER = "#2f9e63"


@pytest.fixture(autouse=True)
def _qt_app(qapp):
    return qapp


@pytest.fixture
def ms(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    yield s
    s.deleteLater()
    QTest.qWait(0)


# ── C1: Graphic Override Clear must not destroy the item's own fill ─────────

@pytest.mark.parametrize("value", [TOKEN_AUTO, ""])
def test_graphic_override_clear_restores_own_fill(mw, qapp, monkeypatch,
                                                  force_theme, value):
    force_theme("light")
    r = _solid_rect(mw.scene)
    r._display_fill_color = "#ff0000"
    assert "#ff0000" in _pixels(r)                          # control
    r.setSelected(True)
    qapp.processEvents()
    _pick_returns(monkeypatch, value)
    mw._graphic_override_fill()
    assert r._display_overrides["fill"] == value
    px = _pixels(r)
    assert "#ff0000" not in px                              # override is on screen
    if value:
        assert LIGHT_INK in px
    # a save while the override is active holds the item's own fill
    assert r.to_dict()["fill"]["color"] == "#ff0000"
    mw._graphic_override_clear()
    assert "#ff0000" in _pixels(r)                          # original pixels back
    assert r.to_dict()["fill"]["color"] == "#ff0000"
    assert r._display_fill_color == "#ff0000"


# ── I1: model item classes honour a token and "" ────────────────────────────

SQUARE = [QPointF(0, 0), QPointF(2000, 0), QPointF(2000, 2000), QPointF(0, 2000)]


def _wall(ms):
    from firepro3d.wall import FILL_SOLID, WallSegment
    w = WallSegment(QPointF(0, 0), QPointF(2000, 0))
    ms.addItem(w)
    w._fill_mode = FILL_SOLID
    return w


def _room(ms):
    from firepro3d.room import Room
    r = Room(list(SQUARE))
    ms.addItem(r)
    return r


def _slab(ms):
    from firepro3d.floor_slab import FloorSlab
    s = FloorSlab(points=list(SQUARE))
    ms.addItem(s)
    return s


def _pipe(ms):
    from firepro3d.pipe import Pipe
    n1, n2 = ms.add_node(0, 0), ms.add_node(2000, 0)
    p = Pipe(n1, n2)
    ms.addItem(p)
    return p


def _area(ms):
    from PyQt6.QtGui import QPainterPath
    from firepro3d.design_area import DesignArea
    d = DesignArea([])
    ms.addItem(d)
    path = QPainterPath()
    path.addRect(QRectF(0, 0, 2000, 2000))
    d.setPath(path)
    return d


_CLASSES = {"wall": _wall, "room": _room, "slab": _slab, "pipe": _pipe,
            "area": _area}


def _set_all(item, value):
    item._display_color = value
    if hasattr(item, "_display_fill_color"):
        item._display_fill_color = value


@pytest.mark.parametrize("kind", sorted(_CLASSES))
def test_class_token_stroke_paints_theme_ink_per_paint(ms, force_theme, kind):
    force_theme("light")
    item = _CLASSES[kind](ms)
    _set_all(item, TOKEN_AUTO)
    assert LIGHT_INK in _pixels(item)
    force_theme("dark")                                     # not latched
    px = _pixels(item)
    assert DARK_INK in px and LIGHT_INK not in px


@pytest.mark.parametrize("kind", sorted(_CLASSES))
def test_class_no_stroke_no_fill_draws_nothing(ms, kind):
    item = _CLASSES[kind](ms)
    assert _pixels(item) != {BG}                            # control: it draws
    _set_all(item, "")
    assert _pixels(item) == {BG}


@pytest.mark.parametrize("kind", ["wall", "room", "slab", "area"])
def test_class_no_fill_keeps_the_stroke(ms, kind):
    """``""`` fill alone must not take the stroke with it, nor fall back to
    the default fill colour."""
    item = _CLASSES[kind](ms)
    item._display_color = "#00ff00"
    item._display_fill_color = ""
    px = _pixels(item)
    assert "#00ff00" in px
    assert len(px - {BG, "#00ff00"}) == 0, px


def test_class_unset_stroke_still_falls_back_to_default(ms):
    """``None`` stays "inherit": a room draws its own colour."""
    r = _room(ms)
    assert r._display_color is None
    assert "#4488cc" in _pixels(r)


def test_wall_section_colour_token_and_no_fill_resolve(ms, force_theme):
    from firepro3d.colour_tokens import section_fill_colour
    force_theme("light")
    assert section_fill_colour(TOKEN_AUTO).name() == LIGHT_INK
    assert section_fill_colour("#112233").name() == "#112233"
    assert section_fill_colour("") is None
    assert section_fill_colour(None) is None


def test_design_area_editing_no_fill_draws_nothing(ms):
    d = _area(ms)
    ms.mode = "design_area"
    d._display_fill_color = "#ffc800"
    assert _pixels(d) != {BG}                               # control
    d._display_fill_color = ""
    assert _pixels(d) == {BG}


# ── I2: category stroke "" reaches NEW items ────────────────────────────────

@pytest.mark.parametrize("value,expect_ink", [("", False), ("#ff0000", True)])
def test_category_stroke_no_stroke_reaches_new_items(ms, value, expect_ink):
    from PyQt6.QtCore import QSettings
    from firepro3d.display_manager import apply_category_defaults
    QSettings("GV", "FirePro3D").setValue("display/Pipe/color", value)
    try:
        p = _pipe(ms)
        apply_category_defaults(p)
        px = _pixels(p)
        if expect_ink:
            assert "#ff0000" in px
        else:
            assert p._display_color == ""
            assert px == {BG}
    finally:
        QSettings("GV", "FirePro3D").remove("display/Pipe/color")


# ── I3: DM reopen keeps a per-item "" ───────────────────────────────────────

@pytest.mark.parametrize("kind,cat", [("pipe", "Pipe"), ("wall", "Wall"),
                                      ("room", "Room"), ("slab", "Floor")])
def test_dm_instance_colour_no_stroke_vs_unset(ms, kind, cat):
    from firepro3d.display_manager import DisplayManager
    item = _CLASSES[kind](ms)
    dm = DisplayManager(ms)
    try:
        item._display_color = ""
        assert dm._read_item_display_state(item, cat)["color"] == ""
        item._display_color = TOKEN_ACCENT
        assert dm._read_item_display_state(item, cat)["color"] == TOKEN_ACCENT
        item._display_color = None
        assert dm._read_item_display_state(item, cat)["color"] != ""
    finally:
        _dispose(dm)


@pytest.mark.parametrize("stored", [TOKEN_AUTO, TOKEN_ACCENT, ""])
def test_dm_instance_row_of_a_roof_shows_the_stored_colour(ms, stored):
    from firepro3d.display_manager import DisplayManager
    from firepro3d.roof import RoofItem
    r = RoofItem(points=list(SQUARE), color=stored)
    ms.addItem(r)
    dm = DisplayManager(ms)
    try:
        assert dm._read_item_display_state(r, "Roof")["color"] == stored
    finally:
        _dispose(dm)


# ── I4: legacy "" data ──────────────────────────────────────────────────────

def _project_with_text_colour(tmp_path, ms, version):
    from firepro3d.paper_space import Sheet
    from firepro3d.text_item import TextAnnotationData
    sheet = Sheet.create_default()
    sheet.annotations = [TextAnnotationData(text="x", x=10, y=10, color="")]
    ms._sheets = [sheet]
    path = tmp_path / "p.fpd"
    ms.save_to_file(str(path))
    data = json.loads(path.read_text())
    data["version"] = version
    path.write_text(json.dumps(data))
    return path


def test_v10_project_text_colour_empty_loads_automatic(ms, tmp_path):
    from firepro3d.model_space import Model_Space
    path = _project_with_text_colour(tmp_path, ms, 10)
    fresh = Model_Space()
    fresh.load_from_file(str(path))
    assert [a.color for a in fresh._sheets[0].annotations] == [TOKEN_AUTO]


def test_v11_project_text_colour_empty_stays_no_colour(ms, tmp_path):
    from firepro3d.model_space import Model_Space
    path = _project_with_text_colour(tmp_path, ms, 11)
    fresh = Model_Space()
    fresh.load_from_file(str(path))
    assert [a.color for a in fresh._sheets[0].annotations] == [""]


def test_v10_payload_model_text_colour_empty_becomes_automatic():
    from firepro3d.colour_migration import migrate_project_payload
    old = {"version": 10, "texts": [{"color": ""}, {"color": "#ff0000"}]}
    migrate_project_payload(old)
    assert [t["color"] for t in old["texts"]] == [TOKEN_AUTO, "#ff0000"]
    new = {"version": 11, "texts": [{"color": ""}]}
    migrate_project_payload(new)
    assert new["texts"][0]["color"] == ""


def test_property_manager_none_colour_value_is_pinned_as_empty(qapp):
    """Pinned (I4 choice: leave): a colour row whose value is ``None`` shows
    the empty chip (``hex() == ""``, the same as No Fill). Every in-tree
    colour row supplies a concrete value (2D fill: the resolved default grey),
    so ``None`` never reaches the panel from a real item; this pins the
    behaviour of the one place that could."""
    from firepro3d.property_manager import PropertyManager
    from firepro3d.ui_kit import Swatch
    r = RectangleItem(QPointF(0, 0), QPointF(500, 300))
    r.fill_type = "solid"
    r._display_fill_color = None
    value = r.get_properties()["Fill Colour"]["value"]
    assert value == "#888888"                    # a real item resolves its default
    pm = PropertyManager()
    try:
        real = {"Probe": {"type": "color", "value": None}}
        r.get_properties = lambda: real
        pm.show_properties(r)
        sw = next(s for s in pm.findChildren(Swatch) if s._context == "Probe")
        assert sw.hex() == ""
    finally:
        _dispose(pm)


# ── R1: roof placement keeps a token and "" ─────────────────────────────────

@pytest.mark.parametrize("stored", [TOKEN_ACCENT, ""])
def test_roof_rect_placement_keeps_the_stored_colour(ms, monkeypatch, stored):
    from firepro3d.roof_dialog import RoofDialog
    monkeypatch.setattr(RoofDialog, "exec",
                        lambda self: QDialog.DialogCode.Accepted)
    ms._get_roof_template()._colour = stored
    ms._press_roof_rect(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    ms._press_roof_rect(None, QPointF(900, 700), QPointF(900, 700), None, None, None)
    (roof,) = ms._roofs
    assert roof._colour == stored


@pytest.mark.parametrize("stored", [TOKEN_ACCENT, ""])
def test_roof_polygon_placement_keeps_the_stored_colour(ms, monkeypatch, stored):
    from firepro3d.roof_dialog import RoofDialog
    monkeypatch.setattr(RoofDialog, "exec",
                        lambda self: QDialog.DialogCode.Accepted)
    ms._get_roof_template()._colour = stored
    pts = [QPointF(0, 0), QPointF(900, 0), QPointF(900, 700), QPointF(0, 0)]
    for p in pts:
        ms._press_roof(None, p, p, None, None, None)
    (roof,) = ms._roofs
    assert roof._colour == stored


# ── P1: a paper pass reaches each class ─────────────────────────────────────

def _paper_pass(ms, mode):
    from firepro3d.paper_display import apply_paper_overrides, save_paper_color_mode
    save_paper_color_mode(mode)
    return apply_paper_overrides(ms, QRectF(-5000, -5000, 10000, 10000),
                                 paper_scale=0.002)   # 125 model-mm pen: visible in _pixels


def _set_paper_category(key, **props):
    from firepro3d.paper_display import load_paper_categories, save_paper_categories
    cats = load_paper_categories()
    cats[key].update(props)
    save_paper_categories(cats)


@pytest.mark.parametrize("kind", ["wall", "room"])
@pytest.mark.parametrize("value,name", [(TOKEN_ACCENT, ACCENT_PAPER), ("", None)])
def test_paper_tab_colour_reaches_the_class_and_restores(ms, force_theme, kind,
                                                         value, name):
    from firepro3d.paper_display import PaperColorMode, restore_model_display
    force_theme("dark")
    item = _CLASSES[kind](ms)
    cat = {"wall": "Wall", "room": "Room"}[kind]
    _set_paper_category(cat, color=value, fill=value)
    item._display_color = TOKEN_AUTO
    saved = _paper_pass(ms, PaperColorMode.CUSTOM)
    try:
        px = _pixels(item)
        if name:
            assert name in px and DARK_INK not in px
        else:
            assert px == {BG}
    finally:
        restore_model_display(saved)
    assert item._display_color == TOKEN_AUTO                # restored raw
    assert DARK_INK in _pixels(item)


@pytest.mark.parametrize("kind", ["wall", "room"])
def test_full_colour_paper_token_stroke_is_paper_green(ms, force_theme, kind):
    from firepro3d.paper_display import PaperColorMode, restore_model_display
    force_theme("dark")
    item = _CLASSES[kind](ms)
    item._display_color = TOKEN_ACCENT
    saved = _paper_pass(ms, PaperColorMode.FULL_COLOR)
    try:
        assert ACCENT_PAPER in _pixels(item)
    finally:
        restore_model_display(saved)


def _pdf_colours(pdf):
    """{("s"|"f", rgb)} of the visible strokes / fills inside the viewport box
    (the viewport border / background, which span the box, are skipped)."""
    import fitz
    from tests.test_lt1_block_paper import _VP_W, _VP_X, _VP_Y
    pt = 25.4 / 72.0
    out = set()
    doc = fitz.open(str(pdf))
    try:
        for d in doc[0].get_drawings():
            r = d["rect"]
            x0, y0, x1, y1 = (v * pt for v in (r.x0, r.y0, r.x1, r.y1))
            if not (_VP_X + 1 < x0 and x1 < _VP_X + _VP_W - 1
                    and _VP_Y + 1 < y0 and y1 < _VP_Y + _VP_W - 1):
                continue
            kind = d.get("type") or ""
            if "s" in kind and d.get("stroke_opacity", 1.0) > 0 and d.get("color"):
                out.add(("s", tuple(round(v * 255) for v in d["color"])))
            if "f" in kind and d.get("fill_opacity", 1.0) > 0 and d.get("fill"):
                out.add(("f", tuple(round(v * 255) for v in d["fill"])))
        return out
    finally:
        doc.close()


@pytest.mark.parametrize("kind", ["wall", "room"])
@pytest.mark.parametrize("value", [TOKEN_ACCENT, ""])
def test_export_pdf_paper_tab_colour(qapp, tmp_path, force_theme, kind, value):
    pytest.importorskip("fitz")
    from firepro3d.model_space import Model_Space
    from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
    from tests.test_lt1_block_paper import _export
    force_theme("dark")
    scene = Model_Space()
    item = _CLASSES[kind](scene)
    item.setPos(0, 0)
    _set_paper_category({"wall": "Wall", "room": "Room"}[kind],
                        color=value, fill=value)
    save_paper_color_mode(PaperColorMode.CUSTOM)
    got = _pdf_colours(_export(tmp_path, scene, 0.01, "c.pdf"))
    green = (0x2f, 0x9e, 0x63)
    if value:
        assert ("s", green) in {(k, tuple(v)) for k, v in got}, got
    else:
        assert got == set(), got


# ── Minors ──────────────────────────────────────────────────────────────────

def test_unstyled_geometry_no_stroke_draws_nothing(ms):
    r = RectangleItem(QPointF(0, 0), QPointF(500, 300))
    r.style = None
    ms.addItem(r)
    pen = r.pen()
    pen.setColor(QColor("#ff0000"))
    r.setPen(pen)
    r._display_color = "#ff0000"
    assert "#ff0000" in _pixels(r)
    r._display_color = ""
    assert "#ff0000" not in _pixels(r)


def test_elevation_gridline_no_fill_bubble_is_transparent(elevation_scene_for):
    from PyQt6.QtCore import QSettings
    from firepro3d.elevation_scene import ElevGridlineItem
    from firepro3d.gridline import GridlineItem
    ms, elev = elevation_scene_for("north")
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="A")
    ms.addItem(gl)
    ms._gridlines.append(gl)
    s = QSettings("GV", "FirePro3D")
    try:
        for value, alpha in (("", 0), ("#ff0000", 255)):
            s.setValue("display/Grid Line/fill", value)
            for it in [i for i in elev.items() if isinstance(i, ElevGridlineItem)]:
                elev.removeItem(it)
            elev._project_gridlines()
            (g,) = [i for i in elev.items() if isinstance(i, ElevGridlineItem)]
            assert g.bubble1.brush().color().alpha() == alpha
    finally:
        s.remove("display/Grid Line/fill")


# ── Slice B follow-ups ──────────────────────────────────────────────────────

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


def test_3d_roof_no_fill_actor_is_not_pickable(real3d):
    from firepro3d.roof import RoofItem
    s, v = real3d
    for colour in ("#d2b48c", ""):
        r = RoofItem(points=list(SQUARE), color=colour)
        s.addItem(r)
        s._roofs.append(r)
    v.rebuild()
    actors = [a for a in v._actors["roofs"] if a is not None]
    assert len(actors) == 2
    hex_actor, empty_actor = actors
    assert hex_actor.GetPickable()                          # control
    assert empty_actor.GetProperty().GetOpacity() == 0.0
    assert not empty_actor.GetPickable()
    assert len(v._actors["roofs"]) == len(v._actors["roof_edges"])


@pytest.mark.parametrize("colour,theme_name,expect", [
    (TOKEN_AUTO, "light", LIGHT_INK), (TOKEN_AUTO, "dark", DARK_INK), ("", "light", None)])
def test_underlay_freeze_capture_uses_token_and_no_fill(
        qapp, ms, force_theme, colour, theme_name, expect):
    from firepro3d.model_view import Model_View
    from tests.test_hf1_universal_picker_b import _underlay
    force_theme(theme_name)
    _underlay(ms, colour=colour)
    view = Model_View(ms)
    view.resize(500, 400)
    view.show()
    QTest.qWaitForWindowExposed(view)
    view.centerOn(0, 0)
    qapp.processEvents()
    try:
        captured = ms._underlay_freeze._capture(view)
        img = captured[0].toImage() if captured else None
        seen = set()
        if img is not None:
            seen = {img.pixelColor(x, y).name()
                    for x in range(img.width()) for y in range(img.height())
                    if img.pixelColor(x, y).alpha() > 0}
        if expect:
            assert expect in seen, seen
        else:
            assert seen == set(), seen
    finally:
        view.close()
        view.deleteLater()


# ── Slice D: wall Colour row, wall placement, roof Enter-close ───────────────

@pytest.mark.parametrize("value", [TOKEN_ACCENT, ""])
def test_wall_panel_colour_stores_token_and_no_colour_and_round_trips(
        qapp, monkeypatch, value):
    from PyQt6.QtCore import Qt as _Qt
    from firepro3d.model_space import Model_Space
    from firepro3d.property_manager import PropertyManager
    from firepro3d.ui_kit import Swatch
    from firepro3d.wall import WallSegment
    scene = Model_Space()
    w = _wall(scene)
    pm = PropertyManager()
    try:
        pm.show_properties(w)
        sw = next(s for s in pm.findChildren(Swatch) if s._context == "Colour")
        _pick_returns(monkeypatch, value)
        QTest.mouseClick(sw._chip, _Qt.MouseButton.LeftButton)
    finally:
        _dispose(pm)
    assert w._colour == value
    assert w.get_properties()["Colour"]["value"] == value
    assert WallSegment.from_dict(w.to_dict())._colour == value


def test_wall_legacy_hex_colour_loads_unchanged(ms):
    from firepro3d.wall import WallSegment
    w = WallSegment.from_dict({"type": "wall", "pt1": [0, 0], "pt2": [100, 0],
                               "color": "#336699"})
    assert w._colour == "#336699" and w._color.name() == "#336699"


def test_wall_own_token_colour_paints_theme_ink_per_paint(ms, force_theme):
    force_theme("light")
    w = _wall(ms)
    w._fill_mode = "None"
    w._colour = TOKEN_AUTO
    assert LIGHT_INK in _pixels(w)
    force_theme("dark")
    px = _pixels(w)
    assert DARK_INK in px and LIGHT_INK not in px


def test_wall_own_no_colour_draws_nothing(ms):
    w = _wall(ms)
    assert _pixels(w) != {BG}
    w._colour = ""
    assert _pixels(w) == {BG}


@pytest.mark.parametrize("stored", [TOKEN_ACCENT, ""])
def test_wall_placement_keeps_the_template_colour(ms, stored):
    ms._get_wall_template()._colour = stored
    ms._press_wall(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    ms._press_wall(None, QPointF(2000, 0), QPointF(2000, 0), None, None, None)
    (wall,) = ms._walls
    assert wall._colour == stored


@pytest.mark.parametrize("stored", [TOKEN_ACCENT, ""])
def test_wall_rect_placement_keeps_the_template_colour(ms, stored):
    ms._get_wall_template()._colour = stored
    for p in (QPointF(0, 0), QPointF(2000, 0), QPointF(2000, 1000)):
        ms._press_wall_rect(None, p, p, None, None, None)
    assert len(ms._walls) == 4
    assert {w._colour for w in ms._walls} == {stored}


def test_dm_instance_row_of_a_wall_shows_the_stored_colour(ms):
    from firepro3d.display_manager import DisplayManager
    w = _wall(ms)
    w._colour = TOKEN_ACCENT
    dm = DisplayManager(ms)
    try:
        assert dm._read_item_display_state(w, "Wall")["color"] == TOKEN_ACCENT
    finally:
        _dispose(dm)


def test_3d_wall_actor_resolves_token_and_no_colour(real3d, force_theme):
    from PyQt6.QtGui import QColor as C
    s, v = real3d
    force_theme("dark")
    w = _wall(s)
    s._walls.append(w)
    w._colour = TOKEN_AUTO
    v.rebuild()
    (actor,) = [a for a in v._actors["walls"] if a is not None]
    prop = actor.GetProperty()
    got = tuple(round(c * 255) for c in prop.GetColor())
    ink = C(DARK_INK)
    assert got == (ink.red(), ink.green(), ink.blue())
    w._colour = ""
    v.rebuild()
    (actor,) = [a for a in v._actors["walls"] if a is not None]
    assert actor.GetProperty().GetOpacity() == 0.0 and not actor.GetPickable()
    assert len(v._actors["walls"]) == len(v._actors["wall_edges"])


@pytest.mark.parametrize("stored", [TOKEN_ACCENT, ""])
def test_roof_enter_close_placement_keeps_the_stored_colour(ms, monkeypatch, stored):
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent
    from firepro3d.roof_dialog import RoofDialog
    monkeypatch.setattr(RoofDialog, "exec",
                        lambda self: QDialog.DialogCode.Accepted)
    ms._get_roof_template()._colour = stored
    ms.mode = "roof"
    for p in (QPointF(0, 0), QPointF(900, 0), QPointF(900, 700)):
        ms._press_roof(None, p, p, None, None, None)
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    ms.keyPressEvent(ev)
    (roof,) = ms._roofs
    assert roof._colour == stored


def test_3d_wall_token_follows_the_theme_bus(real3d, force_theme):
    from PyQt6.QtGui import QColor as C
    s, v = real3d
    force_theme("dark")
    w = _wall(s)
    s._walls.append(w)
    w._colour = TOKEN_AUTO
    v.rebuild()
    v.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    v.show()
    QTest.qWait(300)
    force_theme("light")
    theme.theme_bus().changed.emit()
    QTest.qWait(300)
    (actor,) = [a for a in v._actors["walls"] if a is not None]
    got = tuple(round(c * 255) for c in actor.GetProperty().GetColor())
    ink = C(LIGHT_INK)
    assert got == (ink.red(), ink.green(), ink.blue())


def test_model_text_is_not_a_project_file_record(ms, tmp_path):
    """Pins why the model-text migration has no file round trip: standalone
    model text is forbidden loose content (containment C8), so a project save
    writes no ``texts`` key and a load discards one. The only v10 text-colour
    records that really load are the paper sheet annotations (guarded above)."""
    from firepro3d.model_space import Model_Space
    from firepro3d.text_item import TextAnnotationData, TextItem
    t = TextItem(TextAnnotationData(text="x", x=10, y=10, color=""))
    ms.addItem(t)
    ms._texts.append(t)
    path = tmp_path / "t.fpd"
    ms.save_to_file(str(path))
    data = json.loads(path.read_text())
    assert not data.get("texts")
    data["version"] = 10
    data["texts"] = [{"text": "legacy", "color": ""}]
    path.write_text(json.dumps(data))
    fresh = Model_Space()
    fresh.load_from_file(str(path))
    assert fresh._texts == []
