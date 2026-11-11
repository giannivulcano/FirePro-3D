"""Elevation parity D5 / AC7: Hide is one global flag, honoured by every section."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from tests.test_section_classification import _placed_scene
from tests.test_section_pipe_symbols import _pipe


def test_probe_hidden_pipe_stays_hidden_after_save_and_load(qapp, section_scene_for, tmp_path):
    """Step-1 probe P-E2 (design D5): the suspected network_codec load gap."""
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_space import Model_Space
    ms, _sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 8000.0)
    pipe = _pipe(ms, (2000.0, -1000.0, 2500.0), (6000.0, -1000.0, 2500.0))
    ms._hide_items([pipe])
    path = str(tmp_path / "hidden_pipe.fpd")
    assert ms.save_to_file(path, backup=False)
    ms2 = Model_Space()
    ms2._level_manager = LevelManager()
    ms2.load_from_file(path)
    (p2,) = ms2.sprinkler_system.pipes
    assert p2._display_overrides.get("visible") is False
    assert not p2.isVisible()


def test_hide_and_show_paths_emit_hidden_changed_but_not_scene_modified(qapp, section_scene_for):
    """D5: one signal per Hide / Show call (sections re-run their pass on it);
    Hide stays outside undo, so sceneModified never fires (display_manager.py:899)."""
    from firepro3d.pipe import Pipe
    ms, _sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 8000.0)
    pipe = _pipe(ms, (2000.0, -1000.0, 2500.0), (6000.0, -1000.0, 2500.0))
    hidden, modified = [], []
    ms.hiddenChanged.connect(lambda: hidden.append(1))
    ms.sceneModified.connect(lambda: modified.append(1))
    ms._hide_items([pipe])
    ms._show_items([pipe])
    ms._hide_all_of_type(Pipe)
    ms._show_all_hidden()
    assert len(hidden) == 4
    assert modified == []
    assert pipe._display_overrides.get("visible") is not False


def _pipe_pieces(sec, pipe):
    """Every section item drawn for *pipe*: line spans, symbols, the label."""
    from firepro3d.section_scene import _ElevPipeLabel, _ROLE_SOURCE
    return [i for i in sec.items()
            if i.data(_ROLE_SOURCE) is pipe
            or (isinstance(i, _ElevPipeLabel) and i.host is pipe)]


def _labelled_scene(section_scene_for):
    """A section over a model holding the shipped PipeLabel block (the
    fixture's isolated library has no System tier, so a label would be the
    placeholder)."""
    import os
    import firepro3d
    from firepro3d import block_library
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 8000.0)
    ms.register_block_definition(block_library.load_block_file(os.path.join(
        os.path.dirname(firepro3d.__file__), "system_blocks", "Tags", "PipeLabel.fpdb")))
    return ms, sec


def test_a_plan_hidden_pipe_is_absent_whole_from_a_rebuilt_section(qapp, section_scene_for):
    """AC7: hidden in plan -> every piece of the pipe (line, label) hidden in
    the section after a rebuild; the other pipe stays."""
    from firepro3d.section_scene import _ElevPipeLabel
    ms, sec = _labelled_scene(section_scene_for)
    pipe = _pipe(ms, (2000.0, -1000.0, 2500.0), (6000.0, -1000.0, 2500.0))
    other = _pipe(ms, (2000.0, -1000.0, 1500.0), (6000.0, -1000.0, 1500.0))
    sec.rebuild()
    pieces = _pipe_pieces(sec, pipe)
    assert any(isinstance(i, _ElevPipeLabel) for i in pieces) and len(pieces) >= 2
    ms._hide_items([pipe])
    sec.rebuild()
    pieces = _pipe_pieces(sec, pipe)
    assert pieces and not any(i.isVisible() for i in pieces)
    assert all(i.isVisible() for i in _pipe_pieces(sec, other))


def test_the_pass_reshows_without_a_rebuild_and_deselects_what_it_hides(qapp, section_scene_for):
    """D5: the pass alone (no rebuild) hides, deselects, and re-shows the same items."""
    from firepro3d.section_scene import _ElevProxyLine, _ROLE_SOURCE
    ms, sec = _labelled_scene(section_scene_for)
    pipe = _pipe(ms, (2000.0, -1000.0, 2500.0), (6000.0, -1000.0, 2500.0))
    sec.rebuild()
    line = next(i for i in sec.items()
                if isinstance(i, _ElevProxyLine) and i.data(_ROLE_SOURCE) is pipe)
    line.setSelected(True)
    pipe._display_overrides["visible"] = False      # the model flag alone, as a load leaves it
    sec._apply_hidden_pass()
    assert not line.isVisible() and not line.isSelected()
    pipe._display_overrides.pop("visible")
    sec._apply_hidden_pass()
    assert line.isVisible() and line.scene() is sec   # the same object: no rebuild ran


def test_a_hidden_wall_takes_its_opening_pieces_and_a_hidden_slab_its_mask(qapp, section_scene_for):
    """D5: decoration pieces (opening frame / void, slab mask) follow their source."""
    from firepro3d.section_scene import _ROLE_HIDE_SOURCE, _ROLE_SOURCE
    from tests.test_section_sheet_plot import _section_with_opening_and_slab
    ms, sec, op, slab = _section_with_opening_and_slab(section_scene_for)
    wall = op._wall

    def pieces(src):
        return [i for i in sec.items()
                if i.data(_ROLE_SOURCE) is src or i.data(_ROLE_HIDE_SOURCE) is src]

    assert len(pieces(op)) >= 2 and len(pieces(slab)) >= 2
    ms._hide_items([wall, slab])
    sec.rebuild()
    assert pieces(op) and not any(i.isVisible() for i in pieces(op))
    assert not any(i.isVisible() for i in pieces(slab))
