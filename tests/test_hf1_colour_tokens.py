"""HF1 colour tokens (hatch-and-fill.md § HF1 build design)."""
import pytest
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsLineItem

from firepro3d import theme
from firepro3d.constants import TOKEN_AUTO, TOKEN_ACCENT
from firepro3d.colour_tokens import (is_token, normalize_colour,
                                     resolve_colour, token_label)


@pytest.fixture
def force_theme(monkeypatch):
    def _set(name):
        monkeypatch.setattr(theme, "theme_preference", lambda: name)
    return _set


def test_is_token():
    assert is_token("token:auto") and is_token(TOKEN_ACCENT)
    assert not is_token("#ffffff") and not is_token(None) and not is_token("")


def test_normalize_keeps_tokens_and_lowercases_hex():
    assert normalize_colour("token:auto") == TOKEN_AUTO
    assert normalize_colour("#FF0000") == "#ff0000"
    assert normalize_colour("garbage", "#123456") == "#123456"
    assert normalize_colour(None, "#123456") == "#123456"


@pytest.mark.parametrize("name,ink,acc", [("dark", "#e6e9ec", "#63be8b"),
                                         ("light", "#1c2024", "#2f9e63")])
def test_canvas_resolution_follows_theme(qapp, force_theme, name, ink, acc):
    force_theme(name)
    assert resolve_colour(TOKEN_AUTO).name() == ink
    assert resolve_colour(TOKEN_ACCENT).name() == acc
    assert resolve_colour("#ff0000").name() == "#ff0000"


def test_paper_scene_resolves_black_and_light_accent(qapp, force_theme, monkeypatch):
    from firepro3d import paper_display
    from firepro3d.paper_display import PaperColorMode
    force_theme("dark")
    monkeypatch.setattr(paper_display, "load_paper_color_mode",
                        lambda *a, **k: PaperColorMode.FULL_COLOR)
    sc = QGraphicsScene()
    sc.paints_on_paper = True
    it = QGraphicsLineItem()
    sc.addItem(it)
    assert resolve_colour(TOKEN_AUTO, item=it).name() == "#000000"
    assert resolve_colour(TOKEN_ACCENT, item=it).name() == "#2f9e63"


def test_paper_bw_forces_black(qapp, force_theme, monkeypatch):
    from firepro3d import paper_display
    from firepro3d.paper_display import PaperColorMode
    force_theme("dark")
    monkeypatch.setattr(paper_display, "load_paper_color_mode",
                        lambda *a, **k: PaperColorMode.BW)
    sc = QGraphicsScene()
    sc.paints_on_paper = True
    it = QGraphicsLineItem()
    sc.addItem(it)
    assert resolve_colour(TOKEN_ACCENT, item=it).name() == "#000000"
    assert resolve_colour("#ff0000", item=it).name() == "#ff0000"   # hex untouched


def test_paper_pass_resolves_black(qapp, force_theme, monkeypatch):
    from firepro3d import paper_display
    force_theme("dark")
    monkeypatch.setattr(paper_display, "paper_pass_active", lambda: True)
    assert resolve_colour(TOKEN_AUTO).name() == "#000000"


def test_paper_pass_accent_resolves_light_accent(qapp, force_theme, monkeypatch):
    from firepro3d import paper_display
    from firepro3d.paper_display import PaperColorMode
    force_theme("dark")
    monkeypatch.setattr(paper_display, "paper_pass_active", lambda: True)
    monkeypatch.setattr(paper_display, "load_paper_color_mode",
                        lambda *a, **k: PaperColorMode.FULL_COLOR)
    assert resolve_colour(TOKEN_ACCENT).name() == "#2f9e63"


def test_real_paper_scene_accent_resolves_light_accent(qapp, force_theme, monkeypatch):
    from unittest.mock import MagicMock
    from firepro3d import paper_display
    from firepro3d.paper_display import PaperColorMode
    from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
    force_theme("dark")
    monkeypatch.setattr(paper_display, "load_paper_color_mode",
                        lambda *a, **k: PaperColorMode.FULL_COLOR)
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.return_value = None
    ps = PaperScene(Sheet.create_default(), resolver)
    it = QGraphicsLineItem()
    ps.addItem(it)
    assert resolve_colour(TOKEN_ACCENT, item=it).name() == "#2f9e63"
    assert resolve_colour(TOKEN_AUTO, item=it).name() == "#000000"


def test_alpha_and_unknown_token(qapp, force_theme):
    force_theme("dark")
    assert resolve_colour(TOKEN_AUTO, alpha=40).alpha() == 40
    assert resolve_colour("token:bogus").name() == "#e6e9ec"     # draws as Automatic


def test_token_label():
    assert token_label(TOKEN_AUTO) == "Automatic"
    assert token_label(TOKEN_ACCENT) == "Accent"
    assert token_label("#ff0000") is None


def test_paper_scene_class_flag():
    from firepro3d.paper_space import PaperScene
    assert PaperScene.paints_on_paper is True


def test_style_keeps_tokens():
    from firepro3d import stroke_style as ss
    assert ss.default_style()["colour"] == TOKEN_AUTO
    assert ss.normalize_style({"colour": TOKEN_ACCENT})["colour"] == TOKEN_ACCENT
    assert ss.normalize_style({"colour": "#FF0000"})["colour"] == "#ff0000"
    legacy = ss.migrate_primitive({"type": "draw_line", "color": TOKEN_AUTO})
    assert legacy["style"]["colour"] == TOKEN_AUTO


def test_new_line_defaults_to_automatic_and_round_trips(qapp):
    from PyQt6.QtCore import QPointF
    from firepro3d.geometry_2d import LineItem
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    assert ln.style["colour"] == TOKEN_AUTO
    back = LineItem.from_dict(ln.to_dict())
    assert back.style["colour"] == TOKEN_AUTO
    ln.set_property("Colour", TOKEN_ACCENT)
    assert ln.style["colour"] == TOKEN_ACCENT


def test_canvas_pen_resolves_token(qapp, force_theme):
    from PyQt6.QtCore import QPointF
    from firepro3d.geometry_2d import LineItem
    force_theme("light")
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ln._display_color = None
    ln._sync_stroke_pen()
    assert ln.pen().color().name() == "#1c2024"


def test_text_defaults_to_automatic_and_resolves(qapp, force_theme):
    from firepro3d.text_item import TextAnnotationData, TextItem
    force_theme("dark")
    d = TextAnnotationData(text="A")
    assert d.color == TOKEN_AUTO
    t = TextItem(d)
    assert t.defaultTextColor().name() == "#e6e9ec"
    force_theme("light")
    t.on_theme_changed()
    assert t.defaultTextColor().name() == "#1c2024"
    assert TextItem.from_dict(t.to_dict())._data.color == TOKEN_AUTO


def test_text_colour_prop_offers_tokens(qapp):
    from firepro3d.text_item import TextAnnotationData, TextItem
    props = TextItem(TextAnnotationData(text="A")).get_properties()
    assert props["Font Color"]["allow_tokens"] is True
    assert props["Font Color"]["value"] == TOKEN_AUTO


def test_text_colour_setter_keeps_tokens(qapp):
    from firepro3d.text_item import TextAnnotationData, TextItem
    t = TextItem(TextAnnotationData(text="A", color="#112233"))
    t.set_property("Font Color", TOKEN_ACCENT)
    assert t._data.color == TOKEN_ACCENT
    t.set_property("Font Color", "#FF0000")
    assert t._data.color == "#ff0000"


# ---------------------------------------------------------------------------
# T7: Display Manager tokens (R7, AC1, AC3)
# ---------------------------------------------------------------------------

def test_dm_2d_geometry_factory_is_automatic():
    from firepro3d.display_manager import _CATEGORY_MAP
    assert _CATEGORY_MAP["2D Geometry"]["color"] == TOKEN_AUTO


def test_dm_settings_white_migrates_once(qapp):
    from PyQt6.QtCore import QSettings
    from firepro3d import display_manager as dm
    s = QSettings("GV", "FirePro3D")             # conftest isolates the store
    s.setValue("display/2D Geometry/color", "#FFFFFF")
    s.setValue("display/2D Geometry/default_color", "#ffffff")
    s.remove(dm._HF1_AUTO_MARK)
    dm._migrate_display_keys(s)
    assert s.value("display/2D Geometry/color") == TOKEN_AUTO
    assert s.value("display/2D Geometry/default_color") == TOKEN_AUTO
    s.setValue("display/2D Geometry/color", "#ffffff")       # user picks white later
    dm._migrate_display_keys(s)
    assert s.value("display/2D Geometry/color") == "#ffffff"


def test_dm_read_category_defaults_2d_geometry_to_automatic(qapp):
    from firepro3d import display_manager as dm
    assert dm._read_category_from_settings("2D Geometry")["color"] == TOKEN_AUTO


def test_svg_tint_resolves_token(qapp, force_theme, tmp_path):
    from firepro3d import display_manager as dm
    force_theme("light")
    svg = tmp_path / "s.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" '
                   'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">'
                   '<g inkscape:groupmode="layer"><rect width="1" '
                   'height="1"/></g></svg>', encoding="utf-8")
    data = bytes(dm._recolor_svg_bytes(str(svg), TOKEN_AUTO, None)).decode()
    assert "#1c2024" in data.lower() and "token" not in data


def _paint_pixels(item, rect, size=120):
    from PyQt6.QtGui import QImage, QPainter, QColor
    from PyQt6.QtWidgets import QStyleOptionGraphicsItem
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor("#808080"))
    p = QPainter(img)
    p.setWindow(rect.toRect())
    item.paint(p, QStyleOptionGraphicsItem(), None)
    p.end()
    return {img.pixelColor(x, y).name() for x in range(size) for y in range(size)}


def test_wall_paints_token_display_colour(qapp, force_theme):
    from PyQt6.QtCore import QPointF
    from firepro3d.wall import WallSegment
    force_theme("light")
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    w._display_color = TOKEN_AUTO
    px = _paint_pixels(w, w.boundingRect())
    assert "#1c2024" in px


def test_room_paints_token_display_colour(qapp, force_theme):
    from PyQt6.QtCore import QPointF
    from firepro3d.room import Room
    force_theme("light")
    r = Room([QPointF(0, 0), QPointF(2000, 0), QPointF(2000, 2000), QPointF(0, 2000)])
    r._display_color = TOKEN_AUTO
    px = _paint_pixels(r, r.boundingRect())
    assert "#1c2024" in px


# ── Task 8: picker Theme row + Swatch token display (AC4, D-A18) ────────────

def _dispose(w):
    try:
        w.close()
    finally:
        w.deleteLater()


def test_picker_theme_row_returns_token_and_skips_recents(qapp):
    from firepro3d import colour_picker as cp
    cp.clear_recents()
    dlg = cp.ColourPickerDialog(initial="#ff0000", allow_tokens=True)
    try:
        chips = [c for c in dlg._chips if c.value == TOKEN_AUTO]
        assert len(chips) == 1
        dlg._on_chip(TOKEN_AUTO)
        dlg.accept()
        assert dlg.result_value() == TOKEN_AUTO
        assert cp.load_recents() == []
    finally:
        _dispose(dlg)


def test_picker_without_tokens_has_no_theme_row(qapp):
    from firepro3d import colour_picker as cp
    dlg = cp.ColourPickerDialog(initial="#ff0000")
    try:
        assert not [c for c in dlg._chips if c.value in (TOKEN_AUTO, TOKEN_ACCENT)]
    finally:
        _dispose(dlg)


def test_picker_opens_on_token_initial(qapp):
    from firepro3d import colour_picker as cp
    dlg = cp.ColourPickerDialog(initial=TOKEN_ACCENT, allow_tokens=True)
    try:
        assert dlg.current_value() == TOKEN_ACCENT
        sel = [c.value for c in dlg._chips if c.selected]
        assert sel == [TOKEN_ACCENT]
    finally:
        _dispose(dlg)


def test_picker_hex_edit_after_token_returns_hex(qapp):
    from firepro3d import colour_picker as cp
    dlg = cp.ColourPickerDialog(initial=TOKEN_AUTO, allow_tokens=True)
    try:
        dlg._on_hex_edited("#00ff00")
        assert dlg.current_value() == "#00FF00"
    finally:
        _dispose(dlg)


def test_swatch_shows_token_label(qapp, force_theme):
    from firepro3d.ui_kit import Swatch
    force_theme("dark")
    sw = Swatch(TOKEN_AUTO, allow_tokens=True)
    try:
        assert sw._label.text() == "Automatic"
        sw.set_hex("#ff0000")
        assert sw._label.text() == "#FF0000"
    finally:
        _dispose(sw)


def test_swatch_chip_paints_resolved_token(qapp, force_theme):
    from PyQt6.QtGui import QImage
    from firepro3d.ui_kit import Swatch
    force_theme("light")
    sw = Swatch(TOKEN_ACCENT, allow_tokens=True)
    try:
        img = QImage(sw._chip.size(), QImage.Format.Format_ARGB32)
        sw._chip.render(img)
        c = img.pixelColor(img.width() // 3, img.height() // 2)
        assert c.name() == resolve_colour(TOKEN_ACCENT).name()
    finally:
        _dispose(sw)


def test_swatch_pick_passes_allow_tokens_and_stores_token(qapp, monkeypatch):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from firepro3d import colour_picker
    from firepro3d.ui_kit import Swatch
    seen = {}

    def fake(initial, parent=None, context="", *, allow_none=False, allow_tokens=False):
        seen.update(initial=initial, allow_tokens=allow_tokens)
        return TOKEN_ACCENT
    monkeypatch.setattr(colour_picker, "pick_colour", fake)
    sw = Swatch(TOKEN_AUTO, allow_tokens=True)
    got = []
    sw.colorChanged.connect(got.append)
    try:
        QTest.mouseClick(sw._chip, Qt.MouseButton.LeftButton)
        assert seen == {"initial": TOKEN_AUTO, "allow_tokens": True}
        assert got == [TOKEN_ACCENT] and sw._label.text() == "Accent"
    finally:
        _dispose(sw)


def test_geometry2d_panel_swatch_shows_automatic_and_stores_accent(qapp, monkeypatch):
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtTest import QTest
    from firepro3d import colour_picker
    from firepro3d.geometry_2d import LineItem
    from firepro3d.property_manager import PropertyManager
    from firepro3d.ui_kit import Swatch
    item = LineItem(QPointF(0, 0), QPointF(100, 0))
    assert item.style["colour"] == TOKEN_AUTO
    pm = PropertyManager()
    try:
        pm.show_properties(item)
        sw = next(s for s in pm.findChildren(Swatch) if s._context == "Colour")
        assert sw._label.text() == "Automatic"
        monkeypatch.setattr(
            colour_picker, "pick_colour",
            lambda initial, parent=None, context="", *, allow_none=False,
            allow_tokens=False: TOKEN_ACCENT if allow_tokens else "#123456")
        QTest.mouseClick(sw._chip, Qt.MouseButton.LeftButton)
        assert item.style["colour"] == TOKEN_ACCENT
    finally:
        _dispose(pm)


def test_font_group_pick_offers_tokens_and_stores_auto(paper_text_t8, monkeypatch):
    from firepro3d import colour_picker
    from firepro3d.font_group import FontGroupController
    scene, items = paper_text_t8
    items[0].data.color = "#ff0000"
    c = FontGroupController(get_targets=lambda: [items[0]])
    seen = {}

    def fake(initial, parent=None, context="", *, allow_none=False, allow_tokens=False):
        seen["allow_tokens"] = allow_tokens
        return TOKEN_AUTO
    monkeypatch.setattr(colour_picker, "pick_colour", fake)
    c._pick_color()
    assert seen["allow_tokens"] is True
    assert items[0].data.color == TOKEN_AUTO


@pytest.fixture
def paper_text_t8(qapp):
    from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
    from firepro3d.text_item import TextAnnotationData
    scene = PaperScene(Sheet.create_default(), ViewResolver(None, None, None, None))
    return scene, [scene.add_annotation(TextAnnotationData(text="Alpha"))]


def _dm_token_pick(kind, monkeypatch):
    """Open a real DM, force the colour button's stored value to a token, run
    the pick and return (pick kwargs seen, dialog-based initial validity)."""
    from firepro3d import colour_picker
    from firepro3d.display_manager import DisplayManager
    from firepro3d.model_space import Model_Space
    seen = {}

    def fake(initial, parent=None, context="", *, allow_none=False, allow_tokens=False):
        dlg = colour_picker.ColourPickerDialog(initial=initial, allow_none=allow_none,
                                               allow_tokens=allow_tokens)
        try:
            seen["value"] = dlg.current_value()
        finally:
            _dispose(dlg)
        seen["allow_tokens"] = allow_tokens
        return None
    monkeypatch.setattr(colour_picker, "pick_colour", fake)
    dm = DisplayManager(Model_Space())
    try:
        if kind == "category":
            key = next(iter(dm._cat_data))
            dm._cat_data[key]["widgets"]["color_btn"].setProperty("_color", TOKEN_AUTO)
            dm._pick_category_prop(key, "color")
        else:
            dm._pick_category_prop(next(iter(dm._cat_data)), "fill")
    finally:
        _dispose(dm)
    return seen


def test_dm_category_colour_pick_opens_on_token(qapp, monkeypatch):
    seen = _dm_token_pick("category", monkeypatch)
    assert seen == {"value": TOKEN_AUTO, "allow_tokens": True}


def test_dm_category_fill_pick_stays_hex(qapp, monkeypatch):
    seen = _dm_token_pick("fill", monkeypatch)
    assert seen["allow_tokens"] is False


# --- Task 9: load migration (project v11, .fpdb marker) ---------------------

def _v10_payload():
    return {
        "version": 10,
        "block_definitions": {"b": {"primitives": [
            {"type": "draw_line", "style": {"colour": "#FFFFFF"}},
            {"type": "draw_line", "style": {"colour": "#ff0000"}},
            {"type": "draw_line", "color": "#ffffff"},
            {"type": "text", "color": "#ffffff"},
            {"type": "block_instance", "color": "#ffffff"},
        ]}},
        "sheets": [{"annotations": [{"color": "#000000"}, {"color": "#ff0000"}]}],
        "display_settings": {"2D Geometry": {"color": "#ffffff"}},
    }


def test_project_v10_migrates_known_defaults_only():
    from firepro3d.colour_migration import migrate_project_payload
    p = _v10_payload()
    migrate_project_payload(p)
    prims = p["block_definitions"]["b"]["primitives"]
    assert prims[0]["style"]["colour"] == TOKEN_AUTO
    assert prims[1]["style"]["colour"] == "#ff0000"
    assert prims[2]["color"] == TOKEN_AUTO
    assert prims[3]["color"] == TOKEN_AUTO
    assert prims[4]["color"] == "#ffffff"          # nested block: never touched
    anns = p["sheets"][0]["annotations"]
    assert anns[0]["color"] == TOKEN_AUTO and anns[1]["color"] == "#ff0000"
    assert p["display_settings"]["2D Geometry"]["color"] == TOKEN_AUTO


def test_project_v11_untouched():
    from firepro3d.colour_migration import migrate_project_payload
    p = _v10_payload()
    p["version"] = 11
    migrate_project_payload(p)
    assert p["block_definitions"]["b"]["primitives"][0]["style"]["colour"] == "#FFFFFF"


def test_fpdb_marker_gates_migration():
    from firepro3d.colour_migration import migrate_fpdb_dict
    from firepro3d.constants import COLOUR_TOKENS_MARK
    d = {"primitives": [{"type": "draw_line", "style": {"colour": "#ffffff"}}],
         "bundled": {"n": {"primitives": [{"type": "text", "color": "#ffffff"}]}}}
    migrate_fpdb_dict(d)
    assert d["primitives"][0]["style"]["colour"] == TOKEN_AUTO
    assert d["bundled"]["n"]["primitives"][0]["color"] == TOKEN_AUTO
    m = {COLOUR_TOKENS_MARK: 1,
         "primitives": [{"type": "draw_line", "style": {"colour": "#ffffff"}}]}
    migrate_fpdb_dict(m)
    assert m["primitives"][0]["style"]["colour"] == "#ffffff"


def test_g9_v10_project_file_round_trip(qapp, tmp_path):
    import json
    from firepro3d.model_space import Model_Space
    p = tmp_path / "v10.fpd"
    p.write_text(json.dumps({"version": 10, "block_definitions": {
        "leg": {"schema": 1, "id": "leg", "version": 1, "name": "Leg",
                "library": "L", "series": "S", "origin": [0, 0],
                "primitives": [{"type": "draw_line", "pt1": [0, 0], "pt2": [10, 0],
                                "color": "#ffffff", "lineweight": 1.0}]}}}),
                 encoding="utf-8")
    ms = Model_Space()
    ms.load_from_file(str(p))
    prim = ms.block_registry.get("leg").primitives[0]
    assert prim["style"]["colour"] == TOKEN_AUTO
    out = tmp_path / "v11.fpd"
    ms.save_to_file(str(out))
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["version"] == 11
    ms2 = Model_Space()
    ms2.load_from_file(str(out))
    assert ms2.block_registry.get("leg").primitives[0]["style"]["colour"] == TOKEN_AUTO


def test_g9_v10_project_sheet_text_and_display_colour_load(qapp, tmp_path):
    """Real load path: a v10 file's black sheet text and white 2D Geometry
    display colour reach the live objects as Automatic."""
    import json
    from firepro3d.model_space import Model_Space
    p = tmp_path / "v10b.fpd"
    p.write_text(json.dumps({"version": 10, "display_settings": {
        "2D Geometry": {"color": "#ffffff"}},
        "sheets": [{"number": "A1", "name": "S", "paper_size": "ANSI D",
                    "annotations": [{"type": "text", "text": "hi",
                                     "color": "#000000"}]}]}), encoding="utf-8")
    ms = Model_Space()
    ms.load_from_file(str(p))
    assert ms._sheets[0].annotations[0].color == TOKEN_AUTO
    assert ms._loaded_display_settings["2D Geometry"]["color"] == TOKEN_AUTO


def test_fpdb_round_trip_marks_and_reloads(qapp, tmp_path):
    import json
    from firepro3d import block_library as bl
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.constants import COLOUR_TOKENS_MARK
    d = BlockDefinition.new(
        name="Leg", library="L", series="S", origin=(0.0, 0.0),
        primitives=[{"type": "draw_line", "pt1": [0, 0], "pt2": [10, 0],
                     "style": {"colour": "#ff0000"}}])
    path = bl.save_to_library(d, root=str(tmp_path))
    rec = json.loads(open(path, encoding="utf-8").read())
    assert rec[COLOUR_TOKENS_MARK] == 1
    assert bl.load_block_file(path).primitives[0]["style"]["colour"] == "#ff0000"
    # An un-marked legacy file converts on load; the marked one stays literal.
    rec.pop(COLOUR_TOKENS_MARK)
    rec["primitives"][0]["style"]["colour"] = "#ffffff"
    legacy = tmp_path / "legacy.fpdb"
    legacy.write_text(json.dumps(rec), encoding="utf-8")
    assert bl.load_block_file(str(legacy)).primitives[0]["style"]["colour"] == TOKEN_AUTO
    defn, _ = bl.load_block_file_with_bundle(str(legacy))
    assert defn.primitives[0]["style"]["colour"] == TOKEN_AUTO
    rec[COLOUR_TOKENS_MARK] = 1
    legacy.write_text(json.dumps(rec), encoding="utf-8")
    assert bl.load_block_file(str(legacy)).primitives[0]["style"]["colour"] == "#ffffff"


class _Dxf:
    def __init__(self, **kw):
        self._kw = kw

    def hasattr(self, k):
        return k in self._kw

    def get(self, k, default=None):
        return self._kw.get(k, default)

    def __getattr__(self, k):
        return self._kw[k]


class _Ent:
    def __init__(self, **kw):
        self.dxf = _Dxf(**kw)


def test_dxf_aci7_and_bylayer7_import_as_automatic():
    from firepro3d.dxf_import_worker import _resolve_entity_color, _aci_to_hex
    lc = {"W": _aci_to_hex(7), "R": _aci_to_hex(1)}
    assert _resolve_entity_color(_Ent(color=7), lc) == TOKEN_AUTO
    assert _resolve_entity_color(_Ent(color=256, layer="W"), lc) == TOKEN_AUTO
    assert _resolve_entity_color(_Ent(color=1), lc) == _aci_to_hex(1)
    assert _resolve_entity_color(_Ent(color=256, layer="R"), lc) == _aci_to_hex(1)
    assert _resolve_entity_color(_Ent(color=256, layer="missing"), lc) == TOKEN_AUTO


def test_geometry_import_no_colour_is_automatic(qapp):
    from firepro3d.geometry_import import geom_dicts_to_primitives
    items, skipped = geom_dicts_to_primitives(
        [{"kind": "line", "x1": 0, "y1": 0, "x2": 10, "y2": 0}], 1.0)
    assert skipped == 0
    assert items[0].style["colour"] == TOKEN_AUTO


def test_underlay_cache_version_bumped_for_aci7():
    from firepro3d import underlay_cache
    assert underlay_cache._CACHE_VERSION >= 5


def _legacy_fpdb(tmp_path, name="legacy.fpdb"):
    """An un-marked .fpdb with a white stroke and a bundled nested def whose
    prim is also white."""
    import json
    from firepro3d.block_definition import BlockDefinition
    nested = BlockDefinition.new(
        name="Nest", library="L", series="S", origin=(0.0, 0.0),
        primitives=[{"type": "draw_line", "pt1": [0, 0], "pt2": [5, 0],
                     "style": {"colour": "#ffffff"}}])
    top = BlockDefinition.new(
        name="Top", library="L", series="S", origin=(0.0, 0.0),
        primitives=[{"type": "draw_line", "pt1": [0, 0], "pt2": [10, 0],
                     "style": {"colour": "#ffffff"}}])
    rec = top.to_dict()
    rec["schema"] = 2
    rec["bundled"] = {nested.id: nested.to_dict()}
    path = tmp_path / name
    path.write_text(json.dumps(rec), encoding="utf-8")
    return path, top, nested


def test_load_block_migrates_unmarked_fpdb(qapp, tmp_path):
    """Real ``block_library.load_block`` (library/series/filename path)."""
    from firepro3d import block_library as bl
    _legacy_fpdb(tmp_path, "Top.fpdb")
    got = bl.load_block("", "", "Top.fpdb", root=str(tmp_path))
    assert got is not None
    assert got.primitives[0]["style"]["colour"] == TOKEN_AUTO


def test_load_block_file_migrates_unmarked_fpdb(qapp, tmp_path):
    """Real ``block_library.load_block_file`` (browse-anywhere path)."""
    from firepro3d import block_library as bl
    path, _t, _n = _legacy_fpdb(tmp_path)
    got = bl.load_block_file(str(path))
    assert got.primitives[0]["style"]["colour"] == TOKEN_AUTO


def test_load_block_file_with_bundle_migrates_bundled_defs(qapp, tmp_path):
    """Real ``load_block_file_with_bundle``: top def AND bundled nested def."""
    from firepro3d import block_library as bl
    path, _t, nested = _legacy_fpdb(tmp_path)
    defn, bundled = bl.load_block_file_with_bundle(str(path))
    assert defn.primitives[0]["style"]["colour"] == TOKEN_AUTO
    assert [b.id for b in bundled] == [nested.id]
    assert bundled[0].primitives[0]["style"]["colour"] == TOKEN_AUTO


def test_project_non_numeric_version_migrates_without_raising():
    from firepro3d.colour_migration import migrate_project_payload
    for bad in ("abc", "1.0", [3], {}):
        p = {"version": bad,
             "display_settings": {"2D Geometry": {"color": "#ffffff"}}}
        migrate_project_payload(p)
        assert p["display_settings"]["2D Geometry"]["color"] == TOKEN_AUTO


def _hf1_click(view, x, y):
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication
    vp = view.mapFromScene(QPointF(x, y))
    gp = view.viewport().mapToGlobal(vp)
    for et in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress,
               QEvent.Type.MouseButtonRelease):
        btn = (Qt.MouseButton.NoButton if et == QEvent.Type.MouseMove
               else Qt.MouseButton.LeftButton)
        QApplication.sendEvent(view.viewport(), QMouseEvent(
            et, QPointF(vp), QPointF(gp), btn, btn,
            Qt.KeyboardModifier.NoModifier))
    QApplication.processEvents()


def test_drawn_line_commits_with_automatic_colour(shown_model_view):
    """AC5, end to end: the real draw_line tool (posted mouse events) stores
    ``token:auto`` on the committed item, not a literal white."""
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    scene.set_mode("draw_line")
    _hf1_click(view, 0, 0)
    _hf1_click(view, 600, 0)
    assert len(scene._draw_lines) == 1
    assert scene._draw_lines[0].style["colour"] == TOKEN_AUTO
