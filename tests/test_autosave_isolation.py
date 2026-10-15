"""Guards for conftest's autosave redirect (test-harness.md Invariant 11)."""
from __future__ import annotations

import os

from main import MainWindow
from tests._mainwindow_helpers import dispose_main_window

_HOME_DIR = os.path.join(os.path.expanduser("~"), ".firepro3d")
_seen: list[str] = []


def test_autosave_path_is_not_the_real_home_file():
    p = MainWindow._autosave_path()
    assert not os.path.normcase(os.path.abspath(p)).startswith(
        os.path.normcase(_HOME_DIR))
    _seen.append(os.path.dirname(p))


def test_each_test_gets_a_fresh_autosave_dir():
    p = MainWindow._autosave_path()
    assert _seen and os.path.dirname(p) != _seen[0]
    assert not os.path.exists(p)


def test_autosave_writes_into_the_temp_dir(qapp, stub_view3d):
    """Real path: a dirty window's timer slot writes the redirected file."""
    w = MainWindow()
    try:
        w._modified = True
        w._autosave()
        p = MainWindow._autosave_path()
        assert os.path.isfile(p)
        assert not os.path.normcase(os.path.abspath(p)).startswith(
            os.path.normcase(_HOME_DIR))
    finally:
        dispose_main_window(w)
