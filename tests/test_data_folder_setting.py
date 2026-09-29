"""Preferences → General → Data folder: persist + honor override."""
import os
from PyQt6.QtCore import QSettings


def test_data_folder_persists_across_panes(qapp, tmp_path):
    from firepro3d.settings import panes as pd

    pane = pd.GeneralPane()
    pane.load()
    target = str(tmp_path / "mydata")
    pane._data_folder_edit.setText(target)
    pane.apply()

    # A fresh pane reads the persisted value back.
    pane2 = pd.GeneralPane()
    pane2.load()
    assert pane2._data_folder_edit.text() == target

    # And app_data honors it (same conftest-isolated store).
    from firepro3d import app_data
    assert app_data.app_data_dir("blocks") == os.path.join(target, "blocks")


def test_blank_clears_override(qapp, tmp_path):
    from firepro3d.settings import panes as pd

    pane = pd.GeneralPane()
    pane.load()
    pane._data_folder_edit.setText(str(tmp_path / "x"))
    pane.apply()
    pane._data_folder_edit.clear()          # blank = use default
    pane.apply()

    stored = QSettings("GV", "FirePro3D").value(
        pd._DATA_ROOT_KEY, "?", type=str)
    assert stored == ""


def test_titleblock_dir_persists(qapp, tmp_path):
    """E2: the dedicated title-block library path persists to QSettings."""
    from firepro3d.settings import panes as pd

    pane = pd.GeneralPane()
    pane.load()
    tb = str(tmp_path / "tb")
    pane._tb_dir_edit.setText(tb)
    pane.apply()                                  # pure — no migration prompt

    pane2 = pd.GeneralPane()
    pane2.load()
    assert pane2._tb_dir_edit.text() == tb
    stored = QSettings("GV", "FirePro3D").value(
        "paths/titleblock_dir", "?", type=str)
    assert stored == tb
