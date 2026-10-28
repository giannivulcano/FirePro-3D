"""System-block authoring guards (block-system.md "System library tier",
authoring path 2026-10-27: Workbench + dev gate + Promote to System)."""
import json
import os

import pytest

from firepro3d import block_library


def _fpdb(path, block_id, *, library="Workbench", series="Hatches",
          name=None, version=1, **extra):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rec = {"schema": 1, "id": block_id, "library": library, "series": series,
           "name": name or os.path.basename(path)[:-5], "version": version,
           "primitives": [], **extra}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rec, fh)
    return path


def test_dev_gate_reads_dot_git_file_or_dir(tmp_path):
    pkg = tmp_path / "firepro3d"
    pkg.mkdir()
    assert block_library._dev_gate_at(str(pkg)) is False
    (tmp_path / ".git").write_text("gitdir: elsewhere")   # a worktree's .git is a FILE
    assert block_library._dev_gate_at(str(pkg)) is True


def test_dev_gate_override_and_default_off_in_tests():
    assert block_library.dev_gate() is False              # conftest autouse
    block_library.set_dev_gate(True)
    try:
        assert block_library.dev_gate() is True
    finally:
        block_library.set_dev_gate(False)


def test_workbench_is_an_ordinary_writable_library():
    assert block_library.WORKBENCH_LIBRARY == "Workbench"
    assert not block_library.is_reserved_library("Workbench")
    assert block_library.is_reserved_library("System")


@pytest.fixture
def tiers(tmp_path):
    sysroot, user = tmp_path / "sys", tmp_path / "lib"
    shipped = _fpdb(str(sysroot / "Hatches" / "Brick.fpdb"), "system-hatches-brick",
                    library="System", version=2)
    wb = _fpdb(str(user / "Workbench" / "Hatches" / "Brick.fpdb"),
               "system-hatches-brick", version=3)
    block_library.set_system_root(str(sysroot))
    yield str(user), shipped, wb
    block_library.set_system_root(None)


def test_gate_off_system_owns_the_clash(tiers):
    root, shipped, wb = tiers
    found = block_library._find_by_id("system-hatches-brick", root)
    assert found[3]["path"] == shipped
    assert block_library.is_system_block("system-hatches-brick", root)


def test_gate_on_workbench_owns_the_clash(tiers):
    root, shipped, wb = tiers
    block_library.set_dev_gate(True)
    found = block_library._find_by_id("system-hatches-brick", root)
    assert found[3]["path"] == wb and found[3]["version"] == 3
    assert not block_library.is_system_block("system-hatches-brick", root)
    entries = {e["path"]: e for e in block_library.list_library(root)}
    assert entries[shipped]["duplicate"] and entries[shipped]["tier"] == "system"


def test_gate_on_other_user_folders_still_lose(tiers):
    root, shipped, wb = tiers
    _fpdb(os.path.join(root, "Styles", "Hatches", "Brick.fpdb"),
          "system-hatches-brick", library="Styles")
    block_library.set_dev_gate(True)
    assert block_library._find_by_id("system-hatches-brick", root)[3]["path"] == wb
    os.remove(wb)
    assert block_library._find_by_id("system-hatches-brick", root)[3]["path"] == shipped


def test_shipped_index_lists_system_tier_only(tiers):
    root, shipped, wb = tiers
    assert block_library.shipped_index() == {"system-hatches-brick": shipped}


def test_dev_gate_detects_beside_the_package(tmp_path, monkeypatch):
    pkg = tmp_path / "firepro3d"
    pkg.mkdir()
    monkeypatch.setattr(block_library, "__file__", str(pkg / "block_library.py"))
    block_library.set_dev_gate(None)
    try:
        assert block_library.dev_gate() is False
        (tmp_path / ".git").mkdir()
        assert block_library.dev_gate() is True
    finally:
        block_library.set_dev_gate(False)
