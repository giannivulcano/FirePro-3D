"""tests/test_node_snap_45.py — contextual 45° snap reference (bug B5)."""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.node import Node


def _connect(node, other, pipes_list):
    """Attach a stub pipe between *node* and *other* and register it."""
    class _StubPipe:
        pass
    p = _StubPipe()
    p.node1 = node
    p.node2 = other
    pipes_list.append(p)
    node.pipes.append(p)
    return p


def _angle_of(start: QPointF, end: QPointF) -> float:
    """Plan angle in degrees, Y-up, 0° = right."""
    return math.degrees(math.atan2(-(end.y() - start.y()),
                                   end.x() - start.x()))


class TestContextualReference:

    def test_free_node_soft_snaps_within_tolerance(self, qapp):
        n = Node(0, 0)
        start = QPointF(0, 0)
        # 3° off horizontal — inside the 7.5° soft-snap window
        end = QPointF(1000, -math.tan(math.radians(3)) * 1000)
        out = n.snap_point_45(start, end)
        assert _angle_of(start, out) == pytest.approx(0.0, abs=1e-6)

    def test_free_node_leaves_angle_alone_outside_tolerance(self, qapp):
        n = Node(0, 0)
        start = QPointF(0, 0)
        end = QPointF(1000, -math.tan(math.radians(20)) * 1000)
        out = n.snap_point_45(start, end)
        assert _angle_of(start, out) == pytest.approx(20.0, abs=1e-6)

    def test_single_pipe_behaves_as_before(self, qapp):
        """One coplanar pipe → reference is that pipe (unchanged behaviour)."""
        n = Node(0, 0)
        west = Node(-1000, 0)
        west.z_pos = n.z_pos
        pipes = []
        _connect(n, west, pipes)
        start = QPointF(0, 0)
        end = QPointF(1000, -110)          # ~6.3° — snaps to 0° off the E-W axis
        out = n.snap_point_45(start, end)
        assert _angle_of(start, out) == pytest.approx(0.0, abs=1e-6)

    def test_branching_picks_angularly_nearest_pipe_not_first(self, qapp):
        """B5: two pipes; the *first* added is not the contextual one."""
        n = Node(0, 0)
        west = Node(-1000, 0)              # axis 0°/180° — added FIRST
        south = Node(0, 1000)              # axis -90°/90° — added SECOND
        west.z_pos = south.z_pos = n.z_pos
        pipes = []
        _connect(n, west, pipes)
        _connect(n, south, pipes)
        start = QPointF(0, 0)
        # Drag ~80° (up and slightly right). Nearest axis is the N-S pipe (90°),
        # so the 45° grid is anchored there and 80° snaps to 90°.
        end = QPointF(math.cos(math.radians(80)) * 1000,
                      -math.sin(math.radians(80)) * 1000)
        out = n.snap_point_45(start, end)
        assert _angle_of(start, out) == pytest.approx(90.0, abs=1e-6)

    def test_explicit_reference_pipe_overrides_selection(self, qapp):
        n = Node(0, 0)
        west = Node(-1000, 0)
        south = Node(0, 1000)
        west.z_pos = south.z_pos = n.z_pos
        pipes = []
        p_west = _connect(n, west, pipes)
        _connect(n, south, pipes)
        start = QPointF(0, 0)
        end = QPointF(math.cos(math.radians(80)) * 1000,
                      -math.sin(math.radians(80)) * 1000)
        # Forcing the E-W pipe as reference puts the grid on 0/45/90 → 80° → 90°
        out = n.snap_point_45(start, end, reference_pipe=p_west)
        assert _angle_of(start, out) == pytest.approx(90.0, abs=1e-6)

    def test_riser_only_node_falls_through_to_free_snap(self, qapp):
        """No coplanar pipes → free soft-snap, not a riser's plan angle."""
        n = Node(0, 0)
        n.z_pos = 0.0
        above = Node(0, 0)
        above.z_pos = 3000.0               # riser — not coplanar
        pipes = []
        _connect(n, above, pipes)
        start = QPointF(0, 0)
        end = QPointF(1000, -math.tan(math.radians(20)) * 1000)
        out = n.snap_point_45(start, end)
        assert _angle_of(start, out) == pytest.approx(20.0, abs=1e-6)

    def test_length_is_preserved(self, qapp):
        n = Node(0, 0)
        start = QPointF(0, 0)
        end = QPointF(600, -800)           # length 1000
        out = n.snap_point_45(start, end)
        assert math.hypot(out.x() - start.x(),
                          out.y() - start.y()) == pytest.approx(1000.0, abs=1e-6)
