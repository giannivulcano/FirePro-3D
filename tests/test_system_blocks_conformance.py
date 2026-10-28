"""Every shipped System block is loadable and self-contained (authoring Q9).

Walks firepro3d/system_blocks/ itself (no set_system_root): a promote that
broke a rule fails here before it ships."""
import json
import os
import re

import pytest

from firepro3d import block_library
from firepro3d.assets import system_blocks_path
from firepro3d.block_registry import referenced_ids

# Stable System ids: the legacy shipped hatches, or a promote slug
# (system_promote: system-<series>-<name>[-k]); never a uuid hex.
_LEGACY_ID = re.compile(r"builtin-hatch-[a-z0-9]+(-[a-z0-9]+)*")
_SLUG_ID = re.compile(r"system-[a-z0-9]+(-[a-z0-9]+)*")


def _files():
    out = []
    for dirpath, _dirs, files in os.walk(system_blocks_path()):
        out += [os.path.join(dirpath, f) for f in files if f.endswith(".fpdb")]
    return sorted(out)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


_SHIPPED_IDS = [_read(p).get("id") for p in _files()]


def test_shipped_folder_is_not_empty():
    assert _files()


@pytest.mark.parametrize("path", _files(), ids=os.path.basename)
def test_shipped_block_conforms(path):
    rec = _read(path)
    bid = rec.get("id")
    assert bid, "no id"
    assert _LEGACY_ID.fullmatch(bid) or _SLUG_ID.fullmatch(bid), (
        f"{bid!r} is not a stable System id")
    assert rec.get("library") == block_library.SYSTEM_LIBRARY
    assert isinstance(rec.get("version"), int) and rec["version"] >= 1
    defn = block_library.load_block_file(path)
    assert defn is not None, "does not load"
    assert defn.id == bid, "the loader changed the id"
    outside = referenced_ids(defn) - set(_SHIPPED_IDS)
    assert not outside, f"uses non-System blocks {sorted(outside)}"


def test_shipped_ids_unique():
    assert len(_SHIPPED_IDS) == len(set(_SHIPPED_IDS))
