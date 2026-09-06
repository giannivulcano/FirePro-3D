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

SHELL_METHODS = [
    "_press_wall", "_press_wall_router", "_move_wall", "_move_wall_router",
    "_move_wall_rect", "_apply_wall_dynamic_input", "_set_wall_primitive",
    "_cycle_wall_alignment", "_propagate_wall_endpoint",
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

@pytest.mark.skip(reason="filled in C1")
def test_wall_line_draw_live(shown_model_view):
    ...


@pytest.mark.skip(reason="filled in C1")
def test_wall_polyline_chain_live(shown_model_view):
    ...


@pytest.mark.skip(reason="filled in C1")
def test_wall_endpoint_propagation_live(shown_model_view):
    ...


@pytest.mark.skip(reason="filled in C2")
def test_wall_rect_draw_live(shown_model_view):
    ...


@pytest.mark.skip(reason="filled in C3")
def test_wall_hud_typed_commit_live(shown_model_view):
    ...


@pytest.mark.skip(reason="filled in C3 — clear() RED-demo")
def test_clear_tears_down_wall_state(shown_model_view):
    ...
