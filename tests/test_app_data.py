"""app_data_dir helper + call-site parity + configurable override."""
import os
import pytest
from firepro3d import app_data
from firepro3d.app_data import app_data_dir, user_data_root


@pytest.fixture(autouse=True)
def _no_override(monkeypatch):
    # Isolate from any real QSettings data-folder override on the test machine.
    monkeypatch.setattr(app_data, "_configured_root", lambda: None)


def test_app_data_dir_roots_under_firepro3d(monkeypatch):
    monkeypatch.setenv("APPDATA", r"C:\Users\x\AppData\Roaming")
    assert app_data_dir() == os.path.join(r"C:\Users\x\AppData\Roaming", "FirePro3D")
    assert app_data_dir("blocks") == os.path.join(
        r"C:\Users\x\AppData\Roaming", "FirePro3D", "blocks")


def test_app_data_dir_falls_back_to_home(monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)
    assert app_data_dir("blocks").startswith(os.path.expanduser("~"))


def test_call_sites_use_helper(monkeypatch):
    monkeypatch.setenv("APPDATA", r"C:\Roam")
    from firepro3d import sprinkler_db, titleblock_template
    assert sprinkler_db._default_db_path() == os.path.join(
        r"C:\Roam", "FirePro3D", "sprinklers.json")
    assert titleblock_template._library_dir() == os.path.join(
        r"C:\Roam", "FirePro3D", "titleblocks")


def test_configured_override_wins(monkeypatch, tmp_path):
    # A configured data-folder override relocates the whole root.
    monkeypatch.setattr(app_data, "_configured_root", lambda: str(tmp_path))
    assert user_data_root() == str(tmp_path)
    assert app_data_dir("blocks") == os.path.join(str(tmp_path), "blocks")


def test_blank_override_uses_default(monkeypatch):
    monkeypatch.setenv("APPDATA", r"C:\Roam")
    monkeypatch.setattr(app_data, "_configured_root", lambda: None)
    assert app_data_dir() == os.path.join(r"C:\Roam", "FirePro3D")
