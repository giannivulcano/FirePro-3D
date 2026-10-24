"""SB2b G-M1 -- every creation site mints; load / undo never mint; pipe split keeps n1's Mark."""
import json

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from firepro3d import marks
from firepro3d.constants import DEFAULT_CEILING_OFFSET_MM, DEFAULT_LEVEL
from firepro3d.pipe import Pipe
from firepro3d.sprinkler import Sprinkler
from firepro3d.wall import WallSegment


def _click(view, scene_pt):
    vp = view.viewport()
    p = view.mapFromScene(scene_pt)
    for et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        ev = QMouseEvent(et, p.toPointF(), vp.mapToGlobal(p).toPointF(),
                         Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(vp, ev)


def _marks(scene, cat):
    return [marks.get_mark(i) for i in marks.items_of_category(scene, cat)]


def _pipe_template():
    # A raw Pipe(None, None) has None ceiling offsets; set_mode("pipe", t) callers
    # use the normalized defaults (see tests/test_pipe_slice_parity.py).
    t = Pipe(None, None)
    t.node1_ceiling_level = DEFAULT_LEVEL
    t.node1_ceiling_offset = DEFAULT_CEILING_OFFSET_MM
    t.node2_ceiling_level = DEFAULT_LEVEL
    t.node2_ceiling_offset = DEFAULT_CEILING_OFFSET_MM
    return t


def test_wall_tool_mints_sequentially(qapp, shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("wall")
    _click(view, QPointF(0, 0)); _click(view, QPointF(1000, 0))
    scene.set_mode("wall")                  # single-placement returns to Select
    _click(view, QPointF(0, 2000)); _click(view, QPointF(1000, 2000))
    assert _marks(scene, "Wall") == ["WL1", "WL2"]


def test_wall_rect_mints_four(qapp, shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("wall_rect")
    _click(view, QPointF(0, 0)); _click(view, QPointF(3000, 0))
    _click(view, QPointF(3000, 2000))
    assert sorted(_marks(scene, "Wall")) == ["WL1", "WL2", "WL3", "WL4"]


def test_door_tool_mints(qapp, shown_model_view):
    view, scene = shown_model_view
    w = WallSegment(QPointF(0, 0), QPointF(3000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    scene.set_mode("opening", template="door_914")
    _click(view, QPointF(800, 0))
    scene.set_mode("opening", template="door_914")
    _click(view, QPointF(2200, 0))
    assert _marks(scene, "Door") == ["D1", "D2"]


@pytest.mark.skip(reason="needs Task 8 Level.number")
def test_room_tool_mints_level_pattern(qapp, shown_model_view):
    view, scene = shown_model_view
    scene._level_manager.levels[0].number = 1          # Task 8 field
    scene.set_mode("room_manual")
    for x, y in ((0, 0), (4000, 0), (4000, 3000), (0, 3000)):
        _click(view, QPointF(x, y))
    _click(view, QPointF(0, 0))                          # close the boundary
    assert _marks(scene, "Room") == ["101"]
    assert scene._rooms[0].name == "Room 1"


def test_room_manual_tool_mints_with_pattern_before_level_numbers(qapp, shown_model_view):
    # Level.number lands in Task 8; until then {level} prints empty -> "01".
    view, scene = shown_model_view
    scene.set_mode("room_manual")
    for x, y in ((0, 0), (4000, 0), (4000, 3000), (0, 3000)):
        _click(view, QPointF(x, y))
    _click(view, QPointF(0, 0))                          # close the boundary
    assert len(scene._rooms) == 1
    assert _marks(scene, "Room") == ["01"]
    assert scene._rooms[0].name == "Room 1"


def test_pipe_tool_mints(qapp, shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("pipe", _pipe_template())
    _click(view, QPointF(0, 0)); _click(view, QPointF(1000, 0))
    assert _marks(scene, "Pipe") == ["P1"]


def test_sprinkler_on_pipe_splits_n1_half_keeps(qapp, shown_model_view):
    view, scene = shown_model_view
    n1 = scene.add_node(0, 0); n2 = scene.add_node(2000, 0)
    pipe = scene.add_pipe(n1, n2)
    assert marks.get_mark(pipe) == "P1"
    scene.set_mode("sprinkler", Sprinkler(None))
    _click(view, QPointF(1000, 0))
    pipes = list(scene.sprinkler_system.pipes)
    assert len(pipes) == 2
    by_end = {(p.node1 is n1 or p.node2 is n1): marks.get_mark(p) for p in pipes}
    assert by_end == {True: "P1", False: "P2"}
    assert _marks(scene, "Sprinkler") == ["S1"]


def test_blank_pattern_mints_blank(qapp, shown_model_view):
    view, scene = shown_model_view
    scene.mark_patterns["Wall"] = ""
    scene.set_mode("wall")
    _click(view, QPointF(0, 0)); _click(view, QPointF(1000, 0))
    assert _marks(scene, "Wall") == [""]


def test_load_and_undo_never_mint(qapp, shown_model_view, tmp_path):
    view, scene = shown_model_view
    n1 = scene.add_node(0, 0); n2 = scene.add_node(2000, 0)
    p = scene.add_pipe(n1, n2)
    marks.set_mark(p, "KEEP")
    scene.push_undo_state()
    scene.undo(); scene.redo()
    assert _marks(scene, "Pipe") == ["KEEP"]
    f = tmp_path / "k.fpd"
    scene.save_to_file(str(f))
    scene.load_from_file(str(f))
    assert _marks(scene, "Pipe") == ["KEEP"]


def test_old_file_pipes_stay_blank(qapp, shown_model_view, tmp_path):
    view, scene = shown_model_view
    n1 = scene.add_node(0, 0); n2 = scene.add_node(2000, 0)
    scene.add_pipe(n1, n2)
    f = tmp_path / "old.fpd"
    scene.save_to_file(str(f))
    rec = json.loads(f.read_text(encoding="utf-8"))
    for p in rec["pipes"]:
        p["properties"].pop("Mark", None)
    f.write_text(json.dumps(rec), encoding="utf-8")
    scene.load_from_file(str(f))
    assert _marks(scene, "Pipe") == [""]
