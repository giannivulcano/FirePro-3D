"""Guards for the 2026-11-04 data-loss chain: re-opening a project that holds a
detail view must not leave a half-cleared scene that a Save then writes over
the real file."""
from __future__ import annotations

import json
import shutil

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


def test_reload_with_two_details_needs_one_reload(mw, tmp_path):
    path = tmp_path / "project.FPD"
    _saved_project(mw, path, details=2)
    mw._load_project(str(path))
    assert sorted(mw.detail_manager.detail_names) == ["D0", "D1"]


def test_open_detail_free_project_leaves_no_dead_markers(mw, tmp_path):
    empty = tmp_path / "empty.FPD"
    mw._current_file = str(empty)
    mw.save_file()
    _saved_project(mw, tmp_path / "with.FPD")
    mw._load_project(str(empty))
    assert mw.detail_manager.detail_names == []
    assert mw.scene._detail_manager.to_list() == []


def _boom(*a, **k):
    raise RuntimeError("forced restore failure")


def test_exception_mid_restore_detaches_and_save_cannot_reach_the_file(mw, tmp_path, monkeypatch):
    from firepro3d import themed_message as tm
    import main as main_mod
    path = tmp_path / "project.FPD"
    _saved_project(mw, path)
    original = path.read_bytes()
    errors = []
    monkeypatch.setattr(tm, "themed_error", lambda p, t, m: errors.append(m))
    monkeypatch.setattr(main_mod, "ERROR_LOG_PATH", str(tmp_path / "error.log"))
    monkeypatch.setattr(mw.scene._level_manager, "from_list", _boom)
    mw._load_project(str(path))
    assert len(errors) == 1 and "not changed" in errors[0]
    assert mw._current_file is None
    assert "failed to load" in mw.windowTitle()
    assert "forced restore failure" in (tmp_path / "error.log").read_text()
    monkeypatch.setattr(main_mod.QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    mw.save_file()                                  # Save As dialog, cancelled
    assert path.read_bytes() == original


def test_corrupt_file_keeps_project_and_target_untouched(mw, tmp_path, monkeypatch):
    from firepro3d import themed_message as tm
    good = tmp_path / "good.FPD"
    _saved_project(mw, good)
    bad = tmp_path / "bad.FPD"
    bad.write_text("{ not json")
    errors = []
    monkeypatch.setattr(tm, "themed_error", lambda p, t, m: errors.append(m))
    mw._load_project(str(bad))
    assert len(errors) == 1
    assert mw._current_file == str(good)            # old project still current
    mw.save_file()
    assert bad.read_text() == "{ not json"


def test_blank_save_keeps_a_backup_of_the_real_file(mw, tmp_path):
    path = tmp_path / "project.FPD"
    _saved_project(mw, path)
    original = path.read_bytes()
    mw.scene._clear_scene()
    mw.save_file()
    backups = list((tmp_path / "Backups").glob("project *.FPD"))
    assert len(backups) == 1 and backups[0].read_bytes() == original


def test_backups_prune_to_ten_and_ignore_other_projects(tmp_path):
    from datetime import datetime, timedelta
    from firepro3d import project_backup as pb
    path = tmp_path / "project.FPD"
    path.write_text("{}")
    other = tmp_path / "Backups" / "project 2 2020-01-01 000000.FPD"
    other.parent.mkdir()
    other.write_text("{}")
    start = datetime(2026, 1, 1)
    for i in range(12):
        pb.write_backup(str(path), start + timedelta(seconds=i))
    kept = sorted(p.name for p in other.parent.glob("project 2026-*.FPD"))
    assert len(kept) == 10 and kept[0] == "project 2026-01-01 000002.FPD"
    assert other.exists()


def test_autosave_makes_no_backup(mw, tmp_path, monkeypatch):
    path = tmp_path / "project.FPD"
    _saved_project(mw, path)
    shutil.rmtree(tmp_path / "Backups", ignore_errors=True)
    monkeypatch.setattr(type(mw), "_autosave_path",
                        staticmethod(lambda: str(path)))
    mw._modified = True
    mw._autosave()
    assert not (tmp_path / "Backups").exists()


def test_write_failure_leaves_the_original(tmp_path):
    from firepro3d import project_backup as pb
    path = tmp_path / "project.FPD"
    path.write_text('{"keep": 1}')
    with pytest.raises(TypeError):
        pb.write_atomic(str(path), {"bad": object()})
    assert path.read_text() == '{"keep": 1}'
    assert not (tmp_path / "project.FPD.tmp").exists()
