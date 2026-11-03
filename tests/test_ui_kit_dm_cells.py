"""Kit cell widgets for dense tables (DM chrome revision R2/R3): compact Swatch,
EyeToggle, and the single shared eye painter."""
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d import colour_picker, ui_kit
from firepro3d import underlay_manager_delegates as umd
from firepro3d.colour_tokens import resolve_colour
from firepro3d.constants import TOKEN_AUTO
from firepro3d.theme import detect
from firepro3d.ui_kit import EyeToggle, Swatch

_LEFT = Qt.MouseButton.LeftButton


def _chip_img(sw):
    sw.show()
    QApplication.processEvents()
    return sw._chip.grab().toImage()


def test_compact_swatch_hides_label_keeps_value_semantics(qapp):
    sw = Swatch("#336699", show_label=False, auto_pick=False)
    assert sw._label.isHidden()
    for v in ("", TOKEN_AUTO, "#123456"):
        sw.set_hex(v)
        assert sw.hex() == v and sw.property("_color") == v
    sw.deleteLater()


def test_compact_swatch_paints_value_chip(qapp):
    sw = Swatch("#336699", show_label=False, auto_pick=False)
    w, h = sw._chip.width(), sw._chip.height()
    assert _chip_img(sw).pixelColor(w // 2, h // 2).name() == "#336699"
    sw.set_hex(TOKEN_AUTO)
    assert _chip_img(sw).pixelColor(w // 2, h // 2).name() == resolve_colour(TOKEN_AUTO).name()
    sw.set_hex("")                       # No Fill: the shared white glyph, top-left corner is clear of the slash
    assert _chip_img(sw).pixelColor(4, 3).name() == "#ffffff"
    sw.deleteLater()


def test_auto_pick_false_emits_clicked_and_never_opens_picker(qapp, monkeypatch):
    # A recorder, not a raising stub: an exception inside a Qt slot aborts the
    # process (0xC0000409) instead of failing the test (self-review F2).
    opened = []
    monkeypatch.setattr(colour_picker, "pick_colour",
                        lambda *a, **k: opened.append(a) or "#00ff00")
    sw = Swatch("#336699", show_label=False, auto_pick=False)
    seen = []
    sw.clicked.connect(lambda: seen.append("c"))
    sw.colorChanged.connect(seen.append)
    sw.show()
    QTest.mouseClick(sw._chip, _LEFT)
    assert seen == ["c"] and opened == [] and sw.hex() == "#336699"
    sw.deleteLater()


def test_default_swatch_still_self_picks(qapp, monkeypatch):
    monkeypatch.setattr(colour_picker, "pick_colour", lambda *a, **k: "#00ff00")
    sw = Swatch("#336699")               # property-panel usage: label + auto pick
    assert not sw._label.isHidden()
    seen = []
    sw.colorChanged.connect(seen.append)
    sw.show()
    QTest.mouseClick(sw._chip, _LEFT)
    assert seen == ["#00ff00"] and sw.hex() == "#00ff00"
    sw.deleteLater()


def test_disabled_chip_is_dimmed(qapp):
    sw = Swatch("#336699", show_label=False, auto_pick=False)
    on = _chip_img(sw).pixelColor(17, 7).rgba()
    sw.setEnabled(False)
    QApplication.processEvents()
    assert sw._chip.grab().toImage().pixelColor(17, 7).rgba() != on
    sw.deleteLater()


def _near(img, col, tol=30):
    return sum(1 for x in range(img.width()) for y in range(img.height())
               if abs(img.pixelColor(x, y).red() - col.red()) <= tol
               and abs(img.pixelColor(x, y).green() - col.green()) <= tol
               and abs(img.pixelColor(x, y).blue() - col.blue()) <= tol)


def test_eye_toggle_is_checkbox_compatible_and_paints_state(qapp):
    eye = EyeToggle(checked=True)
    seen = []
    eye.toggled.connect(seen.append)
    eye.show()
    QApplication.processEvents()
    accent = detect().color("accent")
    assert eye.isChecked() and _near(eye.grab().toImage(), accent) > 0       # open eye = accent strokes
    QTest.mouseClick(eye, _LEFT)
    QApplication.processEvents()
    assert seen == [False] and not eye.isChecked()
    assert _near(eye.grab().toImage(), accent) == 0                          # closed eye = faint, no accent
    eye.setChecked(True)
    assert seen == [False, True]
    eye.deleteLater()


def test_underlay_delegate_and_eye_toggle_share_one_painter():
    assert umd._draw_eye is ui_kit.paint_eye
    assert umd._round_pen is ui_kit.round_pen
    # D2 (ratified): closed eye = the Underlay Manager's faint@170, open = accent.
    t = detect()
    assert ui_kit.eye_color(t, False) == t.color("faint", 170)
    assert ui_kit.eye_color(t, True) == t.color("accent")
