"""No rotate knob anywhere (user 2026-09-23: removed app-wide).

The selection manipulator's rotate knob (stalk + circle above the frame) is
gone for every item class and every selection, single and multi. Per-item
``manip_rotate`` stays for the future Rotate transform. Observable checks:
no handle host carries a rotate role / gesture, and the spot where the knob
used to sit (a stem-length above the frame's top-mid) is not a manipulator hit.
"""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtTest import QTest

import firepro3d.manip_math as mm
from firepro3d.model_space import Model_Space
from firepro3d.level_manager import LevelManager
from firepro3d.scale_manager import ScaleManager
from firepro3d.model_view import Model_View
from firepro3d.selection_manipulator import SelectionManipulator

_OLD_KNOB_STEM_PX = 28.0     # where the retired knob sat above the top-mid


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


def _manip(scene) -> SelectionManipulator:
    return next(i for i in scene.items()
                if isinstance(i, SelectionManipulator))


def _items():
    from firepro3d.geometry_2d import (
        LineItem, RectangleItem, CircleItem, ArcItem, EllipseItem,
        PolylineItem,
    )
    from firepro3d.wall import WallSegment
    from firepro3d.gridline import GridlineItem
    from firepro3d.text_item import TextItem, TextAnnotationData
    from firepro3d.room import Room
    pl = PolylineItem(QPointF(0, 0))
    pl.append_point(QPointF(50, 50))
    pl.append_point(QPointF(90, 0))
    return [
        LineItem(QPointF(0, 0), QPointF(100, 0)),
        RectangleItem(QPointF(0, 0), QPointF(100, 50)),
        CircleItem(QPointF(50, 50), 40.0),
        ArcItem(QPointF(50, 50), 40.0, 0.0, 90.0),
        EllipseItem(QPointF(50, 50), 60.0, 30.0, 0.0),
        pl,
        WallSegment(QPointF(0, 100), QPointF(200, 100)),
        GridlineItem(QPointF(0, 150), QPointF(200, 150), label="A"),
        TextItem(TextAnnotationData(text="Hi", x=0, y=200)),
        Room(boundary=[QPointF(0, 0), QPointF(100, 0), QPointF(100, 80)]),
    ]


def test_handle_role_has_no_rotate():
    assert not hasattr(mm.HandleRole, "ROTATE")


def test_no_rotate_handle_for_single_and_multi_selection(qapp, scene_and_view):
    scene, view = scene_and_view
    items = _items()
    for it in items:
        scene.addItem(it)
    m = _manip(scene)
    for sel in [[it] for it in items] + [items]:
        scene.clearSelection()
        for it in sel:
            it.setSelected(True)
        qapp.processEvents()
        names = [type(it).__name__ for it in sel]
        for host in m.childItems():
            h = getattr(host, "handle", None)
            if h is None or not host.isVisible():
                continue
            assert getattr(h.role, "name", "") != "ROTATE", names
            assert h.gesture_mode != "rotate", names
        # The retired knob's spot (stem-length above the frame top-mid) is
        # empty: a press there is no longer routed to the manipulator.
        r = m._rect
        top_mid = view.mapFromScene(QPointF(r.center().x(), r.top()))
        knob_vp = top_mid.toPointF() - QPointF(0.0, _OLD_KNOB_STEM_PX)
        knob_scene = view.mapToScene(knob_vp.toPoint())
        assert m.hit_test(knob_scene) is False, names
