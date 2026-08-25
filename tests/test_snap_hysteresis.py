"""Hysteresis: hold current snap unless beaten by margin or higher priority."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsScene
from firepro3d import snap_engine
from firepro3d.snap_engine import SnapEngine, OsnapResult
from firepro3d.construction_geometry import LineItem, CircleItem


def _x(scale=1.0):
    t = QTransform(); t.scale(scale, scale); return t


def test_default_hysteresis_is_3():
    assert snap_engine.SNAP_HYSTERESIS_PX == 3


def test_hold_survives_small_move_toward_other(qapp):
    scene = QGraphicsScene()
    scene.addItem(LineItem(QPointF(0.0, 0.0), QPointF(100.0, 0.0)))    # endpoint A (0,0)
    scene.addItem(LineItem(QPointF(30.0, 0.0), QPointF(200.0, 0.0)))   # endpoint B (30,0)
    eng = SnapEngine()
    held = OsnapResult(point=QPointF(0.0, 0.0), snap_type="endpoint")
    # Cursor at 16: B(30) is 14 away, A(0) is 16 away — B closer by 2px < 3px margin → hold A.
    res = eng.find(QPointF(16.0, 0.0), scene, _x(), held=held)
    assert res is not None and res.point == QPointF(0.0, 0.0)


def test_higher_priority_breaks_hold(qapp):
    scene = QGraphicsScene()
    scene.addItem(LineItem(QPointF(0.0, 0.0), QPointF(100.0, 0.0)))    # endpoint at (0,0)
    eng = SnapEngine()
    # Hold a low-priority 'nearest' near the endpoint; the endpoint (higher prio) must break it.
    held = OsnapResult(point=QPointF(9.0, 0.0), snap_type="nearest")
    res = eng.find(QPointF(1.0, 0.0), scene, _x(), held=held)
    assert res is not None and res.snap_type == "endpoint" and res.point == QPointF(0.0, 0.0)


def test_hold_released_when_cursor_leaves_aperture(qapp):
    scene = QGraphicsScene()
    scene.addItem(LineItem(QPointF(0.0, 0.0), QPointF(100.0, 0.0)))    # endpoint A (0,0)
    scene.addItem(LineItem(QPointF(30.0, 0.0), QPointF(200.0, 0.0)))   # endpoint B (30,0)
    eng = SnapEngine()
    held = OsnapResult(point=QPointF(0.0, 0.0), snap_type="endpoint")
    # Cursor at 30 (right on B, far outside A's 20px aperture) → B wins, A released.
    res = eng.find(QPointF(30.0, 0.0), scene, _x(), held=held)
    assert res is not None and res.point == QPointF(30.0, 0.0)


def test_held_reemitted_when_nothing_new_but_still_in_aperture(qapp):
    scene = QGraphicsScene()
    scene.addItem(LineItem(QPointF(0.0, 0.0), QPointF(100.0, 0.0)))    # endpoint A (0,0)
    eng = SnapEngine()
    held = OsnapResult(point=QPointF(0.0, 0.0), snap_type="endpoint")
    # Cursor at 5 (within aperture of the endpoint) — best would be that endpoint anyway;
    # this mainly asserts held stays stable. Use a point where only A is snappable.
    res = eng.find(QPointF(5.0, 0.0), scene, _x(), held=held)
    assert res is not None and res.point == QPointF(0.0, 0.0)


# ── Model-level integration: hysteresis wired through get_effective_position ──

def test_model_hysteresis_sticky_then_reset(make_model_space):
    """Two close endpoints: first snap is held on second call (sticky);
    toggle_osnap resets _snap_result to None."""
    from firepro3d.construction_geometry import LineItem
    from PyQt6.QtCore import QPointF

    ms = make_model_space()

    # Add two close endpoints: A at (0,0), B at (18,0) — both within 20px aperture
    ms.addItem(LineItem(QPointF(0.0, 0.0), QPointF(100.0, 0.0)))   # endpoint A
    ms.addItem(LineItem(QPointF(18.0, 0.0), QPointF(200.0, 0.0)))  # endpoint B

    # Enable OSNAP and set a placement mode so snapping is active
    ms._osnap_enabled = True
    ms.set_mode("draw_line")

    # First call: cursor near A (at x=2) — should snap to A (0,0)
    pos1 = ms.get_effective_position(QPointF(2.0, 0.0))
    assert ms._snap_result is not None, "Expected a snap result after first call"
    first_snap_pt = ms._snap_result.point

    # Second call: cursor drifts slightly toward B (at x=10).
    # B(18) is 8px away; A(0) is 10px away; difference=2px < hysteresis(3px) → hold A.
    pos2 = ms.get_effective_position(QPointF(10.0, 0.0))
    assert ms._snap_result is not None, "Expected snap result to be held"
    # The held point should match the first snap (A at 0,0)
    assert ms._snap_result.point == first_snap_pt, (
        f"Expected held snap at {first_snap_pt}, got {ms._snap_result.point}"
    )

    # toggle_osnap() must reset _snap_result
    ms.toggle_osnap(False)
    assert ms._snap_result is None, "toggle_osnap should clear _snap_result"
