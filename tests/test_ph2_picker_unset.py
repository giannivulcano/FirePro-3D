"""PH2 Task 2 (guard e): the picker's "— No override" entry returns NO_OVERRIDE, not NO_FILL;
Swatch shows an unset value as "—"."""
from firepro3d import colour_picker as cp
from firepro3d.ui_kit import Swatch


def test_no_override_entry_only_when_allowed(qapp):
    plain = cp.ColourPickerDialog(None, initial="#808080")
    assert plain.no_override_button() is None
    dlg = cp.ColourPickerDialog(None, initial="#808080", allow_unset=True)
    btn = dlg.no_override_button()
    assert btn is not None and "No override" in btn.text()
    btn.click()
    assert dlg.result_value() == cp.NO_OVERRIDE
    assert cp.NO_OVERRIDE != cp.NO_FILL
    plain.deleteLater(); dlg.deleteLater()


def test_pick_colour_passes_no_override_through(qapp, monkeypatch):
    from PyQt6.QtWidgets import QDialog

    def fake_exec(self):
        self._result_value = cp.NO_OVERRIDE
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(cp.ColourPickerDialog, "exec", fake_exec)
    assert cp.pick_colour("#808080", None, "Colour", allow_unset=True) == cp.NO_OVERRIDE


def test_swatch_unset_shows_dash(qapp):
    sw = Swatch(None, unset_ok=True)
    assert sw.hex() is None
    sw.set_hex("#123456")
    sw.set_hex(None)
    assert sw.hex() is None and sw._label.text() == "—"
    legacy = Swatch(None)                    # default unchanged: None -> black
    assert legacy.hex() == "#000000"
