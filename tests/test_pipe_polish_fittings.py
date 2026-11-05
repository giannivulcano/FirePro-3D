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


# ---- VC9 B1: a riser through several floors, per plan view -------------------

def _floors(scene):
    """Riser through three levels, two branches on each floor."""
    lm = scene._level_manager
    names = (lm.levels[0].name, "L2", "L3")
    lm.add_level("L2", 3000.0)
    lm.add_level("L3", 6000.0)

    def at(x, z, name):
        n = Node(x, 0, z)
        n.level = n.ceiling_level = name
        n.ceiling_offset = 0.0
        scene.addItem(n)
        scene.sprinkler_system.add_node(n)
        return n

    def run(a, b, name):
        scene.add_pipe(a, b, None, _propagate_ceiling=False).level = name

    stack = [at(0, z, nm) for z, nm in zip((0.0, 3000.0, 6000.0), names)]
    run(stack[0], stack[1], names[0])
    run(stack[1], stack[2], names[1])
    for nd, nm in zip(stack, names):
        for x in (1000, -1000):
            run(nd, at(x, nd.z_pos, nm), nm)
    return names


def _symbols_per_view(scene, names):
    """{level: [(fitting type, z), ...]} of symbols drawn in each plan view."""
    lm = scene._level_manager
    out = {}
    for nm in names:
        lvl = lm.get(nm)
        lm.apply_to_scene(scene, nm, view_height=lvl.elevation + lvl.view_top,
                          view_depth=lvl.elevation + lvl.view_bottom)
        drawn = [(n.fitting.type, round(n.z_pos))
                 for n in scene.sprinkler_system.nodes if n.fitting.symbol.isVisible()]
        drawn += [("pipe_riser", round(p.node1.z_pos))
                  for p in scene.sprinkler_system.pipes
                  if p._riser_symbol is not None and p._riser_symbol.isVisible()]
        out[nm] = drawn
    return out


def _expected(names):
    return {names[0]: [("tee_up", 0)],
            names[1]: [("cross_vertical", 3000)],
            names[2]: [("tee_down", 6000)]}


def test_each_floor_draws_its_own_riser_symbol(shown_model_view):
    _view, scene = shown_model_view
    names = _floors(scene)
    assert _symbols_per_view(scene, names) == _expected(names)


def test_each_floor_keeps_its_symbol_after_open_and_undo(shown_model_view, tmp_path):
    _view, scene = shown_model_view
    names = _floors(scene)
    path = str(tmp_path / "floors.fpd")
    scene.save_to_file(path, backup=False)
    assert scene.load_from_file(path) is not False
    assert _symbols_per_view(scene, names) == _expected(names)
    scene.push_undo_state()
    scene.sprinkler_system.nodes[0].set_property("Ceiling Offset", "1")
    scene.push_undo_state()
    scene.undo()
    assert _symbols_per_view(scene, names) == _expected(names)


def test_view_spanning_two_floors_draws_the_top_one_only(shown_model_view):
    _view, scene = shown_model_view
    names = _floors(scene)
    scene._level_manager.apply_to_scene(scene, names[1], view_height=7000.0,
                                        view_depth=2000.0)
    drawn = [n for n in scene.sprinkler_system.nodes if n.fitting.symbol.isVisible()]
    assert [round(n.z_pos) for n in drawn] == [6000]


def test_level_switch_keeps_a_row_hidden_in_the_display_manager(shown_model_view):
    from firepro3d.display_manager import _apply_fitting
    _view, scene = shown_model_view
    names = _floors(scene)
    assert _symbols_per_view(scene, names) == _expected(names)
    hub = next(n for n in scene.sprinkler_system.nodes
               if round(n.z_pos) == 3000 and n.scenePos().x() == 0)
    _apply_fitting(hub.fitting, None, 1.0, 100, False)
    assert _symbols_per_view(scene, names)[names[1]] == []
    hub.fitting.update()
    assert hub.fitting.symbol.isVisible() is False
