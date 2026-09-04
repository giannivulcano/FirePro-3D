"""Block library I/O: .fpdb tree + index.json + divergence (Block system S3)."""
from firepro3d.block_definition import BlockDefinition
from firepro3d import block_library as bl


def _def(name="Corner", library="Typical Detail", series="Wall Joints"):
    return BlockDefinition.new(name=name, library=library, series=series,
                               primitives=[{"type": "draw_line", "pt1": [0, 0],
                                            "pt2": [100, 0], "color": "#ffffff",
                                            "lineweight": 1.0}],
                               origin=(0.0, 0.0))


def test_save_writes_fpdb_and_index(tmp_path):
    d = _def()
    path = bl.save_to_library(d, root=str(tmp_path))
    assert path.endswith(".fpdb")
    assert (tmp_path / "Typical Detail" / "Wall Joints" / "Corner.fpdb").is_file()
    idx = tmp_path / "Typical Detail" / "Wall Joints" / "index.json"
    assert idx.is_file()
    import json
    entry = json.loads(idx.read_text())["Corner.fpdb"]
    assert entry["id"] == d.id and entry["version"] == 1


def test_list_and_load_round_trip(tmp_path):
    d = _def()
    bl.save_to_library(d, root=str(tmp_path))
    entries = bl.list_library(root=str(tmp_path))
    assert len(entries) == 1
    e = entries[0]
    assert e["library"] == "Typical Detail" and e["series"] == "Wall Joints"
    assert e["name"] == "Corner" and e["id"] == d.id
    loaded = bl.load_block(e["library"], e["series"], e["filename"], root=str(tmp_path))
    assert loaded.id == d.id and loaded.primitives == d.primitives


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
    entries = bl.list_library(root=str(tmp_path))
    assert len(entries) == 1
    assert bl.load_block(entries[0]["library"], entries[0]["series"],
                         entries[0]["filename"], root=str(tmp_path)) is None


def test_make_then_save_to_library(model_space, tmp_path):
    from firepro3d.construction_geometry import LineItem
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
