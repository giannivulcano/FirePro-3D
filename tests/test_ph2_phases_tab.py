"""PH2 guards through the real MainWindow / Display Manager (AC6, AC7; ratified Q1-Q4 2026-11-12).

Raw sources: factory graphics = phase_registry.factory_statuses() / constants.PHASE_* (D-PH10);
"phases" project key = scene_io.py save/load (PH1); template = settings/template.py.
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
    pr.reset_project_table()


def test_save_phases_as_default_keeps_other_template_keys(main_window):
    from firepro3d.settings import template
    path = template.ensure_template()
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data["mark_patterns"] = {"Sprinkler": "SP-{n}"}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    rows = pr.factory_statuses()
    rows[1]["graphics"]["colour"] = "#ff0000"
    template.save_phases_as_default(rows)
    with open(path, encoding="utf-8") as fh:
        out = json.load(fh)
    assert out["phases"][1]["graphics"]["colour"] == "#ff0000"
    assert out["mark_patterns"] == {"Sprinkler": "SP-{n}"}


def _tab(dlg):
    return dlg._phases_tab


def test_a_edit_ok_save_load_keeps_graphics(main_window, tmp_path, monkeypatch):
    """Guard (a) AC7: tab edit through the real cells -> OK -> save -> load keeps the graphics."""
    from firepro3d import colour_picker as cp
    monkeypatch.setattr(cp, "pick_colour", lambda *a, **k: "#ff0000")
    dlg = main_window._make_display_manager("model")
    _tab(dlg).swatch("existing", "colour").clicked.emit()     # the cell's own pick flow
    _tab(dlg).cell("demolition", "opacity").setValue(40)       # the real spin box
    main_window._modified = False
    dlg.accept()
    assert main_window._modified                       # OK dirties the project (registry outside undo)
    path = str(tmp_path / "p.fpd")
    main_window.scene.save_to_file(path)
    pr.reset_project_table()
    assert main_window.scene.load_from_file(path)
    assert pr.project_table().graphics_of("existing")["colour"] == "#ff0000"
    assert pr.project_table().graphics_of("demolition")["opacity"] == 40


def test_b_cancel_leaves_registry_and_flag(main_window):
    """Guard (b): edit -> Cancel leaves the registry untouched and the project clean."""
    before = pr.to_list()
    main_window._modified = False
    dlg = main_window._make_display_manager("model")
    _tab(dlg).set_cell("existing", "colour", "#ff0000")
    _tab(dlg).set_cell("demolition", "fill", "#00ff00")
    dlg.reject()
    assert pr.to_list() == before
    assert main_window._modified is False


def test_g_ok_without_net_change_does_not_dirty(main_window):
    """Guard (g): OK installs only when the working copy differs (edit then undo the edit)."""
    main_window._modified = False
    dlg = main_window._make_display_manager("model")
    _tab(dlg).set_cell("existing", "colour", "#ff0000")
    _tab(dlg).set_cell("existing", "colour", "#808080")     # back to the factory value
    dlg.accept()
    assert main_window._modified is False


def test_h_new_row_locked_to_no_override(main_window):
    """Guard (h) Q2 / D-PH9: the New row is shown, every cell "—" and disabled."""
    dlg = main_window._make_display_manager("model")
    t = _tab(dlg)
    assert t.row_names() == ["New", "Existing", "Demolition"]
    for key in ("colour", "fill", "weight", "linetype", "opacity"):
        assert t.cell_text("new", key) == "—"
        assert not t.cell("new", key).isEnabled()
        assert t.cell("existing", key).isEnabled()
    assert "no override" in t.cell("new", "colour").toolTip().lower()
    dlg.reject()


def test_c_reset_all_on_phases_tab_restores_factory(main_window):
    """Guards (c) + (f): Reset All on the Phases tab resets it (key dispatch), nothing else."""
    dlg = main_window._make_display_manager("model")
    _tab(dlg).set_cell("existing", "colour", "#ff0000")
    lw_before = [(d.name, d.width_mm) for d in dlg._lw_defs]
    dlg._tabs.set_current("phases")
    dlg._reset_btn.click()                              # the real footer button
    dlg.accept()
    assert pr.to_list() == pr.factory_statuses()
    assert [(d.name, d.width_mm) for d in dlg._lw_defs] == lw_before


def test_d_set_as_default_seeds_new_project(main_window):
    """Guard (d) D-PH11: Set as Default on the Phases tab -> New project carries the edit."""
    dlg = main_window._make_display_manager("model")
    _tab(dlg).set_cell("existing", "colour", "#123456")
    dlg._tabs.set_current("phases")
    dlg._default_btn.click()                            # the real footer button
    dlg.reject()                                        # the template write is not undone by Cancel
    assert pr.project_table().graphics_of("existing")["colour"] == "#808080"
    main_window._modified = False
    main_window.new_file()
    assert pr.project_table().graphics_of("existing")["colour"] == "#123456"


def test_reset_and_default_enabled_on_phases_tab(main_window):
    dlg = main_window._make_display_manager("model")
    dlg._tabs.set_current("phases")
    assert dlg._reset_btn.isEnabled() and dlg._default_btn.isEnabled()
    dlg._tabs.set_current("materials")
    assert not dlg._reset_btn.isEnabled()
    dlg.reject()


def test_cells_show_factory_and_missing_linetype(main_window):
    """AC6 + D-PH20: factory rows; Demolition's linetype shows the missing state until LT7."""
    from firepro3d.linetype_choices import missing_label
    dlg = main_window._make_display_manager("model")
    t = _tab(dlg)
    names = [dlg._tabs.tabText(i) for i in range(dlg._tabs.count())]
    assert names.index("Phases") == names.index("Materials") + 1
    assert t.row_names() == ["New", "Existing", "Demolition"]
    assert t.cell_text("existing", "colour") == "#808080".upper()
    assert t.cell_text("new", "colour") == "\u2014"
    assert t.cell_text("new", "weight") == "\u2014"
    assert t.cell_text("new", "opacity") == "\u2014"
    assert t.cell_text("demolition", "linetype") == missing_label("Demolition")
    dlg.reject()


def test_e_colour_cell_no_override_clears_to_none(main_window, monkeypatch):
    """Guard (e) through the cell click: the picker's NO_OVERRIDE stores None, not ""."""
    from firepro3d import colour_picker as cp
    monkeypatch.setattr(cp, "pick_colour", lambda *a, **k: cp.NO_OVERRIDE)
    dlg = main_window._make_display_manager("model")
    t = _tab(dlg)
    t.swatch("existing", "fill").clicked.emit()
    assert t.table().graphics_of("existing")["fill"] is None
    monkeypatch.setattr(cp, "pick_colour", lambda *a, **k: cp.NO_FILL)
    t.swatch("demolition", "fill").clicked.emit()
    assert t.table().graphics_of("demolition")["fill"] == ""    # No Fill stays a real override
    dlg.reject()


def _exec_then(action):
    """Stand-in for the picker's modal exec(): run *action* on the REAL dialog, then OK."""
    from PyQt6.QtWidgets import QDialog

    def fake_exec(self):
        action(self)
        self.accept()                                     # the dialog's own OK path
        return QDialog.DialogCode.Accepted
    return fake_exec


def test_i1_ok_on_an_unset_cell_keeps_no_override(main_window, monkeypatch):
    """Seam I1: open a "—" colour cell, press OK untouched -> still None (not No Fill "")."""
    from firepro3d import colour_picker as cp
    dlg = main_window._make_display_manager("model")
    t = _tab(dlg)
    assert t.table().graphics_of("demolition")["colour"] is None     # factory (D-PH10)
    monkeypatch.setattr(cp.ColourPickerDialog, "exec", _exec_then(lambda d: None))
    t.swatch("demolition", "colour").clicked.emit()
    assert t.table().graphics_of("demolition")["colour"] is None
    assert t.cell_text("demolition", "colour") == "—"
    # A real pick from the unset state still lands: No Fill chip -> "".
    monkeypatch.setattr(cp.ColourPickerDialog, "exec",
                        _exec_then(lambda d: d._on_chip(cp.NO_FILL)))
    t.swatch("demolition", "colour").clicked.emit()
    assert t.table().graphics_of("demolition")["colour"] == ""
    dlg.reject()


def test_i2_folder_linetype_loaded_on_ok_survives_undo(main_window, tmp_path, monkeypatch):
    """Seam I2: OK loads a folder linetype outside undo (the registry ref is outside undo too)."""
    import os
    from firepro3d import app_data
    from firepro3d.linetype_choices import _folder_linetypes
    lt_dir = tmp_path / "lt"
    os.makedirs(lt_dir)
    rid = "user-linetypes-phdash"
    with open(lt_dir / "PhDash.fpdb", "w", encoding="utf-8") as fh:
        json.dump({"schema": 1, "id": rid, "library": "User", "series": "Linetypes",
                   "name": "PhDash", "version": 1, "primitives": [],
                   "repeat": {"pieces": []}}, fh)
    monkeypatch.setattr(app_data, "linetypes_dir", lambda: str(lt_dir))
    assert rid in [r[1] for r in _folder_linetypes()]                 # precondition
    ms = main_window.scene
    assert ms.block_registry.get(rid) is None
    dlg = main_window._make_display_manager("model")
    combo = _tab(dlg).cell("existing", "linetype")
    combo.setCurrentIndex(combo.findData(rid))
    dlg.accept()
    assert pr.project_table().graphics_of("existing")["linetype"] == rid
    assert ms.block_registry.get(rid) is not None                     # loaded on OK
    ms.undo()                                                         # Ctrl+Z after OK
    assert ms.block_registry.get(rid) is not None                     # not an undo step


def test_combo_and_opacity_cells_reach_the_registry_on_ok(main_window):
    """Review T4-5 Minor 1: the combo path (itemData -> slot) and opacity back to "—" (None)."""
    from firepro3d.paper_display import weight_names
    name = weight_names()[-1]                     # raw source: the project's weight names
    dlg = main_window._make_display_manager("model")
    t = _tab(dlg)
    weight = t.cell("existing", "weight")
    weight.setCurrentIndex(weight.findText(name))         # the real combo
    linetype = t.cell("demolition", "linetype")           # factory "Demolition" (D-PH10)
    assert linetype.currentIndex() != 0
    linetype.setCurrentIndex(0)                           # the leading "—" entry
    spin = t.cell("demolition", "opacity")
    spin.setValue(40)
    spin.setValue(spin.minimum())                         # back to "—": -1 must store None
    dlg.accept()
    g_existing = pr.project_table().graphics_of("existing")
    g_demo = pr.project_table().graphics_of("demolition")
    assert g_existing["weight"] == name                   # factory None -> a real name
    assert g_demo["linetype"] is None                     # factory "Demolition" -> "—"
    assert g_demo["opacity"] is None
