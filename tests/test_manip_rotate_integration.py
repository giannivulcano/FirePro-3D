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


def _post_mouse(view, etype, scene_pos, button=Qt.MouseButton.LeftButton,
                buttons=None, modifiers=Qt.KeyboardModifier.NoModifier):
    app = QApplication.instance()
    vp = view.viewport()
    p = view.mapFromScene(scene_pos)
    if buttons is None:
        buttons = (Qt.MouseButton.NoButton
                   if etype == QEvent.Type.MouseButtonRelease
                   else Qt.MouseButton.LeftButton)
    ev = QMouseEvent(etype, p.toPointF(), vp.mapToGlobal(p).toPointF(),
                     button, buttons, modifiers)
    app.sendEvent(vp, ev)
    app.processEvents()


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


# ── Task 11: live gesture / undo / byte-parity / elevation ──────────────────


def test_group_rotate_gesture_rotates_all_and_pipe_tracks_nodes(qapp, scene_and_view):
    """A live rotate gesture on a mixed selection rotates every item about the
    frame centre; a pipe tracks its nodes for free (no manip_rotate of its own).
    """
    scene, view = scene_and_view
    from firepro3d.node import Node
    from firepro3d.pipe import Pipe
    from firepro3d.gridline import GridlineItem
    from firepro3d.manip_math import HandleRole
    import math

    n1 = Node(0, 0, z=0.0)
    n2 = Node(100, 0, z=0.0)
    scene.addItem(n1)
    scene.addItem(n2)
    pipe = Pipe(n1, n2)                 # ctor appends itself to n1.pipes/n2.pipes
    scene.addItem(pipe)
    g = GridlineItem(QPointF(0, 60), QPointF(120, 60), label="A")
    scene.addItem(g)
    for it in (n1, n2, g):
        it.setSelected(True)
    qapp.processEvents()

    manip = _manip(scene)
    assert manip._handles[HandleRole.ROTATE].isVisible()
    knob = manip._handles[HandleRole.ROTATE].scenePos()
    center = manip._rect.center()
    n1_0 = QPointF(n1.scenePos())

    # Rotate the knob vector 90° screen-CW (== Y-up +90) about the frame centre.
    r = QPointF(knob.x() - center.x(), knob.y() - center.y())
    rad = math.radians(-90.0)
    knob2 = QPointF(center.x() + r.x() * math.cos(rad) - r.y() * math.sin(rad),
                    center.y() + r.x() * math.sin(rad) + r.y() * math.cos(rad))

    _post_mouse(view, QEvent.Type.MouseButtonPress, knob)
    _post_mouse(view, QEvent.Type.MouseMove, knob2)
    _post_mouse(view, QEvent.Type.MouseButtonRelease, knob2)

    # n1 actually moved (it sat off the pivot).
    assert (abs(n1.scenePos().x() - n1_0.x()) > 1.0
            or abs(n1.scenePos().y() - n1_0.y()) > 1.0)
    # The pipe endpoints follow the nodes through Node.itemChange.
    assert pipe.line().p1() == n1.scenePos()
    assert pipe.line().p2() == n2.scenePos()


def test_group_rotate_one_undo_restores_all(qapp, scene_and_view):
    """One baked rotate gesture = one undo step; a single undo restores every
    item's coordinates to their pre-rotate values."""
    scene, view = scene_and_view
    from firepro3d.construction_geometry import LineItem

    a = LineItem(QPointF(0, 0), QPointF(80, 0))
    b = LineItem(QPointF(0, 40), QPointF(80, 40))
    scene.addItem(a)
    scene.addItem(b)
    scene._draw_lines.append(a)
    scene._draw_lines.append(b)
    a0 = (QPointF(a._pt1), QPointF(a._pt2))
    b0 = (QPointF(b._pt1), QPointF(b._pt2))

    # Baseline snapshot so undo has a prior state to restore to (the bake's
    # commit_hook == push_undo_state pushes the post-rotate state).
    scene.push_undo_state()

    manip = _manip(scene)
    a.setSelected(True)
    b.setSelected(True)
    qapp.processEvents()
    manip._bake_rotate([a, b], 90.0, manip._rect.center())

    scene.undo()

    # After restore the scene rebuilds items; grab the current LineItems.
    assert len(scene._draw_lines) == 2
    la, lb = scene._draw_lines[0], scene._draw_lines[1]
    got = sorted([la, lb], key=lambda ln: ln._pt1.y())
    ra, rb = got[0], got[1]
    # Assert ALL four coordinates restore (a 90° rotation swaps x/y, so a
    # partial x-only/y-only check could false-green).
    for got_ln, orig in ((ra, a0), (rb, b0)):
        assert abs(got_ln._pt1.x() - orig[0].x()) < 1e-6
        assert abs(got_ln._pt1.y() - orig[0].y()) < 1e-6
        assert abs(got_ln._pt2.x() - orig[1].x()) < 1e-6
        assert abs(got_ln._pt2.y() - orig[1].y()) < 1e-6


def test_rotate_noop_is_byte_identical(qapp, scene_and_view):
    """A rotate gesture with no drag (press then release) bakes nothing, so the
    serialized network is byte-identical before and after."""
    scene, view = scene_and_view
    from firepro3d.construction_geometry import RegularPolygonItem
    from firepro3d.manip_math import HandleRole

    rp = RegularPolygonItem(QPointF(50, 20), sides=6, radius_mm=30.0)
    scene.addItem(rp)
    scene._draw_polygons.append(rp)
    rp.setSelected(True)
    qapp.processEvents()

    before = json.dumps(scene._capture_network(), sort_keys=True)
    manip = _manip(scene)
    knob = manip._handles[HandleRole.ROTATE].scenePos()
    _post_mouse(view, QEvent.Type.MouseButtonPress, knob)
    _post_mouse(view, QEvent.Type.MouseButtonRelease, knob)
    after = json.dumps(scene._capture_network(), sort_keys=True)
    assert after == before


def test_rotate_preserves_elevation(qapp, scene_and_view):
    """2D rotation is plane-only: node z_pos and floor-slab boundary offsets are
    untouched."""
    scene, view = scene_and_view
    from firepro3d.node import Node
    from firepro3d.floor_slab import FloorSlab

    n = Node(40, 0, z=3000.0)
    f = FloorSlab(points=[QPointF(0, 0), QPointF(200, 0), QPointF(200, 120)])
    scene.addItem(n)
    scene.addItem(f)
    z_n = n.z_pos
    f_top0, f_bot0 = f._top_offset_mm, f._bottom_offset_mm

    manip = _manip(scene)
    manip._bake_rotate([n], 37.0, QPointF(0, 0))
    manip._bake_rotate([f], 37.0, QPointF(0, 0))

    assert n.z_pos == z_n
    assert f._top_offset_mm == f_top0 and f._bottom_offset_mm == f_bot0
