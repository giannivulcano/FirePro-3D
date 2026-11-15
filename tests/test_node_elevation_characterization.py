"""Node elevation: drawing outcomes that must not change (Q9 characterization).

Each case drives the real placement path (press_pipe / _commit_pipe_at /
complete_confirmation, _press_sprinkler) and asserts every node's
(x, y, ceiling level, offset, z) plus the pipe count. Green at base 6d712eb2
and after every task of the node elevation plan.
"""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.node import Node
from firepro3d.pipe import Pipe
from firepro3d.sprinkler import Sprinkler

L1, L2 = "Level 1", "Level 2"


@pytest.fixture
def sc(shown_model_view):
    view, scene = shown_model_view
    # The scene ships "Level 2" at 3048 (add_level would rename a duplicate to
    # "Level 4"), so move the existing one to 3000.
    scene._level_manager.get(L2).elevation = 3000.0
    scene.set_mode("pipe", Pipe(None, None))
    return scene


def _set(s, n, level, off):
    """Test-side hosting (tests sit outside the single-writer scan)."""
    n.ceiling_level, n.ceiling_offset = level, off
    n.z_pos = s._level_manager.get(level).elevation + off


def _node(s, x, y, level, off):
    n = Node(x, y)
    s.addItem(n)
    s.sprinkler_system.add_node(n)
    _set(s, n, level, off)
    return n


def _run(s, a, b, la, oa, lb=None, ob=None):
    """A pipe a-b whose ends are hosted after add_pipe (base resets them)."""
    na, nb = _node(s, *a, la, oa), _node(s, *b, lb or la, oa if ob is None else ob)
    p = s.add_pipe(na, nb)
    _set(s, na, la, oa)
    _set(s, nb, lb or la, oa if ob is None else ob)
    p.update_geometry()
    return na, nb, p


def _press(s, x, y):
    s._pipe_ctl.press_pipe(None, QPointF(x, y), QPointF(x, y), None, None, None)


def _commit(s, x, y, item=None):
    return s._pipe_ctl._commit_pipe_at(QPointF(x, y), item)


def _sig(s):
    return sorted((round(n.scenePos().x()), round(n.scenePos().y()), n.ceiling_level,
                   round(n.ceiling_offset, 1), round(n.z_pos, 1))
                  for n in s.sprinkler_system.nodes)


def test_new_to_new(sc):
    _press(sc, 0, 0)
    assert _commit(sc, 3000, 0) is True
    assert _sig(sc) == [(0, 0, L1, -50.8, -50.8), (3000, 0, L1, -50.8, -50.8)]
    assert len(sc.sprinkler_system.pipes) == 1


def test_start_on_existing_node_adopts_its_ceiling(sc):
    _node(sc, 0, 0, L2, -3050.8)                 # z -50.8 = template z
    _press(sc, 0, 0)
    _commit(sc, 3000, 0)
    assert _sig(sc) == [(0, 0, L2, -3050.8, -50.8), (3000, 0, L2, -3050.8, -50.8)]


def test_end_on_existing_node(sc):
    _node(sc, 3000, 0, L1, -50.8)
    _press(sc, 0, 0)
    _commit(sc, 3000, 0)
    assert _sig(sc) == [(0, 0, L1, -50.8, -50.8), (3000, 0, L1, -50.8, -50.8)]
    assert len(sc.sprinkler_system.pipes) == 1


@pytest.mark.parametrize("result,sig,pipes", [
    ("riser", [(0, 0, L1, -600.0, -600.0), (0, 0, L1, -50.8, -50.8),
               (3000, 0, L1, -50.8, -50.8)], 2),
    ("match", [(0, 0, L1, -600.0, -600.0), (3000, 0, L1, -600.0, -600.0)], 1),
    ("template", [(0, 0, L1, -600.0, -600.0), (0, 0, L1, -50.8, -50.8),
                  (3000, 0, L1, -50.8, -50.8)], 1),
])
def test_mismatch_at_start(sc, result, sig, pipes):
    _node(sc, 0, 0, L1, -600.0)
    _press(sc, 0, 0)                             # dialog pending: nothing placed yet
    sc.complete_confirmation("elev_mismatch_start", result)
    _commit(sc, 3000, 0)
    assert _sig(sc) == sig
    assert len(sc.sprinkler_system.pipes) == pipes


@pytest.mark.parametrize("result,sig,pipes", [
    ("riser", [(0, 0, L1, -50.8, -50.8), (3000, 0, L1, -600.0, -600.0),
               (3000, 0, L1, -50.8, -50.8)], 2),
    ("match", [(0, 0, L1, -50.8, -50.8), (3000, 0, L1, -600.0, -600.0)], 1),
    ("template", [(0, 0, L1, -50.8, -50.8), (3000, 0, L1, -600.0, -600.0),
                  (3000, 0, L1, -50.8, -50.8)], 1),
])
def test_mismatch_at_end(sc, result, sig, pipes):
    _node(sc, 3000, 0, L1, -600.0)
    _press(sc, 0, 0)
    assert _commit(sc, 3000, 0) is True          # pending dialog
    sc.complete_confirmation("elev_mismatch_end", result)
    assert _sig(sc) == sig
    assert len(sc.sprinkler_system.pipes) == pipes


def test_split_pipe_at_start(sc):
    _run(sc, (0, -1000), (0, 1000), L2, -3050.8)
    _press(sc, 0, 0)                             # splits the run, template re-hosts the split node
    _commit(sc, 3000, 0)
    assert _sig(sc) == [(0, -1000, L2, -3050.8, -50.8), (0, 0, L1, -50.8, -50.8),
                        (0, 1000, L2, -3050.8, -50.8), (3000, 0, L1, -50.8, -50.8)]
    assert len(sc.sprinkler_system.pipes) == 3


def test_split_pipe_at_end(sc):
    _, _, p = _run(sc, (3000, -1000), (3000, 1000), L2, -3050.8)
    _press(sc, 0, 0)
    _commit(sc, 3000, 0, item=p)
    assert _sig(sc) == [(0, 0, L1, -50.8, -50.8), (3000, -1000, L2, -3050.8, -50.8),
                        (3000, 0, L1, -50.8, -50.8), (3000, 1000, L2, -3050.8, -50.8)]
    assert len(sc.sprinkler_system.pipes) == 3


def test_vertical_split(sc):
    _run(sc, (0, 0), (0, 0), L1, -1000.0, L1, 1000.0)
    _press(sc, 0, 0)                             # picks the low node (nearer the template z)
    sc.complete_confirmation("elev_mismatch_start", "template")
    _commit(sc, 3000, 0)
    assert _sig(sc) == [(0, 0, L1, -1000.0, -1000.0), (0, 0, L1, -50.8, -50.8),
                        (0, 0, L1, 1000.0, 1000.0), (3000, 0, L1, -50.8, -50.8)]
    assert len(sc.sprinkler_system.pipes) == 3


def test_continuous_polyline(sc):
    _press(sc, 0, 0)
    _commit(sc, 3000, 0)
    _commit(sc, 3000, 3000)
    assert _sig(sc) == [(0, 0, L1, -50.8, -50.8), (3000, 0, L1, -50.8, -50.8),
                        (3000, 3000, L1, -50.8, -50.8)]
    assert len(sc.sprinkler_system.pipes) == 2
    assert sc.pipe_start_node.scenePos() == QPointF(3000, 3000)


def test_sprinkler_in_empty_space_takes_the_template_ceiling(sc):
    t = Sprinkler(None)
    t.set_property("Ceiling Offset", -300.0)     # a node-less template stores raw mm
    sc.current_template = t                      # what _press_sprinkler reads
    sc._press_sprinkler(None, QPointF(5000, 0), QPointF(5000, 0), None, None, None)
    assert _sig(sc) == [(5000, 0, L1, -300.0, -300.0)]
