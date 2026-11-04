"""Guards for the 2026-11-04 data-loss chain: re-opening a project that holds a
detail view must not leave a half-cleared scene that a Save then writes over
the real file."""
from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QRectF

from tests._mainwindow_helpers import dispose_main_window


@pytest.fixture()
def mw(qapp, tmp_path, monkeypatch):
    """Fresh MainWindow with safe teardown (see test_multi_sheet.py)."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import main as main_mod
    from firepro3d.view_3d import View3D
    from firepro3d import snap_engine
    main_mod.View3D = View3D
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    w = main_mod.MainWindow()
    yield w
    dispose_main_window(w)
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


def _saved_project(win, path, details=1):
    """Save a project holding *details* detail views; return its payload."""
    for i in range(details):
        win.detail_manager.create_detail(
            f"D{i}", QRectF(0, 0, 1000, 1000), win.scene.active_level, mint=False)
    win._current_file = str(path)
    win.save_file()
    return json.loads(path.read_text())


def test_reload_with_detail_view_keeps_the_project(mw, tmp_path):
    """The Recent-menu reload path of the 10:41 traceback: the load completes,
    and the Save that follows writes the same content back."""
    path = tmp_path / "project.FPD"
    before = _saved_project(mw, path)
    assert len(before["gridlines"]) > 0 and len(before["detail_views"]) == 1

    mw._load_project(str(path))

    assert len(mw.scene._gridlines) == len(before["gridlines"])
    assert mw.detail_manager.detail_names == ["D0"]
    mw.save_file()
    after = json.loads(path.read_text())
    assert len(after["gridlines"]) == len(before["gridlines"])
    assert len(after["detail_views"]) == 1
    assert len(after["sections"]) == len(before["sections"])
