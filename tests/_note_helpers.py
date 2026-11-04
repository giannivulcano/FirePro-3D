"""Shared drivers for the Note tests: real mouse and key events through a shown view."""
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

NO = Qt.KeyboardModifier.NoModifier


def mouse(view, etype, pt, mods=NO, buttons=Qt.MouseButton.LeftButton,
          button=Qt.MouseButton.LeftButton):
    """Send one mouse event at scene point *pt* (sendEvent: QTest mouse calls are
    spontaneous and the shown-view fixture drops those)."""
    vp = view.mapFromScene(pt)
    gp = view.viewport().mapToGlobal(vp)
    ev = QMouseEvent(etype, QPointF(vp), QPointF(gp), button, buttons, mods)
    QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()


def click(view, pt, mods=NO):
    mouse(view, QEvent.Type.MouseButtonPress, pt, mods)
    mouse(view, QEvent.Type.MouseButtonRelease, pt, mods, Qt.MouseButton.NoButton)


def dbl(view, pt):
    click(view, pt)
    mouse(view, QEvent.Type.MouseButtonDblClick, pt)
    mouse(view, QEvent.Type.MouseButtonRelease, pt, NO, Qt.MouseButton.NoButton)


def key(view, k, mods=NO):
    QTest.keyClick(view.windowHandle(), k, mods)
    QApplication.processEvents()
