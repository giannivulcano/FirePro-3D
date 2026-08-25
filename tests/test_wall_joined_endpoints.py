"""tests/test_wall_joined_endpoints.py — joined wall endpoint propagation.

Task 10: dragging a shared endpoint grip moves ALL walls whose endpoint is
coincident with the drag start position, keeping polyline-drawn walls joined.
Proximity-based; no stored connectivity; no serialization change.

Grip-arming strategy (documented):
    Posted MouseButtonPress at an exact scene coordinate cannot reliably arm
    the grip in a headless test because:

    1. The shown_model_view fixture centers the 800×600 viewport on (0,0),
       making only the range ±400 × ±300 mm visible.  Walls placed far from
       that range (e.g., the task-spec example at (1000,0)) are off-screen and
       the posted press never reaches the viewport.

    2. Even for on-screen grips, posting QMouseEvent(MouseMove) to the
       viewport does not reach scene.mouseMoveEvent in PyQt6 — the
       QGraphicsView event filter intercepts viewport events differently from
       what sendEvent/postEvent deliver (confirmed experimentally: grip_item
       and grip_dragging stay unchanged after the posted move, and a.pt2 does
       not change).  QGraphicsSceneMouseEvent cannot be instantiated directly
       in PyQt6.

    Resolution — arm directly, call the real propagation method:
        Arm: set scene._grip_item / _grip_index / _grip_dragging = True
        Drive: call scene._drag_grip_to(to_pos) — this is exactly the call
               that scene.mouseMoveEvent makes when grip_dragging is True.

    This exercises the full propagation path (_drag_grip_to →
    _propagate_wall_endpoint → apply_grip on coincident walls) without
    bypassing it.  It does NOT call apply_grip directly on the bystander
    walls, which the task spec prohibits.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from firepro3d.wall import WallSegment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _arm_and_drag(scene, grip_item, grip_index, to_scene):
    """Arm grip state and drive _drag_grip_to — the real propagation path.

    Arms: scene._grip_item, _grip_index, _grip_dragging
    Drives: scene._drag_grip_to(to_scene) — exactly what mouseMoveEvent calls

    See module docstring for why posted viewport events are not used.
    """
    scene._grip_item = grip_item
    scene._grip_index = grip_index
    scene._grip_dragging = True
    scene._drag_grip_to(to_scene)
    # Simulate the release commit (grip flag cleanup + undo snapshot).
    scene._grip_dragging = False
    scene._grip_item = None
    scene._grip_index = -1


def _two_joined_walls(scene):
    """Two walls sharing endpoint (0, 0).

    Wall a: (-200, 0) → (0, 0)   grip index 1 is the shared vertex
    Wall b: (0, 0)   → (0, 200)  grip index 0 is the shared vertex
    """
    a = WallSegment(QPointF(-200, 0), QPointF(0, 0), thickness_mm=100.0)
    b = WallSegment(QPointF(0, 0), QPointF(0, 200), thickness_mm=100.0)
    for w in (a, b):
        scene.addItem(w)
        scene._walls.append(w)
    return a, b


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_dragging_shared_endpoint_moves_both_walls(qapp, shown_model_view):
    """Dragging the shared endpoint of two joined walls moves both endpoints."""
    view, scene = shown_model_view
    a, b = _two_joined_walls(scene)

    scene.set_mode("select")
    a.setSelected(True)

    # Drag wall-a's grip-1 (pt2, the shared (0,0) vertex) to (50, -50).
    _arm_and_drag(scene, grip_item=a, grip_index=1, to_scene=QPointF(50, -50))

    # The dragged wall's endpoint must have moved.
    assert a.pt2 != QPointF(0, 0), "a.pt2 should have moved from the origin"

    # The coincident endpoint on wall b must have followed.
    assert b.pt1 != QPointF(0, 0), "b.pt1 (coincident with a.pt2) should have moved"

    # Both endpoints must still coincide (the join must be preserved).
    assert abs(a.pt2.x() - b.pt1.x()) < 1e-6, "a.pt2 and b.pt1 x must match"
    assert abs(a.pt2.y() - b.pt1.y()) < 1e-6, "a.pt2 and b.pt1 y must match"


def test_three_walls_at_vertex_all_follow(qapp, shown_model_view):
    """When three walls share a vertex, dragging any one endpoint moves all three."""
    view, scene = shown_model_view
    a, b = _two_joined_walls(scene)

    # Third wall also starts at the shared vertex (0, 0).
    c = WallSegment(QPointF(0, 0), QPointF(200, 100), thickness_mm=100.0)
    scene.addItem(c)
    scene._walls.append(c)

    scene.set_mode("select")
    a.setSelected(True)

    # Drag a's grip-1 (the shared (0,0) vertex) to (-30, 80).
    _arm_and_drag(scene, grip_item=a, grip_index=1, to_scene=QPointF(-30, 80))

    # All three shared endpoints must have moved together.
    assert abs(b.pt1.x() - a.pt2.x()) < 1e-6, "b.pt1.x must match a.pt2.x"
    assert abs(b.pt1.y() - a.pt2.y()) < 1e-6, "b.pt1.y must match a.pt2.y"
    assert abs(c.pt1.x() - a.pt2.x()) < 1e-6, "c.pt1.x must match a.pt2.x"
    assert abs(c.pt1.y() - a.pt2.y()) < 1e-6, "c.pt1.y must match a.pt2.y"


def test_non_coincident_endpoint_is_not_moved(qapp, shown_model_view):
    """The non-shared endpoints of connected walls must NOT move."""
    view, scene = shown_model_view
    a, b = _two_joined_walls(scene)

    b_pt2_before = QPointF(b.pt2)   # far end of b — must stay fixed

    scene.set_mode("select")
    a.setSelected(True)

    _arm_and_drag(scene, grip_item=a, grip_index=1, to_scene=QPointF(50, -50))

    # b's far endpoint should be unchanged.
    assert abs(b.pt2.x() - b_pt2_before.x()) < 1e-6, "b.pt2.x must not move"
    assert abs(b.pt2.y() - b_pt2_before.y()) < 1e-6, "b.pt2.y must not move"


def test_isolated_wall_is_not_affected(qapp, shown_model_view):
    """A wall with no coincident neighbours is unaffected by a grip drag elsewhere."""
    view, scene = shown_model_view
    a, b = _two_joined_walls(scene)

    # Isolated wall — far from the shared vertex.
    iso = WallSegment(QPointF(-300, -200), QPointF(-100, -200), thickness_mm=100.0)
    scene.addItem(iso)
    scene._walls.append(iso)

    iso_pt1_before = QPointF(iso.pt1)
    iso_pt2_before = QPointF(iso.pt2)

    scene.set_mode("select")
    a.setSelected(True)

    _arm_and_drag(scene, grip_item=a, grip_index=1, to_scene=QPointF(50, -50))

    # Isolated wall must be entirely unaffected.
    assert abs(iso.pt1.x() - iso_pt1_before.x()) < 1e-6
    assert abs(iso.pt1.y() - iso_pt1_before.y()) < 1e-6
    assert abs(iso.pt2.x() - iso_pt2_before.x()) < 1e-6
    assert abs(iso.pt2.y() - iso_pt2_before.y()) < 1e-6


def test_width_grip_drag_does_not_propagate(qapp, shown_model_view):
    """Dragging a non-endpoint grip (width grip, index 3) must not propagate."""
    view, scene = shown_model_view
    a, b = _two_joined_walls(scene)

    b_pt1_before = QPointF(b.pt1)

    scene.set_mode("select")
    a.setSelected(True)

    # Drag a's width grip (index 3) — should NOT propagate to b.
    _arm_and_drag(scene, grip_item=a, grip_index=3, to_scene=QPointF(-300, 50))

    # b's coincident endpoint must be unaffected (propagation only for indices 0/1).
    assert abs(b.pt1.x() - b_pt1_before.x()) < 1e-6
    assert abs(b.pt1.y() - b_pt1_before.y()) < 1e-6
