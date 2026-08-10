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


def test_property_manager_uses_injected_db(qapp, tmp_path):
    import firepro3d.property_manager as pm_mod
    from firepro3d.property_manager import PropertyManager

    # Module-level cache must be gone.
    assert not hasattr(pm_mod, "_sprinkler_db")
    assert not hasattr(pm_mod, "_get_sprinkler_db")

    db = SprinklerDatabase(path=str(tmp_path / "s.json"))
    db.add_to_library(_CUSTOM)

    pm = PropertyManager()
    pm.set_sprinkler_db(db)

    # Panel reads the injected db, so the Manager-added record is visible now.
    assert "Acme" in pm._get_db().get_unique_manufacturers()


def test_property_managers_do_not_share_global_state(qapp, tmp_path):
    from firepro3d.property_manager import PropertyManager
    a = SprinklerDatabase(path=str(tmp_path / "a.json"))
    b = SprinklerDatabase(path=str(tmp_path / "b.json"))
    pm1 = PropertyManager(); pm1.set_sprinkler_db(a)
    pm2 = PropertyManager(); pm2.set_sprinkler_db(b)
    assert pm1._get_db() is a
    assert pm2._get_db() is b


def test_model_space_passes_injected_db_to_autopopulate(qapp, monkeypatch, tmp_path):
    from firepro3d.model_space import Model_Space
    import firepro3d.auto_populate_dialog as ap_mod

    scene = Model_Space()
    db = SprinklerDatabase(path=str(tmp_path / "s.json"))
    scene.set_sprinkler_db(db)

    captured = {}

    class _StubDialog:
        def __init__(self, room, sprinkler_db, **kwargs):
            captured["db"] = sprinkler_db
        def exec(self):
            return 0  # QDialog.DialogCode.Rejected

    # Import site is function-local (`from .auto_populate_dialog import
    # AutoPopulateDialog`), so patch the source module attribute.
    monkeypatch.setattr(ap_mod, "AutoPopulateDialog", _StubDialog)

    scene._auto_populate_room_dialog(object())  # room unused by the stub
    assert captured["db"] is db
