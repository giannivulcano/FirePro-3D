"""tests/test_dynamic_input_seam.py — the ``Model_Space`` dynamic-input seam.

Anchor publication and placement-state readback, i.e. the scene-side half of
dynamic input.  The HUD widget itself is covered by
``tests/test_dynamic_input_widget.py``.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt

from firepro3d.construction_geometry import PolylineItem
from firepro3d.model_space import Model_Space
from firepro3d.node import Node


@pytest.fixture
def scene(qapp):
    sc = Model_Space()
    yield sc


class _MoveEventStub:
    """Minimal stand-in for the mouse-move event ``_move_draw_line`` reads.

    ``QGraphicsSceneMouseEvent`` cannot be instantiated or sub-classed under
    PyQt6, so a real event cannot be built headlessly.  ``_move_draw_line``
    touches only ``modifiers()`` on the event (the position arrives as the
    separate ``snapped`` argument), so this covers the whole surface the
    handler uses.
    """

    def __init__(self, modifiers=Qt.KeyboardModifier.NoModifier):
        self._modifiers = modifiers

    def modifiers(self):
        return self._modifiers


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


class TestPublishPlacementState:

    def test_publishes_resolved_point_not_raw_cursor(self, scene):
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        scene._last_scene_pos = QPointF(500, -3)      # raw cursor
        constrained = QPointF(500, 0)                 # what Ctrl produced
        scene.publish_placement_state(QPointF(0, 0), constrained)
        assert scene.get_resolved_point() == constrained

    def test_move_draw_line_publishes_the_constrained_point(self, scene):
        """Drive the real handler: the published point must be Ctrl-snapped.

        The previous guard passed the constrained point into
        ``publish_placement_state`` by hand, so it could not tell a publish of
        ``tip`` from a publish of the raw ``snapped`` cursor.  Here the raw
        cursor sits a few degrees off horizontal — well inside the 45° snap —
        so the two points are numerically distinct and only the constrained
        one can satisfy the assertion.

        Driven via ``_move_draw_line`` with a ``_MoveEventStub`` rather than a
        real ``QGraphicsSceneMouseEvent``, which PyQt6 refuses to instantiate.
        """
        anchor = QPointF(0, 0)
        scene.mode = "draw_line"
        scene._draw_line_anchor = anchor
        raw = QPointF(1000, -30)          # ~1.7° off horizontal
        scene._last_scene_pos = raw

        scene._move_draw_line(
            _MoveEventStub(Qt.KeyboardModifier.ControlModifier), raw)

        expected = scene._constrain_angle(anchor, raw)
        got = scene.get_resolved_point()
        assert got is not None
        assert got == expected
        # The constraint actually moved the point, so this is a real distinction.
        assert expected != raw
        assert got != raw

    def test_move_draw_line_readout_matches_the_constrained_point(self, scene):
        """The readout is derived from the same constrained point, not the raw one."""
        anchor = QPointF(0, 0)
        scene.mode = "draw_line"
        scene._draw_line_anchor = anchor
        raw = QPointF(1000, -30)

        scene._move_draw_line(
            _MoveEventStub(Qt.KeyboardModifier.ControlModifier), raw)

        # Snapped to horizontal → 0°, not the raw cursor's ~1.7°.
        assert scene._draw_dim_hint == "L 1000.450 mm  A 0°"

    def test_sets_dim_hint_from_schema(self, scene):
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(1000, -1000))
        assert scene._draw_dim_hint == "L 1414.214 mm  A 45°"

    def test_dim_hint_honours_scale_calibration(self, scene):
        """Scene units are converted through the scene's own ScaleManager.

        This is the assertion that catches treating scene units as mm: at
        2 px/mm a 6000-scene-unit line is 3000 mm, and the readout must say so.
        """
        scene.scale_manager.set_pixels_per_mm(2.0)
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(6000, 0))
        hint = scene._draw_dim_hint
        assert "3000" in hint
        assert "6000" not in hint
        assert hint == "L 3000.000 mm  A 0°"

    def test_clear_resets_both(self, scene):
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(100, 0))
        scene.clear_placement_state()
        assert scene.get_resolved_point() is None
        assert scene._draw_dim_hint is None

    def test_no_schema_mode_publishes_point_without_hint(self, scene):
        scene.mode = "select"
        scene.publish_placement_state(QPointF(0, 0), QPointF(9, 9))
        assert scene.get_resolved_point() == QPointF(9, 9)
        assert scene._draw_dim_hint is None

    def test_resolved_point_is_a_copy(self, scene):
        """Same aliasing guard as get_placement_anchor."""
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        p = QPointF(100, 0)
        scene.publish_placement_state(QPointF(0, 0), p)
        got = scene.get_resolved_point()
        got.setX(999)
        assert scene.get_resolved_point() == QPointF(100, 0)

    def test_gridline_replicate_teardown_drops_the_point(self, scene):
        """Cancelling replication must not leave the last point readable.

        ``_end_gridline_replicate`` returns to select mode, so without a full
        clear a caller reading ``get_resolved_point()`` before the next
        mouse-move would get the cancelled placement's point.
        """
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(100, 0))
        assert scene.get_resolved_point() is not None

        scene._end_gridline_replicate()

        assert scene.get_resolved_point() is None
        assert scene._draw_dim_hint is None
