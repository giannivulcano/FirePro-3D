"""tests/test_manip_shift_handle_press.py — Shift+press on a handle starts the gesture.

Bug (user, 2026-09-16; backlog #427): pressing Shift BEFORE clicking a
manipulator handle started an additive/rubber-band select instead of the
constrained (Shift = aspect/ortho/15deg) handle gesture — clicking the handle
first, then Shift, worked.  In select mode the press reached ``_press_select_item``
(additive/band select) and returned, so a Shift-press never fell through to the
manipulator.  The interior-press guard excluded ALL Shift-presses over the frame;
it must exclude only bare-INTERIOR Shift-presses and let a Shift-press on a HANDLE
route to the manipulator.

Handle delivery via posted QMouseEvent is unreliable headless (screen-constant
ItemIgnoresTransformations handles) — the manip suite drives ``_begin`` directly.
So this tests the routing decision (``_manip_press_should_route``) directly, plus
the ``hit_handle`` primitive it relies on.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt

from firepro3d.geometry_2d import RectangleItem

SHIFT = Qt.KeyboardModifier.ShiftModifier
NONE = Qt.KeyboardModifier.NoModifier


def _rect(scene):
    item = RectangleItem(QPointF(0, 0), QPointF(400, 400), "#ffffff", 1.0)
    scene.addItem(item)
    item.setSelected(True)
    return item


def test_hit_handle_true_on_handle_false_in_bare_interior(shown_model_view):
    view, scene = shown_model_view
    view.resetTransform()
    _rect(scene)
    manip = scene._manipulator
    manip.rebake()
    corner = manip._rect.topLeft()          # a resize handle sits here
    bare = QPointF(120, 120)                 # between centre/edge/corner handles
    assert manip.hit_handle(corner) is True
    assert manip.hit_handle(bare) is False
    assert manip.hit_test(bare) is True      # interior still hits the frame


def test_shift_press_on_handle_routes_to_manipulator(shown_model_view):
    view, scene = shown_model_view
    view.resetTransform()
    _rect(scene)
    scene.set_mode("select")
    manip = scene._manipulator
    manip.rebake()
    corner = manip._rect.topLeft()
    bare = QPointF(120, 120)

    # The fix: Shift on a HANDLE routes to the manipulator (constrained gesture).
    assert scene._manip_press_should_route(corner, SHIFT) is True
    # Regression guard: Shift on the bare INTERIOR does NOT route — it falls
    # through to additive select / floor-vertex editing.
    assert scene._manip_press_should_route(bare, SHIFT) is False
    # No-modifier presses route on both handle (gesture) and interior (move).
    assert scene._manip_press_should_route(corner, NONE) is True
    assert scene._manip_press_should_route(bare, NONE) is True
    # A press well outside the frame never routes.
    assert scene._manip_press_should_route(QPointF(5000, 5000), NONE) is False
