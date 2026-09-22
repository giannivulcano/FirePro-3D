"""House colour picker (todo #70) — dialog behaviour, recents, glyph, themes.

Drives real widgets (QTest mouse/key events), asserts observable results."""
import pytest
from PyQt6.QtCore import Qt, QRectF, QPoint
from PyQt6.QtGui import QImage, QPainter, QColor
from PyQt6.QtTest import QTest


def _render_glyph(w=22, h=22):
    from firepro3d.ui_kit import paint_no_fill
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor("#00ff00"))             # sentinel ground: must be fully covered
    p = QPainter(img)
    paint_no_fill(p, QRectF(0, 0, w, h), 0)
    p.end()
    return img


def test_no_fill_glyph_white_with_red_diagonal(qapp):
    img = _render_glyph()
    # corner off the diagonal (top-left) is white
    assert QColor(img.pixel(2, 2)).name() == "#ffffff"
    # centre sits on the bottom-left -> top-right slash: strongly red
    c = QColor(img.pixel(11, 11))
    assert c.red() > 180 and c.green() < 110 and c.blue() < 110


def test_chip_paints_no_fill_when_empty(qapp):
    from firepro3d.ui_kit import _Chip
    chip = _Chip("")
    chip.resize(chip.size())
    img = chip.grab().toImage()
    cx, cy = img.width() // 2, img.height() // 2
    c = QColor(img.pixel(cx, cy))
    assert c.red() > 180 and c.green() < 110     # red slash through the centre
    assert QColor.fromRgba(img.pixel(3, 3)).alpha() == 255     # glyph fully covers the chip (not transparent)


def test_colour_metric_tokens_match_mockup():
    from firepro3d.theme import M
    assert (M.COLOUR_DLG_W, M.COLOUR_SV_W, M.COLOUR_SV_H, M.COLOUR_HUE_W) == (440, 210, 170, 16)
    assert (M.COLOUR_COL_GAP, M.COLOUR_CHIP, M.COLOUR_CHIP_GAP, M.COLOUR_CHIP_RADIUS) == (16, 22, 4, 3)
    assert (M.COLOUR_SEL_RING, M.COLOUR_SEC_GAP, M.COLOUR_PREVIEW_H) == (2, 12, 40)


def test_palette_is_fixed_cad_set():
    from firepro3d import colour_picker as cp
    assert cp.STANDARD == ("#FF0000", "#FF7F00", "#FFFF00", "#00FF00", "#00FFFF",
                           "#0000FF", "#FF00FF", "#808080", "#C0C0C0", "#FFFFFF")
    assert cp.GREYS == ("#000000", "#1C1C1C", "#393939", "#555555", "#717171",
                        "#8E8E8E", "#AAAAAA", "#C6C6C6", "#E3E3E3", "#FFFFFF")
    assert cp.NO_FILL == ""


def test_recents_mru_dedupe_cap_and_persist(qapp):
    from firepro3d import colour_picker as cp
    cp.clear_recents()
    for h in ["#111111", "#222222", "#111111"]:
        cp.push_recent(h)
    assert cp.load_recents() == ["#111111", "#222222"]     # MRU first, deduped
    cp.push_recent("#abcdef")
    assert cp.load_recents()[0] == "#ABCDEF"               # normalised upper
    cp.push_recent("#AbCdEf")
    assert cp.load_recents().count("#ABCDEF") == 1          # case-insensitive dedupe
    for i in range(20):
        cp.push_recent(f"#0000{i:02X}")
    assert len(cp.load_recents()) == cp.RECENTS_MAX == 10
    cp.push_recent("")                                      # No Fill is never recorded
    assert "" not in cp.load_recents()


# ── Task 3: ColourPickerDialog + pick_colour ───────────────────────────────

def _dlg(qapp, initial="#FF0000", allow_none=False, context="Test"):
    from firepro3d.colour_picker import ColourPickerDialog
    d = ColourPickerDialog(None, initial=initial, context=context, allow_none=allow_none)
    d.show()
    qapp.processEvents()
    return d


def _chip(d, hex_or_nofill):
    return next(c for c in d._chips if c.value == hex_or_nofill)


def test_opens_with_initial_selected(qapp):
    d = _dlg(qapp, "#0000ff")
    assert d.current_value() == "#0000FF"
    assert _chip(d, "#0000FF").selected
    assert d._hex.text() == "#0000FF"
    assert (d._r.value(), d._g.value(), d._b.value()) == (0, 0, 255)
    d.close()


def test_preset_click_then_ok_returns_hex(qapp):
    d = _dlg(qapp, "#FF0000")
    QTest.mouseClick(_chip(d, "#00FFFF"), Qt.MouseButton.LeftButton)
    assert d.current_value() == "#00FFFF"
    QTest.mouseClick(d._ok_btn, Qt.MouseButton.LeftButton)
    assert d.result() == d.DialogCode.Accepted and d.result_value() == "#00FFFF"


def test_double_click_chip_commits(qapp):
    d = _dlg(qapp, "#FF0000")
    QTest.mouseDClick(_chip(d, "#808080"), Qt.MouseButton.LeftButton)
    assert d.result() == d.DialogCode.Accepted and d.result_value() == "#808080"


def test_escape_cancels_and_is_not_no_fill(qapp):
    d = _dlg(qapp, "#FF0000", allow_none=True)
    QTest.mouseClick(_chip(d, "#00FFFF"), Qt.MouseButton.LeftButton)   # move off default
    fired = []
    d.rejected.connect(lambda: fired.append(1))
    QTest.keyClick(d, Qt.Key.Key_Escape)
    assert fired == [1]
    assert not d.isVisible()
    assert d.result() == d.DialogCode.Rejected
    assert d.result_value() is None                 # cancelled ≠ "" (No Fill)


def test_cancel_button_returns_none(qapp):
    from PyQt6.QtWidgets import QDialogButtonBox
    d = _dlg(qapp, "#FF0000")
    QTest.mouseClick(_chip(d, "#00FFFF"), Qt.MouseButton.LeftButton)   # move off default
    fired = []
    d.rejected.connect(lambda: fired.append(1))
    QTest.mouseClick(d._footer_box.button(QDialogButtonBox.StandardButton.Cancel),
                     Qt.MouseButton.LeftButton)
    assert fired == [1]
    assert not d.isVisible()
    assert d.result_value() is None


def test_no_fill_chip_only_when_allowed_and_at_end_of_standard(qapp):
    d = _dlg(qapp, "#FF0000", allow_none=False)
    assert all(c.value != "" for c in d._chips)
    d.close()
    d = _dlg(qapp, "#FF0000", allow_none=True)
    row = d._standard_row_chips
    assert [c.value for c in row] == [*__import__("firepro3d.colour_picker", fromlist=["x"]).STANDARD, ""]
    QTest.mouseClick(row[-1], Qt.MouseButton.LeftButton)
    assert d.current_value() == ""
    QTest.mouseClick(d._ok_btn, Qt.MouseButton.LeftButton)
    assert d.result_value() == ""


def test_initial_no_fill_opens_no_fill_selected(qapp):
    d = _dlg(qapp, "", allow_none=True)
    assert d.current_value() == "" and _chip(d, "").selected
    d.close()


def test_initial_empty_without_allow_none_falls_back_to_black(qapp):
    d = _dlg(qapp, "", allow_none=False)
    assert d.current_value() == "#000000"
    d.close()


def test_hex_entry_valid_and_invalid(qapp):
    d = _dlg(qapp, "#FF0000")
    d._hex.setFocus()
    d._hex.selectAll()
    QTest.keyClicks(d._hex, "#12AB34")
    assert d.current_value() == "#12AB34"
    assert (d._r.value(), d._g.value(), d._b.value()) == (0x12, 0xAB, 0x34)
    d._hex.selectAll()
    QTest.keyClicks(d._hex, "#12")                   # incomplete: keeps last valid
    assert d._hex.text() == "#12"
    assert d.current_value() == "#12AB34"
    d._hex.clearFocus()
    d._hex.editingFinished.emit()                    # focus-out reformat
    assert d._hex.text() == "#12AB34"
    QTest.mouseClick(d._ok_btn, Qt.MouseButton.LeftButton)
    assert d.result_value() == "#12AB34"


def test_rgb_stepper_edits_colour(qapp):
    d = _dlg(qapp, "#000000")
    d._g.setValue(200)
    assert d.current_value() == "#00C800"
    assert d._hex.text() == "#00C800"
    d.close()


def test_sv_field_drag_changes_colour(qapp):
    d = _dlg(qapp, "#FF0000")
    sv = d._sv
    QTest.mouseClick(sv, Qt.MouseButton.LeftButton, pos=QPoint(2, sv.height() - 2))
    c = QColor(d.current_value())
    assert c.value() < 20                           # bottom edge = black
    d.close()


def test_hue_bar_click_changes_hue(qapp):
    d = _dlg(qapp, "#FF0000")
    hb = d._hue
    QTest.mouseClick(hb, Qt.MouseButton.LeftButton, pos=QPoint(hb.width() // 2, hb.height() // 3))
    assert abs(QColor(d.current_value()).hsvHue() - 120) < 12   # ⅓ down ≈ green
    d.close()


def test_ok_records_recent_cancel_and_no_fill_do_not(qapp):
    from firepro3d import colour_picker as cp
    cp.clear_recents()
    d = _dlg(qapp, "#123456", allow_none=True)
    QTest.mouseClick(d._ok_btn, Qt.MouseButton.LeftButton)
    assert cp.load_recents() == ["#123456"]
    d = _dlg(qapp, "#654321")
    QTest.keyClick(d, Qt.Key.Key_Escape)
    d = _dlg(qapp, "", allow_none=True)
    QTest.mouseClick(d._ok_btn, Qt.MouseButton.LeftButton)
    assert cp.load_recents() == ["#123456"]
    # a NEW dialog instance shows it in the Recent row
    d = _dlg(qapp, "#000000")
    assert [c.value for c in d._recent_row_chips if c.value is not None][:1] == ["#123456"]
    d.close()


def test_empty_recent_slots_are_inert(qapp):
    from firepro3d import colour_picker as cp
    cp.clear_recents()
    d = _dlg(qapp, "#FF0000")
    slots = d._recent_row_chips
    assert len(slots) == cp.RECENTS_MAX and all(s.value is None for s in slots)
    QTest.mouseClick(slots[0], Qt.MouseButton.LeftButton)
    assert d.current_value() == "#FF0000"
    d.close()


def test_pick_colour_entry_point_tristate(qapp, monkeypatch):
    from firepro3d import colour_picker as cp
    from PyQt6.QtWidgets import QDialog
    cp.clear_recents()
    def _rej(self):
        self.reject()
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(cp.ColourPickerDialog, "exec", _rej)
    assert cp.pick_colour("#FF0000", None, "x") is None
    def _acc(self):
        self._set_no_fill()
        self.accept()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(cp.ColourPickerDialog, "exec", _acc)
    assert cp.pick_colour("#FF0000", None, "x", allow_none=True) == ""
    assert cp.load_recents() == []                   # No Fill is never recorded


def test_enter_key_accepts(qapp):
    d = _dlg(qapp, "#FF0000")
    QTest.mouseClick(_chip(d, "#0000FF"), Qt.MouseButton.LeftButton)
    QTest.keyClick(d, Qt.Key.Key_Return)
    assert d.result() == d.DialogCode.Accepted and d.result_value() == "#0000FF"


def test_pick_colour_returns_lowercase_like_qcolor_name(qapp, monkeypatch):
    from firepro3d import colour_picker as cp
    from PyQt6.QtWidgets import QDialog
    cp.clear_recents()
    def _accept_blue(self):
        self._set_colour(QColor("#ABCDEF"))
        self.accept()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(cp.ColourPickerDialog, "exec", _accept_blue)
    assert cp.pick_colour("#000000", None, "x") == "#abcdef"
    assert cp.load_recents() == ["#ABCDEF"]


def test_context_label_and_title(qapp):
    d = _dlg(qapp, "#FF0000", context="Roof")
    assert d._ctx_lbl.text() == "Roof"
    assert d._shell_title_lbl.text() == "Colour"
    d.close()


def test_every_interactive_control_has_tooltip(qapp):
    d = _dlg(qapp, "#FF0000", allow_none=True)
    for w in [d._sv, d._hue, d._hex, d._r, d._g, d._b, *d._chips]:
        assert w.toolTip(), f"missing tooltip on {w!r}"
    d.close()


def test_right_click_chip_does_not_pick(qapp):
    d = _dlg(qapp, "#FF0000")
    QTest.mouseClick(_chip(d, "#0000FF"), Qt.MouseButton.RightButton)
    assert d.current_value() == "#FF0000"
    d.close()


@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_dialog_chrome_uses_theme_tokens(qapp, theme_name):
    from firepro3d import theme as th
    from firepro3d.colour_picker import ColourPickerDialog
    from PyQt6.QtWidgets import QFrame
    t = th.DARK if theme_name == "dark" else th.LIGHT
    d = ColourPickerDialog(None, initial="#FF0000", context="x", theme=t)
    d.show(); qapp.processEvents()
    img = d.grab().toImage()
    body = d.findChild(QFrame, "dialogBody")
    pt = body.mapTo(d, body.rect().bottomRight()) - QPoint(4, 4)   # empty body corner
    assert QColor(img.pixel(pt.x(), pt.y())).name() == QColor(t.surface).name()
    footer = d._footer                                             # empty gap left of the buttons
    fp = footer.mapTo(d, QPoint(footer.width() // 2 - 40, footer.height() // 2))
    assert QColor(img.pixel(fp.x(), fp.y())).name() == QColor(t.surface2).name()
    # palette chips are theme-INDEPENDENT: centre of the red ACI chip is pure red
    chip = next(c for c in d._chips if c.value == "#FF0000")
    cp_ = chip.mapTo(d, chip.rect().center())
    assert QColor(img.pixel(cp_.x(), cp_.y())).name() == "#ff0000"
    d.close()


@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_group_labels_are_accent_coloured(qapp, theme_name):
    """User 2026-09-22: the all-caps STANDARD/GREYS/RECENT group labels use the
    theme accent (not the muted dialog-header colour)."""
    from PyQt6.QtGui import QPalette
    from PyQt6.QtWidgets import QLabel
    from firepro3d import theme as th
    from firepro3d.colour_picker import ColourPickerDialog
    t = th.DARK if theme_name == "dark" else th.LIGHT
    d = ColourPickerDialog(None, initial="#FF0000", context="x", theme=t)
    d.show(); qapp.processEvents()
    labels = [l for l in d.findChildren(QLabel) if l.text() in ("STANDARD", "GREYS", "RECENT")]
    assert len(labels) == 3
    for lbl in labels:
        assert lbl.palette().color(QPalette.ColorRole.WindowText).name() == QColor(t.accent).name()
    d.close()


@pytest.mark.parametrize("initial, allow_none", [("", True), ("#000000", False), ("#808080", False)])
def test_hue_drag_from_achromatic_start_changes_colour(qapp, initial, allow_none):
    """User smoke 2026-09-22: opened from No Fill / black, dragging the hue bar
    left the colour #000000 (black/grey at any hue is still black/grey), so the
    preview looked dead until a preset was clicked. Hue on an achromatic colour
    must produce a visible hue."""
    d = _dlg(qapp, initial, allow_none=allow_none)
    hb = d._hue
    QTest.mouseClick(hb, Qt.MouseButton.LeftButton, pos=QPoint(hb.width() // 2, hb.height() // 2))
    c = QColor(d.current_value())
    assert c.hsvSaturation() > 200, d.current_value()          # chromatic now
    assert abs(c.hsvHue() - 180) < 12                           # ≈ cyan at mid-bar
    assert d._hex.text() == d.current_value()                   # hex/RGB follow
    assert (d._r.value(), d._g.value(), d._b.value()) == (c.red(), c.green(), c.blue())
    d.close()


def test_hue_drag_keeps_chromatic_saturation_and_value(qapp):
    d = _dlg(qapp, "#804040")                                   # s≈0.5, v≈0.5
    s0, v0 = QColor("#804040").hsvSaturationF(), QColor("#804040").valueF()
    hb = d._hue
    QTest.mouseClick(hb, Qt.MouseButton.LeftButton, pos=QPoint(hb.width() // 2, hb.height() // 2))
    c = QColor(d.current_value())
    assert abs(c.hsvSaturationF() - s0) < 0.02 and abs(c.valueF() - v0) < 0.02
    d.close()
