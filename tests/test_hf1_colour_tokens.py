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
