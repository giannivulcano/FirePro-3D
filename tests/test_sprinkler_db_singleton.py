import os
import pytest

from firepro3d.sprinkler_db import _default_db_path, SprinklerDatabase


def test_default_path_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert _default_db_path() == os.path.join(str(tmp_path), "FirePro3D", "sprinklers.json")


def test_default_path_falls_back_to_home(monkeypatch, tmp_path):
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(os.path, "expanduser",
                        lambda p: str(tmp_path) if p == "~" else p)
    assert _default_db_path() == os.path.join(str(tmp_path), "FirePro3D", "sprinklers.json")


def test_injected_path_still_wins(tmp_path):
    target = tmp_path / "custom.json"
    db = SprinklerDatabase(path=str(target))
    assert db._path == str(target)


def test_seed_save_creates_missing_dir(tmp_path):
    target = tmp_path / "no" / "such" / "dir" / "sprinklers.json"
    # Injected (non-default) path -> no migration; first run seeds + saves.
    SprinklerDatabase(path=str(target))
    assert target.is_file()
