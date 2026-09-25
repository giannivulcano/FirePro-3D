"""Real-path helpers for the 2026-09-24 snap-polish guards.

Builds a SHOWN Model_View over a real Model_Space (pinned zoom) and posts real
QMouseEvents to the viewport, so presses/moves route through the scene's own
dispatch (get_effective_position, manipulator, placement handlers).
"""
from __future__ import annotations

import time

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication


def make_view(role: str = "block_editor", scale: float = 0.25, mode: str | None = "select"):
    """Return (view, scene): shown 800x600 Model_View, m11 == *scale*, centred on 0,0."""
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_space import Model_Space
    from firepro3d.model_view import Model_View
    from firepro3d.scale_manager import ScaleManager

    scene = Model_Space(scene_role=role)
    scene._level_manager = LevelManager()
    scene.scale_manager = ScaleManager()
    view = Model_View(scene)
    view.resize(800, 600)
    view.show()
    QTest.qWaitForWindowExposed(view)
    view.resetTransform()
    view.scale(scale, scale)
    view.centerOn(0, 0)
    view.setFocus()
    QApplication.processEvents()
    if mode is not None:
        scene.set_mode(mode)
    return view, scene


def close_view(view, scene) -> None:
    scene.cleanup()
    view.close()
    view.deleteLater()
    QApplication.processEvents()


def post(view, etype, spt: QPointF,
         mods=Qt.KeyboardModifier.NoModifier,
         button=Qt.MouseButton.LeftButton) -> None:
    """Post one mouse event at scene point *spt* (float-mapped, not rounded)."""
    vpf = view.viewportTransform().map(spt)
    if etype == QEvent.Type.MouseMove:
        btn, btns = Qt.MouseButton.NoButton, (
            button if getattr(view, "_snap_polish_pressed", False) else Qt.MouseButton.NoButton)
    elif etype == QEvent.Type.MouseButtonRelease:
        btn, btns = button, Qt.MouseButton.NoButton
    else:
        btn, btns = button, button
    ev = QMouseEvent(etype, vpf, view.viewport().mapToGlobal(vpf), btn, btns, mods)
    QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()


def click(view, spt: QPointF, mods=Qt.KeyboardModifier.NoModifier) -> None:
    post(view, QEvent.Type.MouseButtonPress, spt, mods)
    post(view, QEvent.Type.MouseButtonRelease, spt, mods)


def move(view, spt: QPointF, mods=Qt.KeyboardModifier.NoModifier) -> None:
    post(view, QEvent.Type.MouseMove, spt, mods)


def drag(view, start: QPointF, end: QPointF, steps: int = 6,
         mods=Qt.KeyboardModifier.NoModifier) -> None:
    """Press at *start*, move in *steps* to *end* (mods on EVERY event), release."""
    post(view, QEvent.Type.MouseButtonPress, start, mods)
    view._snap_polish_pressed = True
    try:
        for i in range(1, steps + 1):
            t = i / steps
            move(view, QPointF(start.x() + (end.x() - start.x()) * t,
                               start.y() + (end.y() - start.y()) * t), mods)
    finally:
        view._snap_polish_pressed = False
    post(view, QEvent.Type.MouseButtonRelease, end, mods)


def dwell(view, spt: QPointF) -> None:
    """Real ALIGN dwell acquire: two moves on the same point 450 ms apart."""
    move(view, spt)
    time.sleep(0.45)
    move(view, spt)
