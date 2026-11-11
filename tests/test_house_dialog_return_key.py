"""Return inside a HouseDialog presses the primary button, never rejects.

Real entry point: a shown dialog, a real Return key sent to the focus widget.
Todo: "Return in any HouseDialog rejects instead of pressing the primary button".
"""
from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QDialog, QLineEdit, QPushButton

from firepro3d.house_dialog import HouseDialog


def _press_return(w):
    for typ in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QCoreApplication.sendEvent(
            w, QKeyEvent(typ, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))


def _shown(qapp, fired):
    d = HouseDialog(None, title="T", icon=None, min_width=300)
    d.set_footer_buttons(primary=("OK", lambda: (fired.append(1), d.accept())))
    d.show()
    qapp.processEvents()
    return d


def test_return_at_initial_focus_accepts(qapp):
    fired = []
    d = _shown(qapp, fired)
    _press_return(d.focusWidget() or d)
    qapp.processEvents()
    assert fired == [1]
    assert d.result() == QDialog.DialogCode.Accepted


def test_return_in_a_line_edit_accepts(qapp):
    fired = []
    d = HouseDialog(None, title="T", icon=None, min_width=300)
    le = QLineEdit()
    d.set_body(le)
    d.set_footer_buttons(primary=("OK", lambda: (fired.append(1), d.accept())))
    d.show()
    le.setFocus()
    qapp.processEvents()
    _press_return(le)
    qapp.processEvents()
    assert fired == [1]
    assert d.result() == QDialog.DialogCode.Accepted


def test_title_bar_dots_never_take_default_or_focus(qapp):
    from firepro3d.frameless_shell import _WinDot
    d = _shown(qapp, [])
    dots = d.findChildren(_WinDot)
    assert dots, "HouseDialog should have title-bar dots"
    for dot in dots:
        assert not dot.autoDefault()
        assert dot.focusPolicy() == Qt.FocusPolicy.NoFocus


def _confirm(qapp, danger):
    from firepro3d.themed_message import ThemedMessageDialog
    d = ThemedMessageDialog("T", "Sure?")
    d._make_confirm("Delete", "Keep", danger)
    d.show()
    qapp.processEvents()
    _press_return(d.focusWidget() or d)
    qapp.processEvents()
    return d


def test_danger_confirm_return_is_the_safe_choice(qapp):
    d = _confirm(qapp, danger=True)
    assert d.result() == QDialog.DialogCode.Rejected


def test_plain_confirm_return_accepts(qapp):
    d = _confirm(qapp, danger=False)
    assert d.result() == QDialog.DialogCode.Accepted


def test_colour_picker_return_accepts_from_hex_field(qapp):
    from firepro3d.colour_picker import ColourPickerDialog
    d = ColourPickerDialog(None, initial="#FF0000", context="T")
    d.show()
    d._hex.setFocus()
    qapp.processEvents()
    _press_return(d._hex)
    qapp.processEvents()
    assert d.result() == QDialog.DialogCode.Accepted
