"""tests/test_align_track_first_point.py — BUG A: distance-typing at the FIRST point.

Soft-snapping to an ALIGN tracking path at the *first-point* step of a placement
(no first click yet, so the mode's own placement anchor is still None) and typing
a Distance must actually place the first point — it must NOT turn the field red /
refuse the commit.

Ground truth (never a flag flip): after committing Distance along the path the
first-point anchor has advanced to ``origin + Distance*direction`` (the point the
first click would have set), and the HUD was NOT rejected.

The SECOND-point-step case (anchor pre-armed) is also asserted, to prove that
path keeps working after the fix.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF


def _acquire_origin_endpoint(scene):
    """Acquire the (0,0) endpoint directly on the controller (dwell crossed)."""
    scene._align_controller.on_move(
        (0.0, 0.0),
        {"point": (0.0, 0.0), "snap_type": "endpoint", "source_id": 1,
         "direction": None},
        elapsed_ms=500)


def _move_onto_h_path(scene):
    """Drive the seam so the cursor soft-snaps onto the H path through (0,0)."""
    p = scene.get_effective_position(QPointF(800.0, 20.0))
    scene._sync_dynamic_input()
    return p


def test_first_point_distance_commits_and_arms_anchor(shown_model_view):
    """FIRST point: no anchor armed yet; typing Distance must arm the anchor."""
    view, scene = shown_model_view
    scene.set_mode("draw_gridline")
    _acquire_origin_endpoint(scene)

    # First-point step: the mode's own placement anchor is None.
    assert scene._draw_line_anchor is None

    _move_onto_h_path(scene)
    assert scene.active_schema().name == "track"

    assert scene.begin_dynamic_input("") is True
    hud = scene.dynamic_input
    assert hud.schema.name == "track"
    hud.editor("Distance").setText("500")

    n_before = len(scene._gridlines)
    reject_calls = []
    _orig_reject = hud.reject_commit
    hud.reject_commit = lambda *a, **k: (reject_calls.append(1),
                                         _orig_reject(*a, **k))

    hud._accept()   # emits committed → _on_dynamic_input_committed → applier

    # Ground truth: the HUD was NOT rejected (no red border), and the first
    # point advanced to (500, 0) — the point on the path the first click would
    # have placed. No gridline is committed on a first point (it just arms the
    # anchor, exactly like a real first click on the path).
    assert not reject_calls, "the typed Distance must NOT be rejected (red)"
    assert scene._draw_line_anchor is not None, (
        "first-point Distance must arm the placement anchor")
    assert abs(scene._draw_line_anchor.x() - 500.0) < 1e-6, scene._draw_line_anchor
    assert abs(scene._draw_line_anchor.y() - 0.0) < 1e-6, scene._draw_line_anchor
    assert len(scene._gridlines) == n_before, (
        "a first point should not commit a gridline")


def test_second_point_distance_still_commits(shown_model_view):
    """SECOND point: anchor pre-armed; typing Distance commits the segment."""
    view, scene = shown_model_view
    scene.set_mode("draw_gridline")
    _acquire_origin_endpoint(scene)
    _move_onto_h_path(scene)
    assert scene.active_schema().name == "track"

    assert scene.begin_dynamic_input("") is True
    hud = scene.dynamic_input
    assert hud.schema.name == "track"

    # Pre-arm the first click away from the origin (second-point step).
    scene._draw_line_anchor = QPointF(0.0, -1000.0)
    n_before = len(scene._gridlines)
    hud.editor("Distance").setText("500")
    hud._accept()

    assert len(scene._gridlines) == n_before + 1, "a gridline should be committed"
    end = scene._gridlines[-1].line().p2()
    assert abs(end.x() - 500.0) < 1e-6 and abs(end.y() - 0.0) < 1e-6, end
