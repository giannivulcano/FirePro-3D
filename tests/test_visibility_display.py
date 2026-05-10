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
    ss = getattr(scene, "sprinkler_system", None)
    if ss is not None and callable(getattr(ss, "add_node", None)) and n not in ss.nodes:
        ss.add_node(n)
    return n


def _make_pipe(scene, n1, n2):
    p = Pipe(n1, n2)
    scene.addItem(p)
    ss = getattr(scene, "sprinkler_system", None)
    if ss is not None and callable(getattr(ss, "add_pipe", None)) and p not in ss.pipes:
        ss.add_pipe(p)
    # Keep fitting type in sync so callers can rely on it without explicit update()
    n1.fitting.type = n1.fitting.determine_type(n1.pipes)
    n2.fitting.type = n2.fitting.determine_type(n2.pipes)
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


from firepro3d.constants import Z_OVERLAY


# ── Riser pass-through indicator ────────────────────────────────────────


class TestRiserPassthroughIndicator:

    def test_vertical_pipe_creates_riser_symbol(self, qapp, scene):
        """Vertical pipe should have a _riser_symbol."""
        top = _make_node(scene, 0, 0, z=3000)
        bot = _make_node(scene, 0, 0, z=0)
        p = _make_pipe(scene, top, bot)
        p.update_label()
        assert p._riser_symbol is not None

    def test_horizontal_pipe_no_riser_symbol(self, qapp, scene):
        """Horizontal pipe should not create a riser symbol."""
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        p = _make_pipe(scene, n1, n2)
        p.update_label()
        assert p._riser_symbol is None or not p._riser_symbol.isVisible()

    def test_riser_symbol_shown_when_endpoint_has_no_horiz_pipes(self, qapp, scene):
        """Riser symbol shown when visible endpoint has only vertical pipes."""
        top = _make_node(scene, 0, 0, z=3000)
        bot = _make_node(scene, 0, 0, z=0)
        p = _make_pipe(scene, top, bot)
        p.update_label()
        # Both nodes visible but neither has horizontal pipes — symbol shows
        assert p._riser_symbol.isVisible() is True

    def test_riser_symbol_hidden_when_endpoint_has_horiz_pipe(self, qapp, scene):
        """Riser symbol hidden when a visible endpoint has horizontal pipes
        (fitting already indicates the riser)."""
        top = _make_node(scene, 0, 0, z=3000)
        bot = _make_node(scene, 0, 0, z=0)
        east = _make_node(scene, 1000, 0, z=0)
        p = _make_pipe(scene, top, bot)  # riser
        _make_pipe(scene, bot, east)      # horizontal on bot
        p.update_label()
        assert p._riser_symbol.isVisible() is False

    def test_riser_symbol_shown_when_no_endpoint_visible(self, qapp, scene):
        """Riser symbol shows when neither endpoint node is visible."""
        top = _make_node(scene, 0, 0, z=3000)
        bot = _make_node(scene, 0, 0, z=0)
        p = _make_pipe(scene, top, bot)
        top.setVisible(False)
        bot.setVisible(False)
        p.update_label()
        assert p._riser_symbol.isVisible() is True

    def test_riser_symbol_at_z_overlay(self, qapp, scene):
        """Riser symbol should be at Z_OVERLAY."""
        top = _make_node(scene, 0, 0, z=3000)
        bot = _make_node(scene, 0, 0, z=0)
        p = _make_pipe(scene, top, bot)
        top.setVisible(False)
        bot.setVisible(False)
        p.update_label()
        assert p._riser_symbol.zValue() == Z_OVERLAY

    def test_riser_symbol_hidden_when_pipe_hidden(self, qapp, scene):
        """setVisible(False) on pipe cascades to riser symbol."""
        top = _make_node(scene, 0, 0, z=3000)
        bot = _make_node(scene, 0, 0, z=0)
        p = _make_pipe(scene, top, bot)
        top.setVisible(False)
        bot.setVisible(False)
        p.update_label()
        assert p._riser_symbol.isVisible() is True
        p.setVisible(False)
        assert p._riser_symbol.isVisible() is False

    def test_riser_symbol_cleanup_on_delete(self, qapp):
        """Riser symbol removed from scene when pipe is deleted."""
        from firepro3d.model_space import Model_Space
        ms = Model_Space()
        top = _make_node(ms, 0, 0, z=3000)
        bot = _make_node(ms, 0, 0, z=0)
        p = _make_pipe(ms, top, bot)
        top.setVisible(False)
        bot.setVisible(False)
        p.update_label()
        sym = p._riser_symbol
        ms.delete_pipe(p)
        assert sym.scene() is None


from firepro3d.fitting import Fitting


# ── Fitting visibility respects display overrides ───────────────────────


class TestFittingDisplayOverrides:

    def test_fitting_hidden_via_display_override(self, qapp, scene):
        """Fitting with _display_overrides['visible']=False stays hidden
        even after fitting.update()."""
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        _make_pipe(scene, n1, n2)
        n1.fitting._display_overrides["visible"] = False
        n1.fitting.update()
        assert n1.fitting.symbol.isVisible() is False

    def test_fitting_shown_after_override_cleared(self, qapp, scene):
        """Clearing _display_overrides restores fitting visibility."""
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        _make_pipe(scene, n1, n2)
        n1.fitting._display_overrides["visible"] = False
        n1.fitting.update()
        assert n1.fitting.symbol.isVisible() is False
        n1.fitting._display_overrides.pop("visible", None)
        n1.fitting.update()
        assert n1.fitting.symbol.isVisible() is True


# ── Fittings group in model browser ─────────────────────────────────────


class TestFittingsBrowserGroup:

    def _make_browser(self, scene):
        """Create a ModelBrowser attached to the given scene."""
        from firepro3d.model_browser import ModelBrowser
        browser = ModelBrowser()
        browser._scene = scene
        browser.refresh()
        return browser

    def _find_group(self, browser, prefix):
        """Find a top-level group item starting with prefix."""
        root = browser._tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            if item.text(0).startswith(prefix):
                return item
        return None

    def test_fittings_group_exists(self, qapp):
        """Browser should have a Fittings group."""
        from firepro3d.model_space import Model_Space
        ms = Model_Space()
        n1 = _make_node(ms, 0, 0)
        n2 = _make_node(ms, 1000, 0)
        n3 = _make_node(ms, 1000, 1000)
        _make_pipe(ms, n1, n2)
        _make_pipe(ms, n2, n3)
        n2.fitting.update()
        browser = self._make_browser(ms)
        group = self._find_group(browser, "Fittings")
        assert group is not None

    def test_fittings_count_excludes_no_fitting(self, qapp):
        """'no fitting' type nodes should not appear in the Fittings group."""
        from firepro3d.model_space import Model_Space
        ms = Model_Space()
        n1 = _make_node(ms, 0, 0)
        n2 = _make_node(ms, 1000, 0)
        n3 = _make_node(ms, 2000, 0)
        _make_pipe(ms, n1, n2)
        _make_pipe(ms, n2, n3)
        # n2 is collinear — fitting type is "no fitting"
        n2.fitting.update()
        assert n2.fitting.type == "no fitting"
        browser = self._make_browser(ms)
        group = self._find_group(browser, "Fittings")
        # n1 and n3 have "cap" fittings; n2 has "no fitting" → excluded
        assert group.childCount() == 2

    def test_fitting_item_stores_node_id(self, qapp):
        """Fitting tree items should store the parent node id."""
        from firepro3d.model_space import Model_Space
        ms = Model_Space()
        n1 = _make_node(ms, 0, 0)
        n2 = _make_node(ms, 1000, 0)
        _make_pipe(ms, n1, n2)
        browser = self._make_browser(ms)
        group = self._find_group(browser, "Fittings")
        assert group is not None
        # Check that at least one child stores a node id
        from firepro3d.model_browser import _ROLE_ENTITY
        child = group.child(0)
        eid = child.data(0, _ROLE_ENTITY)
        assert eid == id(n1) or eid == id(n2)
