"""tests/test_pipe_data_integrity.py — Pipe data integrity cluster tests."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.node import Node
from firepro3d.pipe import Pipe
from firepro3d.fitting import Fitting


@pytest.fixture
def scene(qapp):
    """Bare QGraphicsScene for items that need one."""
    return QGraphicsScene()


def _make_node(scene, x, y, z=0.0):
    n = Node(x, y)
    scene.addItem(n)
    n.z_pos = z
    return n


def _make_pipe(scene, n1, n2):
    p = Pipe(n1, n2)
    scene.addItem(p)
    return p


# ── Fitting stacking visibility ────────────────────────────────────────────


class TestFittingStackingVisibility:

    def test_lower_fitting_hidden_when_higher_visible(self, qapp, scene):
        """Standard case: higher node visible → lower fitting hidden."""
        top = _make_node(scene, 0, 0, z=3000)
        bot = _make_node(scene, 0, 0, z=0)
        east = _make_node(scene, 1000, 0, z=3000)
        _make_pipe(scene, top, bot)   # riser
        _make_pipe(scene, top, east)  # horizontal
        top.fitting.update()
        bot.fitting.update()
        assert top.fitting.symbol.isVisible() is True
        assert bot.fitting.symbol.isVisible() is False

    def test_lower_fitting_shows_when_higher_hidden(self, qapp, scene):
        """When higher node is hidden (outside view range), lower fitting shows."""
        top = _make_node(scene, 0, 0, z=3000)
        bot = _make_node(scene, 0, 0, z=0)
        east = _make_node(scene, 1000, 0, z=0)
        _make_pipe(scene, top, bot)   # riser
        _make_pipe(scene, bot, east)  # horizontal on lower level
        # Simulate level_manager hiding the upper node (outside view range)
        top.setVisible(False)
        bot.fitting.update()
        assert bot.fitting.symbol.isVisible() is True

    def test_both_fittings_hidden_when_both_have_sprinklers(self, qapp, scene):
        """Sprinkler nodes suppress fitting regardless of stacking."""
        top = _make_node(scene, 0, 0, z=3000)
        bot = _make_node(scene, 0, 0, z=0)
        _make_pipe(scene, top, bot)
        top.add_sprinkler()
        bot.add_sprinkler()
        top.fitting.update()
        bot.fitting.update()
        assert top.fitting.symbol.isVisible() is False
        assert bot.fitting.symbol.isVisible() is False
