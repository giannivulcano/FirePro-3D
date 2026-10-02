"""Primitive uid — §6.1: assigned, carried by restore/load/seed, minted by copies."""
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem, ReferenceLineItem
from firepro3d.model_space import Model_Space
from firepro3d.text_item import TextItem


def _def_with_line(uid="src-line"):
    return BlockDefinition.new(
        name="U", library="L", series="S",
        primitives=[{"type": "draw_line", "pt1": [0, 0], "pt2": [100, 0],
                     "color": "#ffffff", "lineweight": 1.0, "uid": uid}],
        origin=(0.0, 0.0))


def test_every_primitive_gets_a_uid_and_round_trips(qapp):
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    assert isinstance(ln._uid, str) and len(ln._uid) == 32
    d = ln.to_dict()
    assert d["uid"] == ln._uid
    assert LineItem.from_dict(d)._uid == ln._uid
    legacy = {k: v for k, v in d.items() if k != "uid"}
    assert len(LineItem.from_dict(legacy)._uid) == 32      # legacy: minted on build
    assert LineItem(QPointF(0, 0), QPointF(1, 0))._uid != ln._uid
    rl = ReferenceLineItem.from_dict(ReferenceLineItem(QPointF(0, 0), QPointF(1, 1)).to_dict())
    assert rl.to_dict()["uid"] == rl._uid


def test_text_uid_round_trips(qapp):
    t = TextItem.from_dict(TextItem.from_dict({"type": "text", "text": "A", "x": 1, "y": 2}).to_dict())
    d = t.to_dict()
    assert TextItem.from_dict(d)._uid == d["uid"] == t._uid


def test_copy_paths_mint_fresh_uids(qapp):
    sc = Model_Space(scene_role="block_editor")
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    sc.addItem(ln); sc._draw_lines.append(ln)
    payload = [ln.to_dict()]
    assert payload[0]["uid"] == ln._uid          # clipboard keeps the source uid
    new = sc.paste_items(QPointF(5, 5), data=payload)
    assert len(new) == 1 and new[0]._uid != ln._uid
    assert len(new[0]._uid) == 32
    assert payload[0]["uid"] == ln._uid          # payload not mutated by the mint


def test_block_explode_mints_fresh_uids(qapp):
    from firepro3d.block_explode import explode_instances
    sc = Model_Space()
    d = _def_with_line("src-line")
    sc.register_block_definition(d)
    inst = sc.place_block_instance(d.id, (0.0, 0.0))
    created = explode_instances(sc, [inst], flatten=False)
    lines = [c for c in created if isinstance(c, LineItem)]
    assert len(lines) == 1 and lines[0]._uid not in ("src-line", None)


def test_undo_restore_carries_uids(qapp):
    sc = Model_Space(scene_role="block_editor")
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    sc.addItem(ln); sc._draw_lines.append(ln)
    sc.push_undo_state()
    uid = ln._uid
    ln.translate(5, 0); sc.push_undo_state()
    sc.undo()
    assert [l._uid for l in sc._draw_lines] == [uid]


def test_block_instance_uid_carried_by_nested_record_and_place(qapp):
    from firepro3d.block_instance import BlockInstance
    inst = BlockInstance(block_id="b", resolver=lambda _id: None)
    assert inst.to_nested_dict()["uid"] == inst._uid == inst.to_dict()["uid"]
    assert BlockInstance.from_dict(inst.to_dict(), lambda _id: None)._uid == inst._uid
    sc = Model_Space(scene_role="block_editor")
    placed = sc.place_block_instance("b", (0, 0), uid="abc")
    assert placed._uid == "abc"
    assert sc.place_block_instance("b", (0, 0))._uid not in ("abc", None)


def test_block_instance_uid_survives_undo_restore(qapp):
    sc = Model_Space()
    d = _def_with_line()
    sc.register_block_definition(d)
    inst = sc.place_block_instance(d.id, (0.0, 0.0))
    uid = inst._uid
    sc.push_undo_state()
    inst.translate(5, 0); sc.push_undo_state()
    sc.undo()
    assert [i._uid for i in sc._block_instances] == [uid]


def test_block_instance_uid_survives_save_and_load(qapp, tmp_path):
    sc = Model_Space()
    d = _def_with_line()
    sc.register_block_definition(d)
    uid = sc.place_block_instance(d.id, (3.0, 4.0))._uid
    fpath = str(tmp_path / "p.fpd")
    assert sc.save_to_file(fpath)
    sc2 = Model_Space()
    sc2.load_from_file(fpath)
    assert [i._uid for i in sc2._block_instances] == [uid]


def test_block_instance_paste_mints_fresh_uid(qapp):
    sc = Model_Space()
    d = _def_with_line()
    sc.register_block_definition(d)
    src = sc.place_block_instance(d.id, (0.0, 0.0))
    new = sc.paste_items(QPointF(10, 0), data=[src.to_dict()])
    assert len(new) == 1 and new[0]._uid not in (src._uid, None)


def test_editor_seed_carries_uids(qapp):
    from firepro3d.block_editor import BlockEditorWidget
    w = BlockEditorWidget(Model_Space())
    line = LineItem(QPointF(0, 0), QPointF(10, 0)).to_dict()
    w.seed_from_dicts([
        line,
        {"type": "block_instance", "block_id": "b", "pos": [0.0, 0.0],
         "rotation": 0.0, "uid": "nest1"},
    ])
    es = w.editor_scene
    assert [l._uid for l in es._draw_lines] == [line["uid"]]
    assert [i._uid for i in es._block_instances] == ["nest1"]
