"""Guards for conftest's autosave redirect (test-harness.md Invariant 11)."""
from __future__ import annotations

import os

import pytest

import main
from main import MainWindow
from tests._mainwindow_helpers import dispose_main_window

_HOME_DIR = os.path.join(os.path.expanduser("~"), ".firepro3d")
_HOME_FILE = os.path.join(_HOME_DIR, "autosave", "recovery.FPD")


def _under_home(path: str) -> bool:
    return os.path.normcase(os.path.abspath(path)).startswith(
        os.path.normcase(_HOME_DIR))


def _home_state():
    """The real recovery file's (exists, mtime) -- must not change."""
    if os.path.isfile(_HOME_FILE):
        return True, os.path.getmtime(_HOME_FILE)
    return False, None


@pytest.fixture(scope="module")
def _dir_at_module_setup():
    """The autosave dir in force when this module's fixtures were built
    (before any of its tests' function fixtures ran)."""
    return os.path.dirname(MainWindow._autosave_path())


def test_autosave_path_is_not_the_real_home_file():
    assert not _under_home(MainWindow._autosave_path())


def test_each_test_gets_a_fresh_autosave_dir(_dir_at_module_setup):
    p = MainWindow._autosave_path()
    assert os.path.dirname(p) != _dir_at_module_setup
    assert not _under_home(p)


def test_autosave_writes_into_the_temp_dir(qapp, stub_view3d):
    """Real path: a dirty window's timer slot writes the redirected file."""
    before = _home_state()
    p = MainWindow._autosave_path()
    assert not _under_home(p)          # refuse to write before checking
    w = MainWindow()
    try:
        w._modified = True
        w._autosave()
        assert os.path.isfile(p)
    finally:
        dispose_main_window(w)
    assert _home_state() == before


def test_recovery_check_consumes_only_the_redirected_file(
        qapp, stub_view3d, monkeypatch):
    """Real path: ``_check_recovery`` (declined) deletes the recovery file --
    the redirected one, never the user's real one."""
    before = _home_state()
    p = MainWindow._autosave_path()
    assert not _under_home(p)          # never plant/consume the real file
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("{}")
    asked = []
    monkeypatch.setattr(main, "themed_confirm",
                        lambda *a, **k: asked.append(a) or False)
    w = MainWindow()
    try:
        w._check_recovery()
        assert asked                   # the redirected file was found
        assert not os.path.exists(p)   # ...and consumed
    finally:
        dispose_main_window(w)
    assert _home_state() == before
