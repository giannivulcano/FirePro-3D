"""tests/test_pipe_data_integrity.py — Pipe data integrity cluster tests."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.node import Node
from firepro3d.pipe import Pipe
from firepro3d.fitting import Fitting
from firepro3d.constants import Z_OVERLAY


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


# ── Pipe ceiling attr removal ──────────────────────────────────────────────


class TestPipeCeilingRemoval:

    def test_pipe_has_no_ceiling_level_attr(self, qapp, scene):
        """Pipe should not have ceiling_level as an instance attribute."""
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        p = _make_pipe(scene, n1, n2)
        assert not hasattr(p, "ceiling_level")

    def test_pipe_has_no_ceiling_offset_attr(self, qapp, scene):
        """Pipe should not have ceiling_offset as an instance attribute."""
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        p = _make_pipe(scene, n1, n2)
        assert not hasattr(p, "ceiling_offset")

    def test_pipe_properties_no_ceiling_keys(self, qapp, scene):
        """_properties dict should not contain Ceiling Level or Ceiling Offset."""
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        p = _make_pipe(scene, n1, n2)
        assert "Ceiling Level" not in p._properties
        assert "Ceiling Offset" not in p._properties

    def test_get_properties_no_ceiling_in_output(self, qapp, scene):
        """get_properties() should not include Ceiling Level or Ceiling Offset."""
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        p = _make_pipe(scene, n1, n2)
        props = p.get_properties()
        assert "Ceiling Level" not in props
        assert "Ceiling Offset" not in props

    def test_set_property_ceiling_offset_is_noop(self, qapp, scene):
        """Setting Ceiling Offset on a pipe should be a no-op (read-only)."""
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        n1.ceiling_offset = -50.8
        p = _make_pipe(scene, n1, n2)
        p.set_property("Ceiling Offset", "-100.0")
        assert n1.ceiling_offset == -50.8  # unchanged


# ── Pipe label Z-ordering ──────────────────────────────────────────────────


class TestPipeLabelZOrdering:

    def test_label_is_top_level_scene_item(self, qapp, scene):
        """Pipe label should be a top-level scene item, not a child of pipe."""
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        p = _make_pipe(scene, n1, n2)
        p.update_label()
        assert p.label.parentItem() is None
        assert p.label.scene() is scene

    def test_label_z_value_is_overlay(self, qapp, scene):
        """Pipe label should render at Z_OVERLAY."""
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        p = _make_pipe(scene, n1, n2)
        p.update_label()
        assert p.label.zValue() == Z_OVERLAY

    def test_label_hidden_when_pipe_hidden(self, qapp, scene):
        """setVisible(False) on pipe cascades to label without update_label."""
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        p = _make_pipe(scene, n1, n2)
        p.update_label()
        assert p.label.isVisible() is True
        p.setVisible(False)  # no update_label needed — setVisible cascades
        assert p.label.isVisible() is False

    def test_label_reshown_when_pipe_reshown(self, qapp, scene):
        """setVisible(True) on pipe re-shows label if Show Label is on."""
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        p = _make_pipe(scene, n1, n2)
        p.update_label()
        p.setVisible(False)
        assert p.label.isVisible() is False
        p.setVisible(True)
        assert p.label.isVisible() is True

    def test_label_removed_on_pipe_delete(self, qapp):
        """When pipe is deleted, label should be removed from scene."""
        from firepro3d.model_space import Model_Space
        scene = Model_Space()
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        p = _make_pipe(scene, n1, n2)
        p.update_label()
        label = p.label
        scene.delete_pipe(p)
        assert label.scene() is None
