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


import json
from firepro3d.sprinkler_db import SprinklerRecord

_CUSTOM = SprinklerRecord(
    id="acme_x1", manufacturer="Acme", model="X1", type="Pendent",
    k_factor=5.6, min_pressure=7.0, coverage_area=130, temp_rating=155,
    orifice='1/2"', notes="user-added",
)


def _write_db(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"library": [r.to_dict() for r in records], "templates": []}, f)


def test_migration_copies_legacy_when_target_absent(monkeypatch, tmp_path):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    _write_db(cwd / "sprinklers.json", [_CUSTOM])
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    db = SprinklerDatabase()  # default path -> migration fires
    assert any(r.id == "acme_x1" for r in db.library)
    assert os.path.isfile(os.path.join(str(tmp_path / "appdata"), "FirePro3D", "sprinklers.json"))


def test_migration_idempotent_target_wins(monkeypatch, tmp_path):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    _write_db(cwd / "sprinklers.json", [_CUSTOM])
    monkeypatch.chdir(cwd)
    appdata = tmp_path / "appdata"
    monkeypatch.setenv("APPDATA", str(appdata))
    # Target already exists with DIFFERENT content -> must NOT be overwritten.
    target = appdata / "FirePro3D" / "sprinklers.json"
    other = SprinklerRecord(id="zzz", manufacturer="Z", model="Z", type="Upright",
                            k_factor=8.0, min_pressure=7.0, coverage_area=196,
                            temp_rating=155, orifice='1/2"')
    _write_db(target, [other])

    db = SprinklerDatabase()
    ids = {r.id for r in db.library}
    assert ids == {"zzz"}                       # target won, no copy
    assert not any(r.id == "acme_x1" for r in db.library)


def test_no_legacy_seeds_defaults(monkeypatch, tmp_path):
    empty_cwd = tmp_path / "empty"
    empty_cwd.mkdir()
    monkeypatch.chdir(empty_cwd)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    db = SprinklerDatabase()
    assert len(db.library) == 15                # fresh default seed
