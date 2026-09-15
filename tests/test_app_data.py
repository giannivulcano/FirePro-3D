"""app_data_dir helper + call-site parity + configurable override."""
import os
import pytest
from firepro3d import app_data
from firepro3d.app_data import app_data_dir, user_data_root


@pytest.fixture(autouse=True)
def _no_override(monkeypatch):
    # Isolate from any real QSettings override on the test machine.
    monkeypatch.setattr(app_data, "_configured_root", lambda: None)
    monkeypatch.setattr(app_data, "_configured_titleblock_dir", lambda: None)


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


# ── E2: dedicated title-block library location ─────────────────────────────

def test_titleblock_library_dir_defaults_under_root(monkeypatch, tmp_path):
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    assert app_data.titleblock_library_dir() == os.path.join(str(tmp_path), "titleblocks")


def test_titleblock_library_dir_override_wins(monkeypatch, tmp_path):
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    monkeypatch.setattr(app_data, "_configured_titleblock_dir",
                        lambda: r"X:\shared\titleblocks")
    assert app_data.titleblock_library_dir() == r"X:\shared\titleblocks"


# ── E3: migrate-on-change helpers ──────────────────────────────────────────

def test_data_root_has_content(tmp_path):
    empty = tmp_path / "empty"; empty.mkdir()
    assert not app_data.data_root_has_content(str(empty))
    (empty / "default.fpdt").write_text("{}")
    assert app_data.data_root_has_content(str(empty))


def test_migrate_data_root_copies_known_content(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    (old / "titleblocks").mkdir(parents=True)
    (old / "titleblocks" / "a.json").write_text("{}")
    (old / "sprinklers.json").write_text("[]")
    migrated = app_data.migrate_data_root(str(old), str(new))
    assert set(migrated) == {"titleblocks", "sprinklers.json"}
    assert (new / "titleblocks" / "a.json").exists()
    assert (new / "sprinklers.json").exists()
    assert (old / "sprinklers.json").exists()          # copy → source kept


def test_migrate_data_root_move_removes_source(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    (old / "titleblocks").mkdir(parents=True)
    (old / "titleblocks" / "a.json").write_text("{}")
    app_data.migrate_data_root(str(old), str(new), move=True)
    assert (new / "titleblocks" / "a.json").exists()
    assert not (old / "titleblocks").exists()          # move → source removed


def test_migrate_data_root_never_clobbers_destination(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir(); new.mkdir()
    (old / "sprinklers.json").write_text("OLD")
    (new / "sprinklers.json").write_text("KEEP")
    migrated = app_data.migrate_data_root(str(old), str(new))
    assert "sprinklers.json" not in migrated
    assert (new / "sprinklers.json").read_text() == "KEEP"


def test_migrate_data_root_same_root_is_noop(tmp_path):
    r = tmp_path / "r"; (r / "blocks").mkdir(parents=True)
    assert app_data.migrate_data_root(str(r), str(r)) == []
