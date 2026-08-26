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


@pytest.fixture(autouse=True)
def _pin_aperture():
    # These tests place candidates at fixed screen-pixel distances (e.g. 16px),
    # so pin the aperture they were written against rather than inherit the
    # shipped default (which is user-tunable). conftest restores it afterward.
    snap_engine.SNAP_TOLERANCE_PX = 20
    yield


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


def test_held_reemitted_with_fields_preserved_when_no_candidate(qapp):
    """Held snap is re-emitted (not stripped) when NO candidate is within aperture.

    Geometry math (SNAP_TOLERANCE_PX=20, scale=1 → search_tol=20):
      - held at (0,0); cursor at (12,0) → held distance = 12px < 20px (in aperture)
      - line endpoint at (40,0); cursor distance = 28px > 20px → outside search rect
      - Therefore ctx.best_result is None and the "best is None" branch fires.
    Asserts source_item is preserved (was stripped before the fix).
    """
    scene = QGraphicsScene()
    line = LineItem(QPointF(40.0, 0.0), QPointF(140.0, 0.0))  # nearest endpoint at (40,0)
    scene.addItem(line)
    eng = SnapEngine()
    held = OsnapResult(point=QPointF(0.0, 0.0), snap_type="endpoint", source_item=line)
    # cursor at (12,0): 12px from held (0,0) → in aperture; 28px from (40,0) → outside search rect
    res = eng.find(QPointF(12.0, 0.0), scene, _x(), held=held)
    assert res is not None and res.point == QPointF(0.0, 0.0)
    assert res.source_item is line, "held re-emit must preserve source_item for the trace highlight"


# ── Model-level integration: hysteresis wired through get_effective_position ──

def test_model_hysteresis_sticky_then_reset(make_model_space):
    """Two close endpoints: first snap is held on second call (sticky);
    toggle_snap resets _snap_result to None."""
    from firepro3d.construction_geometry import LineItem
    from PyQt6.QtCore import QPointF

    ms = make_model_space()

    # Add two close endpoints: A at (0,0), B at (18,0) — both within 20px aperture
    ms.addItem(LineItem(QPointF(0.0, 0.0), QPointF(100.0, 0.0)))   # endpoint A
    ms.addItem(LineItem(QPointF(18.0, 0.0), QPointF(200.0, 0.0)))  # endpoint B

    # Enable SNAP and set a placement mode so snapping is active
    ms._snap_enabled = True
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

    # toggle_snap() must reset _snap_result
    ms.toggle_snap(False)
    assert ms._snap_result is None, "toggle_snap should clear _snap_result"
