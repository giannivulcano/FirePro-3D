"""Pipe polish D7-D10: single-node X / Y / Z rows through the real panel."""
import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication, QLabel

from firepro3d.dimension_edit import DimensionEdit
from firepro3d.gridline import GridlineItem
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space
from firepro3d.node import Node
from firepro3d.property_manager import PropertyManager


@pytest.fixture
def ms(qapp):
    s = Model_Space()
    s._level_manager = LevelManager()
    s.push_undo_state()
    yield s
    s.cleanup()


def _node(s, x, y, z=-50.8):
    n = Node(x, y, z)
    s.addItem(n)
    s.sprinkler_system.add_node(n)
    return n


def _panel(item):
    pm = PropertyManager()
    pm.show_properties(item)
    return pm


def _labels(pm):
    return [w.text() for w in pm.findChildren(QLabel)]


def _riser(s):
    low, high = _node(s, 100, 200, 0.0), _node(s, 100, 200, 3000.0)
    branch = _node(s, 900, 200, 3000.0)
    s.add_pipe(low, high, None, _propagate_ceiling=False)
    s.add_pipe(high, branch, None, _propagate_ceiling=False)
    s.push_undo_state()
    return low, high, branch


def test_x_edit_moves_stack_and_undo_restores(ms):
    low, high, branch = _riser(ms)
    _panel(high)._apply_property("X", 500.0)
    assert low.scenePos() == QPointF(500, 200)
    assert high.scenePos() == QPointF(500, 200)
    assert branch.scenePos() == QPointF(900, 200)
    assert low.pipes[0]._is_vertical() is True
    ms.undo()
    # undo reloads the scene, so the old node objects are gone: look at the new
    stack = [n for n in ms.sprinkler_system.nodes if n.scenePos().x() < 800]
    assert len(stack) == 2
    assert all(n.scenePos() == QPointF(100, 200) for n in stack)
    assert [n.scenePos() for n in ms.sprinkler_system.nodes
            if n.scenePos().x() > 800] == [QPointF(900, 200)]


def test_stack_with_a_sprinkler_head_carries_it(ms):
    """The head on a stack-mate rides its node; its panel row follows too."""
    low, high, _branch = _riser(ms)
    low.add_sprinkler()
    head = low.sprinkler
    head0 = head.scenePos()
    _panel(high)._apply_property("Y", 700.0)
    assert low.scenePos() == QPointF(100, -700)
    assert head.scenePos() - head0 == QPointF(0, -900)       # rode its node
    assert head.get_properties()["Y"]["value_mm"] == 700.0


def test_sloped_riser_is_not_in_the_stack(ms):
    """A pipe 50 mm off plumb is a slope, not a riser: only this node moves."""
    low, high = _node(ms, 0, 0, 0.0), _node(ms, 50, 0, 3000.0)
    ms.add_pipe(low, high, None, _propagate_ceiling=False)
    assert high.riser_stack() == [high]
    _panel(high)._apply_property("X", 400.0)
    assert high.scenePos() == QPointF(400, 0)
    assert low.scenePos() == QPointF(0, 0)


def test_y_row_reads_and_writes_up_positive(ms):
    n = _node(ms, 0, -250)
    assert n.get_properties()["Y"]["value_mm"] == 250.0
    _panel(n)._apply_property("Y", 400.0)
    assert n.scenePos().y() == -400.0


def test_y_of_zero_is_not_negative_zero(ms):
    n = _node(ms, 5, 0)
    y = n.get_properties()["Y"]["value_mm"]
    assert y == 0.0 and math.copysign(1.0, y) == 1.0


def test_gridline_uses_same_sign(ms):
    gl = GridlineItem(QPointF(0, -300), QPointF(0, -900))
    ms.addItem(gl)
    assert gl.get_properties()["Origin Y"]["value_mm"] == 300.0


def test_z_edit_solves_offset_keeps_level_and_undo(ms, monkeypatch):
    lvl = ms._level_manager.levels[1]            # Level 2: a non-zero elevation
    assert lvl.elevation != 0.0
    n = _node(ms, 0, 0, lvl.elevation - 50.8)
    n.ceiling_level = lvl.name
    other = _node(ms, 1000, 0, lvl.elevation - 50.8)
    other.ceiling_level = lvl.name
    pipe = ms.add_pipe(n, other, None, _propagate_ceiling=False)
    ms.push_undo_state()
    repaints = []
    monkeypatch.setattr(pipe, "update_geometry", lambda: repaints.append(1))
    _panel(n)._apply_property("Z", lvl.elevation + 300.0)
    assert n.z_pos == lvl.elevation + 300.0
    assert n.ceiling_level == lvl.name
    assert n.ceiling_offset == 300.0
    assert float(n._properties["Ceiling Offset"]["value"]) == 300.0
    assert other.z_pos == lvl.elevation - 50.8
    assert repaints
    assert n.z_pos - other.z_pos == pytest.approx(350.8)     # the pipe now slopes
    ms.undo()
    assert min(x.z_pos for x in ms.sprinkler_system.nodes) == lvl.elevation - 50.8


def test_z_edit_on_a_node_whose_level_is_missing_sets_z_only(ms):
    n = _node(ms, 0, 0, -50.8)
    n.ceiling_level = "No Such Level"
    ms.push_undo_state()
    _panel(n)._apply_property("Z", 1234.0)
    assert n.z_pos == 1234.0
    assert n.ceiling_level == "No Such Level"


def test_no_change_commit_is_no_undo_step(ms):
    n = _node(ms, 10, 20)
    ms.push_undo_state()
    depth = ms._undo_pos
    _panel(n)._apply_property("X", 10.0)
    assert n.scenePos().x() == 10.0
    assert ms._undo_pos == depth


def test_bare_focus_out_on_the_real_row_does_nothing(ms):
    """editingFinished on an untouched X / Y / Z editor: no move, no undo step."""
    n = _node(ms, 1234.5678, -20.125, 77.7)
    ms.push_undo_state()
    depth = ms._undo_pos
    pm = _panel(n)
    for key in ("X", "Y", "Z"):
        edit = pm._prop_widgets[key]
        assert isinstance(edit, DimensionEdit)
        edit.editingFinished.emit()
    assert n.scenePos() == QPointF(1234.5678, -20.125)
    assert n.z_pos == 77.7
    assert ms._undo_pos == depth


def test_typed_text_reaches_the_node_through_the_row(ms):
    """Typed text goes through the row's parser, one undo step."""
    n = _node(ms, 0, 0)
    ms.push_undo_state()
    depth = ms._undo_pos
    pm = _panel(n)
    edit = pm._prop_widgets["X"]
    edit.setText("2500 mm")
    edit.editingFinished.emit()
    assert n.scenePos().x() == 2500.0
    assert ms._undo_pos == depth + 1


def test_rows_hidden_on_multi_select_and_pipe_sections(ms):
    a, b = _node(ms, 0, 0), _node(ms, 1000, 0)
    p = ms.add_pipe(a, b, None, _propagate_ceiling=False)
    pm = PropertyManager()
    pm.show_properties([a, b])
    assert "X" not in _labels(pm)
    pm.show_properties(p)
    assert "X" not in _labels(pm)
    labels = _labels(_panel(a))
    assert "X" in labels and "Z" in labels and "Absolute Elev." not in labels


def test_multi_select_never_writes_a_position(ms):
    """Two sprinklers, or a node and a sprinkler: no X row, a commit moves none."""
    a, b, c = _node(ms, 0, 0), _node(ms, 1000, 0), _node(ms, 2000, 0)
    a.add_sprinkler()
    b.add_sprinkler()
    for targets in ([a, b], [a, c]):
        pm = PropertyManager()
        pm.show_properties(targets)
        assert not {"X", "Y", "Z"} & set(pm._prop_widgets)
        pm._apply_property("Mark", "M1")
    assert [n.scenePos().x() for n in (a, b, c)] == [0, 1000, 2000]


def test_offset_label_and_old_key(ms):
    n = _node(ms, 0, 0)
    labels = _labels(_panel(n))
    assert "Offset" in labels and "Ceiling Offset" not in labels
    n.set_property("Ceiling Offset", "-100")
    assert n.ceiling_offset == -100.0
    n.set_property("Offset", "-120")
    assert n.ceiling_offset == -120.0


def test_old_file_sprinkler_rows_do_not_move_a_node(ms):
    from firepro3d.sprinkler import Sprinkler
    t = Sprinkler(None)
    t.set_property("X", "5 mm")      # what load replays from a saved row
    assert "X" not in t._properties


def test_sprinkler_edit_moves_node_up_positive(ms):
    n = _node(ms, 0, 0)
    n.add_sprinkler()
    labels = _labels(_panel(n.sprinkler))
    assert labels.count("Y") == 1 and "Offset" in labels
    head = n.sprinkler.scenePos()
    _panel(n.sprinkler)._apply_property("Y", 700.0)
    assert n.scenePos().y() == -700.0
    assert n.sprinkler.scenePos() - head == QPointF(0, -700)


def test_template_copy_does_not_move_node(ms, monkeypatch):
    # bare-number display text (the no-ScaleManager fallback) parses as a float,
    # the worst case for a copy that would replay the X / Y / Z rows
    monkeypatch.setattr(Node, "_fmt", lambda self, mm: f"{mm:.1f}")
    a, b = _node(ms, 0, 0), _node(ms, 1000, 1000)
    a.add_sprinkler()
    b.add_sprinkler()
    b.sprinkler.set_properties(a.sprinkler)
    assert b.scenePos() == QPointF(1000, 1000)
