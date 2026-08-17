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


def _two_pipe_node():
    """Node with two reference pipes whose 45° grids are distinguishable.

    IMPORTANT — the reference pair must NOT be mutually perpendicular.  The
    45° grid anchored at 0° and the one anchored at 90° are the *same* grid
    (90 is itself a multiple of 45), so a horizontal + vertical pair snaps
    every drag identically no matter which pipe is chosen and therefore cannot
    detect a wrong reference.  The two axes must sit at a non-multiple-of-45
    angle to each other; here 180° and 30° (150° apart) give the disjoint
    grids {0, 45, 90, …} and {30, 75, 120, …}.

    Returns ``(node, pipes, p_west, p_diag)`` with:
      * pipe W → (-1000, 0): scene axis 180°, grid {…, 0, 45, 90, …}.
        Added FIRST, so this is what the old ``self.pipes[0]`` would pick.
      * pipe D → 30° scene: grid {30, 75, 120, …}.  Added SECOND.
    """
    n = Node(0, 0)
    west = Node(-1000, 0)
    diag = Node(math.cos(math.radians(30)) * 1000,
                math.sin(math.radians(30)) * 1000)      # scene coords, Y down
    west.z_pos = diag.z_pos = n.z_pos                   # keep all three coplanar
    pipes = []
    p_west = _connect(n, west, pipes)
    p_diag = _connect(n, diag, pipes)
    return n, pipes, p_west, p_diag


# Drag to scene 20°: axis delta to W is 20°, to D is 10° → D is contextual.
_DRAG_END = QPointF(math.cos(math.radians(20)) * 1000,
                    math.sin(math.radians(20)) * 1000)


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
        """B5: two pipes; the *first* added is not the contextual one.

        The drag sits 10° off pipe D's axis and 20° off pipe W's, so D is the
        reference and the grid is {30, 75, …} → scene 30° (Y-up -30°).
        Anchoring to ``pipes[0]`` (W) would instead give scene 0°.
        """
        n, _pipes, _p_west, _p_diag = _two_pipe_node()
        start = QPointF(0, 0)
        out = n.snap_point_45(start, _DRAG_END)
        assert _angle_of(start, out) == pytest.approx(-30.0, abs=1e-6)

    def test_explicit_reference_pipe_overrides_selection(self, qapp):
        """Forcing W flips the result away from the contextual choice.

        Same geometry and drag as above, where the default selection yields
        Y-up -30° off pipe D; naming W as the reference must land on W's grid
        instead → scene 0°.
        """
        n, _pipes, p_west, _p_diag = _two_pipe_node()
        start = QPointF(0, 0)
        out = n.snap_point_45(start, _DRAG_END, reference_pipe=p_west)
        assert _angle_of(start, out) == pytest.approx(0.0, abs=1e-6)

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
