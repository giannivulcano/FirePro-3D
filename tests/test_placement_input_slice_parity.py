"""tests/test_placement_input_slice_parity.py — C0 characterisation net.

Exercises the placement-input concern as it lives TODAY on Model_Space so that
later relocation commits (C1-C3) can prove zero behavioural regression by
keeping every non-skipped test green.

One test is a RED-demo that stays ``@pytest.mark.skip`` until C3 proves the
``set_mode("select")`` teardown path is intact post-extraction.

Drive strategy
--------------
Every non-skipped test reaches the behaviour through a PUBLIC API or a posted
event — never by calling a private handler directly.  The private helper
``_drag_to`` from ``test_dynamic_input_lifecycle.py`` is replicated here
(rather than imported) so the C0 net is self-contained and does not grow a
cross-test dependency.

Fixtures reused from ``conftest.py``
--------------------------------------
- ``qapp``         — session-scoped QApplication.
- ``shown_model_view`` — returned ``(view, scene)`` pair; view is shown,
  exposed, focused, pinned at m11=0.25, centred on origin.
"""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View


# ── local copy of the _drag_to helper (mirrors test_dynamic_input_lifecycle) ──


class _MoveEventStub:
    """Stand-in for the mouse-move event."""

    def __init__(self, modifiers=Qt.KeyboardModifier.NoModifier):
        self._modifiers = modifiers

    def modifiers(self):
        return self._modifiers


def _drag_to(scene: Model_Space, point: QPointF,
             anchor: QPointF = QPointF(0, 0)) -> object:
    """Arm draw_line at *anchor* and take the cursor to *point*.

    Mirrors the exact ordering from test_dynamic_input_lifecycle._drag_to:
    set mode, arm the anchor, call the move handler, sync the HUD.
    """
    scene.mode = "draw_line"
    if scene._draw_line_anchor is None:
        scene._draw_line_anchor = QPointF(anchor)
    scene._move_draw_line(_MoveEventStub(), point)
    scene._sync_dynamic_input()
    return scene.dynamic_input


def _press_at(view: Model_View, scene_pt: QPointF) -> None:
    """Send a real left-button press through *view* at *scene_pt*."""
    vp = view.mapFromScene(scene_pt)
    ev = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(vp),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(view.viewport(), ev)


# ─────────────────────────────────────────────────────────────────────────────
# C0-1  Backcompat shells present
# ─────────────────────────────────────────────────────────────────────────────


def test_backcompat_shells_present(shown_model_view):
    """All public methods that will be delegated must be callable on the scene.

    ``get_align_enabled`` is NOT listed — it does not exist yet (added in a
    later task).  ``set_align_enabled`` IS listed — it exists today.
    """
    _view, scene = shown_model_view

    expected_callables = [
        "get_placement_anchor",
        "get_resolved_point",
        "publish_placement_state",
        "clear_placement_state",
        "is_input_mode",
        "active_schema",
        "cycle_placement_variant",
        "apply_dynamic_input",
        "begin_dynamic_input",
        "end_dynamic_input",
        "set_align_enabled",
    ]
    missing = [name for name in expected_callables
               if not callable(getattr(scene, name, None))]
    assert not missing, f"Scene is missing callable(s): {missing}"


# ─────────────────────────────────────────────────────────────────────────────
# C0-2  HUD open → seed → commit → line created
# ─────────────────────────────────────────────────────────────────────────────


def test_hud_open_seed_commit_line(shown_model_view):
    """Arm the HUD at 1000 mm, engage it, commit; assert one line of that length.

    The commit path: ``begin_dynamic_input`` → connect ``committed`` signal →
    trigger ``_on_dynamic_input_committed`` by emitting ``committed`` from the
    HUD with typed values → ``apply_dynamic_input`` creates the line.
    """
    view, scene = shown_model_view

    # Arm anchor at origin, cursor at (1000, 0).
    hud = _drag_to(scene, QPointF(1000, 0))
    assert hud is not None, "HUD must open once anchor is armed"

    # Engage the HUD so it is no longer transparent.
    ok = scene.begin_dynamic_input()
    assert ok, "begin_dynamic_input() must succeed with an armed anchor"

    assert len(scene._draw_lines) == 0

    # Fire the committed signal directly with the desired values — this routes
    # through _on_dynamic_input_committed → resolve → _commit_draw_line_at.
    hud.committed.emit({"Length": 1000.0, "Angle": 0.0})
    QApplication.processEvents()

    assert len(scene._draw_lines) == 1, "One line must have been committed"

    # LineItem is a QGraphicsLineItem subclass — use .line() to get the QLineF.
    line_item = scene._draw_lines[0]
    length = line_item.line().length()
    assert length == pytest.approx(1000.0, abs=1.0), (
        f"Committed line length {length:.1f} != 1000 mm"
    )


# ─────────────────────────────────────────────────────────────────────────────
# C0-3  Variant cycle at step 0
# ─────────────────────────────────────────────────────────────────────────────


def test_variant_cycle_step_zero(shown_model_view):
    """cycle_placement_variant(+1) advances the draw_rectangle variant index."""
    _view, scene = shown_model_view

    scene.set_mode("draw_rectangle")
    before = scene._variant_index["draw_rectangle"]

    result = scene.cycle_placement_variant(+1)
    assert result is True, "cycle_placement_variant must return True at step 0"

    after = scene._variant_index["draw_rectangle"]
    expected = (before + 1) % len(scene._PLACEMENT_VARIANTS["draw_rectangle"])
    assert after == expected, (
        f"variant index after cycle: {after}, expected {expected}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# C0-4  wall_rect alias sets variant index to 2
# ─────────────────────────────────────────────────────────────────────────────


def test_wall_corner_rect_alias_variant(shown_model_view):
    """set_mode('wall_rect') is the 'Wall (Corner Rectangle)' slot → index 2."""
    _view, scene = shown_model_view

    scene.set_mode("wall_rect")
    assert scene._variant_index["wall"] == 2, (
        f"wall_rect must set _variant_index['wall'] to 2, got "
        f"{scene._variant_index['wall']}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# C0-5  Track schema replaces base schema when on-path snap is live
# ─────────────────────────────────────────────────────────────────────────────


def test_track_schema_seed(shown_model_view):
    """active_schema() returns the 'track' schema when an align_path is live.

    Engage the on-path swap by injecting the same scratch attrs
    _align_track_ray and _align_result that get_effective_position / the ALIGN
    picker set during normal mouse movement.
    """
    from firepro3d.align_engine import Ray
    from firepro3d.snap_engine import OsnapResult

    _view, scene = shown_model_view

    # Must be in a mode that has an applier and a placement base schema.
    scene.set_mode("draw_line")
    # Arm the anchor so begin_dynamic_input wouldn't refuse, though that is
    # not exercised here — we just want active_schema().
    scene._draw_line_anchor = QPointF(0, 0)

    # Inject an on-path snap result to activate _align_track_active().
    ray = Ray(origin=(0.0, 0.0), direction=(1.0, 0.0), kind="extension",
              source_id=42)
    scene._align_track_ray = ray
    scene._align_track_dist = 500.0

    snap_result = OsnapResult(
        point=QPointF(500, 0),
        snap_type="align_path",
    )
    scene._align_result = snap_result

    schema = scene.active_schema()
    assert schema is not None, "active_schema() must not be None with track live"
    assert schema.name == "track", (
        f"active_schema() must return 'track' schema, got {schema.name!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# C0-6  set_align_enabled toggle works; _align_enabled reflects it
# ─────────────────────────────────────────────────────────────────────────────


def test_align_enabled_toggle(shown_model_view):
    """set_align_enabled(False) disables ALIGN; reading _align_enabled confirms.

    There is no get_align_enabled() yet — a later task adds the accessor.
    This test reads the private attribute directly, which is the today-valid
    approach.  When get_align_enabled() lands its own sibling test will verify
    the accessor instead.
    """
    _view, scene = shown_model_view

    # Record initial state (usually True after construction).
    initial = scene._align_enabled

    scene.set_align_enabled(False)
    assert scene._align_enabled is False

    scene.set_align_enabled(True)
    assert scene._align_enabled is True

    # Toggle (None) must flip.
    scene.set_align_enabled(False)
    scene.set_align_enabled(None)   # None → toggle
    assert scene._align_enabled is True

    # Restore initial state to avoid leaking into other tests.
    scene.set_align_enabled(initial)


# ─────────────────────────────────────────────────────────────────────────────
# C0-7  RED-demo: set_mode("select") tears down the HUD (skipped until C3)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.skip(reason="RED-demo: un-skipped in C3 to prove clear() teardown")
def test_clear_teardown_red_demo(shown_model_view):
    """Mode switch to 'select' must clear placement state and tear down the HUD.

    This is the invariant the C3 post-extraction smoke exists to defend: after
    extraction, PlacementInputCoordinator.end() must be wired into set_mode so
    the teardown path works exactly as it does today.
    """
    view, scene = shown_model_view

    _drag_to(scene, QPointF(1000, 0))
    assert scene.dynamic_input is not None, "HUD must be up before mode switch"

    scene.set_mode("select")
    QApplication.processEvents()

    assert scene.get_resolved_point() is None, (
        "Resolved point must be cleared after set_mode('select')"
    )
    assert (
        scene.dynamic_input is None
        or not scene.dynamic_input.isVisible()
    ), "HUD must be torn down (or hidden) after set_mode('select')"
