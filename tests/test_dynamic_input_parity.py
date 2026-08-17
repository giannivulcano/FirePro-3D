"""tests/test_dynamic_input_parity.py — mouse vs HUD produce identical geometry.

Covers ``Model_Space._commit_draw_line_at``, the point-taking commit extracted
from ``_press_draw_line`` so that Dynamic Input and the mouse click share one
line-building path instead of two.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.model_space import Model_Space


@pytest.fixture
def scene(qapp):
    return Model_Space()


class TestCommitDrawLineAt:

    def test_creates_line_item(self, scene):
        scene.set_mode("draw_line")
        scene._draw_line_anchor = QPointF(0, 0)
        before = len(scene._draw_lines)
        scene._commit_draw_line_at(QPointF(100, 0))
        assert len(scene._draw_lines) == before + 1
        item = scene._draw_lines[-1]
        assert item.line().p1() == QPointF(0, 0)
        assert item.line().p2() == QPointF(100, 0)

    def test_clears_anchor_after_commit(self, scene):
        scene.set_mode("draw_line")
        scene._draw_line_anchor = QPointF(0, 0)
        scene._commit_draw_line_at(QPointF(100, 0))
        assert scene._draw_line_anchor is None

    def test_rejects_zero_length(self, scene):
        scene.set_mode("draw_line")
        scene._draw_line_anchor = QPointF(0, 0)
        before = len(scene._draw_lines)
        scene._commit_draw_line_at(QPointF(0.1, 0))
        # nothing created, anchor still armed
        assert len(scene._draw_lines) == before
        assert scene._draw_line_anchor == QPointF(0, 0)

    def test_no_anchor_is_a_noop(self, scene):
        scene.set_mode("draw_line")
        scene._draw_line_anchor = None
        before = len(scene._draw_lines)
        scene._commit_draw_line_at(QPointF(100, 0))
        assert len(scene._draw_lines) == before

    def test_gridline_mode_creates_gridline(self, scene):
        scene.set_mode("draw_gridline")
        scene._draw_line_anchor = QPointF(0, 0)
        before = len(scene._gridlines)
        scene._commit_draw_line_at(QPointF(1000, 0))
        assert len(scene._gridlines) == before + 1
        assert len(scene._draw_lines) == 0
        assert scene._draw_line_anchor is None

    def test_clears_published_placement_state(self, scene):
        scene.set_mode("draw_line")
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(100, 0))
        assert scene.get_resolved_point() is not None
        scene._commit_draw_line_at(QPointF(100, 0))
        assert scene.get_resolved_point() is None

    def test_single_place_mode_exits_to_select(self, scene):
        scene.set_mode("draw_line")
        scene.single_place_mode = True
        scene._draw_line_anchor = QPointF(0, 0)
        scene._commit_draw_line_at(QPointF(100, 0))
        assert scene.mode == "select"

    def test_repeat_mode_rearms(self, scene):
        scene.set_mode("draw_line")
        scene.single_place_mode = False
        scene._draw_line_anchor = QPointF(0, 0)
        scene._commit_draw_line_at(QPointF(100, 0))
        assert scene.mode == "draw_line"

    def test_repeat_mode_emits_start_instruction(self, scene):
        scene.set_mode("draw_line")
        scene.single_place_mode = False
        seen = []
        scene.instructionChanged.connect(seen.append)
        scene._draw_line_anchor = QPointF(0, 0)
        scene._commit_draw_line_at(QPointF(100, 0))
        assert seen[-1] == "Pick first point"

    def test_gridline_repeat_mode_emits_gridline_wording(self, scene):
        scene.set_mode("draw_gridline")
        scene.single_place_mode = False
        seen = []
        scene.instructionChanged.connect(seen.append)
        scene._draw_line_anchor = QPointF(0, 0)
        scene._commit_draw_line_at(QPointF(1000, 0))
        assert seen[-1] == "Pick start point"
