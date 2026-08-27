"""Tests for wall-mode ALIGN lifecycle wiring.

Task 6 removed the retired auto-proximity provider (WallSegment.
``alignment_reference_points``) and ``Model_Space._collect_alignment_refs``; the
two tests that asserted those (provider emits centerline refs; collect filters
by distance) were deleted with that behavior — it is replaced by the ALIGN
acquire model (see tests/test_align_seam.py + tests/test_align_controller.py).

What survives here is the still-live lifecycle: entering wall mode arms the
ALIGN active-item sentinel so the ALIGN tier runs during wall placement.
"""
from PyQt6.QtCore import QPointF


def test_wall_mode_sets_align_active_item(qapp):
    """set_mode('wall') must arm the ALIGN sentinel so wall placement runs the
    ALIGN tracking tier."""
    from firepro3d.model_space import Model_Space
    scene = Model_Space()
    scene.set_mode("wall")
    assert scene._align_active_item is scene._PLACEMENT_SENTINEL
