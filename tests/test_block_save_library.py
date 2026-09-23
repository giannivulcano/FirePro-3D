"""Slice 2 (block polish, 2026-09-23): Save dialog library folders + house
chrome, block-library location setting, rename-on-collision (L141).

Decisions (user grill): dropdowns list on-disk Library/Series folders UNION the
project's own; "+" opens an inline name field and creates the folder on disk
immediately; a Save-to-Library filename collision offers Overwrite / Rename /
Cancel; "Also save to library" defaults ON and remembers the last choice; the
library location is a System Settings > General > Data folder row.
"""
from __future__ import annotations

import os

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QTabWidget

from firepro3d import block_library as bl
from firepro3d.block_definition import BlockDefinition


def _def(name="A", library="L", series="S"):
    return BlockDefinition.new(name=name, library=library, series=series,
                               primitives=[{"type": "draw_line", "pt1": [0, 0],
                                            "pt2": [100, 0], "color": "#ffffff",
                                            "lineweight": 1.0}],
                               origin=(0.0, 0.0))


# ── block_library folder API ────────────────────────────────────────────────

def test_list_folders_reads_the_two_tier_tree(tmp_path):
    (tmp_path / "Fire" / "Valves").mkdir(parents=True)
    (tmp_path / "Fire" / "Heads").mkdir()
    (tmp_path / "Civil").mkdir()
    (tmp_path / "stray.txt").write_text("x")
    assert bl.list_folders(str(tmp_path)) == {"Civil": [], "Fire": ["Heads", "Valves"]}


def test_list_folders_missing_root_is_empty(tmp_path):
    assert bl.list_folders(str(tmp_path / "nope")) == {}


def test_create_folder_makes_library_and_series(tmp_path):
    bl.create_folder("New Lib", root=str(tmp_path))
    bl.create_folder("New Lib", "Ser/1", root=str(tmp_path))
    assert bl.list_folders(str(tmp_path)) == {"New Lib": ["Ser_1"]}


def test_find_collision_reports_a_different_id_only(tmp_path):
    a = _def("N")
    bl.save_to_library(a, root=str(tmp_path))
    assert bl.find_collision(a.id, "L", "S", "N", root=str(tmp_path)) is None
    assert bl.find_collision("other", "L", "S", "N", root=str(tmp_path)) == "N"
    assert bl.find_collision("other", "L", "S", "M", root=str(tmp_path)) is None


# ── Block-library location override ─────────────────────────────────────────

def test_block_library_dir_honours_override(qapp, tmp_path, monkeypatch):
    from firepro3d import app_data
    target = str(tmp_path / "shared_blocks")
    QSettings("GV", "FirePro3D").setValue(app_data.BLOCK_DIR_KEY, target)
    try:
        assert app_data.block_library_dir() == target
        d = _def("Z")
        path = bl.save_to_library(d)               # default root -> override
        assert path.startswith(target)
    finally:
        QSettings("GV", "FirePro3D").setValue(app_data.BLOCK_DIR_KEY, "")
    assert app_data.block_library_dir() == app_data.app_data_dir("blocks")


def test_general_pane_block_library_row_persists(qapp, tmp_path, monkeypatch):
    from firepro3d import preferences_dialog as pd
    import firepro3d.settings.panes as panes_mod
    ini = str(tmp_path / "s.ini")
    factory = lambda *a, **k: QSettings(ini, QSettings.Format.IniFormat)
    monkeypatch.setattr(pd, "QSettings", factory)
    monkeypatch.setattr(panes_mod, "QSettings", factory)
    pane = pd.GeneralPane()
    pane.load()
    pane._block_dir_edit.setText(str(tmp_path / "blk"))
    pane.apply()
    pane2 = pd.GeneralPane()
    pane2.load()
    assert pane2._block_dir_edit.text() == str(tmp_path / "blk")
    pane2._block_dir_edit.setText("changed")
    pane2.revert()
    assert pane2._block_dir_edit.text() == str(tmp_path / "blk")


# ── CreatableSelector (ui_kit) ──────────────────────────────────────────────

def test_creatable_selector_inline_create(qapp):
    from firepro3d.ui_kit import CreatableSelector
    w = CreatableSelector()
    w.set_items(["A", "B"])
    got = []
    w.createRequested.connect(got.append)
    assert w.add_button.toolTip()
    assert not w.name_edit.isVisibleTo(w)
    w.add_button.click()
    assert w.name_edit.isVisibleTo(w)
    QTest.keyClicks(w.name_edit, "New One")
    QTest.keyClick(w.name_edit, Qt.Key.Key_Return)
    assert got == ["New One"] and not w.name_edit.isVisibleTo(w)
    w.add_button.click()
    QTest.keyClicks(w.name_edit, "zzz")
    QTest.keyClick(w.name_edit, Qt.Key.Key_Escape)
    assert got == ["New One"] and not w.name_edit.isVisibleTo(w)


# ── BlockSaveDialog ─────────────────────────────────────────────────────────

def _dialog(tmp_path, **kw):
    from firepro3d.block_editor import BlockSaveDialog
    tree = kw.pop("tree", {"Fire": ["Heads", "Valves"], "Civil": ["Pipes"]})
    return BlockSaveDialog(None, library_tree=tree, root=str(tmp_path), **kw)


def test_save_dialog_series_follow_library(qapp, tmp_path):
    dlg = _dialog(tmp_path)
    dlg.library_combo.setCurrentText("Civil")
    assert [dlg.series_combo.itemText(i) for i in range(dlg.series_combo.count())] == ["Pipes"]
    dlg.library_combo.setCurrentText("Fire")
    assert [dlg.series_combo.itemText(i) for i in range(dlg.series_combo.count())] == ["Heads", "Valves"]


def test_save_dialog_plus_creates_folder_on_disk_and_selects_it(qapp, tmp_path):
    dlg = _dialog(tmp_path)
    dlg.library_combo.setCurrentText("Fire")
    dlg.series_sel.createRequested.emit("Hangers")
    assert (tmp_path / "Fire" / "Hangers").is_dir()
    assert dlg.series_combo.currentText() == "Hangers"
    dlg.library_sel.createRequested.emit("Mech")
    assert (tmp_path / "Mech").is_dir()
    assert dlg.library_combo.currentText() == "Mech"
    assert dlg.series_combo.count() == 0


def test_save_dialog_uses_house_toggles_and_remembers_save_choice(qapp, tmp_path):
    from firepro3d.ui_kit import ToggleSwitch, Selector
    dlg = _dialog(tmp_path)
    assert isinstance(dlg.save_to_library_cb, ToggleSwitch)
    assert isinstance(dlg.library_combo, Selector)
    assert dlg.save_to_library_cb.isChecked() is True          # default ON
    dlg.save_to_library_cb.setChecked(False)
    dlg.name_edit.setText("N")
    dlg.library_combo.setCurrentText("Fire")
    dlg._on_save()
    assert _dialog(tmp_path).save_to_library_cb.isChecked() is False


def _colliding_dialog(tmp_path, monkeypatch, choice):
    import firepro3d.block_editor as be
    bl.save_to_library(_def("N", "Fire", "Valves"), root=str(tmp_path))
    monkeypatch.setattr(be, "themed_choice", lambda *a, **k: choice, raising=False)
    import firepro3d.themed_message as tm
    monkeypatch.setattr(tm, "themed_choice", lambda *a, **k: choice)
    dlg = _dialog(tmp_path, collision_id="mine")
    dlg.name_edit.setText("N")
    dlg.library_combo.setCurrentText("Fire")
    dlg.series_combo.setCurrentText("Valves")
    dlg._on_save()
    return dlg


def test_collision_overwrite_accepts_with_overwrite(qapp, tmp_path, monkeypatch):
    dlg = _colliding_dialog(tmp_path, monkeypatch, "overwrite")
    assert dlg.result() == dlg.DialogCode.Accepted
    assert dlg.values()["overwrite"] is True


def test_collision_rename_keeps_dialog_open_on_name(qapp, tmp_path, monkeypatch):
    dlg = _colliding_dialog(tmp_path, monkeypatch, "rename")
    assert dlg.result() != dlg.DialogCode.Accepted
    assert dlg.name_edit.selectedText() == "N"
    assert dlg.error_label.isVisibleTo(dlg) and "N" in dlg.error_label.text()


def test_collision_cancel_rejects(qapp, tmp_path, monkeypatch):
    dlg = _colliding_dialog(tmp_path, monkeypatch, "cancel")
    assert dlg.result() == dlg.DialogCode.Rejected


# ── Editor Save wiring ──────────────────────────────────────────────────────

def test_editor_save_lists_disk_and_project_libraries(qapp, tmp_path, monkeypatch):
    from firepro3d.model_space import Model_Space
    import firepro3d.block_editor as be
    (tmp_path / "Disk" / "S1").mkdir(parents=True)
    monkeypatch.setattr(bl, "_root", lambda root: root if root is not None else str(tmp_path))
    project = Model_Space()
    project.register_block_definition(_def("P", "Proj", "PS"))
    seen = {}

    class _Spy:
        def __init__(self, *a, library_tree=None, **k):
            seen["tree"] = library_tree
        def exec(self):
            return 0
    monkeypatch.setattr(be, "BlockSaveDialog", _Spy)
    tabs = QTabWidget()
    w = be.BlockEditorManager(tabs, project).open_new()
    from PyQt6.QtCore import QPointF
    from firepro3d.geometry_2d import LineItem
    w._add_primitive(LineItem(QPointF(0, 0), QPointF(10, 0)))
    w.save()
    assert seen["tree"] == {"Disk": ["S1"], "Proj": ["PS"]}


def test_editor_save_overwrite_flag_reaches_the_library(qapp, tmp_path, monkeypatch):
    from firepro3d.model_space import Model_Space
    import firepro3d.block_editor as be
    other = _def("N", "L", "S")
    bl.save_to_library(other, root=str(tmp_path))
    monkeypatch.setattr(bl, "_root", lambda root: root if root is not None else str(tmp_path))

    class _Fake:
        def __init__(self, *a, **k): pass
        def exec(self):
            from PyQt6.QtWidgets import QDialog
            return QDialog.DialogCode.Accepted
        def values(self):
            return {"name": "N", "library": "L", "series": "S",
                    "save_to_library": True, "replace_source": True,
                    "overwrite": True}
    monkeypatch.setattr(be, "BlockSaveDialog", _Fake)
    tabs, project = QTabWidget(), Model_Space()
    w = be.BlockEditorManager(tabs, project).open_new()
    from PyQt6.QtCore import QPointF
    from firepro3d.geometry_2d import LineItem
    w._add_primitive(LineItem(QPointF(0, 0), QPointF(10, 0)))
    defn = w.save()
    assert bl.find_collision(defn.id, "L", "S", "N", root=str(tmp_path)) is None


# ── Block Manager Save-to-Library rename (L141) ─────────────────────────────

def test_manager_collision_rename_saves_under_new_name(model_space, qapp, tmp_path, monkeypatch):
    from firepro3d.block_manager import BlockManagerDialog
    import firepro3d.themed_message as tm
    theirs = _def("N")
    bl.save_to_library(theirs, root=str(tmp_path))
    mine = _def("N")
    model_space.register_block_definition(mine)
    monkeypatch.setattr(tm, "themed_choice", lambda *a, **k: "rename")
    monkeypatch.setattr(tm, "themed_input_text", lambda *a, **k: ("N2", True))

    class _MW: settings = None
    dlg = BlockManagerDialog(model_space, _MW(), apply_stylesheet=False, root=str(tmp_path))
    src_row = dlg.model.row_for_id(mine.id)
    dlg.view.setCurrentIndex(dlg.proxy.mapFromSource(dlg.model.index(src_row, 0)))
    dlg._save_to_library()
    assert mine.name == "N2"
    assert os.path.isfile(tmp_path / "L" / "S" / "N2.fpdb")
    assert bl.find_collision(theirs.id, "L", "S", "N", root=str(tmp_path)) is None
    dlg.close()


def test_enter_in_the_new_folder_field_commits_and_keeps_dialog_open(qapp, tmp_path):
    # Smoke 2026-09-23: Enter created the folder AND pressed the dialog's
    # default Save button (QLineEdit ignores Return after returnPressed).
    dlg = _dialog(tmp_path)
    dlg.name_edit.setText("N")
    dlg.show()
    QTest.qWaitForWindowExposed(dlg)
    try:
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            dlg.library_sel.add_button.click()
            field = dlg.library_sel.name_edit
            QTest.keyClicks(field, f"Lib{int(key)}")
            QTest.keyClick(field, key)
            assert (tmp_path / f"Lib{int(key)}").is_dir()
            assert dlg.isVisible() and dlg.result() != dlg.DialogCode.Accepted
    finally:
        dlg.close()
