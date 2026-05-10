"""tests/test_visibility_display.py — Visibility & display cluster tests."""

from __future__ import annotations

import types

import pytest
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.node import Node
from firepro3d.pipe import Pipe


@pytest.fixture
def scene(qapp):
    """Bare QGraphicsScene with minimal sprinkler_system stub."""
    s = QGraphicsScene()
    # Provide empty containers so apply_to_scene doesn't blow up
    ss = types.SimpleNamespace(nodes=[], pipes=[])
    s.sprinkler_system = ss
    return s


def _make_node(scene, x, y, z=0.0):
    n = Node(x, y)
    scene.addItem(n)
    n.z_pos = z
    return n


def _make_pipe(scene, n1, n2):
    p = Pipe(n1, n2)
    scene.addItem(p)
    return p


def _make_level_manager(level_name="Level 1", elevation=0.0):
    """Create a minimal LevelManager via __new__ with a single level."""
    from firepro3d.level_manager import LevelManager, Level
    lm = LevelManager.__new__(LevelManager)
    lm._levels = [Level(name=level_name, elevation=elevation)]
    return lm


# ── Task 1: Hidden items respect display overrides ─────────────────────


class TestHiddenItemsRespectOverrides:

    def test_hidden_pipe_stays_hidden_after_set_level_vis(self, qapp, scene):
        """A pipe with _display_overrides['visible']=False must not be
        re-shown by _set_level_vis logic."""
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        p = _make_pipe(scene, n1, n2)
        p.level = "Level 1"
        p._display_overrides["visible"] = False
        p.setVisible(False)

        # Register the pipe in the stub sprinkler_system so apply_to_scene sees it
        scene.sprinkler_system.pipes.append(p)

        lm = _make_level_manager("Level 1")
        lm.apply_to_scene(scene, active_level="Level 1")

        assert p.isVisible() is False

    def test_hidden_node_stays_hidden_after_set_level_vis(self, qapp, scene):
        """A node with _display_overrides['visible']=False stays hidden."""
        n = _make_node(scene, 0, 0)
        n.level = "Level 1"
        n._display_overrides["visible"] = False
        n.setVisible(False)

        scene.sprinkler_system.nodes.append(n)

        lm = _make_level_manager("Level 1")
        lm.apply_to_scene(scene, active_level="Level 1")

        assert n.isVisible() is False

    def test_non_hidden_pipe_shown_normally(self, qapp, scene):
        """Pipe without display override is shown on active level."""
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        p = _make_pipe(scene, n1, n2)
        p.level = "Level 1"
        # No _display_overrides['visible'] set — should be shown normally

        scene.sprinkler_system.pipes.append(p)

        lm = _make_level_manager("Level 1")
        lm.apply_to_scene(scene, active_level="Level 1")

        assert p.isVisible() is True
