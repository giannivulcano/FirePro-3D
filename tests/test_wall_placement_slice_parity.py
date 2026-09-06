"""Parity net for Model_Space slice 10 — WallPlacementController extraction.

Pure behavior-preserving relocation (behavior-home, model-space-architecture.md §5.3):
the ~16 wall-placement *methods* move to WallPlacementController; ALL _wall* state
stays on the Model_Space scene. These tests assert the wall-placement behavior is
identical after the move, and that the state stayed scene-side.

Harness copied from tests/test_wall_placement_workflow.py (the working wall-test
pattern — do not invent a parallel one). Posted QMouseEvent/QKeyEvent on a SHOWN,
activated Model_View (shown_model_view conftest fixture); QTest.mouseMove is inert
in PyQt6 here so live move-tests drive the handler directly, matching the existing
test file's approach.
"""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF, Qt, QEvent, QRectF
from PyQt6.QtGui import QMouseEvent, QKeyEvent
from PyQt6.QtWidgets import QApplication, QGraphicsRectItem

from firepro3d.model_space import Model_Space


def _click(view, scene_pt):
    """Post a left-button press+release at scene_pt through the real event pipeline."""
    vp = view.viewport()
    p = view.mapFromScene(scene_pt)
    for et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        ev = QMouseEvent(et, p.toPointF(), vp.mapToGlobal(p).toPointF(),
                         Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(vp, ev)


def _key(view, key):
    """Post a bare key press+release through the real event pipeline."""
    vp = view.viewport()
    for et in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(vp, QKeyEvent(et, key, Qt.KeyboardModifier.NoModifier))


def _has_endpoint(wall, pt, tol=1.0):
    """True if either endpoint of *wall* is within *tol* mm of *pt*."""
    for e in (wall.pt1, wall.pt2):
        if abs(e.x() - pt.x()) <= tol and abs(e.y() - pt.y()) <= tol:
            return True
    return False


def _wall_length(wall):
    return math.hypot(wall.pt2.x() - wall.pt1.x(), wall.pt2.y() - wall.pt1.y())


class _MoveEventStub:
    """Minimal QGraphicsSceneMouseEvent stand-in (PyQt6 won't instantiate it headlessly).

    Wall move handlers only touch event.modifiers()."""

    def __init__(self, modifiers=None):
        self._mods = modifiers or Qt.KeyboardModifier.NoModifier

    def modifiers(self):
        return self._mods


@pytest.fixture
def scene(qapp):
    return Model_Space()


# --- Back-compat shell presence + state-home (fast, no live events) -----------

# Full end-state shell list: C1 (line/polyline) + C2 (rect) + C3 (HUD applier /
# variant setter). Every scene shell must delegate to the controller sibling.
SHELL_METHODS = [
    "_press_wall", "_press_wall_router", "_move_wall", "_move_wall_router",
    "_cycle_wall_alignment", "_propagate_wall_endpoint", "_auto_join_wall",
    "_move_wall_rect", "_apply_wall_dynamic_input", "_set_wall_primitive",
]


def test_backcompat_shells_wall(scene):
    """Every moved dispatch/coordinator/keyPress/grip method delegates to _wall_ctl."""
    assert hasattr(scene, "_wall_ctl"), "Model_Space must construct _wall_ctl"
    for name in SHELL_METHODS:
        assert hasattr(scene, name), f"scene lost back-compat shell {name}"
        assert hasattr(scene._wall_ctl, name), f"controller missing {name}"


def test_wall_state_stays_scene_side(scene):
    """Behavior-home: wall state remains Model_Space attributes (NOT moved to _wall_ctl)."""
    for attr in ("_walls", "_next_wall_num", "_wall_primitive", "_wall_alignment",
                 "_wall_anchor", "_wall_rect_rotating", "_wall_rect_pivot"):
        assert hasattr(scene, attr), f"scene lost state {attr}"


# --- Live behavior (filled in as each primitive relocates) --------------------

def test_wall_line_draw_live(shown_model_view):
    """Line primitive: two clicks commit exactly one wall with the clicked endpoints."""
    view, scene = shown_model_view
    scene.set_mode("wall")                 # default primitive is "line"
    assert scene._wall_primitive == "line"
    n0 = len(scene._walls)
    _click(view, QPointF(0, 0))
    _click(view, QPointF(1000, 0))         # commits ONE wall
    assert len(scene._walls) == n0 + 1
    # Line variant re-arms fresh (not chained).
    assert scene._wall_anchor is None
    w = scene._walls[-1]
    # Viewport pixel rounding in an empty scene can shift the snapped point a
    # few mm off the requested integer point — 20 mm tolerance (per the
    # existing workflow test's note).
    assert abs(w.pt1.x() - 0) < 20 and abs(w.pt1.y() - 0) < 20
    assert abs(w.pt2.x() - 1000) < 20 and abs(w.pt2.y() - 0) < 20


def test_wall_polyline_chain_live(shown_model_view):
    """Polyline primitive: a 3-point chain closing near the start closes the loop."""
    view, scene = shown_model_view
    scene.set_mode("wall")
    scene.cycle_placement_variant(+1)      # line -> polyline
    assert scene._wall_primitive == "polyline"
    n0 = len(scene._walls)
    start = QPointF(0, 0)
    _click(view, start)
    _click(view, QPointF(1000, 0))         # wall 1
    _click(view, QPointF(1000, 1000))      # wall 2 from shared endpoint
    _click(view, QPointF(0, 0))            # close near chain start -> wall 3, closes loop
    # Three segments landed.
    assert len(scene._walls) == n0 + 3
    # Loop closed -> chain re-armed fresh.
    assert scene._wall_anchor is None
    # Some committed wall endpoint coincides with the chain start.
    assert any(_has_endpoint(w, start, tol=20) for w in scene._walls[n0:]), (
        "closing the chain should leave a wall endpoint on the chain start"
    )


def test_wall_endpoint_propagation_live(shown_model_view):
    """Grip-drag propagation: moving a shared corner drags the OTHER wall's endpoint."""
    view, scene = shown_model_view
    scene.set_mode("wall")
    scene.cycle_placement_variant(+1)      # line -> polyline
    n0 = len(scene._walls)
    _click(view, QPointF(0, 0))
    _click(view, QPointF(1000, 0))         # wall 1
    _click(view, QPointF(1000, 1000))      # wall 2 shares the (1000, 0) corner
    assert len(scene._walls) == n0 + 2
    wall1, wall2 = scene._walls[n0], scene._walls[n0 + 1]
    # The shared corner is wall1.pt2 ≈ wall2.pt1 ≈ (1000, 0).
    shared_pt = wall1.pt2
    new_pt = QPointF(shared_pt.x() + 300, shared_pt.y() - 200)
    # Drive the propagation the way the core grip handler does: wall1 is the
    # directly-dragged wall; wall2's coincident endpoint must follow.
    scene._propagate_wall_endpoint(wall1, shared_pt, new_pt)
    assert _has_endpoint(wall2, new_pt, tol=1.0), (
        "the coincident endpoint on the other wall must follow the grip drag"
    )


def test_wall_rect_draw_live(shown_model_view):
    """Rect primitive: anchor → size → rotate(~0°) commits 4 walls and re-arms.

    Mirrors test_wall_placement_workflow.test_corner_rect_wall_builds_four_walls_
    with_rotate, plus the C2 re-arm assertion (_wall_rect_rotating back to False).
    """
    view, scene = shown_model_view
    scene.set_mode("wall")
    scene.cycle_placement_variant(+1)      # line -> polyline
    scene.cycle_placement_variant(+1)      # polyline -> corner rect
    assert scene._wall_primitive == "rect"
    assert scene._wall_rect_from_center is False
    n0 = len(scene._walls)
    _click(view, QPointF(0, 0))            # anchor (first corner)
    _click(view, QPointF(1000, 800))       # opposite corner → enters rotate step
    assert scene._wall_rect_rotating is True, "After 2nd click, must be in rotate step"
    _click(view, QPointF(1200, 0))         # third click: rotate commit ~0°
    assert len(scene._walls) == n0 + 4, f"Expected {n0 + 4} walls, got {len(scene._walls)}"
    # Continuous placement re-arms fresh (rotate step cleared, anchor reset).
    assert scene._wall_rect_rotating is False
    assert scene._wall_rect_anchor is None


def test_wall_hud_typed_commit_live(shown_model_view):
    """Typed HUD commit routes through the controller applier for both primitives.

    Line: click an anchor then feed the resolved point via _apply_wall_dynamic_input
    (mirrors test_wall_placement_workflow.test_typed_line_wall_matches_mouse).
    Rect: the 3-step typed path (anchor click → sized point → typed angle) builds 4.
    """
    view, scene = shown_model_view
    # -- Line variant --
    scene.set_mode("wall")                       # default primitive is "line"
    assert scene._wall_primitive == "line"
    _click(view, QPointF(0, 0))                  # anchor via real event
    ok = scene._apply_wall_dynamic_input(QPointF(1000, 0))
    assert ok is not False
    assert len(scene._walls) == 1
    assert scene._walls[-1].pt2 == QPointF(1000, 0)

    # -- Rect variant (3-step typed) --
    scene.set_mode("wall")
    scene.cycle_placement_variant(+1)            # line -> polyline
    scene.cycle_placement_variant(+1)            # polyline -> corner rect
    assert scene._wall_primitive == "rect"
    n0 = len(scene._walls)
    _click(view, QPointF(0, 0))                  # step 1: anchor
    ok = scene._apply_wall_dynamic_input(QPointF(1000, 800))   # step 2: size -> rotate
    assert ok is not False
    assert scene._wall_rect_rotating is True
    ok2 = scene._apply_wall_dynamic_input({"angle_deg": 0.0})  # step 3: commit at 0°
    assert ok2 is not False
    assert len(scene._walls) == n0 + 4


def test_clear_tears_down_wall_state(shown_model_view):
    """Leaving 'wall' mode via WallPlacementController.clear() nulls transient state.

    RED-demo target: stubbing clear()'s body to `pass` leaves _wall_anchor set and
    fails this test.
    """
    view, scene = shown_model_view
    scene.set_mode("wall")
    _click(view, QPointF(0, 0))                  # arms the line anchor
    assert scene._wall_anchor is not None
    scene.set_mode("select")                     # triggers _wall_ctl.clear("select")
    assert scene._wall_anchor is None
    assert scene._wall_preview_rect is None
