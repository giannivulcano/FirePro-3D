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
