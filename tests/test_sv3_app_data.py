"""SV3 Task 1/2 -- schematics folder: key, default, override, migration,
System Settings row (schematics.md D-S5; concept SD7).

QSettings + the block / schematics folders are isolated by tests/conftest.py.
"""
from __future__ import annotations

import os

from PyQt6.QtCore import QSettings

from firepro3d import app_data


def test_schematic_dir_key_name():
    assert app_data.SCHEMATIC_DIR_KEY == "paths/schematic_dir"


def test_schematics_dir_defaults_under_data_root(qapp, tmp_path, monkeypatch):
    QSettings("GV", "FirePro3D").setValue(app_data.SCHEMATIC_DIR_KEY, "")
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    assert app_data.schematics_dir() == os.path.join(str(tmp_path), "schematics")


def test_schematics_dir_override_wins(qapp, tmp_path):
    QSettings("GV", "FirePro3D").setValue(
        app_data.SCHEMATIC_DIR_KEY, str(tmp_path / "tpl"))
    assert app_data.schematics_dir() == str(tmp_path / "tpl")


def test_conftest_isolates_the_schematics_folder(qapp):
    # The autouse fixture must keep every test off the user's real folder.
    raw = QSettings("GV", "FirePro3D").value(app_data.SCHEMATIC_DIR_KEY, "", type=str)
    assert raw and os.path.isabs(raw)
    assert app_data.schematics_dir() == raw


def test_migrate_data_root_carries_schematics(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    (old / "schematics" / "Risers").mkdir(parents=True)
    (old / "schematics" / "Risers" / "Riser.fpdb").write_text("{}")
    migrated = app_data.migrate_data_root(str(old), str(new))
    assert "schematics" in migrated
    assert (new / "schematics" / "Risers" / "Riser.fpdb").exists()


def test_data_root_has_content_sees_schematics(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    assert not app_data.data_root_has_content(str(root))
    (root / "schematics").mkdir()
    assert app_data.data_root_has_content(str(root))


# -- System Settings row (settings-dialog.md 4.5b; mirrors the End types row) --

def test_general_pane_schematics_row_round_trips(qapp, tmp_path):
    from firepro3d.settings import panes as pd
    pane = pd.GeneralPane()
    pane.load()
    assert pane._schem_dir_edit.toolTip() == (
        "Folder of schematic templates offered by New Schematic "
        "(default: <data folder>/schematics)")
    assert pane._schem_dir_edit.placeholderText() == "(data folder)/schematics"
    pane._schem_dir_edit.setText(str(tmp_path / "tpl"))
    pane.apply()
    assert QSettings("GV", "FirePro3D").value(
        app_data.SCHEMATIC_DIR_KEY, "", type=str) == str(tmp_path / "tpl")
    assert app_data.schematics_dir() == str(tmp_path / "tpl")
    pane2 = pd.GeneralPane()
    pane2.load()
    assert pane2._schem_dir_edit.text() == str(tmp_path / "tpl")
    pane2._schem_dir_edit.setText("changed")
    pane2.revert()
    assert pane2._schem_dir_edit.text() == str(tmp_path / "tpl")
    pane2._schem_dir_edit.clear()                   # blank = default
    pane2.apply()
    assert app_data.schematics_dir() == app_data.app_data_dir("schematics")


def test_general_pane_schematics_buttons_have_tooltips(qapp):
    from PyQt6.QtWidgets import QPushButton
    from firepro3d.settings import panes as pd
    pane = pd.GeneralPane()
    tips = {b.toolTip() for b in pane.findChildren(QPushButton)}
    assert "Choose the schematics folder" in tips
    assert "Use the default (<data folder>/schematics)" in tips
