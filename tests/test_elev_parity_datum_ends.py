"""Elevation-parity D7 / AC10 / AC11: level-datum and gridline end edits in a
section persist per section on the SectionMarker (gridline uid / level name
keyed), survive rebuilds, model edits, tab switches and save / reopen, are one
undo step on the plan stack, and the right datum grip draws where dragged.

Drags are posted QMouseEvents on the SHOWN section view's viewport (the
tests/test_constraint_live_drag.py ``_send`` idiom): QTest.mouseMove would move
the real cursor. Undo / redo go through the wired window QShortcut.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.section_scene import ElevDatumItem, ElevGridlineItem
from tests._mainwindow_helpers import dispose_main_window
from tests.test_sb4c_level_datum import BG, _render

L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
DATUM_PULL_MM = 2000.0     # test choice: the right end is pulled this far left of the auto end
GRID_PULL_MM = 700.0       # test choice: the gridline's bottom end is pulled this far up
GRID_X_MM = 2500.0         # test choice: plan x of the test gridline (crosses the north cut)


def _send(v, etype, scene_pt, button, buttons):
    vp = QPointF(v.mapFromScene(scene_pt))
    gp = QPointF(v.viewport().mapToGlobal(vp.toPoint()))
    QApplication.sendEvent(v.viewport(), QMouseEvent(
        etype, vp, gp, button, buttons, Qt.KeyboardModifier.NoModifier))
    QApplication.processEvents()


def _drag(v, a: QPointF, b: QPointF) -> None:
    """Hover, press on *a*, move through the midpoint to *b*, release."""
    _send(v, QEvent.Type.MouseMove, a, NB, NB)
    _send(v, QEvent.Type.MouseButtonPress, a, L, L)
    _send(v, QEvent.Type.MouseMove,
          QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0), NB, L)
    _send(v, QEvent.Type.MouseMove, b, NB, L)
    _send(v, QEvent.Type.MouseButtonRelease, b, L, NB)


def _px_mm(v) -> float:
    """Scene mm per viewport pixel on the shown view (posted points snap to px)."""
    return 1.0 / v.transform().m11()


def _datum(sec, level_name: str) -> ElevDatumItem:
    (dt,) = [i for i in sec.items()
             if isinstance(i, ElevDatumItem) and i._level.name == level_name]
    return dt


def _ink(sec, rect: QRectF) -> int:
    """Painted (non-background) pixels of *sec* inside scene *rect* (5 mm / px)."""
    w, h = max(int(rect.width() / 5.0), 1), max(int(rect.height() / 5.0), 1)
    img = _render(sec, rect, w, h)
    return sum(1 for x in range(w) for y in range(h) if img.pixel(x, y) != BG)


def _drag_datum_right(v, sec, level_name: str = "Level 1"):
    """Select *level_name*'s datum and drag its right grip DATUM_PULL_MM left.
    Holds the debounced rebuild so the live item can be read. Returns
    (item, start h, target h)."""
    dt = _datum(sec, level_name)
    p2 = QPointF(dt.line().p2())
    target = QPointF(p2.x() - DATUM_PULL_MM, p2.y())
    v.fitInView(QRectF(p2.x() - 4000.0, p2.y() - 2500.0, 5000.0, 5000.0),
                Qt.AspectRatioMode.KeepAspectRatio)
    QApplication.processEvents()
    sec.clearSelection()
    dt.setSelected(True)
    QApplication.processEvents()
    _drag(v, p2, target)
    sec._rebuild_timer.stop()
    return dt, p2.x(), target.x()


def test_right_grip_drag_moves_the_painted_line_end(qapp, section_scene_for):
    """Absorbed "Level datum right grip is invisible": the line is painted to the
    dragged right end (p2), not the construction h_max. Ink right of the new
    end is gone, ink left of it stays."""
    from firepro3d.elevation_view import SectionView
    _ms, sec = section_scene_for("north")
    sec.rebuild()
    auto_right = sec.basis.h_max                        # the crop box = the auto right end
    v = SectionView(sec)
    try:
        v.resize(900, 700)
        v.show()
        QTest.qWaitForWindowExposed(v)
        dt, start, target = _drag_datum_right(v, sec)
        assert start == pytest.approx(auto_right)
        end = dt.line().p2().x()
        assert end == pytest.approx(target, abs=2 * _px_mm(v))
        sec.clearSelection()                            # no manipulator frame in the render
        QApplication.processEvents()
        gone = _ink(sec, QRectF(end + 150.0, -150.0, auto_right - end - 300.0, 300.0))
        kept = _ink(sec, QRectF(end - 1850.0, -150.0, 1700.0, 300.0))
        assert kept > 0, "datum line not painted left of its right end"
        assert gone == 0, "datum line still painted past its dragged right end"
    finally:
        sec._rebuild_timer.stop()
        v.close()
