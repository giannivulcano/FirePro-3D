"""SV1 Task 1 -- schematic kind, place refusal (G2), identity (D-S15)."""
from PyQt6.QtCore import QPointF

from firepro3d import block_library
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _line():
    return LineItem(QPointF(0, 0), QPointF(30, 0)).to_dict()


def _schematic(ms, name="Riser", series=""):
    d = BlockDefinition.new(name=name, library="", series=series,
                            primitives=[_line()], origin=(0.0, 0.0),
                            kind="schematic")
    ms.register_block_definition(d)
    return d


def _plain(ms, name="Plain"):
    d = BlockDefinition.new(name=name, library="L", series="S",
                            primitives=[_line()], origin=(0.0, 0.0))
    ms.register_block_definition(d)
    return d


# ── kind field ───────────────────────────────────────────────────────────────

def test_plain_block_to_dict_has_no_kind_key():
    d = BlockDefinition.new(name="P", library="L", series="S",
                            primitives=[_line()], origin=(0.0, 0.0))
    assert d.kind == "block"
    assert "kind" not in d.to_dict()


def test_schematic_kind_round_trips_through_dict():
    d = BlockDefinition.new(name="R", library="", series="", primitives=[_line()],
                            origin=(0.0, 0.0), kind="schematic")
    data = d.to_dict()
    assert data["kind"] == "schematic"
    assert BlockDefinition.from_dict(data).kind == "schematic"
    del data["kind"]
    assert BlockDefinition.from_dict(data).kind == "block"


def test_fpd_round_trip_keeps_schematic(qapp, tmp_path):
    ms = Model_Space()
    s = _schematic(ms)
    ms.push_undo_state()
    path = tmp_path / "p.fpd"
    ms.save_to_file(str(path))
    ms2 = Model_Space()
    ms2.load_from_file(str(path))
    d2 = ms2.get_block_definition(s.id)
    assert d2.kind == "schematic"
    assert d2.primitives == s.primitives


def test_undo_restore_keeps_schematic_kind(qapp):
    ms = Model_Space()
    ms.push_undo_state()
    s = _schematic(ms)
    ms.push_undo_state()
    ms.undo()
    assert ms.get_block_definition(s.id) is None
    ms.redo()
    assert ms.get_block_definition(s.id).kind == "schematic"


# ── G2 refusals ──────────────────────────────────────────────────────────────

def test_g2_set_mode_insert_refuses_a_schematic(qapp):
    ms = Model_Space()
    s = _schematic(ms)
    shown = []
    ms._show_status = lambda msg, timeout=5000: shown.append(msg)
    ms.set_mode("place_block", template=s.id)
    assert ms.mode != "place_block"
    assert ms.instance_count(s.id) == 0
    assert shown == [block_library.SCHEMATIC_REASON]
    p = _plain(ms)
    ms.set_mode("place_block", template=p.id)
    assert ms.mode == "place_block"


def test_g2_armed_click_refuses_a_block_that_became_a_schematic(qapp):
    ms = Model_Space()
    d = _plain(ms)
    ms.set_mode("place_block", template=d.id)
    d.kind = "schematic"
    ms._press_place_block(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    assert ms.instance_count(d.id) == 0
    assert ms.mode != "place_block"


def test_g2_drag_gate_refuses_in_plan_and_editor_scenes(qapp):
    from firepro3d.model_view import Model_View
    ms = Model_Space()
    s = _schematic(ms)
    p = _plain(ms)
    assert Model_View._resolve_block_drag(ms, {"id": s.id})[2] == \
        block_library.SCHEMATIC_REASON
    assert Model_View._resolve_block_drag(ms, {"id": p.id})[2] is None
    ed = Model_Space(scene_role="block_editor")
    ed.borrow_block_registry(ms.block_registry, owner=ms)
    assert Model_View._resolve_block_drag(ed, {"id": s.id})[2] == \
        block_library.SCHEMATIC_REASON
    assert Model_View._resolve_block_drag(ed, {"id": p.id})[2] is None


def test_g2_paste_skips_schematic_instances(qapp):
    ms = Model_Space()
    s = _schematic(ms)
    p = _plain(ms)
    shown = []
    ms._show_status = lambda msg, timeout=5000: shown.append(msg)
    rec = {"type": "block_instance", "pos": [0, 0], "rotation": 0.0,
           "level": ms.active_level}
    new = ms.paste_items(QPointF(0, 0), data=[{**rec, "block_id": s.id},
                                              {**rec, "block_id": p.id}])
    assert [i.block_id for i in new] == [p.id]
    assert ms.instance_count(s.id) == 0
    assert shown == [block_library.SCHEMATIC_REASON]


def test_commit_never_places_a_schematic(qapp):
    ms = Model_Space()
    d = ms.commit_block_definition(block_id=None, name="R", library="X", series="",
                                   primitives=[_line()], origin=(0.0, 0.0),
                                   place_instance=True, kind="schematic")
    assert d.kind == "schematic"
    assert d.library == ""
    assert ms.instance_count(d.id) == 0


def test_commit_edit_in_place_keeps_kind(qapp):
    ms = Model_Space()
    s = _schematic(ms)
    d = ms.commit_block_definition(block_id=s.id, name="R2", library="", series="",
                                   primitives=[_line(), _line()], origin=(0.0, 0.0),
                                   place_instance=False, kind="schematic")
    assert d is s and d.kind == "schematic" and d.name == "R2"


# ── identity (D-S15) ─────────────────────────────────────────────────────────

def test_schematic_rename_needs_only_a_name(qapp):
    ms = Model_Space()
    s = _schematic(ms)
    assert ms.set_block_metadata(s.id, "Riser B", "", "") is True
    assert (s.name, s.library, s.series) == ("Riser B", "", "")
    assert ms.set_block_metadata(s.id, "  ", "", "") is False


def test_schematic_name_unique_within_its_series(qapp):
    ms = Model_Space()
    a = _schematic(ms, "A", "Risers")
    b = _schematic(ms, "B", "Risers")
    _schematic(ms, "C", "")
    assert ms.set_block_metadata(b.id, "A", "", "Risers") is False
    assert ms.set_block_metadata(b.id, "A", "", "Details") is True
    assert ms.set_block_metadata(a.id, "C", "", "Risers") is True


def test_block_rename_rules_unchanged(qapp):
    ms = Model_Space()
    p = _plain(ms)
    assert ms.set_block_metadata(p.id, "X", "", "S") is False
    assert ms.set_block_metadata(p.id, "X", "L", "") is False


def test_commit_edit_without_kind_keeps_schematic(qapp):
    ms = Model_Space()
    s = _schematic(ms)
    d = ms.commit_block_definition(block_id=s.id, name="R3", library="", series="",
                                   primitives=[_line()], origin=(0.0, 0.0),
                                   place_instance=True)
    assert d.kind == "schematic" and ms.instance_count(s.id) == 0


def test_commit_refuses_a_kind_change_on_edit(qapp):
    ms = Model_Space()
    p = _plain(ms)
    s = _schematic(ms)
    assert ms.commit_block_definition(block_id=p.id, name="P", library="L", series="S",
                                      primitives=[_line()], origin=(0.0, 0.0),
                                      place_instance=False, kind="schematic") is None
    assert p.kind == "block"
    assert ms.commit_block_definition(block_id=s.id, name="R", library="", series="",
                                      primitives=[_line()], origin=(0.0, 0.0),
                                      place_instance=False, kind="block") is None
    assert s.kind == "schematic"
