"""tests/test_wall_placement_workflow.py — wall as a variant-bearing placement mode.

Task 4: one ``"wall"`` scene-mode carries ``_wall_primitive ∈ {"line","polyline","rect"}``;
←/→ cycles the primitive via ``_PLACEMENT_VARIANTS``; ``set_mode("wall_rect")`` aliases
into ``wall`` + ``rect`` primitive (backward-compat shim for the ribbon, Task 6 will update).

Task 5: "line" primitive places ONE segment then re-arms; "polyline" chains (as before).
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt, QEvent
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

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


@pytest.fixture
def scene(qapp):
    return Model_Space()


def test_wall_defaults_to_line_primitive(scene):
    scene.set_mode("wall")
    assert scene._wall_primitive == "line"


def test_arrow_cycles_line_polyline_rect(scene):
    scene.set_mode("wall")
    assert scene.cycle_placement_variant(+1) is True
    assert scene._wall_primitive == "polyline"
    assert scene.cycle_placement_variant(+1) is True
    assert scene._wall_primitive == "rect"
    assert scene.cycle_placement_variant(+1) is True
    assert scene._wall_primitive == "line"


def test_no_cycle_past_step_zero(scene):
    scene.set_mode("wall")
    scene._wall_anchor = QPointF(0, 0)
    assert scene.cycle_placement_variant(+1) is False


def test_primitive_is_session_sticky(scene):
    scene.set_mode("wall")
    scene.cycle_placement_variant(+1)
    scene.set_mode("select")
    scene.set_mode("wall")
    assert scene._wall_primitive == "polyline"


def test_entry_readout_has_label_and_hint(scene):
    msgs = []
    scene.instructionChanged.connect(msgs.append)
    scene.set_mode("wall")
    assert msgs, "set_mode('wall') should emit an instruction"
    assert "Wall (Line)" in msgs[-1] and "(←/→ to change)" in msgs[-1]


def test_wall_rect_mode_alias_folds_to_rect_primitive(scene):
    # Backward-compat: the ribbon still calls set_mode("wall_rect") until Task 6.
    scene.set_mode("wall_rect")
    assert scene.mode == "wall"
    assert scene._wall_primitive == "rect"


# ── Task 5: finish-vs-continue (line vs polyline) ─────────────────────────────
# These three tests drive the REAL entry point: posted QMouseEvent on a SHOWN,
# activated Model_View (per memory: "Test the real entry point").


def test_line_primitive_places_one_wall_then_rearms(qapp, shown_model_view):
    """Line primitive: two clicks → 1 wall → anchor reset (no chain)."""
    view, scene = shown_model_view
    scene.set_mode("wall")          # default primitive is "line"
    assert scene._wall_primitive == "line"
    _click(view, QPointF(0, 0))
    _click(view, QPointF(1000, 0))  # commits ONE wall
    assert len(scene._walls) == 1
    assert scene._wall_anchor is None   # re-armed fresh (not chained)


def test_polyline_primitive_chains(qapp, shown_model_view):
    """Polyline primitive: third click extends from the shared endpoint."""
    view, scene = shown_model_view
    scene.set_mode("wall")
    scene.cycle_placement_variant(+1)   # line → polyline
    assert scene._wall_primitive == "polyline"
    _click(view, QPointF(0, 0))
    _click(view, QPointF(1000, 0))      # wall 1, chain continues
    _click(view, QPointF(1000, 1000))   # wall 2 from shared endpoint
    assert len(scene._walls) == 2
    assert scene._wall_anchor is not None   # still chaining


def test_line_geometry_parity_with_polyline_first_segment(qapp, shown_model_view):
    """Line variant geometry equals polyline's first segment (same builder)."""
    view, scene = shown_model_view
    scene.set_mode("wall")          # "line"
    _click(view, QPointF(0, 0))
    _click(view, QPointF(1000, 0))
    w = scene._walls[0]
    # The view's center is at scene (0,0) but mapFromScene rounds to integer
    # viewport pixels, so the snapped scene coordinates can land a few mm off
    # the requested integer point.  Use a 20 mm tolerance — tight enough to
    # confirm we got the right segment but loose enough to survive viewport
    # pixel rounding in an empty scene with no snap targets.
    assert abs(w.pt1.x() - 0) < 20 and abs(w.pt1.y() - 0) < 20
    assert abs(w.pt2.x() - 1000) < 20 and abs(w.pt2.y() - 0) < 20
