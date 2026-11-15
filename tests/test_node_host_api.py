"""Node elevation API (D1): host / rehost_keep_z / set_z / rederive."""
import pytest

from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space
from firepro3d.node import Node


@pytest.fixture
def ms(qapp):
    s = Model_Space()
    s._level_manager = LevelManager()
    s._level_manager.get("Level 2").elevation = 3000.0
    yield s
    s.cleanup()


def _n(s, where):
    """A node at z 100 on Level 1 / offset -50.8: in the scene, or off it."""
    n = Node(0, 0, 100.0)
    if where == "scene":
        s.addItem(n)
        s.sprinkler_system.add_node(n)
    return n


def _state(n):
    return (n.ceiling_level, round(n.ceiling_offset, 6), round(n.z_pos, 6))


@pytest.mark.parametrize("where,level,want", [
    ("scene", "Level 2", ("Level 2", -300.0, 2700.0)),
    ("scene", "Ghost", ("Ghost", -300.0, 100.0)),      # unresolved: z kept (Q2, Q12)
    ("off", "Level 2", ("Level 2", -300.0, 100.0)),    # no level manager: z kept
])
def test_host_keeps_offset_and_derives_z(ms, where, level, want):
    n = _n(ms, where)
    n.host(level, -300.0)
    assert _state(n) == want


@pytest.mark.parametrize("where,level,want", [
    ("scene", "Level 2", ("Level 2", -2900.0, 100.0)),
    ("scene", "Ghost", ("Ghost", -50.8, 100.0)),       # unresolved: offset and z kept
    ("off", "Level 2", ("Level 2", -50.8, 100.0)),
])
def test_rehost_keep_z_solves_the_offset(ms, where, level, want):
    n = _n(ms, where)
    n.rehost_keep_z(level)
    assert _state(n) == want


@pytest.mark.parametrize("where,level,want", [
    ("scene", "Level 1", ("Level 1", 500.0, 500.0)),
    ("scene", "Ghost", ("Ghost", -50.8, 500.0)),
    ("off", "Level 1", ("Level 1", -50.8, 500.0)),
])
def test_set_z_keeps_the_level(ms, where, level, want):
    n = _n(ms, where)
    if level != "Level 1":
        n.host(level, n.ceiling_offset)
    n.set_z(500.0)
    assert _state(n) == want


def test_rederive_follows_a_level_elevation_change(ms):
    n = _n(ms, "scene")
    n.host("Level 2", -300.0)
    ms._level_manager.get("Level 2").elevation = 4000.0
    n.rederive()
    assert _state(n) == ("Level 2", -300.0, 3700.0)


def test_no_change_skips_the_refresh(ms, monkeypatch):
    calls = []
    monkeypatch.setattr(Node, "refresh_nodes", staticmethod(lambda nodes: calls.append(list(nodes))))
    n = _n(ms, "scene")
    n.host("Level 1", -50.8)        # derives z -50.8 from 100: a change
    n.host("Level 1", -50.8)        # same again: no refresh
    n.set_z(n.z_pos)
    n.rederive()
    n.host("Level 2", -50.8, refresh=False)
    assert calls == [[n]]
