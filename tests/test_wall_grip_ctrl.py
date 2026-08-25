"""tests/test_wall_grip_ctrl.py — Ctrl angle-snap for both endpoints during grip-drag.

Bug (fixed): Ctrl angle-constrain during grip-drag was gated to ``_grip_index == 0``,
so dragging endpoint index 1 (pt2) on a WallSegment or GridlineItem was never
constrained — the raw snapped position was passed to ``_drag_grip_to`` instead.

Fix: generalised to both endpoint indices for WallSegment / GridlineItem (indices 0
and 1) and for LineItem (indices 0 and 2), anchoring against the *opposite* endpoint.
Other item types (RectangleItem etc.) are not affected.

Test strategy
-------------
``QGraphicsSceneMouseEvent`` cannot be instantiated in PyQt6.  Instead we:
1. Arm the grip state directly (``scene._grip_item``, ``_grip_index``,
   ``_grip_dragging = True``).
2. Construct a ``SimpleNamespace`` stub with ``.scenePos()`` and ``.modifiers()``
   (the only two attributes ``mouseMoveEvent`` reads in the grip-drag block).
3. Monkeypatch ``scene._drag_grip_to`` to capture the ``pos`` argument.
4. Call ``scene.mouseMoveEvent(stub)``.
5. Compare the captured ``pos`` against ``scene._constrain_angle(expected_anchor,
   raw_snapped)`` (Ctrl ON) or the raw snapped position (Ctrl OFF).

This exercises the real ``mouseMoveEvent`` Ctrl-constrain code path without
bypassing it, while avoiding the PyQt6 limitation on synthetic scene events.
"""
from __future__ import annotations

import math
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication

from firepro3d.wall import WallSegment
from firepro3d.gridline import GridlineItem
from firepro3d.construction_geometry import LineItem, RectangleItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _move_stub(scene_pos: QPointF, ctrl: bool = False):
    """Minimal stand-in for QGraphicsSceneMouseEvent with .scenePos()/.modifiers().

    PyQt6 does not allow direct instantiation of QGraphicsSceneMouseEvent.
    Model_Space.mouseMoveEvent only reads these two methods in the grip-drag block.
    """
    mods = (Qt.KeyboardModifier.ControlModifier
            if ctrl else Qt.KeyboardModifier.NoModifier)
    return SimpleNamespace(
        scenePos=lambda: QPointF(scene_pos),
        modifiers=lambda: mods,
        # The is_input_mode guard reads nothing from the event; cursorMoved emits
        # with scenePos() which is already provided.
    )


def _arm_and_collect(scene, grip_item, grip_index, raw_pos: QPointF, ctrl: bool):
    """Arm grip state and call mouseMoveEvent; return the pos passed to _drag_grip_to.

    Monkeypatches _drag_grip_to to capture the argument without running the
    full apply_grip / undo machinery.
    """
    captured = []

    def _fake_drag_grip_to(pos):
        captured.append(QPointF(pos))

    # Arm
    scene._grip_item = grip_item
    scene._grip_index = grip_index
    scene._grip_dragging = True

    # Patch the sink so we see what pos arrived
    original = scene._drag_grip_to
    scene._drag_grip_to = _fake_drag_grip_to

    try:
        scene.mouseMoveEvent(_move_stub(raw_pos, ctrl=ctrl))
    finally:
        # Restore and disarm
        scene._drag_grip_to = original
        scene._grip_dragging = False
        scene._grip_item = None
        scene._grip_index = -1

    assert captured, "_drag_grip_to was not called — grip-drag block not reached"
    return captured[0]


def _make_wall(scene):
    """Horizontal wall: pt1=(0,0), pt2=(500,0)."""
    w = WallSegment(QPointF(0.0, 0.0), QPointF(500.0, 0.0), thickness_mm=100.0)
    scene.addItem(w)
    scene._walls.append(w)
    return w


def _make_gridline(scene):
    """Horizontal gridline: p1=(0,0), p2=(600,0)."""
    gl = GridlineItem(QPointF(0.0, 0.0), QPointF(600.0, 0.0), label="A")
    scene.addItem(gl)
    scene._gridlines.append(gl)
    return gl


def _make_line(scene):
    """LineItem: pt1=(0,0), pt2=(500,0)."""
    li = LineItem(QPointF(0.0, 0.0), QPointF(500.0, 0.0))
    scene.addItem(li)
    scene._draw_lines.append(li)
    return li


# ---------------------------------------------------------------------------
# WallSegment — endpoint indices 0 and 1
# ---------------------------------------------------------------------------

class TestWallGripCtrl:
    """Ctrl angle-snap for WallSegment endpoint grips."""

    def test_index0_ctrl_constrains_against_pt2(self, qapp, shown_model_view):
        """Dragging grip-0 (pt1) with Ctrl constrains against pt2 — existing behaviour."""
        view, scene = shown_model_view
        w = _make_wall(scene)
        scene.set_mode("select")

        # Raw cursor: not aligned to any 45° increment from pt2=(500,0).
        raw = QPointF(100.0, 200.0)

        pos = _arm_and_collect(scene, w, grip_index=0, raw_pos=raw, ctrl=True)

        # pt2 is grips[1] for WallSegment.
        anchor = w.grip_points()[1]
        expected = scene._constrain_angle(anchor, scene.get_effective_position(raw))
        assert pos.x() == pytest.approx(expected.x(), abs=1e-4)
        assert pos.y() == pytest.approx(expected.y(), abs=1e-4)

    def test_index1_ctrl_constrains_against_pt1(self, qapp, shown_model_view):
        """Dragging grip-1 (pt2) with Ctrl should constrain against pt1.

        RED before fix: index-1 drag was not constrained (raw pos passed through).
        GREEN after fix: constrained pos returned.
        """
        view, scene = shown_model_view
        w = _make_wall(scene)
        scene.set_mode("select")

        # Raw cursor: not aligned to any 45° increment from pt1=(0,0).
        raw = QPointF(350.0, 200.0)

        pos = _arm_and_collect(scene, w, grip_index=1, raw_pos=raw, ctrl=True)

        # pt1 is grips[0] for WallSegment.
        anchor = w.grip_points()[0]
        snapped_raw = scene.get_effective_position(raw)
        expected = scene._constrain_angle(anchor, snapped_raw)

        # Constrained pos must differ from raw (otherwise the test is vacuous).
        assert math.hypot(expected.x() - snapped_raw.x(),
                          expected.y() - snapped_raw.y()) > 0.5, (
            "Test is vacuous: raw pos already lies on a constrained angle")

        assert pos.x() == pytest.approx(expected.x(), abs=1e-4)
        assert pos.y() == pytest.approx(expected.y(), abs=1e-4)

    def test_index1_no_ctrl_passes_raw(self, qapp, shown_model_view):
        """Without Ctrl, grip-1 drag passes through the raw snapped position."""
        view, scene = shown_model_view
        w = _make_wall(scene)
        scene.set_mode("select")

        raw = QPointF(350.0, 200.0)
        snapped_raw = scene.get_effective_position(raw)

        pos = _arm_and_collect(scene, w, grip_index=1, raw_pos=raw, ctrl=False)

        assert pos.x() == pytest.approx(snapped_raw.x(), abs=1e-4)
        assert pos.y() == pytest.approx(snapped_raw.y(), abs=1e-4)

    def test_index0_no_ctrl_passes_raw(self, qapp, shown_model_view):
        """Without Ctrl, grip-0 drag passes through the raw snapped position."""
        view, scene = shown_model_view
        w = _make_wall(scene)
        scene.set_mode("select")

        raw = QPointF(100.0, 200.0)
        snapped_raw = scene.get_effective_position(raw)

        pos = _arm_and_collect(scene, w, grip_index=0, raw_pos=raw, ctrl=False)

        assert pos.x() == pytest.approx(snapped_raw.x(), abs=1e-4)
        assert pos.y() == pytest.approx(snapped_raw.y(), abs=1e-4)


# ---------------------------------------------------------------------------
# GridlineItem — endpoint indices 0 (origin) and 1 (far point)
# ---------------------------------------------------------------------------

class TestGridlineGripCtrl:
    """Ctrl angle-snap for GridlineItem endpoint grips."""

    def test_index0_ctrl_constrains_against_far(self, qapp, shown_model_view):
        """Dragging grip-0 (origin) with Ctrl constrains against the far endpoint."""
        view, scene = shown_model_view
        gl = _make_gridline(scene)
        scene.set_mode("select")

        raw = QPointF(50.0, 250.0)
        pos = _arm_and_collect(scene, gl, grip_index=0, raw_pos=raw, ctrl=True)

        anchor = gl.grip_points()[1]  # far endpoint
        expected = scene._constrain_angle(anchor, scene.get_effective_position(raw))
        assert pos.x() == pytest.approx(expected.x(), abs=1e-4)
        assert pos.y() == pytest.approx(expected.y(), abs=1e-4)

    def test_index1_ctrl_constrains_against_origin(self, qapp, shown_model_view):
        """Dragging grip-1 (far end) with Ctrl should constrain against the origin."""
        view, scene = shown_model_view
        gl = _make_gridline(scene)
        scene.set_mode("select")

        raw = QPointF(450.0, 300.0)
        pos = _arm_and_collect(scene, gl, grip_index=1, raw_pos=raw, ctrl=True)

        anchor = gl.grip_points()[0]  # origin endpoint
        snapped_raw = scene.get_effective_position(raw)
        expected = scene._constrain_angle(anchor, snapped_raw)

        assert math.hypot(expected.x() - snapped_raw.x(),
                          expected.y() - snapped_raw.y()) > 0.5, (
            "Test is vacuous: raw pos already lies on a constrained angle")

        assert pos.x() == pytest.approx(expected.x(), abs=1e-4)
        assert pos.y() == pytest.approx(expected.y(), abs=1e-4)


# ---------------------------------------------------------------------------
# LineItem — endpoint indices 0 (pt1) and 2 (pt2); index 1 is midpoint
# ---------------------------------------------------------------------------

class TestLineItemGripCtrl:
    """Ctrl angle-snap for LineItem endpoint grips."""

    def test_index0_ctrl_constrains_against_pt2(self, qapp, shown_model_view):
        """Dragging grip-0 (pt1) with Ctrl constrains against pt2 (grips[2])."""
        view, scene = shown_model_view
        li = _make_line(scene)
        scene.set_mode("select")

        raw = QPointF(80.0, 200.0)
        pos = _arm_and_collect(scene, li, grip_index=0, raw_pos=raw, ctrl=True)

        anchor = li.grip_points()[2]  # pt2 for LineItem
        expected = scene._constrain_angle(anchor, scene.get_effective_position(raw))
        assert pos.x() == pytest.approx(expected.x(), abs=1e-4)
        assert pos.y() == pytest.approx(expected.y(), abs=1e-4)

    def test_index2_ctrl_constrains_against_pt1(self, qapp, shown_model_view):
        """Dragging grip-2 (pt2) with Ctrl constrains against pt1 (grips[0])."""
        view, scene = shown_model_view
        li = _make_line(scene)
        scene.set_mode("select")

        raw = QPointF(400.0, 250.0)
        pos = _arm_and_collect(scene, li, grip_index=2, raw_pos=raw, ctrl=True)

        anchor = li.grip_points()[0]  # pt1 for LineItem
        snapped_raw = scene.get_effective_position(raw)
        expected = scene._constrain_angle(anchor, snapped_raw)

        assert math.hypot(expected.x() - snapped_raw.x(),
                          expected.y() - snapped_raw.y()) > 0.5, (
            "Test is vacuous: raw pos already lies on a constrained angle")

        assert pos.x() == pytest.approx(expected.x(), abs=1e-4)
        assert pos.y() == pytest.approx(expected.y(), abs=1e-4)

    def test_midpoint_grip_index1_not_constrained(self, qapp, shown_model_view):
        """Dragging grip-1 (midpoint) with Ctrl must NOT apply endpoint constraint.

        The midpoint grip translates the whole line; angle-snapping against an
        endpoint anchor makes no geometric sense there.
        """
        view, scene = shown_model_view
        li = _make_line(scene)
        scene.set_mode("select")

        raw = QPointF(300.0, 175.0)
        snapped_raw = scene.get_effective_position(raw)

        pos = _arm_and_collect(scene, li, grip_index=1, raw_pos=raw, ctrl=True)

        # Must be the raw snapped pos, not constrained.
        assert pos.x() == pytest.approx(snapped_raw.x(), abs=1e-4)
        assert pos.y() == pytest.approx(snapped_raw.y(), abs=1e-4)


# ---------------------------------------------------------------------------
# Non-endpoint-pair items — RectangleItem must NOT be angle-constrained
# ---------------------------------------------------------------------------

class TestRectangleGripCtrlNotAffected:
    """Ctrl must NOT angle-constrain RectangleItem grips (not an endpoint-pair type)."""

    def test_rect_grip0_ctrl_passes_raw(self, qapp, shown_model_view):
        """Ctrl + grip-0 on a RectangleItem must pass through the raw snapped pos."""
        view, scene = shown_model_view

        rect = RectangleItem(QPointF(0.0, 0.0), QPointF(400.0, 300.0))
        scene.addItem(rect)
        scene.set_mode("select")

        raw = QPointF(80.0, 200.0)
        snapped_raw = scene.get_effective_position(raw)

        pos = _arm_and_collect(scene, rect, grip_index=0, raw_pos=raw, ctrl=True)

        assert pos.x() == pytest.approx(snapped_raw.x(), abs=1e-4)
        assert pos.y() == pytest.approx(snapped_raw.y(), abs=1e-4)

    def test_rect_grip1_ctrl_passes_raw(self, qapp, shown_model_view):
        """Ctrl + grip-1 on a RectangleItem must pass through the raw snapped pos."""
        view, scene = shown_model_view

        rect = RectangleItem(QPointF(0.0, 0.0), QPointF(400.0, 300.0))
        scene.addItem(rect)
        scene.set_mode("select")

        raw = QPointF(250.0, 50.0)
        snapped_raw = scene.get_effective_position(raw)

        pos = _arm_and_collect(scene, rect, grip_index=1, raw_pos=raw, ctrl=True)

        assert pos.x() == pytest.approx(snapped_raw.x(), abs=1e-4)
        assert pos.y() == pytest.approx(snapped_raw.y(), abs=1e-4)
