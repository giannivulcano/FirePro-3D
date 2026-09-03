"""tests/test_node_snap.py — Unit tests for find_nearby_node Z disambiguation."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtCore import QPointF

from firepro3d.node import Node
from firepro3d.sprinkler import Sprinkler
from firepro3d.constants import DEFAULT_LEVEL, DEFAULT_CEILING_OFFSET_MM


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

class _FakeLevel:
    """Minimal level stand-in for tests."""
    def __init__(self, name, elevation, view_bottom=-1000.0, view_top=2000.0):
        self.name = name
        self.elevation = elevation
        self.view_bottom = view_bottom
        self.view_top = view_top


class _FakeLevelManager:
    """Minimal LevelManager stand-in."""
    def __init__(self, levels):
        self._levels = {l.name: l for l in levels}
        self.levels = levels

    def get(self, name):
        return self._levels.get(name)


class _FakePlanView:
    """Minimal PlanView stand-in."""
    def __init__(self, view_depth, view_height):
        self.view_depth = view_depth
        self.view_height = view_height


class _FakePlanViewManager:
    """Minimal PlanViewManager stand-in."""
    def __init__(self, pv):
        self._pv = pv

    def get(self, name):
        return self._pv


class _StubScene(QGraphicsScene):
    """Lightweight scene with find_nearby_node dependencies."""
    SNAP_RADIUS = 10

    # Bind the methods under test from Model_Space
    from firepro3d.model_space import Model_Space as _MS
    _get_active_view_range = _MS._get_active_view_range
    find_nearby_node = _MS.find_nearby_node
    find_nearby_candidates = _MS.find_nearby_candidates
    find_or_create_node = _MS.find_or_create_node
    add_node = _MS.add_node
    del _MS

    def __init__(self, nodes=None, level_manager=None, plan_view_manager=None,
                 active_level=DEFAULT_LEVEL):
        super().__init__()
        from firepro3d.sprinkler_system import SprinklerSystem
        self.sprinkler_system = SprinklerSystem()
        self._level_manager = level_manager
        self._plan_view_manager = plan_view_manager
        self.active_level = active_level
        # Node CRUD moved to PipeNetworkController (pipe slice C2a); the bound
        # scene shells delegate to it, so the stub needs the controller too.
        from firepro3d.pipe_network_controller import PipeNetworkController
        self._pipe_ctl = PipeNetworkController(self)
        for n in (nodes or []):
            self.addItem(n)
            self.sprinkler_system.add_node(n)


def _make_node(x, y, z_pos):
    n = Node(x, y)
    n.z_pos = z_pos
    return n


# ─────────────────────────────────────────────────────────────────────────────
# 1. z_hint selection
# ─────────────────────────────────────────────────────────────────────────────

class TestZHintSelection:

    def test_no_nodes_returns_none(self, qapp):
        scene = _StubScene()
        result = scene.find_nearby_node(0, 0)
        assert result is None

    def test_single_node_returned_regardless_of_z_hint(self, qapp):
        n = _make_node(0, 0, z_pos=3000.0)
        pv = _FakePlanView(view_depth=-1000.0, view_height=5000.0)
        scene = _StubScene([n], plan_view_manager=_FakePlanViewManager(pv))
        assert scene.find_nearby_node(0, 0, z_hint=0.0) is n

    def test_z_hint_picks_closest_z(self, qapp):
        """Two nodes at same XY, different Z — z_hint picks closer one."""
        n_low = _make_node(0, 0, z_pos=0.0)
        n_high = _make_node(0, 0, z_pos=3000.0)
        pv = _FakePlanView(view_depth=-1000.0, view_height=5000.0)
        scene = _StubScene([n_low, n_high],
                           plan_view_manager=_FakePlanViewManager(pv))
        assert scene.find_nearby_node(0, 0, z_hint=2800.0) is n_high
        assert scene.find_nearby_node(0, 0, z_hint=100.0) is n_low

    def test_z_hint_none_preserves_insertion_order(self, qapp):
        """Without z_hint, first XY match wins (backward compat)."""
        n1 = _make_node(0, 0, z_pos=0.0)
        n2 = _make_node(0, 0, z_pos=3000.0)
        pv = _FakePlanView(view_depth=-1000.0, view_height=5000.0)
        scene = _StubScene([n1, n2],
                           plan_view_manager=_FakePlanViewManager(pv))
        assert scene.find_nearby_node(0, 0) is n1

    def test_z_hint_with_sprinkler_bbox(self, qapp):
        """Sprinkler bbox candidates also sorted by z_hint."""
        n_low = _make_node(0, 0, z_pos=0.0)
        n_high = _make_node(0, 0, z_pos=3000.0)
        n_low.add_sprinkler()
        n_high.add_sprinkler()
        pv = _FakePlanView(view_depth=-1000.0, view_height=5000.0)
        scene = _StubScene([n_low, n_high],
                           plan_view_manager=_FakePlanViewManager(pv))
        # Sprinkler bbox at (0,0) — both contain cursor
        assert scene.find_nearby_node(0, 0, z_hint=2800.0) is n_high


# ─────────────────────────────────────────────────────────────────────────────
# 2. View-range filtering
# ─────────────────────────────────────────────────────────────────────────────

class TestViewRangeFiltering:

    def test_node_outside_view_range_excluded(self, qapp):
        """Node at z=5000 excluded when view range is [0, 3500]."""
        n_in = _make_node(0, 0, z_pos=1000.0)
        n_out = _make_node(0, 0, z_pos=5000.0)
        pv = _FakePlanView(view_depth=0.0, view_height=3500.0)
        scene = _StubScene([n_in, n_out],
                           plan_view_manager=_FakePlanViewManager(pv))
        assert scene.find_nearby_node(0, 0, z_hint=5000.0) is n_in

    def test_all_nodes_outside_view_range_returns_none(self, qapp):
        n = _make_node(0, 0, z_pos=5000.0)
        pv = _FakePlanView(view_depth=0.0, view_height=3500.0)
        scene = _StubScene([n], plan_view_manager=_FakePlanViewManager(pv))
        assert scene.find_nearby_node(0, 0) is None

    def test_no_plan_view_manager_skips_filtering(self, qapp):
        """Without a plan view manager, all nodes are candidates (backward compat)."""
        n = _make_node(0, 0, z_pos=5000.0)
        scene = _StubScene([n])
        assert scene.find_nearby_node(0, 0) is n

    def test_node_at_boundary_included(self, qapp):
        """Node at exactly view_depth or view_height is included."""
        n = _make_node(0, 0, z_pos=3500.0)
        pv = _FakePlanView(view_depth=0.0, view_height=3500.0)
        scene = _StubScene([n], plan_view_manager=_FakePlanViewManager(pv))
        assert scene.find_nearby_node(0, 0) is n


# ─────────────────────────────────────────────────────────────────────────────
# 3. Wrapper threading
# ─────────────────────────────────────────────────────────────────────────────

class TestWrapperThreading:

    def test_find_or_create_node_passes_z_hint(self, qapp):
        n_low = _make_node(0, 0, z_pos=0.0)
        n_high = _make_node(0, 0, z_pos=3000.0)
        pv = _FakePlanView(view_depth=-1000.0, view_height=5000.0)
        scene = _StubScene([n_low, n_high],
                           plan_view_manager=_FakePlanViewManager(pv))
        result = scene.find_or_create_node(0, 0, z_hint=2800.0)
        assert result is n_high

    def test_add_node_passes_z_hint(self, qapp):
        n_low = _make_node(0, 0, z_pos=0.0)
        n_high = _make_node(0, 0, z_pos=3000.0)
        pv = _FakePlanView(view_depth=-1000.0, view_height=5000.0)
        scene = _StubScene([n_low, n_high],
                           plan_view_manager=_FakePlanViewManager(pv))
        result = scene.add_node(0, 0, z_hint=2800.0)
        assert result is n_high


# ─────────────────────────────────────────────────────────────────────────────
# 4. Tab cycling state
# ─────────────────────────────────────────────────────────────────────────────

class TestPipeTabCycling:

    def _make_scene_with_stack(self, qapp):
        """Three nodes stacked at (0,0) with z=0, 3000, 6000."""
        n1 = _make_node(0, 0, z_pos=0.0)
        n2 = _make_node(0, 0, z_pos=3000.0)
        n3 = _make_node(0, 0, z_pos=6000.0)
        pv = _FakePlanView(view_depth=-1000.0, view_height=9000.0)
        scene = _StubScene([n1, n2, n3],
                           plan_view_manager=_FakePlanViewManager(pv))
        return scene, n1, n2, n3

    def test_find_nearby_candidates_returns_all_matches(self, qapp):
        scene, n1, n2, n3 = self._make_scene_with_stack(qapp)
        candidates = scene.find_nearby_candidates(0, 0)
        assert set(candidates) == {n1, n2, n3}

    def test_find_nearby_candidates_filtered_by_view_range(self, qapp):
        n_in = _make_node(0, 0, z_pos=1000.0)
        n_out = _make_node(0, 0, z_pos=5000.0)
        pv = _FakePlanView(view_depth=0.0, view_height=3500.0)
        scene = _StubScene([n_in, n_out],
                           plan_view_manager=_FakePlanViewManager(pv))
        candidates = scene.find_nearby_candidates(0, 0)
        assert candidates == [n_in]

    def test_find_nearby_candidates_sorted_by_z_hint(self, qapp):
        scene, n1, n2, n3 = self._make_scene_with_stack(qapp)
        # Sorted by distance to z_hint=2800 → n2(3000), n1(0), n3(6000)
        candidates = scene.find_nearby_candidates(0, 0, z_hint=2800.0)
        assert candidates[0] is n2

    def test_find_nearby_candidates_empty_at_distance(self, qapp):
        """No node within SNAP_RADIUS → empty list."""
        n = _make_node(100, 100, z_pos=0.0)
        pv = _FakePlanView(view_depth=-1000.0, view_height=5000.0)
        scene = _StubScene([n], plan_view_manager=_FakePlanViewManager(pv))
        assert scene.find_nearby_candidates(0, 0) == []

    # Tab-cycle state now lives on PipeNetworkController (pipe slice C2d).
    # These drive the REAL ``cycle_tab()`` on a real Model_Space so they guard
    # the relocated controller logic (not a hand-copied modulo formula).
    def _pipe_scene(self):
        from firepro3d.model_space import Model_Space
        scene = Model_Space()
        scene.mode = "pipe"
        return scene

    def test_pipe_tab_state_advances(self, qapp):
        scene = self._pipe_scene()
        n1 = _make_node(0, 0, z_pos=0.0)
        n2 = _make_node(0, 0, z_pos=3000.0)
        n3 = _make_node(0, 0, z_pos=6000.0)
        scene._pipe_ctl._tab_candidates = [n1, n2, n3]
        scene._pipe_ctl._tab_index = 0
        scene._pipe_ctl.cycle_tab()
        assert scene._pipe_ctl._tab_index == 1
        assert scene._pipe_ctl._tab_candidates[scene._pipe_ctl._tab_index] is n2

    def test_pipe_tab_wraps_around(self, qapp):
        scene = self._pipe_scene()
        n1 = _make_node(0, 0, z_pos=0.0)
        n2 = _make_node(0, 0, z_pos=3000.0)
        n3 = _make_node(0, 0, z_pos=6000.0)
        scene._pipe_ctl._tab_candidates = [n1, n2, n3]
        scene._pipe_ctl._tab_index = 2
        scene._pipe_ctl.cycle_tab()
        assert scene._pipe_ctl._tab_index == 0

    def test_single_node_no_cycle(self, qapp):
        scene = self._pipe_scene()
        n = _make_node(0, 0, z_pos=0.0)
        scene._pipe_ctl._tab_candidates = [n]
        scene._pipe_ctl._tab_index = 0
        scene._pipe_ctl.cycle_tab()
        assert scene._pipe_ctl._tab_index == 0
