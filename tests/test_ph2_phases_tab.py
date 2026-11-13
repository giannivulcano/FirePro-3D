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
