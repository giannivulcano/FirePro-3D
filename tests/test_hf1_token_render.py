"""HF1 render guards G8a/G8b/G8c (hatch-and-fill.md § HF1 verification)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QGraphicsView

from firepro3d import theme
from firepro3d.block_definition import BlockDefinition
from firepro3d.constants import TOKEN_AUTO
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


@pytest.fixture
def force_theme(monkeypatch):
    def _set(name):
        monkeypatch.setattr(theme, "theme_preference", lambda: name)
    return _set


def _token_block(ms, colour, bid="tok"):
    ln = LineItem(QPointF(-500, 0), QPointF(500, 0), colour)
    d = BlockDefinition.new(name=bid, library="L", series="S",
                            primitives=[ln.to_dict()], origin=(0, 0))
    ms.register_block_definition(d)
    return ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)


def _shown_pixels(ms):
    """Every opaque non-background colour on a shown view of *ms*."""
    v = QGraphicsView(ms)
    v.resize(400, 200)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.fitInView(QRectF(-600, -100, 1200, 200))
    v.viewport().repaint()
    img = v.viewport().grab().toImage()
    bg = img.pixelColor(2, 2).name()
    out = {img.pixelColor(x, y).name()
           for x in range(img.width()) for y in range(img.height())} - {bg}
    v.close()
    return out


@pytest.mark.parametrize("name,ink", [("dark", "#e6e9ec"), ("light", "#1c2024")])
def test_g8a_block_line_draws_theme_ink(qapp, force_theme, name, ink):
    force_theme(name)
    ms = Model_Space()
    _token_block(ms, TOKEN_AUTO)
    assert ink in _shown_pixels(ms)


def test_g8a_selected_block_uses_theme_accent(qapp, force_theme):
    force_theme("light")
    ms = Model_Space()
    inst = _token_block(ms, "#ff0000")
    inst.setSelected(True)
    px = _shown_pixels(ms)
    assert "#2f9e63" in px and "#63be8b" not in px


def test_g8a_theme_switch_repaints_without_recompile(qapp, force_theme):
    """The compiled op keeps the token; ink follows the theme at paint."""
    force_theme("dark")
    ms = Model_Space()
    inst = _token_block(ms, TOKEN_AUTO)
    assert "#e6e9ec" in _shown_pixels(ms)
    force_theme("light")
    inst.update()
    px = _shown_pixels(ms)
    assert "#1c2024" in px and "#e6e9ec" not in px
