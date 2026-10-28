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
