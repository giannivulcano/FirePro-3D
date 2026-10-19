"""UP1 FillSwatch + "fill" row: chip click -> pick_fill -> layerChanged -> set_property."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from firepro3d import colour_picker
from firepro3d.fill_layers import NO_LAYER, BackgroundLayer, PatternLayer


class _Target:
    """Minimal panel target: two fill rows, records set_property calls."""
    def __init__(self, bg=None, pat=None):
        self.bg, self.pat, self.calls = bg, pat, []

    def scene(self):
        return None

    def get_properties(self):
        return {"Fill": {"type": "fill", "value": self.bg, "pattern": False},
                "Fill Pattern": {"type": "fill", "value": self.pat, "pattern": True}}

    def set_property(self, key, value):
        self.calls.append((key, value))


def _swatches(pm):
    from firepro3d.ui_kit import FillSwatch
    return {s._context: s for s in pm.findChildren(FillSwatch)}


def test_fill_row_builds_two_swatches_in_their_modes(qapp):
    from firepro3d.property_manager import PropertyManager
    pm = PropertyManager(); pm.show_properties(_Target())
    sw = _swatches(pm)
    assert set(sw) == {"Fill", "Fill Pattern"}
    assert sw["Fill"]._pattern is False and sw["Fill Pattern"]._pattern is True
    assert sw["Fill"].layer() is None and sw["Fill"]._label.text() == "None"


def test_swatch_click_opens_pick_fill_and_writes_back(qapp, monkeypatch):
    from firepro3d.property_manager import PropertyManager
    t = _Target(pat=PatternLayer("builtin-hatch-diagonal", "#123456", 0.5, 2.0))
    pm = PropertyManager(); pm.show_properties(t)
    seen = {}
    new = PatternLayer("builtin-hatch-diagonal", "#ff0000", 1.0, 3.0)
    def fake(initial, parent=None, *, pattern, context="", registry=None, exclude=()):
        seen.update(initial=initial, pattern=pattern, context=context)
        return new
    monkeypatch.setattr(colour_picker, "pick_fill", fake)
    QTest.mouseClick(_swatches(pm)["Fill Pattern"]._chip, Qt.MouseButton.LeftButton)
    assert seen == {"initial": t.pat, "pattern": True, "context": "Fill Pattern"}
    assert t.calls == [("Fill Pattern", new)]


def test_no_layer_and_cancel(qapp, monkeypatch):
    from firepro3d.property_manager import PropertyManager
    t = _Target(bg=BackgroundLayer("#00ff00", 0.5))
    pm = PropertyManager(); pm.show_properties(t)
    sw = _swatches(pm)["Fill"]
    monkeypatch.setattr(colour_picker, "pick_fill", lambda *a, **k: None)
    QTest.mouseClick(sw._chip, Qt.MouseButton.LeftButton)
    assert t.calls == []                                        # cancel: nothing
    monkeypatch.setattr(colour_picker, "pick_fill", lambda *a, **k: NO_LAYER)
    QTest.mouseClick(sw._chip, Qt.MouseButton.LeftButton)
    assert t.calls == [("Fill", NO_LAYER)]


def test_multi_select_apply_writes_every_target(qapp, monkeypatch):            # G8 (panel half)
    from firepro3d.property_manager import PropertyManager
    a, b = _Target(), _Target(pat=PatternLayer("x"))
    pm = PropertyManager(); pm.show_properties([a, b])
    new = PatternLayer("builtin-hatch-diagonal")
    monkeypatch.setattr(colour_picker, "pick_fill", lambda *a_, **k: new)
    QTest.mouseClick(_swatches(pm)["Fill Pattern"]._chip, Qt.MouseButton.LeftButton)
    assert a.calls == [("Fill Pattern", new)] and b.calls == [("Fill Pattern", new)]


def test_label_text_per_layer(qapp):
    from firepro3d.ui_kit import FillSwatch
    s = FillSwatch(BackgroundLayer("#00ff00", 0.45), pattern=False, context="Fill")
    assert s._label.text() == "#00FF00 · 45%"
    s.set_layer(PatternLayer("no-such-tile", "token:auto", 1.0, 1.0))
    assert s._label.text().endswith("· 100%")
    s.set_layer(None)
    assert s._label.text() == "None"


def test_set_layer_treats_no_layer_as_off(qapp):
    """The public setter normalises NO_LAYER -> None (no AttributeError)."""
    from firepro3d.ui_kit import FillSwatch
    s = FillSwatch(BackgroundLayer("#00ff00", 0.45), pattern=False, context="Fill")
    s.set_layer(NO_LAYER)
    assert s.layer() is None
    assert s._label.text() == "None"
    assert s._chip._layer is None


def _pixels(chip):
    img = chip.grab().toImage()
    return img, {img.pixel(x, y) for x in range(img.width()) for y in range(img.height())}


def test_fill_chip_paints_all_three_branches(qapp, shipped_hatches):
    """grab() over _FillChip.paintEvent: none glyph, background colour, pattern."""
    from PyQt6.QtGui import QColor
    from firepro3d.theme import detect
    from firepro3d.ui_kit import FillSwatch
    reg = shipped_hatches(None)
    s = FillSwatch(None, pattern=False, context="Fill", registry=reg)
    chip = s._chip
    none_img, none_px = _pixels(chip)
    assert len(none_px) > 1                                  # the No-Fill glyph, not a flat chip
    s.set_layer(BackgroundLayer("#00ff00", 1.0))
    img, px = _pixels(chip)
    assert img.pixelColor(img.width() // 2, img.height() // 2) == QColor("#00ff00")
    assert px != none_px
    sunken = QColor(detect().bg_sunken)
    s.set_layer(PatternLayer("builtin-hatch-diagonal", "#ff0000", 1.0, 1.0))
    img, _px = _pixels(chip)
    inner = [img.pixelColor(x, y) for x in range(3, img.width() - 3)
             for y in range(3, img.height() - 3)]
    assert any(c != sunken for c in inner)                   # pattern strokes drawn
    assert any(c == sunken for c in inner)                   # over the sunken background


def test_theme_change_restyles_the_label(qapp):
    from firepro3d.theme import detect, theme_bus
    from firepro3d.ui_kit import FillSwatch
    s = FillSwatch(None, pattern=False, context="Fill")
    s._label.setStyleSheet("")
    theme_bus().changed.emit()
    assert detect().muted in s._label.styleSheet()
