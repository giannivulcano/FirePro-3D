"""WM2 G9 (part) -- overrides survive every serialisation + restore path."""
import ast
import pathlib

from PyQt6.QtCore import QPointF

from firepro3d.block_instance import BlockInstance
from firepro3d.model_space import Model_Space
from tests.wm2_support import nested_record, scene_with, sprinkler_def

_OV = {"weight": "Thick", "linetype": "continuous"}
_OV2 = {"weight": "by_category", "linetype": "as_authored"}


def test_to_dict_omits_as_authored_and_round_trips(qapp):
    d = sprinkler_def()
    ms, inst = scene_with([d], d.id)
    assert "overrides" not in inst.to_dict()
    assert "overrides" not in inst.to_nested_dict()
    inst.set_overrides(_OV)
    assert inst.to_dict()["overrides"] == _OV
    assert inst.to_nested_dict()["overrides"] == _OV
    back = BlockInstance.from_dict(inst.to_dict(), ms.get_block_definition)
    assert back.overrides == _OV


def test_undo_restore_keeps_overrides(qapp):
    d = sprinkler_def()
    ms, inst = scene_with([d], d.id)
    ms.push_undo_state()
    inst.set_overrides(_OV)
    ms.push_undo_state()
    ms._block_instances[0].set_overrides(_OV2)
    ms.push_undo_state()
    ms.undo()
    assert ms._block_instances[0].overrides == _OV
    ms.redo()
    assert ms._block_instances[0].overrides == _OV2


def test_paste_keeps_overrides(qapp):
    d = sprinkler_def()
    ms, inst = scene_with([d], d.id, _OV)
    ms.paste_items(QPointF(100, 0), data=[inst.to_dict()])
    assert [i.overrides for i in ms._block_instances] == [_OV, _OV]


def test_file_round_trip(qapp, tmp_path):
    d = sprinkler_def()
    ms, _ = scene_with([d], d.id, _OV)
    path = tmp_path / "p.fpd"
    assert ms.save_to_file(str(path))
    ms2 = Model_Space()
    ms2.load_from_file(str(path))
    assert ms2._block_instances[0].overrides == _OV


def test_block_editor_seed_keeps_nested_overrides(qapp):
    from firepro3d.block_editor import BlockEditorWidget
    d = sprinkler_def()
    project = Model_Space()
    project.register_block_definition(d)
    w = BlockEditorWidget(project)
    w.seed_from_dicts([nested_record(d.id, _OV)])
    assert [i.overrides for i in w.editor_scene._block_instances] == [_OV]


def test_every_restore_caller_passes_overrides():
    """Structural backstop: each place_block_instance call that rebuilds a
    saved record (the five restore paths) passes overrides=."""
    root = pathlib.Path(__file__).resolve().parents[1] / "firepro3d"
    sites = {("scene_io.py", "bdict"), ("model_space.py", "bdict"),
             ("model_space.py", "obj"), ("block_editor.py", "d"),
             ("block_explode.py", "rec")}
    found = set()
    for fname, var in sites:
        tree = ast.parse((root / fname).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "attr", None) == "place_block_instance"
                    and any(isinstance(a, ast.Subscript)
                            and getattr(a.value, "id", None) == var
                            for a in node.args)):
                assert any(k.arg == "overrides" for k in node.keywords), (fname, var)
                found.add((fname, var))
    assert found == sites


def test_fpdb_round_trip_keeps_record_overrides(qapp, tmp_path):
    """G9: a host whose nested record overrides weight + linetype survives a
    .fpdb save / load into a fresh project, bringing the linetype along."""
    from firepro3d import block_library
    from firepro3d.block_definition import BlockDefinition
    from tests.lt3_support import make_linetype
    lt = make_linetype()
    s = sprinkler_def()
    ov = {"weight": "Thick", "linetype": lt.id}
    h = BlockDefinition.new(name="H", library="L", series="S",
                            primitives=[nested_record(s.id, ov)],
                            origin=(0.0, 0.0))
    ms, _inst = scene_with([lt, s, h], h.id)
    path = block_library.save_to_library(
        h, root=str(tmp_path), bundled=ms.block_registry.bundle_for(h.id))
    fresh = Model_Space()
    summary = fresh.load_blocks_from_files([path])
    assert summary["loaded"] and not summary["missing"]
    assert {h.id, s.id, lt.id} <= set(fresh._block_definitions)
    rec = fresh.get_block_definition(h.id).primitives[0]
    assert rec["overrides"] == ov
    # Observable: a placement in the fresh project strokes the override.
    inst = fresh.place_block_instance(h.id, (0.0, 0.0), level=fresh.active_level)
    strokes = [op for op in inst.render_ops() if op.kind == "stroke"]
    assert strokes and {op.weight for op in strokes} == {"Thick"}
    assert {op.linetype for op in strokes} == {lt.id}
