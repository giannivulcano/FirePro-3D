"""Integration tests for U1 universal rigid rotate (live gestures + bakes)."""
import json

import pytest
from PyQt6.QtCore import QPointF, Qt, QEvent
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.model_space import Model_Space
from firepro3d.level_manager import LevelManager
from firepro3d.scale_manager import ScaleManager
from firepro3d.model_view import Model_View
from firepro3d.selection_manipulator import SelectionManipulator


@pytest.fixture
def scene_and_view(qapp):
    scene = Model_Space()
    scene._level_manager = LevelManager()
    scene.scale_manager = ScaleManager()
    view = Model_View(scene)
    view.resize(800, 600)
    view.show()
    QTest.qWaitForWindowExposed(view)
    view.resetTransform()
    view.centerOn(150, 50)
    view.setFocus()
    qapp.processEvents()
    yield scene, view
    view.close()


def _manip(scene):
    return next(i for i in scene.items()
               if isinstance(i, SelectionManipulator))


def test_bake_rotate_refreshes_fittings(qapp, scene_and_view):
    """A rotated node's fitting is refreshed by the shared post-bake step."""
    scene, view = scene_and_view
    from firepro3d.node import Node
    calls = {"n": 0}
    n = Node(100, 0, z=0.0)
    scene.addItem(n)

    class _Spy:
        def update(self_inner):
            calls["n"] += 1
    n.fitting = _Spy()

    manip = _manip(scene)
    manip._bake_rotate([n], 90.0, QPointF(0, 0))
    assert calls["n"] >= 1


def test_lone_room_hides_rotate_knob(qapp, scene_and_view):
    scene, view = scene_and_view
    from firepro3d.room import Room
    from firepro3d.manip_math import HandleRole
    r = Room(boundary=[QPointF(0, 0), QPointF(100, 0), QPointF(100, 80)])
    scene.addItem(r)
    r.setSelected(True)
    qapp.processEvents()
    manip = _manip(scene)
    assert not manip._handles[HandleRole.ROTATE].isVisible()


def test_room_in_group_shows_rotate_knob(qapp, scene_and_view):
    scene, view = scene_and_view
    from firepro3d.room import Room
    from firepro3d.construction_geometry import LineItem
    from firepro3d.manip_math import HandleRole
    r = Room(boundary=[QPointF(0, 0), QPointF(100, 0), QPointF(100, 80)])
    ln = LineItem(QPointF(0, 0), QPointF(60, 0))
    scene.addItem(r)
    scene.addItem(ln)
    r.setSelected(True)
    ln.setSelected(True)
    qapp.processEvents()
    manip = _manip(scene)
    assert manip._handles[HandleRole.ROTATE].isVisible()
