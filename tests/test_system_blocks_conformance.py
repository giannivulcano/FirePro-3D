"""Every shipped System block is loadable and self-contained (authoring Q9).

Walks firepro3d/system_blocks/ itself (no set_system_root): a promote that
broke a rule fails here before it ships."""
import json
import os

import pytest

from firepro3d import block_library
from firepro3d.assets import system_blocks_path
from firepro3d.block_registry import referenced_ids


def _files():
    out = []
    for dirpath, _dirs, files in os.walk(system_blocks_path()):
        out += [os.path.join(dirpath, f) for f in files if f.endswith(".fpdb")]
    return sorted(out)


def _ids():
    out = []
    for p in _files():
        with open(p, encoding="utf-8") as fh:
            out.append(json.load(fh)["id"])
    return out


def test_shipped_folder_is_not_empty():
    assert _files()


@pytest.mark.parametrize("path", _files(), ids=os.path.basename)
def test_shipped_block_conforms(path):
    with open(path, encoding="utf-8") as fh:
        rec = json.load(fh)
    assert rec.get("id"), "no id"
    assert rec.get("library") == block_library.SYSTEM_LIBRARY
    assert isinstance(rec.get("version"), int) and rec["version"] >= 1
    defn = block_library.load_block_file(path)
    assert defn is not None, "does not load"
    assert not (referenced_ids(defn) - set(_ids())), "uses a non-System block"


def test_shipped_ids_unique():
    ids = _ids()
    assert len(ids) == len(set(ids))
