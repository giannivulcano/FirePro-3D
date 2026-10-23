"""HF5 Task 2 -- the fill-type table travels with the project (AC1, AC10)."""
import json

import pytest

import main as _main_module
from firepro3d.view_3d import View3D          # heavy import required before MainWindow
_main_module.View3D = View3D
from main import MainWindow

from firepro3d import fill_types as ft
from firepro3d.fill_layers import BackgroundLayer, FillLayers
from firepro3d.model_space import Model_Space
from tests._mainwindow_helpers import dispose_main_window

RED = FillLayers(BackgroundLayer("#ff0000", 1.0))


@pytest.fixture
def main_window(qapp, tmp_path, monkeypatch):
    # Keep the real ~/.firepro3d autosave untouched and skip the template-push modal.
    recovery = str(tmp_path / "autosave" / "recovery.FPD")
    monkeypatch.setattr(MainWindow, "_autosave_path",
                        staticmethod(lambda: recovery))
    monkeypatch.setattr(MainWindow, "_maybe_offer_template_push",
                        lambda self: None)
    w = MainWindow()
    yield w
    dispose_main_window(w)


def test_save_open_round_trip(qapp, tmp_path):
    ft.reset_project_table()
    added = ft.project_table().add(ft.FillType(ft.new_id(), "Red", RED))
    ms = Model_Space()
    path = str(tmp_path / "p.fpd")
    ms.save_to_file(path)
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)["fill_types"]
    assert any(r["id"] == added.id and r["name"] == "Red" for r in rows)
    ft.reset_project_table()
    assert ft.project_table().get(added.id) is None
    Model_Space().load_from_file(path)
    assert ft.project_table().get(added.id).layers == RED


def test_old_file_without_key_gets_seed(qapp, tmp_path):
    ms = Model_Space()
    path = str(tmp_path / "old.fpd")
    ms.save_to_file(path)
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    payload.pop("fill_types")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    ft.set_project_table(ft.FillTypeTable([ft.FillType("x", "Leftover", RED)]))
    Model_Space().load_from_file(path)
    names = {t.name for t in ft.project_table().all()}
    assert "Leftover" not in names and "Solid Black" in names


def test_new_project_resets_to_seed(main_window):
    ft.project_table().add(ft.FillType(ft.new_id(), "Stale", RED))
    main_window._modified = False
    main_window.new_file()
    assert ft.project_table().by_name("Stale") is None
    assert ft.project_table().by_name("Solid Black") is not None


def test_startup_installs_seed_over_stale_table(qapp, tmp_path, monkeypatch):
    """MainWindow() startup resets the store (AC10): a table left by a prior session is gone."""
    ft.set_project_table(ft.FillTypeTable([ft.FillType("x", "Stale", RED)]))
    recovery = str(tmp_path / "autosave" / "recovery.FPD")
    monkeypatch.setattr(MainWindow, "_autosave_path", staticmethod(lambda: recovery))
    monkeypatch.setattr(MainWindow, "_maybe_offer_template_push", lambda self: None)
    w = MainWindow()
    try:
        assert ft.project_table().by_name("Stale") is None
        assert ft.project_table().by_name("Solid Black") is not None
    finally:
        dispose_main_window(w)
