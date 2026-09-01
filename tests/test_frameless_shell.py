from PyQt6.QtWidgets import QDialog
from PyQt6.QtCore import Qt
from firepro3d.frameless_shell import FramelessShellMixin


class _Host(FramelessShellMixin, QDialog):
    def __init__(self):
        super().__init__()
        self.init_frameless_shell(title="Host", controls=("min", "max", "close"), resizable=True)


def test_shell_is_frameless_with_three_controls(qapp):
    h = _Host()
    assert h.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert {"min", "max", "close"} <= set(h._win_controls.keys())
    h.deleteLater()


def test_double_click_titlebar_toggles_maximize(qapp):
    h = _Host()
    h.show(); qapp.processEvents()
    assert not h.isMaximized()
    h._toggle_max(); qapp.processEvents()
    assert h.isMaximized()
    h._toggle_max(); qapp.processEvents()
    assert not h.isMaximized()
    h.deleteLater()
