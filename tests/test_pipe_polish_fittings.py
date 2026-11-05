"""Pipe polish D1, D2, H1: plan fitting symbols and through-riser hydraulics."""
import os

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.constants import DEFAULT_LEVEL
from firepro3d.equivalent_length import equivalent_length_ft
from firepro3d.fitting import Fitting
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space
from firepro3d.node import Node


@pytest.fixture
def scene(qapp):
    ms = Model_Space()
    ms._level_manager = LevelManager()
    yield ms
    ms.cleanup()


def _node(scene, x, y, z=0.0):
    n = Node(x, y, z)
    scene.addItem(n)
    scene.sprinkler_system.add_node(n)
    return n


def _pipe(scene, a, b):
    return scene.add_pipe(a, b, None, _propagate_ceiling=False)


def _plain(scene, ends):
    hub = _node(scene, 0, 0)
    for x, y in ends:
        _pipe(scene, hub, _node(scene, x, y))
    hub.fitting.update()
    return hub


PLAIN = [
    ("cap", [(1000, 0)]),
    ("90elbow", [(1000, 0), (0, 1000)]),
    ("45elbow", [(1000, 0), (-1000, 1000)]),
    ("tee", [(1000, 0), (-1000, 0), (0, 1000)]),
    ("wye", [(1000, 0), (-1000, 0), (1000, 1000)]),
    ("cross", [(1000, 0), (-1000, 0), (0, 1000), (0, -1000)]),
]


@pytest.mark.parametrize("ftype,ends", PLAIN, ids=[p[0] for p in PLAIN])
def test_plain_symbol_hidden_type_kept(scene, ftype, ends):
    hub = _plain(scene, ends)
    assert hub.fitting.type == ftype
    assert hub.fitting.symbol.isVisible() is False
    assert hub.fitting.clip_region_scene() is None


def test_display_apply_does_not_resurrect_plain(scene):
    from firepro3d.display_manager import _items_for_category_static
    hub = _plain(scene, [(1000, 0), (0, 1000)])
    assert hub.fitting in _items_for_category_static(scene, "Fitting")
    hub.fitting.update()
    hub.fitting.rescale()
    assert hub.fitting.symbol.isVisible() is False


def test_plain_symbol_leaves_no_pixels(scene):
    hub = _plain(scene, [(1000, 0), (0, 1000)])

    def render():
        img = QImage(200, 200, QImage.Format.Format_ARGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        scene.render(p, QRectF(0, 0, 200, 200), QRectF(-300, -300, 600, 600))
        p.end()
        return img

    hidden = render()
    Fitting.SHOW_PLAIN_SYMBOLS = True
    try:
        hub.fitting.update()
        shown = render()
    finally:
        Fitting.SHOW_PLAIN_SYMBOLS = False
    assert hidden != shown


def _stack(scene, ups, downs, branches, swap):
    node = _node(scene, 0, 0, 3000.0)
    partners = []
    verts = [(_node(scene, 0, 0, 6000.0)) for _ in range(ups)]
    verts += [(_node(scene, 0, 0, 0.0)) for _ in range(downs)]
    for other in (reversed(verts) if swap else verts):
        _pipe(scene, node, other)
        partners.append(other)
    ends = [(1000, 0), (-1000, 0)][:branches]
    for x, y in ends:
        _pipe(scene, node, _node(scene, x, y, 3000.0))
    return node, partners


CASES = [
    (1, 0, 1, "elbow_up", "elbow_up.svg"),
    (0, 1, 1, "elbow_down", "elbow_down.svg"),
    (1, 0, 2, "tee_up", "tee_up.svg"),
    (0, 1, 2, "tee_down", "tee_down.svg"),
    (1, 1, 0, "riser_through", "riser_passthrough.svg"),
    (1, 1, 1, "tee_vertical", "riser_passthrough.svg"),
    (1, 1, 2, "cross_vertical", "riser_passthrough.svg"),
]


@pytest.mark.parametrize("swap", [False, True])
@pytest.mark.parametrize("ups,downs,branches,ftype,svg", CASES)
def test_riser_symbol_per_case(scene, ups, downs, branches, ftype, svg, swap):
    node, partners = _stack(scene, ups, downs, branches, swap)
    for n in partners:
        n.setVisible(False)
    node.fitting.update()
    for p in node.pipes:
        p._update_riser_symbol()
    assert node.fitting.type == ftype
    assert node.fitting.symbol.isVisible() is True
    assert os.path.basename(node.fitting.symbol._svg_source_path) == svg
    risers = [p for p in node.pipes
              if p._riser_symbol is not None and p._riser_symbol.isVisible()]
    assert risers == []


@pytest.mark.parametrize("swap", [False, True])
@pytest.mark.parametrize("ups,downs,branches,_f,_s", CASES)
def test_exactly_one_symbol_at_xy(scene, ups, downs, branches, _f, _s, swap):
    node, partners = _stack(scene, ups, downs, branches, swap)
    stack = [node] + partners
    for n in stack:
        n.fitting.update()
    pipes = {p for n in stack for p in n.pipes}
    for p in pipes:
        p._update_riser_symbol()
    drawn = sum(n.fitting.symbol.isVisible() for n in stack)
    drawn += sum(1 for p in pipes
                 if p._riser_symbol is not None and p._riser_symbol.isVisible())
    assert drawn == 1


def test_bare_two_node_riser_keeps_pipe_symbol(scene):
    a = _node(scene, 0, 0, 3000.0)
    b = _node(scene, 0, 0, 0.0)
    p = _pipe(scene, a, b)
    a.fitting.update()
    b.fitting.update()
    p._update_riser_symbol()
    assert p._riser_symbol.isVisible() is True
    assert a.fitting.symbol.isVisible() is False
    assert b.fitting.symbol.isVisible() is False


@pytest.mark.parametrize("ftype,ft", [("riser_through", 0.0),
                                      ("tee_vertical", 5.0),
                                      ("cross_vertical", 5.0)])
def test_through_equivalent_length(ftype, ft):
    # Raw source: NFPA table rows in equivalent_length.py, 1" column.
    assert equivalent_length_ft(ftype, '1"Ø') == ft


def test_through_type_reaches_solver_loss(scene):
    node, _ = _stack(scene, 1, 1, 1, False)
    node.fitting.update()
    assert equivalent_length_ft(node.fitting.type, '1"Ø') == 5.0


# -- D2 on the interactive path: no hand-called update anywhere below ---------

def _census(scene):
    """Visible fitting symbols plus visible pipe riser symbols in the scene.
    Every vertical stack here shares x=0, y=0; horizontal branches draw no
    symbol, so the count is the count at the XY."""
    n = 0
    for node in scene.sprinkler_system.nodes:
        s = node.fitting.symbol
        if s is not None and s.scene() is scene and s.isVisible():
            n += 1
    for p in scene.sprinkler_system.pipes:
        r = p._riser_symbol
        if r is not None and r.scene() is scene and r.isVisible():
            n += 1
    return n


def _build(scene, zs, pipes, branches):
    """Nodes at the stack XY for each z, pipes added one by one through
    ``scene.add_pipe`` in the given order, then horizontal branches."""
    stack = [_node(scene, 0, 0, z) for z in zs]
    made = [_pipe(scene, stack[a], stack[b]) for a, b in pipes]
    for idx, k in branches:
        for x, y in [(1000, 0), (-1000, 0)][:k]:
            _pipe(scene, stack[idx], _node(scene, x, y, zs[idx]))
    return stack, made


SEQ_A = ([3000.0, 0.0, -3000.0], [(0, 1), (1, 2)], [])
SEQ_C = ([6000.0, 4000.0, 2000.0, 0.0],
         [(0, 1), (1, 2), (2, 3)], [(1, 1), (2, 2)])


def _ordered(seq, reverse):
    zs, pipes, branches = seq
    return zs, (list(reversed(pipes)) if reverse else pipes), branches


@pytest.mark.parametrize("reverse", [False, True], ids=["forward", "reverse"])
@pytest.mark.parametrize("seq", [SEQ_A, SEQ_C], ids=["A", "C"])
def test_incremental_build_draws_exactly_one(scene, seq, reverse):
    _build(scene, *_ordered(seq, reverse))
    assert _census(scene) == 1


def test_deleting_the_through_pipe_leaves_exactly_one(scene):
    stack, made = _build(scene, *SEQ_A)
    assert _census(scene) == 1
    scene.delete_pipe(made[1])
    assert _census(scene) == 1
    assert stack[1].fitting.symbol.isVisible() is False
    assert made[0]._riser_symbol.isVisible() is True


@pytest.mark.parametrize("reverse", [False, True], ids=["forward", "reverse"])
@pytest.mark.parametrize("seq", [SEQ_A, SEQ_C], ids=["A", "C"])
def test_undo_restore_path_draws_exactly_one(scene, seq, reverse):
    stack, _made = _build(scene, *_ordered(seq, reverse))
    # The codec rebuilds z_pos from ceiling_level + ceiling_offset, not from a
    # z set on the Node: pin each node's z through its ceiling offset on a
    # level at elevation 0, so the restored scene keeps the stack.
    level = scene._level_manager.get(DEFAULT_LEVEL)
    assert level is not None and level.elevation == 0
    built_z = {}
    for node in list(scene.sprinkler_system.nodes):
        z = node.z_pos
        node.ceiling_level = DEFAULT_LEVEL
        node.ceiling_offset = z
        built_z[(round(node.scenePos().x()), round(node.scenePos().y()), z)] = node
    state = scene._capture_network()
    scene._restore_network(state)
    restored = scene.sprinkler_system.nodes
    assert len(restored) == len(built_z)
    assert {(round(n.scenePos().x()), round(n.scenePos().y()), n.z_pos)
            for n in restored} == set(built_z)
    # the stack really is a stack: every interior stack node is a through node
    zs = seq[0]
    at_xy = {round(n.z_pos): n for n in restored
             if round(n.scenePos().x()) == 0 and round(n.scenePos().y()) == 0}
    assert sorted(at_xy) == sorted(round(z) for z in zs)
    for z in zs[1:-1]:
        assert Fitting.is_through(at_xy[round(z)]) is True
    assert _census(scene) == 1
