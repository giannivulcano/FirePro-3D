"""LT5 A2 -- the ``end`` capability and linetype default ends (design A).

Every persistence hop a ``tile`` / ``repeat`` record takes goes through
``BlockDefinition.to_dict`` / ``from_dict`` (``.fpd`` embed in scene_io,
undo snapshots, ``.fpdb`` save / load / bundle); these guards drive the
real ones and read the result back through the consumers (``end``,
``LinetypeDef.from_block``, ``stroke_style.resolve_ends``).
"""
import json

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import block_library
from firepro3d import stroke_style as ss
from firepro3d.block_definition import BlockDefinition, _norm_end, _norm_repeat
from firepro3d.geometry_2d import LineItem
from firepro3d.linetype_render import LinetypeDef
from firepro3d.model_space import Model_Space
from tests.lt3_support import make_linetype


def _end_block(name="Arrow", end=None):
    arm = LineItem(QPointF(-3.0, 1.0), QPointF(0.0, 0.0))
    return BlockDefinition.new(
        name=name, library="L", series="End Types", origin=(0.0, 0.0),
        primitives=[arm.to_dict()],
        end=end if end is not None else {"size": "fixed", "trim": 1.5})


@pytest.mark.parametrize("raw, exp", [
    (None, None), ("x", None), ([], None),
    ({}, {"size": "fixed", "trim": 0.0}),
    ({"size": "weight_relative", "trim": 2}, {"size": "weight_relative", "trim": 2.0}),
    ({"size": "huge", "trim": 1.0}, {"size": "fixed", "trim": 1.0}),
    ({"size": "fixed", "trim": -4}, {"size": "fixed", "trim": 0.0}),
    ({"size": "fixed", "trim": "abc"}, {"size": "fixed", "trim": 0.0}),
    ({"size": "fixed", "trim": float("nan")}, {"size": "fixed", "trim": 0.0}),
    ({"size": "fixed", "trim": None}, {"size": "fixed", "trim": 0.0}),
])
def test_norm_end(raw, exp):
    assert _norm_end(raw) == exp


def test_end_property_new_and_absent():
    d = _end_block()
    assert d.end == {"size": "fixed", "trim": 1.5}
    d.end["trim"] = 99.0                           # a copy, never the record
    assert d.end["trim"] == 1.5
    plain = BlockDefinition.new(name="P", library="L", series="S",
                                primitives=[], origin=(0, 0))
    assert plain.end is None and "end" not in plain.to_dict()


def test_set_end_bumps_version_and_notifies_like_the_other_capabilities():
    d = _end_block()
    seen = []

    class _Inst:
        def on_definition_changed(self):
            seen.append(d.version)
    d._instances.append(_Inst())
    v = d.version
    d.render_ops()
    d.set_end({"size": "weight_relative", "trim": 0.5})
    assert d.end == {"size": "weight_relative", "trim": 0.5}
    assert d.version == v + 1 and seen == [v + 1]
    assert d._render_ops is None                   # caches dropped
    d.set_end(None, notify=False)
    assert d.end is None and d.version == v + 1    # no bump without notify
    d.set_tile({"w": 5, "h": 5})                    # shared body: same bump
    assert d.version == v + 2 and seen == [v + 1, v + 2]
    d.set_repeat({"length": 9})
    assert d.version == v + 3 and seen == [v + 1, v + 2, v + 3]


def test_to_dict_from_dict_round_trip():
    d = _end_block(end={"size": "weight_relative", "trim": 0.25})
    rec = json.loads(json.dumps(d.to_dict()))
    assert rec["end"] == {"size": "weight_relative", "trim": 0.25}
    d2 = BlockDefinition.from_dict(rec)
    assert d2.end == d.end and d2.version == d.version


def test_fpd_save_load_embeds_the_end(qapp, tmp_path):
    ms = Model_Space()
    d = _end_block()
    ms.register_block_definition(d)
    path = tmp_path / "p.fpd"
    ms.save_to_file(str(path))
    ms2 = Model_Space()
    ms2.load_from_file(str(path))
    d2 = ms2.get_block_definition(d.id)
    assert d2 is not d and d2.end == {"size": "fixed", "trim": 1.5}


def test_undo_snapshot_keeps_the_end(qapp):
    ms = Model_Space()
    d = _end_block()
    ms.register_block_definition(d)
    ms.push_undo_state()
    d.set_end({"size": "weight_relative", "trim": 3.0})
    ms.push_undo_state()
    ms.undo()
    assert ms.get_block_definition(d.id).end == {"size": "fixed", "trim": 1.5}
    ms.redo()
    assert ms.get_block_definition(d.id).end == {"size": "weight_relative",
                                                 "trim": 3.0}


def test_fpdb_save_load_keeps_the_end(tmp_path):
    d = _end_block()
    path = block_library.save_to_library(d, root=str(tmp_path))
    with open(path, encoding="utf-8") as fh:
        assert json.load(fh)["end"] == {"size": "fixed", "trim": 1.5}
    loaded = block_library.load_block_file(path)
    assert loaded is not None and loaded.end == d.end


# ── linetype default ends: repeat.ends ────────────────────────────────────

def test_norm_repeat_keeps_end_ids_only():
    base = {"length": 9.0, "size": "drafting"}
    assert _norm_repeat({**base, "ends": {"start": "a1", "finish": "b2"}}) == {
        **base, "ends": {"start": "a1", "finish": "b2"}}
    assert _norm_repeat({**base, "ends": {"start": "a1", "finish": ""}}) == {
        **base, "ends": {"start": "a1"}}
    for junk in ({}, {"start": None}, {"start": ss.NONE, "finish": ss.BY_LINETYPE},
                 "a1", None, {"start": 5}):
        assert _norm_repeat({**base, "ends": junk}) == base     # byte-identical


def test_repeat_is_a_deep_copy():
    d = make_linetype()
    d.set_repeat({**d.repeat, "ends": {"start": "a1"}})
    d.repeat["ends"]["start"] = "zz"
    assert d.repeat["ends"] == {"start": "a1"}
    rec = d.to_dict()
    rec["repeat"]["ends"]["start"] = "zz"
    assert d.repeat["ends"] == {"start": "a1"}


def test_linetype_def_reads_the_default_ends():
    d = make_linetype()
    lt = LinetypeDef.from_block(d)
    assert (lt.start_end, lt.finish_end) == (None, None)
    d.set_repeat({**d.repeat, "ends": {"start": "a1", "finish": "b2"}})
    lt = LinetypeDef.from_block(d)
    assert (lt.start_end, lt.finish_end) == ("a1", "b2")


def test_linetype_with_ends_round_trips_fpd_and_fpdb(qapp, tmp_path):
    arrow = _end_block()
    lt_def = make_linetype()
    lt_def.set_repeat({**lt_def.repeat, "ends": {"finish": arrow.id}})
    ms = Model_Space()
    for d in (arrow, lt_def):
        ms.register_block_definition(d)
    path = tmp_path / "p.fpd"
    ms.save_to_file(str(path))
    ms2 = Model_Space()
    ms2.load_from_file(str(path))
    reg = ms2.block_registry
    lt2 = LinetypeDef.from_block(reg.get(lt_def.id))
    assert (lt2.start_end, lt2.finish_end) == (None, arrow.id)
    # The cascade resolves By Linetype to the reloaded end block.
    start, finish = ss.resolve_ends(ss.default_style(), lt2, reg)
    assert start == ss.ResolvedEnd(None, None, False)
    assert finish.defn is reg.get(arrow.id) and finish.missing_id is None
    fpdb = block_library.save_to_library(lt_def, root=str(tmp_path / "lib"))
    lt3 = LinetypeDef.from_block(block_library.load_block_file(fpdb))
    assert lt3.finish_end == arrow.id


def test_resolve_ends_through_a_real_registry(qapp):
    ms = Model_Space()
    arrow, hidden = _end_block(), make_linetype()
    for d in (arrow, hidden):
        ms.register_block_definition(d)
    reg = ms.block_registry
    st = ss.default_style()
    st["start"] = {"end": arrow.id, "visible": True}
    st["finish"] = {"end": hidden.id, "visible": True}    # a linetype: missing
    s, f = ss.resolve_ends(st, None, reg)
    assert s.defn is arrow and s.missing_id is None
    assert f == ss.ResolvedEnd(None, hidden.id, False)
    arrow.set_end(None)                                    # end capability off
    s, _ = ss.resolve_ends(st, None, reg)
    assert s == ss.ResolvedEnd(None, arrow.id, False)
