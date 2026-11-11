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
