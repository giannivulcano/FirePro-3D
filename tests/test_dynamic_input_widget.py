"""tests/test_dynamic_input_widget.py — HUD widget and Model_Space seam."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.construction_geometry import PolylineItem
from firepro3d.model_space import Model_Space
from firepro3d.node import Node


@pytest.fixture
def scene(qapp):
    sc = Model_Space()
    yield sc


class TestPlacementAnchor:

    def test_none_when_nothing_started(self, scene):
        scene.mode = "draw_line"
        assert scene.get_placement_anchor() is None

    def test_draw_line_anchor(self, scene):
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(10, 20)
        assert scene.get_placement_anchor() == QPointF(10, 20)

    def test_draw_gridline_shares_line_anchor(self, scene):
        scene.mode = "draw_gridline"
        scene._draw_line_anchor = QPointF(1, 2)
        assert scene.get_placement_anchor() == QPointF(1, 2)

    def test_rectangle_anchor(self, scene):
        scene.mode = "draw_rectangle"
        scene._draw_rect_anchor = QPointF(3, 4)
        assert scene.get_placement_anchor() == QPointF(3, 4)

    def test_circle_centre(self, scene):
        scene.mode = "draw_circle"
        scene._draw_circle_center = QPointF(5, 6)
        assert scene.get_placement_anchor() == QPointF(5, 6)

    def test_wall_anchor(self, scene):
        scene.mode = "wall"
        scene._wall_anchor = QPointF(7, 8)
        assert scene.get_placement_anchor() == QPointF(7, 8)

    def test_unknown_mode_is_none(self, scene):
        scene.mode = "select"
        scene._draw_line_anchor = QPointF(10, 20)
        assert scene.get_placement_anchor() is None

    def test_construction_line_is_out_of_scope(self, scene):
        """construction_line is excluded by design — no dynamic input."""
        scene.mode = "construction_line"
        scene._cline_anchor = QPointF(9, 9)
        assert scene.get_placement_anchor() is None

    # ── Branches with real logic ──────────────────────────────────────────

    def test_polyline_returns_last_vertex(self, scene):
        """The anchor is the most recent vertex, not the first."""
        pl = PolylineItem(QPointF(1, 1))
        pl.append_point(QPointF(2, 2))
        pl.append_point(QPointF(3, 3))
        scene.mode = "polyline"
        scene._polyline_active = pl
        assert scene.get_placement_anchor() == QPointF(3, 3)

    def test_polyline_none_when_no_active(self, scene):
        scene.mode = "polyline"
        scene._polyline_active = None
        assert scene.get_placement_anchor() is None

    def test_pipe_returns_node_scene_pos(self, scene):
        """pipe mode stores a Node; the anchor is its scene position.

        The Node sits off-origin so a bug returning a default QPointF()
        cannot pass.
        """
        scene.mode = "pipe"
        scene.node_start_pos = Node(5.0, 7.0)
        assert scene.get_placement_anchor() == QPointF(5.0, 7.0)

    def test_move_returns_raw_point(self, scene):
        """move mode stores a raw QPointF, not a Node."""
        scene.mode = "move"
        scene.node_start_pos = QPointF(11, 22)
        assert scene.get_placement_anchor() == QPointF(11, 22)

    def test_pipe_none_when_no_start_node(self, scene):
        scene.mode = "pipe"
        scene.node_start_pos = None
        assert scene.get_placement_anchor() is None

    # ── Aliasing ──────────────────────────────────────────────────────────

    def test_returned_point_is_a_copy(self, scene):
        """Callers may mutate the result without corrupting internal state."""
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(1, 2)
        a = scene.get_placement_anchor()
        a.setX(999)
        assert scene._draw_line_anchor == QPointF(1, 2)

        # The polyline branch reaches into the item — mutating the result
        # must not relocate an already-committed vertex.
        pl = PolylineItem(QPointF(1, 1))
        pl.append_point(QPointF(3, 4))
        scene.mode = "polyline"
        scene._polyline_active = pl
        b = scene.get_placement_anchor()
        b.setY(-777)
        assert pl._points[-1] == QPointF(3, 4)
