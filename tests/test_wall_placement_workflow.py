"""tests/test_wall_placement_workflow.py — wall as a variant-bearing placement mode.

Task 4: one ``"wall"`` scene-mode carries ``_wall_primitive ∈ {"line","polyline","rect"}``;
←/→ cycles the primitive via ``_PLACEMENT_VARIANTS``; ``set_mode("wall_rect")`` aliases
into ``wall`` + ``rect`` primitive (backward-compat shim for the ribbon, Task 6 will update).
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.model_space import Model_Space


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
