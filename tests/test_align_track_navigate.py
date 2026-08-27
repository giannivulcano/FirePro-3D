"""tests/test_align_track_navigate.py — ALIGN on-path Navigate (track schema).

Task 6 follow-up: when the cursor soft-snaps to a *single* ALIGN tracking path,
the HUD swaps to the ``track`` schema (one signed Distance field armed with the
path direction) so typing a distance places the point that far along the path
from its origin.  Driven through the real seam on a shown+activated view.

Ground truth (never a flag flip):
  * moving onto the acquired point's horizontal path makes the live HUD schema
    ``track``;
  * committing Distance=500 on that +x path from origin (0,0) resolves to
    (500, 0);
  * moving OFF the path swaps the schema back to the primitive.
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
    # Just below y=0 at x=800: within the align aperture of the H path, no real
    # snap nearby, so the ALIGN tier projects onto y=0 (see test_align_seam).
    p = scene.get_effective_position(QPointF(800.0, 20.0))
    scene._sync_dynamic_input()
    return p


def test_on_path_swaps_schema_to_track(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_gridline")
    _acquire_origin_endpoint(scene)

    p = _move_onto_h_path(scene)
    assert abs(p.y()) < 1e-6, f"expected the seam to project onto y=0, got {p.y()}"

    assert scene.active_schema() is not None
    assert scene.active_schema().name == "track", (
        f"on-path schema should be 'track', got "
        f"{scene.active_schema().name!r}")
    # The live HUD must be built on the track schema too.
    assert scene.dynamic_input is not None
    assert scene.dynamic_input.schema.name == "track"


def test_typing_distance_places_along_path(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_gridline")
    _acquire_origin_endpoint(scene)
    _move_onto_h_path(scene)
    assert scene.active_schema().name == "track"

    # Engage the HUD and type a distance; commit it through the real signal path.
    assert scene.begin_dynamic_input("") is True
    hud = scene.dynamic_input
    assert hud.schema.name == "track"
    hud.editor("Distance").setText("500")

    # Ground truth #1: resolving exactly the way the commit path does lands the
    # point 500 along the +x path from origin (0,0) → (500, 0).
    values = hud.values()
    assert values.get("__dir__") is not None, "track direction must be armed"
    resolved = scene.active_schema().resolve(scene.get_placement_anchor(), values)
    assert abs(resolved.x() - 500.0) < 1e-6, resolved
    assert abs(resolved.y() - 0.0) < 1e-6, resolved

    # Ground truth #2: the resolved point flows through the mode's *own*
    # click-commit path (draw_gridline → _commit_draw_line_at).  Arm the
    # gridline's first click away from the origin so the commit spans it to the
    # track point; the track point is the endpoint the second click would place.
    scene._draw_line_anchor = QPointF(0.0, -1000.0)
    n_before = len(scene._gridlines)
    hud.editor("Distance").setText("500")
    hud._accept()   # emits committed → _on_dynamic_input_committed → applier
    assert len(scene._gridlines) == n_before + 1, "a gridline should be committed"
    # The committed gridline ends at the track point (500, 0), not the raw cursor.
    end = scene._gridlines[-1].line().p2()
    assert abs(end.x() - 500.0) < 1e-6 and abs(end.y() - 0.0) < 1e-6, end


def test_off_path_swaps_schema_back(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_gridline")
    _acquire_origin_endpoint(scene)
    _move_onto_h_path(scene)
    assert scene.active_schema().name == "track"

    # Move well off every path (far from x/y axes, outside the aperture).
    scene.get_effective_position(QPointF(800.0, 800.0))
    scene._sync_dynamic_input()
    # Back to the primitive line schema (draw_gridline → 'line'), not track.
    schema = scene.active_schema()
    assert schema is None or schema.name != "track", (
        f"off-path schema should not be 'track', got "
        f"{None if schema is None else schema.name!r}")
