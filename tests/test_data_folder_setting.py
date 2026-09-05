"""Preferences → General → Data folder: persist + honor override."""
import os
from PyQt6.QtCore import QSettings


def _ini_settings(monkeypatch, ini_path):
    """Point the preferences pane's QSettings at a temp INI (no registry writes)."""
    from firepro3d import preferences_dialog as pd
    monkeypatch.setattr(
        pd, "QSettings",
        lambda *a, **k: QSettings(ini_path, QSettings.Format.IniFormat))


def test_data_folder_persists_across_panes(qapp, tmp_path, monkeypatch):
    from firepro3d import preferences_dialog as pd
    ini = str(tmp_path / "s.ini")
    _ini_settings(monkeypatch, ini)

    pane = pd.GeneralPane()
    pane.load()
    target = str(tmp_path / "mydata")
    pane._data_folder_edit.setText(target)
    pane.apply()

    # A fresh pane reads the persisted value back.
    pane2 = pd.GeneralPane()
    pane2.load()
    assert pane2._data_folder_edit.text() == target

    # And app_data honors it (read the same INI for the override).
    from firepro3d import app_data
    monkeypatch.setattr(
        app_data, "_configured_root",
        lambda: QSettings(ini, QSettings.Format.IniFormat).value(
            app_data.ROOT_KEY, "", type=str) or None)
    assert app_data.app_data_dir("blocks") == os.path.join(target, "blocks")


def test_blank_clears_override(qapp, tmp_path, monkeypatch):
    from firepro3d import preferences_dialog as pd
    ini = str(tmp_path / "s.ini")
    _ini_settings(monkeypatch, ini)

    pane = pd.GeneralPane()
    pane.load()
    pane._data_folder_edit.setText(str(tmp_path / "x"))
    pane.apply()
    pane._data_folder_edit.clear()          # blank = use default
    pane.apply()

    stored = QSettings(ini, QSettings.Format.IniFormat).value(
        pd._DATA_ROOT_KEY, "?", type=str)
    assert stored == ""
