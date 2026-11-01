"""DS3 Flip quadrants (AC-X1..X3): centre = bbox centre of the selection, the
cursor quadrant + arrow keys choose lr / ud, live crosshair + ghost, commit
reflects once per active axis. Mirror keeps the edge-pick axis.

Item: an open polyline (0,0)(100,0)(100,-100) -> bbox x 0..100, y -100..0,
centre (CX, CY) = (50, -50) (scene is Y-down: smaller y = upper).
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QKeyEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.transform_ghost import GhostFrame
from tests._modify_tools_helpers import add_primitive, grips, ignore_os_mouse
from tests._snap_polish_helpers import click, close_view, make_view, move
from tests.test_modify_tools_flip_mirror import (_PaintSpy, _capture_status,
                                                 _grab, _px)

CX, CY = 50.0, -50.0
OFF = 60.0
QUADS = {                       # name -> (cursor, lr, ud)
    "UR": (QPointF(CX + OFF, CY - OFF), False, False),
    "UL": (QPointF(CX - OFF, CY - OFF), True, False),
    "LR": (QPointF(CX + OFF, CY + OFF), False, True),
    "LL": (QPointF(CX - OFF, CY + OFF), True, True),
}
POLY0 = [(0.0, 0.0), (100.0, 0.0), (100.0, -100.0)]
POLY_LR = [(100.0, 0.0), (0.0, 0.0), (0.0, -100.0)]      # x -> 100 - x
POLY_UD = [(0.0, -100.0), (100.0, -100.0), (100.0, 0.0)]  # y -> -100 - y
POLY_BOTH = [(100.0, -100.0), (0.0, -100.0), (0.0, 0.0)]
EXPECT = {"UR": POLY0, "UL": POLY_LR, "LR": POLY_UD, "LL": POLY_BOTH}
SAMPLES = [QPointF(0, 0), QPointF(100, 0), QPointF(100, -100), QPointF(20, -70)]
HINT = "Move into a quadrant or ←→ / ↑↓ to flip · click/Enter applies"


def _poly(scene):
    return add_primitive(scene, "polyline_open")[0]


def _reflect_expected(p, lr, ud):
    return (2 * CX - p.x() if lr else p.x(), 2 * CY - p.y() if ud else p.y())


def test_union_manip_bounds_is_the_frame_the_manipulator_draws(qapp):
    from firepro3d.selection_manipulator import union_manip_bounds
    view, scene = make_view(scale=1.0)
    try:
        a = RectangleItem(QPointF(0, 0), QPointF(100, -50))      # manip_bounds
        b = RectangleItem(QPointF(200, 40), QPointF(260, 100))
        for it in (a, b):
            scene.addItem(it)
            scene._draw_rects.append(it)
        r = union_manip_bounds([a, b])
        assert (r.left(), r.top(), r.right(), r.bottom()) == (0.0, -50.0, 260.0, 100.0)
        assert (r.center().x(), r.center().y()) == (130.0, 25.0)
        assert union_manip_bounds([]).isNull()
        # single source of truth: the live manipulator frame is the same union
        scene.clearSelection()
        a.setSelected(True)
        b.setSelected(True)
        QApplication.processEvents()
        frame = scene._live_manip()._rect
        assert (frame.left(), frame.top(), frame.right(), frame.bottom()) == (
            r.left(), r.top(), r.right(), r.bottom())
    finally:
        close_view(view, scene)
