"""Interaction tests for the SelectionManipulator (model scene)."""
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
    """A shown Model_View over a Model_Space, pinned to identity zoom.

    The transform pin matters: the auto-fit-on-show zoom (m11 ~ 0.02) makes
    posted drags sub-pixel and inflates the 12 px grip tolerance to cover
    entire items.  At m11 == 1 centred on (150, 50) all test coordinates map
    inside the 800x600 viewport, grips cover only 12 scene units, and the
    snap aperture is 20 scene units.
    """
    scene = Model_Space()
    scene._level_manager = LevelManager()      # seeds Level 1 (elevation 0.0)
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


def _press_move_release(view, p0, p1, modifiers=Qt.KeyboardModifier.NoModifier):
    _post_mouse(view, QEvent.Type.MouseButtonPress, p0, modifiers=modifiers)
    _post_mouse(view, QEvent.Type.MouseMove, p1, modifiers=modifiers)
    _post_mouse(view, QEvent.Type.MouseButtonRelease, p1, modifiers=modifiers)


def _manip(scene):
    return next(i for i in scene.items()
                if isinstance(i, SelectionManipulator))


def test_manipulator_attached_once_per_scene(qapp, scene_and_view):
    scene, view = scene_and_view
    manips = [i for i in scene.items() if isinstance(i, SelectionManipulator)]
    assert len(manips) == 1


def test_frame_appears_on_selection_and_hides_on_clear(qapp, scene_and_view):
    scene, view = scene_and_view
    from firepro3d.construction_geometry import LineItem
    item = LineItem(QPointF(0, 0), QPointF(100, 0))
    scene.addItem(item)
    manip = _manip(scene)
    assert not manip.isVisible()
    item.setSelected(True)
    qapp.processEvents()
    assert manip.isVisible()
    scene.clearSelection()
    qapp.processEvents()
    assert not manip.isVisible()


def test_interior_drag_moves_item_baked(qapp, scene_and_view):
    scene, view = scene_and_view
    from firepro3d.construction_geometry import LineItem
    item = LineItem(QPointF(100, 100), QPointF(200, 100))
    scene.addItem(item)
    item.setSelected(True)
    qapp.processEvents()
    # (125, 100) is inside the frame but clear of the endpoint/midpoint grips
    # (12 px tolerance) so the press exercises the manipulator, not grip-drag.
    _press_move_release(view, QPointF(125, 100), QPointF(125, 160))
    assert item.transform().isIdentity()          # baked, no held transform
    assert abs(item.line().p1().y() - 160.0) < 2.0  # snap may adjust slightly


def test_noop_press_release_is_byte_identical(qapp, scene_and_view):
    scene, view = scene_and_view
    from firepro3d.construction_geometry import LineItem
    item = LineItem(QPointF(100, 100), QPointF(200, 100))
    scene.addItem(item)
    item.setSelected(True)
    qapp.processEvents()
    before = json.dumps(scene._capture_network(), sort_keys=True, default=str)
    _press_move_release(view, QPointF(125, 100), QPointF(125, 100))
    after = json.dumps(scene._capture_network(), sort_keys=True, default=str)
    assert before == after


def test_click_through_selects_item_under_frame(qapp, scene_and_view):
    scene, view = scene_and_view
    from firepro3d.construction_geometry import LineItem
    # Diagonal `a` gives the frame real height, so (100, 40) is inside the
    # frame yet off a's own shape (a passes through (100, 20)) and on b.
    a = LineItem(QPointF(0, 0), QPointF(300, 60))
    b = LineItem(QPointF(100, -50), QPointF(100, 50))
    scene.addItem(a)
    scene.addItem(b)
    a.setSelected(True)
    qapp.processEvents()
    _press_move_release(view, QPointF(100, 40), QPointF(100, 40))
    qapp.processEvents()
    assert b.isSelected() and not a.isSelected()
