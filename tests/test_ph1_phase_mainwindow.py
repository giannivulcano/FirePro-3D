"""PH1 through the real MainWindow: R6 underlay dirty flag (Task 3); PD4 / §3.7
template persistence, R7 sticky sprinkler phase (Task 7).

Raw sources: ruling R6 2026-11-11 ("editing an underlay's Phase marks the
project unsaved, not undoable"); the save prompt reads MainWindow._modified
(main.py _ask_save_changes); precedent tests/test_hf5_fill_types_persist.py:1-26.
"""
import json

import pytest

import main as _main_module
from firepro3d import phase_registry as pr
from firepro3d.view_3d import View3D          # heavy import required before MainWindow
_main_module.View3D = View3D
from main import MainWindow                   # noqa: E402
from tests._mainwindow_helpers import dispose_main_window  # noqa: E402


@pytest.fixture
def main_window(qapp, tmp_path, monkeypatch):
    from firepro3d import app_data
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))   # B5: no real default.fpdt
    monkeypatch.setattr(MainWindow, "_maybe_offer_template_push", lambda self: None)
    w = MainWindow()
    yield w
    dispose_main_window(w)


def test_underlay_phase_edit_marks_the_project_unsaved_not_undoable(main_window, tmp_path):
    from firepro3d.underlay import Underlay
    w = main_window
    data = Underlay(type="dxf", path=str(tmp_path / "no_such.dxf"))
    w.scene._create_underlay_placeholder(data)
    idx = next(i for i, (d, _it) in enumerate(w.scene.underlays) if d is data)
    w._modified = False
    pos = w.scene._undo_pos
    w.model_browser._on_underlay_selected(idx)          # the real panel route (main.py:507)
    w.prop_manager._prop_widgets["Phase"].setCurrentText("Existing")
    assert data.phase == "existing"
    assert w._modified is True                           # the save prompt's flag
    assert w.scene.is_dirty()
    assert w.scene._undo_pos == pos                      # not undoable (R6)
