"""Block library I/O: .fpdb tree + divergence (Block system S3; the per-folder
index.json is retired 2026-10-10 -- the files on disk are the listing)."""
import json

import pytest

from firepro3d.block_definition import BlockDefinition
from firepro3d.stroke_style import migrate_primitive
from firepro3d import block_library as bl


def _def(name="Corner", library="Typical Detail", series="Wall Joints"):
    return BlockDefinition.new(name=name, library=library, series=series,
                               primitives=[{"type": "draw_line", "pt1": [0, 0],
                                            "pt2": [100, 0], "color": "#ffffff",
                                            "lineweight": 1.0}],
                               origin=(0.0, 0.0))


def _file_id(tmp_path, name="Corner"):
    p = tmp_path / "Typical Detail" / "Wall Joints" / f"{name}.fpdb"
    return json.loads(p.read_text())


def test_save_writes_fpdb_and_no_index(tmp_path):
    d = _def()
    path = bl.save_to_library(d, root=str(tmp_path))
    assert path.endswith(".fpdb")
    rec = _file_id(tmp_path)
    assert rec["id"] == d.id and rec["version"] == 1
    assert not list(tmp_path.rglob("index.json"))           # retired 2026-10-10


def test_list_and_load_round_trip(tmp_path):
    d = _def()
    bl.save_to_library(d, root=str(tmp_path))
    entries = bl.list_library(root=str(tmp_path))
    assert len(entries) == 1
    e = entries[0]
    assert e["library"] == "Typical Detail" and e["series"] == "Wall Joints"
    assert e["name"] == "Corner" and e["id"] == d.id
    loaded = bl.load_block(e["library"], e["series"], e["filename"], root=str(tmp_path))
    assert loaded.id == d.id and loaded.primitives == [migrate_primitive(p) for p in d.primitives]


def test_source_status(tmp_path):
    d = _def()
    assert bl.source_status(d, root=str(tmp_path)) == "project-only"
    bl.save_to_library(d, root=str(tmp_path))
    assert bl.source_status(d, root=str(tmp_path)) == "library"
    d.set_primitives(d.primitives + [{"type": "draw_line", "pt1": [0, 0],
                                      "pt2": [0, 50], "color": "#ffffff",
                                      "lineweight": 1.0}])  # bumps version to 2
    assert bl.source_status(d, root=str(tmp_path)) == "modified"


def test_reload_from_library_returns_library_version(tmp_path):
    d = _def()
    bl.save_to_library(d, root=str(tmp_path))
    d.set_primitives(d.primitives)   # version -> 2
    lib_def = bl.reload_from_library(d, root=str(tmp_path))
    assert lib_def is not None and lib_def.version == 1


def test_corrupt_fpdb_skipped(tmp_path):
    d = _def()
    bl.save_to_library(d, root=str(tmp_path))
    (tmp_path / "Typical Detail" / "Wall Joints" / "Corner.fpdb").write_text("{bad")
    assert bl.list_library(root=str(tmp_path)) == []        # unreadable: skipped
    assert bl.load_block("Typical Detail", "Wall Joints", "Corner.fpdb",
                         root=str(tmp_path)) is None


def test_make_then_save_to_library(model_space, tmp_path):
    from firepro3d.geometry_2d import LineItem
    from PyQt6.QtCore import QPointF
    li = LineItem.from_dict({"type": "draw_line", "pt1": [0, 0], "pt2": [100, 0],
                             "color": "#ffffff", "lineweight": 1.0})
    model_space.addItem(li)
    model_space._draw_lines.append(li)
    inst = model_space.make_block_from_selection(
        [li], origin=QPointF(0, 0), name="Corner", library="Detail", series="Joints")
    defn = model_space.get_block_definition(inst.block_id)
    bl.save_to_library(defn, root=str(tmp_path))
    assert bl.source_status(defn, root=str(tmp_path)) == "library"


def test_load_block_file_reads_arbitrary_path(tmp_path):
    from firepro3d import block_library as bl2
    d = _def(name="Loose")
    # write a .fpdb anywhere (NOT in the library tree)
    p = tmp_path / "somewhere" / "Loose.fpdb"
    p.parent.mkdir(parents=True)
    import json
    p.write_text(json.dumps(d.to_dict()), encoding="utf-8")
    loaded = bl2.load_block_file(str(p))
    assert loaded is not None
    assert loaded.id == d.id and loaded.name == "Loose"
    assert loaded.primitives == [migrate_primitive(p) for p in d.primitives]


def test_load_block_file_missing_and_corrupt(tmp_path):
    from firepro3d import block_library as bl2
    assert bl2.load_block_file(str(tmp_path / "nope.fpdb")) is None
    bad = tmp_path / "bad.fpdb"
    bad.write_text("{not json", encoding="utf-8")
    assert bl2.load_block_file(str(bad)) is None


# --- Identity-based lookups: scan-by-id, re-file, collision (fix batch) ---------

def test_save_re_files_stale_copy_on_relocation(tmp_path):
    """Saving a block whose library/series changed removes the old .fpdb + entry."""
    d = _def(library="LibA", series="SerX")
    bl.save_to_library(d, root=str(tmp_path))
    assert (tmp_path / "LibA" / "SerX" / "Corner.fpdb").is_file()
    # relocate (as the future editor / metadata edit would) and re-save
    d.library, d.series = "LibB", "SerY"
    bl.save_to_library(d, root=str(tmp_path))
    assert (tmp_path / "LibB" / "SerY" / "Corner.fpdb").is_file()
    # old copy is gone (re-filed, not duplicated)
    assert not (tmp_path / "LibA" / "SerX" / "Corner.fpdb").exists()
    # exactly one library entry for this id, correctly resolved
    entries = [e for e in bl.list_library(root=str(tmp_path)) if e["id"] == d.id]
    assert len(entries) == 1
    assert bl.source_status(d, root=str(tmp_path)) == "library"


def test_source_status_scans_by_id_across_tree(tmp_path):
    """A block whose in-memory series diverges from disk still reads 'library'."""
    d = _def(library="LibA", series="SerX")
    bl.save_to_library(d, root=str(tmp_path))
    # in-memory metadata drifts (not yet re-saved); disk copy is under SerX
    d.series = "SerY"
    # old code scanned only LibA/SerY (empty) -> 'project-only' (the bug)
    assert bl.source_status(d, root=str(tmp_path)) == "library"


def test_reload_from_library_finds_relocated_by_id(tmp_path):
    d = _def(library="LibA", series="SerX")
    bl.save_to_library(d, root=str(tmp_path))
    d.series = "SerY"                 # in-memory drift; disk copy still under SerX
    d.set_primitives(d.primitives)    # version -> 2 (locally modified)
    lib_def = bl.reload_from_library(d, root=str(tmp_path))
    assert lib_def is not None
    assert lib_def.id == d.id and lib_def.version == 1


def test_cross_id_name_collision_raises_and_preserves_existing(tmp_path):
    d1 = _def(name="Corner")
    bl.save_to_library(d1, root=str(tmp_path))
    d2 = _def(name="Corner")          # different id, same library/series/name
    assert d2.id != d1.id
    with pytest.raises(bl.BlockNameCollision):
        bl.save_to_library(d2, root=str(tmp_path))
    # the existing block is untouched
    assert _file_id(tmp_path)["id"] == d1.id


def test_cross_id_collision_overwrite_replaces(tmp_path):
    d1 = _def(name="Corner")
    bl.save_to_library(d1, root=str(tmp_path))
    d2 = _def(name="Corner")
    bl.save_to_library(d2, root=str(tmp_path), overwrite=True)
    assert _file_id(tmp_path)["id"] == d2.id
    entries = bl.list_library(root=str(tmp_path))
    assert len(entries) == 1 and entries[0]["id"] == d2.id


def test_same_id_re_save_updates_no_collision(tmp_path):
    """Re-saving the SAME block (same id) at the same location is a clean update."""
    d = _def(name="Corner")
    bl.save_to_library(d, root=str(tmp_path))
    d.set_primitives(d.primitives)    # version -> 2
    bl.save_to_library(d, root=str(tmp_path))   # must NOT raise
    e = _file_id(tmp_path)
    assert e["id"] == d.id and e["version"] == 2
    assert len(bl.list_library(root=str(tmp_path))) == 1
