"""Notes on schematics, Part 3: the two definition keys (N9, AC7, G5 keys half)."""
import json

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import block_library
from firepro3d.annotative import editor_text_printed, editor_text_scale
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_editor import BlockEditorWidget
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _line():
    return LineItem(QPointF(0, 0), QPointF(100, 0))


def _schematic(proj, name="Riser", sizing=None, scale=None):
    d = BlockDefinition.new(name=name, library="", series="", origin=(0.0, 0.0),
                            primitives=[_line().to_dict()], kind="schematic")
    d.text_sizing, d.text_scale = sizing, scale
    proj.register_block_definition(d)
    return d


def test_absent_keys_are_real_size_and_write_nothing(qapp):
    d = _schematic(Model_Space())
    rec = d.to_dict()
    assert "text_sizing" not in rec and "text_scale" not in rec
    back = BlockDefinition.from_dict(json.loads(json.dumps(rec)))
    assert back.text_sizing is None and back.text_scale is None
    assert back.text_print_scale is None


def test_both_keys_round_trip_the_dict(qapp):
    d = _schematic(Model_Space(), sizing="printed", scale=20.0)
    rec = json.loads(json.dumps(d.to_dict()))
    assert rec["text_sizing"] == "printed" and rec["text_scale"] == 20.0
    back = BlockDefinition.from_dict(rec)
    assert back.text_sizing == "printed" and back.text_scale == 20.0
    assert back.text_print_scale == 20.0


@pytest.mark.parametrize("rec", [{"text_sizing": "banana", "text_scale": 20.0},
                                 {"text_sizing": "printed", "text_scale": "x"},
                                 {"text_sizing": "printed", "text_scale": -4.0},
                                 {"text_sizing": "printed"}])
def test_a_damaged_record_never_scales(qapp, rec):
    d = _schematic(Model_Space())
    d2 = BlockDefinition.from_dict({**d.to_dict(), **rec})
    assert d2.text_print_scale is None


def test_project_save_and_reload_keeps_both_keys(qapp, tmp_path):
    proj = Model_Space()
    d = _schematic(proj, sizing="printed", scale=20.0)
    path = tmp_path / "p.fpd"
    proj.save_to_file(str(path), backup=False)
    other = Model_Space()
    other.load_from_file(str(path))
    got = other.get_block_definition(d.id)
    assert got.text_sizing == "printed" and got.text_scale == 20.0


def test_library_file_keeps_both_keys(qapp, tmp_path):
    d = _schematic(Model_Space(), sizing="printed", scale=20.0)
    path = block_library.save_to_library(d, root=str(tmp_path), overwrite=True)
    got = block_library.load_block_file(path)
    assert got.text_sizing == "printed" and got.text_scale == 20.0


def test_project_undo_keeps_both_keys(qapp):
    proj = Model_Space()
    d = _schematic(proj, sizing="printed", scale=20.0)
    proj.push_undo_state()
    assert proj.set_block_metadata(d.id, "Riser 2", "", "")
    proj.undo()
    got = proj.get_block_definition(d.id)
    assert got.name == "Riser"
    assert got.text_sizing == "printed" and got.text_scale == 20.0


def test_editor_seeds_saves_and_undoes_the_keys(qapp):
    """The editor's block_meta carries them from the definition, through an
    edit, back onto the definition, and through an editor undo."""
    proj = Model_Space()
    d = _schematic(proj, sizing="printed", scale=20.0)
    w = BlockEditorWidget(proj, block_id=d.id, kind="schematic")
    w.seed_from_definition(d)
    sc = w.editor_scene
    assert editor_text_printed(sc) and editor_text_scale(sc) == 20.0
    sc.set_block_meta({**sc.block_meta, "text_scale": 50.0})
    assert editor_text_scale(sc) == 50.0
    sc.undo()
    assert editor_text_scale(sc) == 20.0
    sc.redo()
    assert editor_text_scale(sc) == 50.0
    saved = w.commit_block("Riser", "", "")
    assert saved.text_sizing == "printed" and saved.text_scale == 50.0


def test_an_old_schematic_saves_with_neither_key(qapp):
    proj = Model_Space()
    d = _schematic(proj)
    w = BlockEditorWidget(proj, block_id=d.id, kind="schematic")
    w.seed_from_definition(d)
    assert not editor_text_printed(w.editor_scene)
    assert editor_text_scale(w.editor_scene) == 1.0
    rec = w.commit_block("Riser", "", "").to_dict()
    assert "text_sizing" not in rec and "text_scale" not in rec


def test_duplicate_carries_the_keys(qapp):
    proj = Model_Space()
    d = _schematic(proj, sizing="printed", scale=20.0)
    copy = proj.duplicate_block_definition(d.id)
    assert copy.kind == "schematic"
    assert copy.text_sizing == "printed" and copy.text_scale == 20.0


def test_seam_is_one_outside_a_printed_schematic(qapp):
    assert editor_text_scale(None) == 1.0
    assert editor_text_scale(Model_Space()) == 1.0                     # the plan
    assert editor_text_scale(Model_Space(scene_role="block_editor")) == 1.0
    sc = Model_Space(scene_role="block_editor")
    sc.set_block_meta({**sc.block_meta, "text_sizing": "printed", "text_scale": 48.0},
                      push_undo=False)
    assert editor_text_scale(sc) == 48.0
    sc.set_block_meta({**sc.block_meta, "text_sizing": None}, push_undo=False)
    assert editor_text_scale(sc) == 1.0
