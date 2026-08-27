"""tests/test_align_seam.py — Model_Space ALIGN seam (real entry point).

Drives the ALIGN acquire→track seam through the *real* pipeline: a shown,
activated ``Model_View`` over a ``Model_Space``, posting real ``QMouseEvent``s
(QTest.mouseMove is inert here — see project memory).  The ground-truth assertion
is that after acquiring the (0,0) endpoint, the cursor near that point's H path
resolves ONTO y=0 through ``get_effective_position`` (the seam's ALIGN tier), and
that a mode change clears the controller.
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


def test_align_tier_snaps_to_path_after_acquire(shown_model_view):
    view, scene = shown_model_view
    # Enter a placement mode so the ALIGN tier is live (_align_active_item set).
    scene.set_mode("draw_gridline")
    assert scene._align_active_item is not None
    _acquire_origin_endpoint(scene)
    assert len(scene._align_controller.acquired) == 1

    # Cursor sitting just below the horizontal path through (0,0): the ALIGN
    # tier must project it onto y=0 (ground truth: the resolved point lands on
    # the path, not merely "some result exists").
    p = scene.get_effective_position(QPointF(800.0, 20.0))
    assert abs(p.y()) < 1e-6, f"expected y≈0 on the H path, got {p.y()}"


def test_lifecycle_clear_on_mode_change(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_gridline")
    _acquire_origin_endpoint(scene)
    assert len(scene._align_controller.acquired) == 1

    scene.set_mode("select")     # leaving placement clears the acquire set
    assert scene._align_controller.acquired == []


def test_acquired_points_clear_after_placement_commit(shown_model_view):
    """Placing geometry resets the acquire set (AutoCAD OTRACK: per-point acquisition).

    Continuous placement modes stay in-mode after a commit, so the mode-change
    clear never fires. ``push_undo_state`` is the single funnel every committed
    placement passes through; acquisitions must reset there so the next element
    starts with a clean tracking set.
    """
    view, scene = shown_model_view
    scene.set_mode("draw_gridline")
    _acquire_origin_endpoint(scene)
    assert len(scene._align_controller.acquired) == 1

    scene.push_undo_state()      # a placement commit landed
    assert scene._align_controller.acquired == []


def test_auto_anchor_reads_raw_mode_anchor_not_track_ray(shown_model_view):
    """The auto-acquired anchor is the RAW placement from-point, never the track
    ray origin — so a cursor-following parallel preview (which self-snaps →
    activates the track schema → get_placement_anchor returns the ray origin)
    cannot pin stray H/V rays to the cursor before a first point exists
    (smoke-test regression, 2026-08-26).
    """
    from PyQt6.QtCore import QPointF
    from firepro3d.align_engine import Ray
    view, scene = shown_model_view
    scene.set_mode("draw_line")
    # No first click yet: even with a track ray armed (as a self-snapped
    # parallel preview would), the auto-anchor stays None.
    scene._align_track_ray = Ray((999.0, 999.0), (1.0, 0.0), "parallel", 1)
    assert scene._mode_placement_anchor() is None
    assert scene._align_anchor_point() is None
    # After the first click, it is the real from-point.
    scene._draw_line_anchor = QPointF(10.0, 20.0)
    assert scene._align_anchor_point() == (10.0, 20.0)
