"""SV4 -- a same-id ``.fpdb`` must never change a definition's ``kind`` on the
swap path (schematics.md D-S3; SV1 seam review #6).

``commit_block_definition`` already refuses a kind change on edit; the two
swap callers (``load_blocks_from_files`` replace branch and
``reload_block_definition``) are the remaining routes by which a placed block
could silently become a schematic (or a schematic a block).
"""
import json

from PyQt6.QtCore import QPointF

from firepro3d import block_library
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem


def _line(length=30):
    return LineItem(QPointF(0, 0), QPointF(length, 0)).to_dict()


def _block(ms, name="Plain"):
    d = BlockDefinition.new(name=name, library="L", series="S",
                            primitives=[_line()], origin=(0.0, 0.0))
    ms.register_block_definition(d)
    return d


def _schematic(ms, name="Riser"):
    d = BlockDefinition.new(name=name, library="", series="",
                            primitives=[_line()], origin=(0.0, 0.0),
                            kind="schematic")
    ms.register_block_definition(d)
    return d


def _same_id_file(tmp_path, defn, *, kind, stem):
    """A ``.fpdb`` carrying *defn*'s id at a higher version but another kind."""
    data = defn.to_dict()
    data["version"] = defn.version + 1
    data["primitives"] = [_line(400)]
    if kind == "schematic":
        data["kind"] = "schematic"
        data["library"] = ""
    else:
        data.pop("kind", None)
        data["library"] = data["library"] or "L"
        data["series"] = data["series"] or "S"
    p = tmp_path / f"{stem}.fpdb"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def test_load_refuses_a_same_id_file_that_would_turn_a_placed_block_into_a_schematic(
        model_space, tmp_path):
    d = _block(model_space)
    inst = model_space.place_block_instance(d.id, (0.0, 0.0))
    width_before = inst.boundingRect().width()
    path = _same_id_file(tmp_path, d, kind="schematic", stem="plain_as_schematic")

    summary = model_space.load_blocks_from_files([path])

    kept = model_space.get_block_definition(d.id)
    assert kept is d and kept.kind == "block", "a placed block became a schematic"
    assert kept.version == d.version
    assert summary["replaced"] == [] and summary["loaded"] == []
    assert summary["refused"] == [f"Plain ({block_library.KIND_REASON})"]
    assert inst.boundingRect().width() == width_before     # geometry untouched
    assert inst in kept._instances


def test_load_refuses_a_same_id_file_that_would_turn_a_schematic_into_a_block(
        model_space, tmp_path):
    s = _schematic(model_space)
    path = _same_id_file(tmp_path, s, kind="block", stem="riser_as_block")

    summary = model_space.load_blocks_from_files([path])

    kept = model_space.get_block_definition(s.id)
    assert kept is s and kept.kind == "schematic"
    assert summary["refused"] == [f"Riser ({block_library.KIND_REASON})"]
    assert summary["replaced"] == []


def test_reload_from_library_refuses_a_kind_change(model_space, tmp_path):
    d = _block(model_space)
    inst = model_space.place_block_instance(d.id, (0.0, 0.0))
    root = str(tmp_path / "lib")
    # The library copy: same id, higher version, kind schematic.
    lib_copy = BlockDefinition.from_dict(json.loads(open(
        _same_id_file(tmp_path, d, kind="schematic", stem="lib_src"),
        encoding="utf-8").read()))
    lib_copy.library, lib_copy.series = "L", "S"       # file it where blocks live
    block_library.save_to_library(lib_copy, root=root)
    assert block_library._find_by_id(d.id, root) is not None

    assert model_space.reload_block_definition(d.id, root=root) is False

    kept = model_space.get_block_definition(d.id)
    assert kept is d and kept.kind == "block"
    assert kept.version == d.version
    assert inst in kept._instances
