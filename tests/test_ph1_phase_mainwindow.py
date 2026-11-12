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


def _pre_ph1_template():
    """C1: a default.fpdt written before PH1 (no "phases" key), so the template
    overlay cannot restore the factory and the reset line is the only thing that does."""
    from firepro3d.settings import template
    path = template.ensure_template()
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data.pop("phases", None)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def _dirty_registry():
    rows = pr.PhaseRegistry().to_list()
    rows[2]["name"] = "Removed"
    pr.set_project_table(pr.PhaseRegistry.from_list(rows))


def test_new_project_resets_the_registry(main_window):
    _pre_ph1_template()
    _dirty_registry()
    main_window._modified = False
    main_window.new_file()
    assert pr.project_table().names() == ["New", "Existing", "Demolition"]


def test_startup_resets_the_registry(qapp, tmp_path, monkeypatch):
    from firepro3d import app_data
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    monkeypatch.setattr(MainWindow, "_maybe_offer_template_push", lambda self: None)
    _pre_ph1_template()
    _dirty_registry()
    w = MainWindow()
    try:
        assert pr.project_table().names() == ["New", "Existing", "Demolition"]
    finally:
        dispose_main_window(w)


def test_template_phases_survive_save_settings(main_window):
    w = main_window
    w.current_pipe_template.phase = "existing"
    w.current_sprinkler_template.phase = "demolition"
    w.current_opening_template.phase = "existing"                    # M4: template/opening
    w.save_settings()
    w.current_pipe_template.phase = "new"
    w.current_sprinkler_template.phase = w.current_opening_template.phase = "new"
    w.restore_settings()
    assert (w.current_pipe_template.phase, w.current_sprinkler_template.phase,
            w.current_opening_template.phase) == ("existing", "demolition", "existing")


def test_a_pre_ph1_pipe_template_demo_value_restores_as_demolition(main_window):
    w = main_window
    w.settings.setValue("template/pipe", {"Phase": "Demo"})          # what 0.99 saved
    w.restore_settings()
    assert w.current_pipe_template.phase == "demolition"


def test_catalog_pick_keeps_the_template_phase(main_window):
    """R7: the new catalog template takes the previous template's phase."""
    from firepro3d.sprinkler_db import _DEFAULTS
    w = main_window
    old = w.current_sprinkler_template
    old.phase = "existing"
    w._apply_sprinkler_template_from_record(_DEFAULTS[0])
    assert w.current_sprinkler_template is not old
    assert w.current_sprinkler_template.phase == "existing"


def test_auto_populate_heads_take_the_template_phase(main_window, monkeypatch):
    """R7: auto-populate heads take the CURRENT sprinkler template's phase."""
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QDialog
    import firepro3d.auto_populate_dialog as apd
    from firepro3d.room import Room
    from firepro3d.sprinkler_db import _DEFAULTS
    w = main_window
    sc = w.scene
    room = Room([QPointF(0, 0), QPointF(3000, 0), QPointF(3000, 2000), QPointF(0, 2000)])
    room._scale_manager_ref = sc.scale_manager
    sc.addItem(room); sc._rooms.append(room)
    lvl = sc.active_level

    class _AcceptDialog:                       # the modal dialog, accepted with fixed results
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def get_results(self):
            return {"positions": [QPointF(1000, 1000), QPointF(2000, 1000)],
                    "record": _DEFAULTS[0], "level": lvl, "ceiling_level": lvl,
                    "ceiling_offset": -50.8}
    monkeypatch.setattr(apd, "AutoPopulateDialog", _AcceptDialog)
    w.current_sprinkler_template.phase = "demolition"
    sc._auto_populate_room_dialog(room)                 # the real entry (model_space.py:8564)
    heads = list(sc.sprinkler_system.sprinklers)
    assert len(heads) == 2 and {h.phase for h in heads} == {"demolition"}
