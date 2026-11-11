"""AC14 / R16: on the 3D tab the modify and clipboard shortcuts refuse with a
footer message instead of starting on the hidden plan scene."""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from tests._mainwindow_helpers import dispose_main_window

SHIFT = Qt.KeyboardModifier.ShiftModifier
CTRL = Qt.KeyboardModifier.ControlModifier


@pytest.mark.parametrize("key,mods", [
    (Qt.Key.Key_M, SHIFT), (Qt.Key.Key_C, CTRL),
    (Qt.Key.Key_X, CTRL), (Qt.Key.Key_D, CTRL)],
    ids=["Shift+M", "Ctrl+C", "Ctrl+X", "Ctrl+D"])
def test_modify_shortcut_on_the_3d_tab_refuses_with_a_footer_message(qapp, key, mods):
    from firepro3d.constants import VIEW_3D_EDIT_REFUSED_HINT
    from firepro3d.wall import WallSegment
    from tests.test_section_manager import _main_window
    win = _main_window()
    ms = win.scene
    try:
        win.show()
        QTest.qWaitForWindowExposed(win)
        wall = WallSegment(QPointF(0, 0), QPointF(1000, 0))
        ms.addItem(wall)
        wall.setSelected(True)       # plan would start Move / Copy / Cut / Duplicate on it
        win.view3d_tab.open()
        QApplication.processEvents()
        assert win.central_tabs.currentWidget() is win.view_3d     # precondition
        mode0 = ms.mode
        QTest.keyClick(win.windowHandle(), key, mods)
        QApplication.processEvents()
        assert ms.mode == mode0                                    # [RED] plan tool started
        assert win.footer.instruction.text() == VIEW_3D_EDIT_REFUSED_HINT
    finally:
        dispose_main_window(win)
