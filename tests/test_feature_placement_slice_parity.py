"""Parity net for Model_Space slice 11 — FeaturePlacementController extraction.

Pure behavior-preserving relocation (behavior-home, model-space-architecture.md §5.3):
the 11 Feature-placement *methods* move to FeaturePlacementController; ALL _opening_*
state + the shared current_template stay on the Model_Space scene. These tests assert
the opening-placement behavior is identical after the move, that the state stayed
scene-side, and that the moved shells delegate to _feature_ctl.

Harness mirrors tests/test_opening_placement.py + tests/test_wall_placement_slice_parity.py
(the working opening/wall test pattern — do not invent a parallel one). Posted
QMouseEvent/QKeyEvent on a SHOWN, activated Model_View (shown_model_view conftest
fixture); QTest.mouseMove is inert in PyQt6 here so live move-tests drive the handler
directly, matching the existing test files' approach.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt, QEvent
from PyQt6.QtGui import QMouseEvent, QKeyEvent
from PyQt6.QtWidgets import QApplication

from firepro3d.model_space import Model_Space
from firepro3d.wall import WallSegment
from firepro3d.wall_opening import WallOpening
from firepro3d.constants import OPENING_ALIGNMENTS


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
    for et in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(view.viewport(),
            QKeyEvent(et, key, Qt.KeyboardModifier.NoModifier))


@pytest.fixture
def scene(qapp):
    return Model_Space()


# --- Back-compat shell presence + state-home (fast, no live events) -----------

# The dispatch/core-keyPress/test-reached shells that MUST remain on the scene
# and delegate to _feature_ctl. _find_wall_at / _offset_along_wall /
# _clear_opening_ghost move BARE (controller-internal only) and are absent here.
SHELL_METHODS = [
    "_press_opening", "_press_door", "_press_window",
    "_move_opening", "_move_door_window",
    "_cycle_opening_alignment", "_sync_opening_state_to_template",
    "_refresh_opening_ghost",
]


def test_backcompat_shells_feature(scene):
    """Every moved dispatch/core-keyPress/test shell delegates to _feature_ctl."""
    assert hasattr(scene, "_feature_ctl"), "Model_Space must construct _feature_ctl"
    for name in SHELL_METHODS:
        assert hasattr(scene, name), f"scene lost back-compat shell {name}"
        assert hasattr(scene._feature_ctl, name), f"controller missing {name}"


def test_feature_state_stays_scene_side(scene):
    """Behavior-home: opening state remains Model_Space attributes (NOT on _feature_ctl)."""
    for attr in ("_opening_feature_id", "_opening_alignment",
                 "_opening_mirror_hinge", "_opening_mirror_facing",
                 "_opening_ghost"):
        assert hasattr(scene, attr), f"scene lost state {attr}"


# --- Live behavior ------------------------------------------------------------

def test_opening_place_on_wall_live(shown_model_view):
    """Enter opening mode, hover a wall (ghost appears), click → WallOpening lands."""
    view, scene = shown_model_view
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    scene.set_mode("opening", template="door_914")
    # Hover the wall via the controller move handler → the ghost is created.
    scene._move_opening(None, QPointF(400, 0))
    assert scene._opening_ghost is not None
    _click(view, QPointF(400, 0))
    assert len(w.openings) == 1
    op = w.openings[0]
    assert op.feature_id == "door_914"
    # Offset-along matches the click (wall runs +x from origin; click at x=400).
    assert abs(op._offset_along - 400.0) < 20.0


def test_opening_empty_space_rejected_live(shown_model_view):
    """Click well off any wall → no opening created, status prompt emitted."""
    view, scene = shown_model_view
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    scene.set_mode("opening", template="door_914")
    prompts = []
    scene.instructionChanged.connect(prompts.append)
    _click(view, QPointF(500, 500))          # well off the wall (wall lies on y=0)
    assert len(w.openings) == 0
    assert any("wall" in p.lower() for p in prompts), "empty-space click should prompt"


def test_opening_spacebar_cycles_alignment_live(shown_model_view):
    """Space advances _opening_alignment through OPENING_ALIGNMENTS; template follows."""
    view, scene = shown_model_view
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    scene.set_mode("opening", template="door_914")
    a0 = scene._opening_alignment
    _key(view, Qt.Key.Key_Space)
    a1 = scene._opening_alignment
    assert a1 != a0
    assert a1 in OPENING_ALIGNMENTS
    # The shared template mirrors the cycled alignment (sync ran).
    assert isinstance(scene.current_template, WallOpening)
    assert scene.current_template.alignment == a1


def test_opening_arrow_toggles_live(shown_model_view):
    """←/→ toggles _opening_mirror_hinge, ↑/↓ toggles _opening_mirror_facing; placed carries it."""
    view, scene = shown_model_view
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    scene.set_mode("opening", template="door_914")
    assert scene._opening_mirror_hinge is False
    _key(view, Qt.Key.Key_Left)
    assert scene._opening_mirror_hinge is True
    assert scene._opening_mirror_facing is False
    _key(view, Qt.Key.Key_Up)
    assert scene._opening_mirror_facing is True
    _click(view, QPointF(400, 0))
    op = w.openings[0]
    assert op.mirror_hinge is True
    assert op.mirror_facing is True


def test_feature_enter_arms_template_live(shown_model_view):
    """set_mode('opening', template) arms current_template, mirrors _opening_*, emits update.

    Both a WallOpening template and a bare feature-id string are exercised.
    """
    view, scene = shown_model_view
    updates = []
    scene.requestPropertyUpdate.connect(updates.append)
    door = WallOpening(feature_id="door_914")
    scene.set_mode("opening", template=door)
    assert scene.current_template is door
    assert scene._opening_feature_id == door.feature_id
    assert scene._opening_alignment == door.alignment
    assert door in updates
    assert door._scene_ref is scene
    # A bare feature-id string is adopted onto a fresh WallOpening template.
    scene.set_mode("select")                 # leave/re-enter to reset
    scene.set_mode("opening", template="window_900")
    assert isinstance(scene.current_template, WallOpening)
    assert scene.current_template.feature_id == "window_900"
    assert scene._opening_feature_id == "window_900"


def test_clear_tears_down_opening_ghost(shown_model_view):
    """Leaving 'opening' mode via _feature_ctl.clear() removes the live ghost.

    RED-demo target: stubbing clear()'s ghost-teardown to a no-op strands the
    ghost on the canvas and fails this test.
    """
    view, scene = shown_model_view
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    scene.set_mode("opening", template="door_914")
    scene._move_opening(None, QPointF(400, 0))   # arms the ghost
    assert scene._opening_ghost is not None
    scene.set_mode("select")                     # triggers _feature_ctl.clear("select")
    assert scene._opening_ghost is None
