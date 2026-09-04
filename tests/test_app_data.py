"""app_data_dir helper + call-site parity (Block system S3)."""
import os
from firepro3d.app_data import app_data_dir


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
