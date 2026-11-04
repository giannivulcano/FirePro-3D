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


def _big_project(path):
    path.write_text(json.dumps({"gridlines": [{}] * 20}))


def test_save_warns_and_cancel_leaves_the_file(mw, tmp_path, monkeypatch):
    from firepro3d import themed_message as tm
    path = tmp_path / "project.FPD"
    _big_project(path)
    before = path.read_bytes()
    mw._current_file = str(path)
    asks = []
    monkeypatch.setattr(tm, "themed_confirm", lambda *a, **k: asks.append(a) or False)
    assert mw.save_file() is False
    assert len(asks) == 1 and path.read_bytes() == before


def test_small_file_saves_without_warning(mw, tmp_path, monkeypatch):
    from firepro3d import themed_message as tm
    path = tmp_path / "project.FPD"
    path.write_text(json.dumps({"gridlines": [{}] * 9}))
    mw._current_file = str(path)
    monkeypatch.setattr(tm, "themed_confirm", lambda *a, **k: pytest.fail("asked"))
    assert mw.save_file() is True


@pytest.mark.parametrize("disk,scene,warn", [
    (10, 4, True), (10, 5, False), (9, 0, False), (None, 0, False),
])
def test_loses_content_boundary(disk, scene, warn):
    from firepro3d.project_backup import loses_content
    assert loses_content(disk, scene) is warn


def test_failed_recovery_keeps_the_recovery_file(mw, tmp_path, monkeypatch):
    from firepro3d import themed_message as tm
    import main as main_mod
    recovery = tmp_path / "recovery.FPD"
    _saved_project(mw, recovery)
    original = recovery.read_bytes()
    monkeypatch.setattr(type(mw), "_autosave_path",
                        staticmethod(lambda: str(recovery)))
    monkeypatch.setattr(main_mod, "themed_confirm", lambda *a, **k: True)
    monkeypatch.setattr(tm, "themed_error", lambda p, t, m: None)
    monkeypatch.setattr(main_mod, "ERROR_LOG_PATH", str(tmp_path / "error.log"))
    monkeypatch.setattr(mw.scene._level_manager, "from_list", _boom)
    mw._check_recovery()
    assert recovery.read_bytes() == original
    mw._modified = True
    mw._autosave()                                  # the timer, on the partial scene
    assert recovery.read_bytes() == original


def test_second_save_in_one_second_keeps_the_first_backup(tmp_path):
    from datetime import datetime
    from firepro3d import project_backup as pb
    path = tmp_path / "project.FPD"
    moment = datetime(2026, 1, 1)
    path.write_text("good")
    first = pb.write_backup(str(path), moment)
    path.write_text("blank")
    second = pb.write_backup(str(path), moment)
    assert first != second
    assert open(first).read() == "good" and open(second).read() == "blank"


def test_failed_save_as_stays_detached(mw, tmp_path, monkeypatch):
    import main as main_mod
    target = tmp_path / "new.FPD"
    mw._detached_name = "project.FPD"
    monkeypatch.setattr(main_mod.QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(target), ""))
    monkeypatch.setattr(mw.scene, "save_to_file", lambda path: False)
    assert mw.save_file_as() is False
    assert mw._current_file is None and mw._detached_name == "project.FPD"


def test_close_while_detached_keeps_the_recovery_file(mw, tmp_path, monkeypatch):
    recovery = tmp_path / "recovery.FPD"
    recovery.write_text("{}")
    monkeypatch.setattr(type(mw), "_autosave_path",
                        staticmethod(lambda: str(recovery)))
    monkeypatch.setattr(mw, "_ask_save_changes", lambda action: True)
    mw._detached_name = "recovery.FPD"
    from PyQt6.QtGui import QCloseEvent
    mw.closeEvent(QCloseEvent())
    assert recovery.exists()


def test_save_to_file_goes_through_the_atomic_write(mw, tmp_path, monkeypatch):
    path = tmp_path / "project.FPD"
    _saved_project(mw, path)
    original = path.read_bytes()
    monkeypatch.setattr("firepro3d.project_backup.json.dump", _boom)
    assert mw.scene.save_to_file(str(path)) is False
    assert path.read_bytes() == original


def test_cancelled_save_stops_close(mw, tmp_path, monkeypatch):
    import main as main_mod
    mw._modified = True
    monkeypatch.setattr(main_mod, "themed_choice", lambda *a, **k: "save")
    monkeypatch.setattr(main_mod.QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    assert mw._ask_save_changes("closing") is False
