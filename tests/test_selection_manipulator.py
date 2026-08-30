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


def _hud_of(view):
    """The manipulator's live HUD (owned per gesture on ``_hud``)."""
    return _manip(view.scene())._hud


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


def test_group_move_bakes_all_and_one_undo_restores(qapp, scene_and_view):
    scene, view = scene_and_view
    from firepro3d.construction_geometry import LineItem
    items = [LineItem(QPointF(x, 0), QPointF(x + 30, 0)) for x in (0, 60, 120)]
    for it in items:
        scene.addItem(it)
        scene._draw_lines.append(it)   # register in the serialized network
        it.setSelected(True)
    scene.push_undo_state()            # baseline: lines at y=0
    qapp.processEvents()

    def _line_ys():
        return sorted(l.line().p1().y() for l in scene._draw_lines)

    assert _line_ys() == [0.0, 0.0, 0.0]
    # (45, 0) sits in the gap between the first two lines (x 30..60), inside
    # the group frame but >12 px from every endpoint/midpoint grip, so the
    # press drives the manipulator, not a grip-drag on one line.
    _press_move_release(view, QPointF(45, 0), QPointF(45, 80))
    for it in items:
        assert it.transform().isIdentity()          # baked, no held transform
        assert abs(it.line().p1().y() - 80.0) < 2.0
    scene.undo()                       # one undo reverts the whole group move
    qapp.processEvents()
    # _restore_network rebuilds items, so re-read the live network list.
    assert len(scene._draw_lines) == 3
    for y in _line_ys():
        assert abs(y - 0.0) < 1e-6
    for li in scene._draw_lines:
        assert abs(li.line().p2().x() - (li.line().p1().x() + 30.0)) < 1e-6


def test_escape_mid_drag_restores_byte_identical(qapp, scene_and_view):
    scene, view = scene_and_view
    from firepro3d.construction_geometry import LineItem
    item = LineItem(QPointF(100, 100), QPointF(200, 100))
    scene.addItem(item)
    item.setSelected(True)
    qapp.processEvents()
    before = json.dumps(scene._capture_network(), sort_keys=True, default=str)
    _post_mouse(view, QEvent.Type.MouseButtonPress, QPointF(125, 100))
    _post_mouse(view, QEvent.Type.MouseMove, QPointF(125, 180))
    from PyQt6.QtGui import QKeyEvent
    scene.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                  Qt.KeyboardModifier.NoModifier))
    qapp.processEvents()
    after = json.dumps(scene._capture_network(), sort_keys=True, default=str)
    assert before == after
    _post_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(125, 180))  # no dangling drag


def test_shift_mid_drag_is_ortho(qapp, scene_and_view):
    scene, view = scene_and_view
    from firepro3d.construction_geometry import LineItem
    item = LineItem(QPointF(100, 100), QPointF(200, 100))
    scene.addItem(item)
    item.setSelected(True)
    qapp.processEvents()
    _post_mouse(view, QEvent.Type.MouseButtonPress, QPointF(125, 100))
    _post_mouse(view, QEvent.Type.MouseMove, QPointF(195, 115),
                modifiers=Qt.KeyboardModifier.ShiftModifier)
    _post_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(195, 115),
                modifiers=Qt.KeyboardModifier.ShiftModifier)
    assert abs(item.line().p1().y() - 100.0) < 2.0
    assert item.line().p1().x() > 130.0


def test_sprinkler_selection_resolves_to_node(qapp, scene_and_view):
    # rebake() resolves a selected Sprinkler child to its parent Node (same
    # rule as Model_Space.move_items): the Node is wrapped, the Sprinkler is
    # not. Sprinklers set ItemIsSelectable=False in normal use (clicks land on
    # the Node), so we flip the flag just to force the Sprinkler into
    # selectedItems() and exercise the resolution branch directly.
    from PyQt6.QtWidgets import QGraphicsItem
    scene, view = scene_and_view
    from firepro3d.node import Node
    node = Node(100, 100)
    node.add_sprinkler()
    scene.addItem(node)
    qapp.processEvents()
    spr = node.sprinkler
    spr.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    spr.setSelected(True)
    qapp.processEvents()
    assert spr.isSelected()          # precondition: sprinkler is in the selection
    manip = _manip(scene)
    manip.rebake()
    resolved = manip.selection_items()
    assert node in resolved
    assert spr not in resolved


def test_hud_shows_live_move_values_then_returns_inactive(qapp, scene_and_view):
    scene, view = scene_and_view
    from firepro3d.construction_geometry import LineItem
    item = LineItem(QPointF(100, 100), QPointF(200, 100))
    scene.addItem(item)
    item.setSelected(True)
    qapp.processEvents()
    _post_mouse(view, QEvent.Type.MouseButtonPress, QPointF(125, 100))
    _post_mouse(view, QEvent.Type.MouseMove, QPointF(165, 130))
    hud = _hud_of(view)
    assert hud is not None                       # HUD opened for the gesture
    vals = hud.current_values()                  # schema units (uncal: 1==1 mm)
    assert set(("dX", "dY")).issubset(vals)      # move-schema fields present
    assert vals["dX"] > 0                         # dragged right → +dX
    assert abs(vals["dX"] - 40.0) < 2.0
    assert abs(vals["dY"] - (-30.0)) < 2.0        # Y-up: dragged down → -dY
    _post_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(165, 130))
    assert _hud_of(view) is None                  # torn down on release
    manip = _manip(scene)
    assert not manip.is_dragging()


def test_typed_move_commits_exact_and_one_undo(qapp, scene_and_view):
    scene, view = scene_and_view
    from firepro3d.construction_geometry import LineItem
    item = LineItem(QPointF(100, 100), QPointF(200, 100))
    scene.addItem(item)
    scene._draw_lines.append(item)               # register in serialized net
    item.setSelected(True)
    scene.push_undo_state()                       # baseline
    undo_depth0 = len(scene._undo_stack)
    qapp.processEvents()

    x0 = item.line().p1().x()
    y0 = item.line().p1().y()

    _post_mouse(view, QEvent.Type.MouseButtonPress, QPointF(125, 100))
    _post_mouse(view, QEvent.Type.MouseMove, QPointF(130, 100))  # arm gesture
    hud = _hud_of(view)
    assert hud is not None

    # Drive the real engage/commit path: type an exact dX/dY, then accept.
    hud.engage()
    hud.editor("dX").setText("75")
    hud.editor("dY").setText("0")
    hud._accept()                                 # emits committed → _on_hud_committed
    qapp.processEvents()

    # Exact typed move applied (Y-up dY=0 → no vertical move).
    assert abs(item.line().p1().x() - (x0 + 75.0)) < 1e-6
    assert abs(item.line().p1().y() - y0) < 1e-6
    assert item.transform().isIdentity()          # baked, no held transform
    # Exactly one new undo entry for the gesture.
    assert len(scene._undo_stack) == undo_depth0 + 1
    # HUD torn down, gesture over.
    assert _hud_of(view) is None
    assert not _manip(scene).is_dragging()


# ── Task 5: resize handles + rotate knob (capability-gated) ─────────────────

def test_rect_shows_8_handles_and_knob(qapp, scene_and_view):
    scene, view = scene_and_view
    from firepro3d.construction_geometry import RectangleItem
    r = RectangleItem(QPointF(100, 100), QPointF(200, 150))
    scene.addItem(r)
    r.setSelected(True)
    qapp.processEvents()
    manip = _manip(scene)
    visible = [h for h in manip.childItems() if h.isVisible()]
    assert len(visible) >= 9   # 8 resize + rotate knob


def test_line_shows_no_resize_handles(qapp, scene_and_view):
    scene, view = scene_and_view
    from firepro3d.construction_geometry import LineItem
    ln = LineItem(QPointF(0, 0), QPointF(100, 0))
    scene.addItem(ln)
    ln.setSelected(True)
    qapp.processEvents()
    manip = _manip(scene)
    visible = [h for h in manip.childItems() if h.isVisible()]
    assert len(visible) == 0   # parametric line: frame + its own grips only


def test_rotate_gesture_bakes_angle_no_transform(qapp, scene_and_view):
    scene, view = scene_and_view
    from firepro3d.construction_geometry import RectangleItem
    from firepro3d.manip_math import HandleRole
    r = RectangleItem(QPointF(100, 100), QPointF(200, 150))
    scene.addItem(r)
    r.setSelected(True)
    qapp.processEvents()
    manip = _manip(scene)
    # Drive the manipulator API directly (adapted to the ported signatures).
    # Centre is (150, 125); start due-east, drag to due-north → ~90° CCW,
    # Shift snaps the absolute angle to 15°.
    manip._begin("rotate", QPointF(200, 125), QPointF(200, 125), HandleRole.ROTATE)
    manip._update(QPointF(150, 25), Qt.KeyboardModifier.ShiftModifier,
                  QPointF(150, 25))
    manip._finish(QPointF(150, 25), Qt.KeyboardModifier.ShiftModifier)
    qapp.processEvents()
    assert r._angle % 15.0 == 0.0 and r._angle != 0.0
    assert r.rotation() == 0.0            # baked-at-rest: no held Qt transform


def test_resize_gesture_bakes_scale_no_transform(qapp, scene_and_view):
    scene, view = scene_and_view
    from firepro3d.construction_geometry import RectangleItem
    from firepro3d.manip_math import HandleRole
    r = RectangleItem(QPointF(100, 100), QPointF(200, 150))
    scene.addItem(r)
    scene._draw_rects.append(r)
    r.setSelected(True)
    qapp.processEvents()
    manip = _manip(scene)
    # Drag the bottom-right handle from (200,150) out to (300,200): the rect's
    # width/height should grow, anchored at the top-left (100,100).
    manip._begin("resize", QPointF(200, 150), QPointF(200, 150),
                 HandleRole.BOTTOM_RIGHT)
    manip._update(QPointF(300, 200), Qt.KeyboardModifier.NoModifier,
                  QPointF(300, 200))
    manip._finish(QPointF(300, 200), Qt.KeyboardModifier.NoModifier)
    qapp.processEvents()
    assert r.transform().isIdentity()                 # baked, no held transform
    assert abs(r.rect().left() - 100.0) < 2.0         # TL anchor held
    assert abs(r.rect().top() - 100.0) < 2.0
    assert r.rect().width() > 120.0                    # grew from 100 wide
    assert r.rect().height() > 60.0                    # grew from 50 tall


def test_scene_clear_then_press_self_heals(qapp, scene_and_view):
    """Regression (live smoke 2026-08-30): a scene clear (load/new/undo restore)
    deletes the manipulator's C++ object. The next press read at the top of
    Model_Space.mousePressEvent must self-heal, not raise 'wrapped C/C++ object
    ... has been deleted' — which broke EVERY click, placement included."""
    from PyQt6 import sip
    scene, view = scene_and_view
    m0 = scene._manipulator
    scene.clear()                         # simulate a load/new reset
    assert sip.isdeleted(m0)              # C++ object is gone
    # a press must NOT raise and must restore a live manipulator
    _post_mouse(view, QEvent.Type.MouseButtonPress, QPointF(50, 50))
    _post_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(50, 50))
    assert not sip.isdeleted(scene._live_manip())
