"""A property-panel ``button`` row must get real width (Edit Revisions regression).

The form uses ``ExpandingFieldsGrow``; a field whose horizontal policy lacks the
Expand flag (the old ``Ignored``) laid out at 0 px, so every button row (Edit
Revisions, View Range, Design Point, ...) rendered invisible while Qt still
reported it visible.  The long-face case keeps the 2026-07-14 containment rule:
a long face must shrink, never widen the dock.
"""
from PyQt6.QtWidgets import QApplication, QPushButton
from PyQt6.QtTest import QTest

from firepro3d.property_manager import PropertyManager

DOCK_W = 240


class _Target:
    def __init__(self, face):
        self._face = face

    def get_properties(self):
        return {
            "Name": {"type": "string", "value": "x"},
            "": {"type": "button", "value": self._face, "callback": lambda: None},
        }

    def set_property(self, key, value):
        pass


def _shown_panel(qapp, face):
    pm = PropertyManager()
    pm.resize(DOCK_W, 400)
    pm.show()
    QTest.qWaitForWindowExposed(pm)
    pm.show_properties(_Target(face))
    QApplication.processEvents()
    QApplication.processEvents()
    return pm


def test_button_row_has_real_width(qapp):
    pm = _shown_panel(qapp, "Edit Revisions…")
    try:
        btn = [b for b in pm.findChildren(QPushButton) if b.isVisible()][0]
        assert btn.width() > 60, f"button laid out at {btn.width()} px"
    finally:
        pm.close()


def test_long_button_face_does_not_widen_the_panel(qapp):
    pm = _shown_panel(qapp, "Design Point: a very long face " * 6)
    try:
        btn = [b for b in pm.findChildren(QPushButton) if b.isVisible()][0]
        assert btn.width() > 60
        assert btn.mapTo(pm, btn.rect().topRight()).x() <= DOCK_W, (
            "a long face widened the form past the dock")
    finally:
        pm.close()
