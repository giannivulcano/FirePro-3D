"""Mirror / scale pose survives every save / copy path (design DD7)."""
import json
import logging
import re
from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_instance import BlockInstance
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _def(ms):
    d = BlockDefinition.new(name="L", library="L", series="S", origin=(0.0, 0.0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict(),
                                        LineItem(QPointF(0, 0), QPointF(0, -40)).to_dict()])
    ms.register_block_definition(d)
    return d


def _posed(ms):
    inst = ms.place_block_instance(_def(ms).id, (30.0, 40.0))
    inst.set_block_rotation(30.0)
    inst.set_block_mirrored(True)
    inst.set_block_scale(2.0)
    inst._level_offset_mm = 300.0
    return inst


def _pose(inst):
    return (inst.block_pos(), round(inst.block_rotation(), 6), inst.block_mirrored(),
            round(inst.block_scale(), 6), inst._level_offset_mm)


def test_records_are_sparse(qapp):
    ms = Model_Space()
    plain = ms.place_block_instance(_def(ms).id, (0.0, 0.0))
    d = plain.to_dict()
    assert "mirrored" not in d and "scale" not in d
    nd = plain.to_nested_dict()
    assert "mirrored" not in nd and "scale" not in nd
    p = _posed(ms)
    assert p.to_dict()["mirrored"] is True and p.to_dict()["scale"] == 2.0
    assert p.to_nested_dict()["mirrored"] is True and p.to_nested_dict()["scale"] == 2.0


def test_from_dict_round_trip(qapp):
    ms = Model_Space()
    p = _posed(ms)
    q = BlockInstance.from_dict(p.to_dict(), ms.get_block_definition)
    assert _pose(q) == _pose(p)


def test_undo_restore_keeps_the_pose(qapp):
    ms = Model_Space()
    p = _posed(ms)
    want = _pose(p)
    ms.push_undo_state()
    p.set_block_mirrored(False)
    ms.push_undo_state()
    ms.undo()
    (inst,) = ms._block_instances
    assert _pose(inst) == want


def test_fpd_save_load_keeps_the_pose(qapp, tmp_path):
    ms = Model_Space()
    want = _pose(_posed(ms))
    f = tmp_path / "p.fpd"
    ms.save_to_file(str(f))
    rec = json.loads(f.read_text(encoding="utf-8"))["blocks"][0]
    assert (rec["mirrored"], rec["scale"]) == (True, 2.0)       # on disk, not in memory
    ms2 = Model_Space()
    ms2.load_from_file(str(f))
    (inst,) = ms2._block_instances
    assert _pose(inst) == want


def test_old_file_without_keys_loads_identity(qapp, tmp_path):
    ms = Model_Space()
    ms.place_block_instance(_def(ms).id, (5.0, 5.0))
    f = tmp_path / "old.fpd"
    ms.save_to_file(str(f))
    rec = json.loads(f.read_text(encoding="utf-8"))["blocks"][0]
    assert "mirrored" not in rec and "scale" not in rec
    ms2 = Model_Space()
    ms2.load_from_file(str(f))
    (inst,) = ms2._block_instances
    assert (inst.block_mirrored(), inst.block_scale()) == (False, 1.0)


@pytest.mark.parametrize("bad", [0.0, -2.0, "x", None])
def test_corrupt_scale_loads_as_identity(qapp, tmp_path, caplog, bad):
    ms = Model_Space()
    ms.place_block_instance(_def(ms).id, (5.0, 5.0))
    f = tmp_path / "bad.fpd"
    ms.save_to_file(str(f))
    data = json.loads(f.read_text(encoding="utf-8"))
    data["blocks"][0]["scale"] = bad
    f.write_text(json.dumps(data), encoding="utf-8")
    ms2 = Model_Space()
    with caplog.at_level(logging.WARNING, logger="firepro3d.block_instance"):
        ms2.load_from_file(str(f))
    (inst,) = ms2._block_instances
    assert inst.block_scale() == 1.0
    assert any("invalid scale" in r.getMessage() for r in caplog.records)
    q = BlockInstance.from_dict(data["blocks"][0], ms2.get_block_definition)
    assert q.block_scale() == 1.0


def test_paste_keeps_pose_and_level_offset(qapp):
    ms = Model_Space()
    p = _posed(ms)
    ms.paste_items(QPointF(100.0, 0.0), data=[p.to_dict()])
    new = [i for i in ms._block_instances if i is not p][0]
    want = _pose(p)
    assert _pose(new) == ((130.0, 40.0),) + want[1:]


def test_paste_keeps_level_offset(qapp):
    """G9: the pre-existing Level Offset drop (RED at a6caccfd)."""
    ms = Model_Space()
    inst = ms.place_block_instance(_def(ms).id, (0.0, 0.0))
    inst._level_offset_mm = 300.0
    ms.paste_items(QPointF(10.0, 0.0), data=[inst.to_dict()])
    new = [i for i in ms._block_instances if i is not inst][0]
    assert new._level_offset_mm == 300.0


def test_add_from_dict_builds_a_posed_block_copy(qapp):
    ms = Model_Space()
    p = _posed(ms)
    c = ms._add_from_dict(p.to_dict())
    assert c is not None and c is not p and c._uid != p._uid
    assert c in ms._block_instances and c.scene() is ms
    assert _pose(c) == _pose(p)


def test_add_from_dict_skips_a_missing_definition(qapp):
    ms = Model_Space()
    rec = _posed(ms).to_dict()
    rec["block_id"] = "no-such-block"
    assert ms._add_from_dict(rec) is None


def test_editor_seed_keeps_nested_pose(qapp):
    from firepro3d.schematic_scene import materialize_primitives
    src = Model_Space()
    p = _posed(src)
    rec = p.to_nested_dict()
    ed = Model_Space(scene_role="block_editor")
    ed.register_block_definition(src.get_block_definition(p.block_id))
    materialize_primitives(ed, [rec])
    (inst,) = ed._block_instances
    assert _pose(inst)[:4] == _pose(p)[:4]


def _call_text(src, start):
    """Source of the call opening at *start* up to its matching ')'."""
    i = src.index("(", start)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "(":
            depth += 1
        elif src[j] == ")":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
    raise AssertionError("unbalanced call")


@pytest.mark.xfail(strict=True, reason="Task 11 converts block_explode")
def test_every_place_block_instance_site_carries_the_pose():
    """Structural tripwire (not an AC guard): a rebuild site that passes
    fields one by one drops the next new field silently."""
    identity_sites = {("model_space.py", "rotation=0.0)"),       # commit_block_definition
                      ("model_view.py", "rotation=0.0)"),        # drag-drop: 0 deg rule
                      ("model_space.py", "self._place_block_rot")}  # placement (Task 10)
    root = Path(__file__).resolve().parents[1] / "firepro3d"
    bad = []
    for f in sorted(root.glob("*.py")):
        src = f.read_text(encoding="utf-8")
        for m in re.finditer(r"place_block_instance\(", src):
            if src[m.start() - 4:m.start()] == "def ":
                continue
            call = _call_text(src, m.start())
            ok = "place_kwargs" in call or "_compose" in call or any(
                f.name == n and k in call for n, k in identity_sites)
            if not ok:
                bad.append(f.name)
    assert not bad, f"place_block_instance calls without place_kwargs: {bad}"
