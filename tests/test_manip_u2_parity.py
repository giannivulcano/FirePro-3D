"""Posted-event vs slot parity tests for the U2 selection-manipulator refactor.

Proves that driving a resize/rotate gesture via POSTED QMouseEvents (the real
event → _HandleItem → _begin_handle routing) produces byte-identical
serialisation to driving the same gesture at slot level (_begin/_update/_finish),
and that no-op / Esc gestures are byte-identical to the pre-gesture state.

House rules (from prior debugging, enforced here):
  - Drive real widgets with QApplication.sendEvent(view.viewport(), ev).
    QTest.mouseMove is inert here (drives zero handlers).
  - The fixture view is shown and pinned to identity zoom so handles are
    hittable at the expected scene coords (mirrors test_selection_manipulator).
  - Assertions use json.dumps(item.to_dict(), sort_keys=True) byte-equality —
    observable ground truth, not internal constant matching.
"""
from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QPointF, QEvent, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.model_space import Model_Space
from firepro3d.level_manager import LevelManager
from firepro3d.scale_manager import ScaleManager
from firepro3d.model_view import Model_View
from firepro3d.selection_manipulator import SelectionManipulator
from firepro3d.manip_math import HandleRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ser(item) -> str:
    """Byte-stable serialisation of a single geometry item."""
    return json.dumps(item.to_dict(), sort_keys=True)


def _post_mouse(view, etype, scene_pos: QPointF,
                button: Qt.MouseButton = Qt.MouseButton.LeftButton,
                buttons=None,
                modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier):
    """Post a real QMouseEvent to the viewport (mirrors test_selection_manipulator)."""
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


def _manip(scene) -> SelectionManipulator:
    return next(i for i in scene.items() if isinstance(i, SelectionManipulator))


# ---------------------------------------------------------------------------
# Fixture  (mirrors the scene_and_view fixture in test_selection_manipulator)
# ---------------------------------------------------------------------------

@pytest.fixture
def scene_and_view(qapp):
    """A shown Model_View over a Model_Space, pinned to identity zoom.

    At m11==1 centred on (150, 50) all test coordinates map inside the 800×600
    viewport, grips cover only the handle grab-pad scene units, and the snap
    aperture is 20 scene units — the same conditions that let the existing
    handle-press tests route correctly.
    """
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


# ---------------------------------------------------------------------------
# Test 1: no-op press/release is byte-identical (slot-level)
# ---------------------------------------------------------------------------

def test_noop_press_release_byte_identical(qapp, scene_and_view):
    """A _begin / _finish at the same point (below drag threshold) must leave
    the item's serialisation unchanged — no spurious bake, no undo entry."""
    scene, view = scene_and_view
    from firepro3d.construction_geometry import RectangleItem

    rect = RectangleItem(QPointF(100, 100), QPointF(200, 150))
    scene.addItem(rect)
    rect.setSelected(True)
    qapp.processEvents()

    manip = _manip(scene)
    manip.rebake()
    before = ser(rect)

    br = QPointF(200.0, 150.0)
    # Same start + end point → below drag threshold → no geometry change.
    manip._begin("resize", br, br, HandleRole.BOTTOM_RIGHT)
    manip._finish(br, Qt.KeyboardModifier.NoModifier)
    qapp.processEvents()

    assert ser(rect) == before, "No-op resize changed serialisation unexpectedly"


# ---------------------------------------------------------------------------
# Test 2: Esc mid-drag is byte-identical (slot-level)
# ---------------------------------------------------------------------------

def test_escape_mid_drag_byte_identical(qapp, scene_and_view):
    """cancel_drag() mid-resize must restore the item to byte-identical
    pre-gesture state (no bake, no undo geometry churn)."""
    scene, view = scene_and_view
    from firepro3d.construction_geometry import RectangleItem

    rect = RectangleItem(QPointF(100, 100), QPointF(200, 150))
    scene.addItem(rect)
    rect.setSelected(True)
    qapp.processEvents()

    manip = _manip(scene)
    manip.rebake()
    before = ser(rect)

    br = QPointF(200.0, 150.0)
    end = QPointF(br.x() + 50, br.y() + 30)
    screen_past_threshold = QPointF(300.0, 250.0)  # > startDragDistance

    manip._begin("resize", br, br, HandleRole.BOTTOM_RIGHT)
    manip._update(end, Qt.KeyboardModifier.NoModifier, screen_past_threshold)
    manip.cancel_drag()
    qapp.processEvents()

    assert ser(rect) == before, "cancel_drag() did not restore byte-identical state"


# ---------------------------------------------------------------------------
# Test 3: resize posted == slot (parametrized over BOTTOM_RIGHT and RIGHT)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", [HandleRole.BOTTOM_RIGHT, HandleRole.RIGHT])
def test_resize_posted_matches_slot(qapp, scene_and_view, role):
    """A resize driven by POSTED QMouseEvents must produce byte-identical
    serialisation to the same resize driven at slot level (_begin/_update/_finish).

    Two independent RectangleItems with identical initial geometry are used so
    the slot-path and the posted-path operate on separate objects in sequence.
    The posted press must land on the _HandleItem so _begin_handle fires — not
    fall through to selection and clear the item.  Evidence: the posted result
    differs from before-gesture AND equals the slot result.
    """
    scene, view = scene_and_view
    from firepro3d.construction_geometry import RectangleItem

    # ── Item A: slot-level resize ──────────────────────────────────────────
    rect_a = RectangleItem(QPointF(100, 100), QPointF(200, 150))
    scene.addItem(rect_a)
    scene.clearSelection()
    rect_a.setSelected(True)
    qapp.processEvents()

    manip = _manip(scene)
    manip.rebake()

    start = QPointF(200.0, 150.0)
    end   = QPointF(280.0, 210.0)
    # screen_pos must exceed startDragDistance (usually 4 px) from the press
    # so _moved is set; we pass a vector clearly past threshold (50+ px).
    screen_past = QPointF(start.x() + 80, start.y() + 60)

    manip._begin("resize", start, start, role)
    manip._update(end, Qt.KeyboardModifier.NoModifier, screen_past)
    manip._finish(end, Qt.KeyboardModifier.NoModifier)
    qapp.processEvents()

    ser_a = ser(rect_a)

    # Sanity: slot path actually changed the geometry.
    before_a = json.dumps(
        {"type": "draw_rectangle", "x": 100.0, "y": 100.0, "w": 100.0, "h": 50.0,
         "color": rect_a.pen().color().name(), "lineweight": rect_a.pen().widthF(),
         "angle": 0.0, "pivot": None},
        sort_keys=True)
    # (We do NOT assert == before_a; we assert ser_a != before_a below.)

    # ── Item B: posted-event resize ───────────────────────────────────────
    rect_b = RectangleItem(QPointF(100, 100), QPointF(200, 150))
    scene.addItem(rect_b)
    scene.clearSelection()
    rect_b.setSelected(True)
    qapp.processEvents()

    manip.rebake()

    # The handle for this role is positioned at the frame's role corner.
    # At identity zoom (m11==1) mapFromScene is pixel-accurate.
    handle_item = manip._handles[role]
    handle_scene_pos = handle_item.scenePos()

    # POST: press on the handle → _HandleItem.mousePressEvent → _begin_handle
    _post_mouse(view, QEvent.Type.MouseButtonPress, handle_scene_pos)
    # Confirm the gesture started (not a click-through to deselect)
    assert rect_b.isSelected(), "posted press deselected the item before gesture"
    assert manip._mode == "resize", (
        f"posted press did not start resize gesture (mode={manip._mode!r}); "
        "the handle was not hit")

    # POST: move to end point (past threshold in screen space)
    _post_mouse(view, QEvent.Type.MouseMove, end)
    # POST: release
    _post_mouse(view, QEvent.Type.MouseButtonRelease, end)
    qapp.processEvents()

    ser_b = ser(rect_b)

    # Primary assertion: posted path == slot path (byte-identical)
    assert ser_a == ser_b, (
        f"Posted-event resize ({role.name}) differs from slot-level resize.\n"
        f"  slot : {ser_a}\n"
        f"  posted: {ser_b}")

    # Secondary (routing proof): both results differ from the initial geometry
    # (the gesture was not a no-op — the posted events actually routed through
    # the handle, not silently dropped).
    initial = json.dumps({"type": "draw_rectangle",
                          "x": 100.0, "y": 100.0,
                          "w": 100.0, "h": 50.0,
                          "angle": 0.0, "pivot": None,
                          "color": rect_b.pen().color().name(),
                          "lineweight": rect_b.pen().widthF()},
                         sort_keys=True)
    assert ser_b != initial or ser_a != initial, (
        "Both slot and posted paths left geometry unchanged — "
        "the gesture may have been silently dropped (sub-threshold or mis-routed).")


# ---------------------------------------------------------------------------
# Test 4: rotate posted == slot
# ---------------------------------------------------------------------------

def test_rotate_posted_matches_slot(qapp, scene_and_view):
    """A rotate driven by POSTED QMouseEvents must produce byte-identical
    serialisation to the same rotate driven at slot level.

    The posted press must land on the RotateHandle _HandleItem so
    _begin_handle fires a rotate gesture.  Evidence: the posted result differs
    from the pre-gesture state AND equals the slot result.
    """
    scene, view = scene_and_view
    from firepro3d.construction_geometry import RectangleItem
    from firepro3d.selection_manipulator import _ROTATE_OFFSET_PX

    # ── Item A: slot-level rotate ──────────────────────────────────────────
    rect_a = RectangleItem(QPointF(100, 100), QPointF(220, 180))
    scene.addItem(rect_a)
    scene.clearSelection()
    rect_a.setSelected(True)
    qapp.processEvents()

    manip = _manip(scene)
    manip.rebake()

    # Rotate geometry: centre is (160, 140); start due-east of the top-mid,
    # drag westward/upward → clear non-zero angle.
    frame_rect = manip._rect
    rotate_scene_pos = QPointF(frame_rect.center().x(), frame_rect.top() - _ROTATE_OFFSET_PX)

    # Start from the knob scene pos; drag noticeably (>4px screen dist).
    start_rot = QPointF(rotate_scene_pos)
    end_rot   = QPointF(frame_rect.left() - 30, frame_rect.center().y())
    screen_past = QPointF(start_rot.x() - 60, start_rot.y() + 20)

    manip._begin("rotate", start_rot, start_rot, HandleRole.ROTATE)
    manip._update(end_rot, Qt.KeyboardModifier.NoModifier, screen_past)
    manip._finish(end_rot, Qt.KeyboardModifier.NoModifier)
    qapp.processEvents()

    ser_a = ser(rect_a)

    # Sanity: slot path actually rotated.
    assert rect_a._angle != 0.0, "slot-level rotate did not change the angle"

    # ── Item B: posted-event rotate ───────────────────────────────────────
    rect_b = RectangleItem(QPointF(100, 100), QPointF(220, 180))
    scene.addItem(rect_b)
    scene.clearSelection()
    rect_b.setSelected(True)
    qapp.processEvents()

    manip.rebake()

    # The RotateHandle _HandleItem is parented at the frame's top-mid scene point
    # (scenePos()), but the actual knob CIRCLE is drawn _ROTATE_OFFSET_PX above
    # that anchor in device space.  At identity zoom (m11==1) device pixels ==
    # scene units, so the knob's scene coord is (center.x, frame.top - offset).
    # This mirrors test_rotate_knob_press_starts_rotation_via_gate exactly.
    frame_rect_b = manip._rect
    knob_scene_pos = QPointF(frame_rect_b.center().x(),
                             frame_rect_b.top() - _ROTATE_OFFSET_PX)

    # POST: press on the knob → _HandleItem.mousePressEvent → _begin_handle("rotate")
    _post_mouse(view, QEvent.Type.MouseButtonPress, knob_scene_pos)
    assert rect_b.isSelected(), "posted knob press deselected the item"
    assert manip._mode == "rotate", (
        f"posted press on rotate knob did not start rotate gesture "
        f"(mode={manip._mode!r}); the knob was not hit")

    # POST: move to end and release (same geometry as slot path)
    _post_mouse(view, QEvent.Type.MouseMove, end_rot)
    _post_mouse(view, QEvent.Type.MouseButtonRelease, end_rot)
    qapp.processEvents()

    ser_b = ser(rect_b)

    # Primary assertion: posted path == slot path (byte-identical)
    assert ser_a == ser_b, (
        f"Posted-event rotate differs from slot-level rotate.\n"
        f"  slot  : {ser_a}\n"
        f"  posted: {ser_b}")

    # Routing proof: both results have a non-zero angle (gesture was real).
    assert rect_b._angle != 0.0, (
        "posted rotate left angle == 0 — the gesture was not routed through "
        "the knob handle (silently no-op'd or mis-hit)")
