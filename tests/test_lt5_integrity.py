"""LT5 D3 / E9 integrity -- end references are real block dependencies:
referenced_ids (explicit ends + linetype defaults) -> users_of / delete
refusal ("used by N lines / linetypes"), bundle_for -> .fpdb, would_cycle;
End type off refused while used; invalidate repaints raw end users and the
placed blocks hosting them (I1)."""
import json

from PyQt6.QtCore import QPointF

from firepro3d import block_library
from firepro3d import stroke_style as ss
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_registry import end_users_in, referenced_ids
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import make_linetype
from tests.lt5_support import scene_line, v_end


def _rec(end=None, which="finish", linetype=None):
    ln = LineItem(QPointF(0, 0), QPointF(30, 0))
    if end is not None:
        ln.style[which] = {"end": end, "visible": True}
    if linetype is not None:
        ln.style["linetype"] = linetype
    return ln.to_dict()


def _host(ms, *recs, name="Host"):
    d = BlockDefinition.new(name=name, library="L", series="S",
                            primitives=list(recs), origin=(0.0, 0.0))
    ms.register_block_definition(d)
    return d


def _lt_with_default(ms, eid, which="start", name="Hidden"):
    lt = make_linetype(name)
    rep = lt.repeat
    rep["ends"] = {which: eid}
    lt.set_repeat(rep)
    ms.register_block_definition(lt)
    return lt


def _arrow(ms):
    e = v_end("Arrow")
    ms.register_block_definition(e)
    return e


def test_explicit_end_is_a_dependency_and_refuses_delete(qapp):
    ms = Model_Space()
    e = _arrow(ms)
    h = _host(ms, _rec(e.id))
    assert e.id in referenced_ids(h)
    assert ms.block_registry.users_of(e.id) == {h.id}
    assert ms.delete_block_definition(e.id) is False
    assert ms.block_users_message(e.id) == (
        "“Arrow” is used by 1 line — change their ends first.")


def test_linetype_default_end_is_a_dependency_and_refuses_delete(qapp):
    ms = Model_Space()
    e = _arrow(ms)
    lt = _lt_with_default(ms, e.id)
    assert e.id in referenced_ids(lt)
    assert ms.delete_block_definition(e.id) is False
    assert ms.block_users_message(e.id) == (
        "“Arrow” is used by 1 linetype — change their ends first.")


def test_live_plan_line_refuses_delete_until_removed(qapp):
    ms = Model_Space()
    e = _arrow(ms)
    ln = scene_line(ms, finish={"end": e.id, "visible": True})
    assert end_users_in(ms, e.id) == [ln]
    assert ms.delete_block_definition(e.id) is False
    assert ms.block_users_message(e.id) == (
        "“Arrow” is used by 1 line — change their ends first.")
    ms._remove_item_from_lists(ln)
    assert ms.delete_block_definition(e.id) is True


def test_lines_and_linetypes_counted_together(qapp):
    ms = Model_Space()
    e = _arrow(ms)
    _host(ms, _rec(e.id), _rec(e.id, which="start"))
    _lt_with_default(ms, e.id)
    scene_line(ms, start={"end": e.id, "visible": False})   # hidden still counts
    assert ms.block_users_message(e.id) == (
        "“Arrow” is used by 3 lines and 1 linetype — change their ends first.")


def test_keywords_are_not_dependencies(qapp):
    ms = Model_Space()
    e = _arrow(ms)
    for kw in (ss.BY_LINETYPE, ss.NONE):
        h = _host(ms, _rec(kw), name=kw)
        assert referenced_ids(h) == set()
    assert ms.delete_block_definition(e.id) is True


def test_fpdb_bundles_an_explicit_end(qapp, tmp_path):
    ms = Model_Space()
    e = _arrow(ms)
    h = _host(ms, _rec(e.id))
    path = block_library.save_to_library(
        h, root=str(tmp_path), bundled=ms.block_registry.bundle_for(h.id))
    data = json.loads(open(path, encoding="utf-8").read())
    assert data["bundled"][e.id]["end"] == {"size": "fixed", "trim": 0.0}


def test_fpdb_bundles_an_end_via_linetype_default(qapp, tmp_path):
    ms = Model_Space()
    e = _arrow(ms)
    lt = _lt_with_default(ms, e.id)
    h = _host(ms, _rec(linetype=lt.id))
    bundle = ms.block_registry.bundle_for(h.id)
    assert set(bundle) == {lt.id, e.id}
    assert bundle[lt.id]["repeat"]["ends"] == {"start": e.id}
    path = block_library.save_to_library(h, root=str(tmp_path), bundled=bundle)
    data = json.loads(open(path, encoding="utf-8").read())
    assert set(data["bundled"]) == {lt.id, e.id}


def test_end_through_its_own_linetype_is_a_cycle(qapp):
    ms = Model_Space()
    shown = []
    ms._show_status = lambda m, t=5000: shown.append(m)
    e = _arrow(ms)
    lt = _lt_with_default(ms, e.id)
    assert ms.block_registry.would_cycle(e.id, lt.id)
    before = [dict(p) for p in e.primitives]
    out = ms.commit_block_definition(
        block_id=e.id, name="Arrow", library="L", series="End Types",
        primitives=[_rec(linetype=lt.id)], origin=(0.0, 0.0),
        place_instance=False, capability=("end", e.end))
    assert out is None
    assert ms.get_block_definition(e.id).primitives == before
    assert shown == ["A block can't contain itself"]


def test_end_off_refused_at_save_while_used(qapp):
    ms = Model_Space()
    shown = []
    ms._show_status = lambda m, t=5000: shown.append(m)
    e = _arrow(ms)
    scene_line(ms, finish={"end": e.id, "visible": True})
    assert ms.end_off_refusal(e.id) == (
        "“Arrow” is used by 1 line — change their ends first.")
    out = ms.commit_block_definition(
        block_id=e.id, name="Arrow", library="L", series="End Types",
        primitives=list(e.primitives), origin=(0.0, 0.0),
        place_instance=False, capability=None)
    assert out is None and ms.get_block_definition(e.id).end is not None
    assert shown == ["“Arrow” is used by 1 line — change their ends first."]
    assert ms.end_off_refusal(None) is None


def _spy(item):
    calls = []
    prep, upd = item.prepareGeometryChange, item.update
    item.prepareGeometryChange = lambda: (calls.append("prep"), prep())[1]
    item.update = lambda *a: (calls.append("update"), upd(*a))[1]
    return calls


def test_invalidate_repaints_explicit_and_by_linetype_end_users(qapp):
    """The bounds / trimmed-path of raw lines follow an end edit: explicit
    users and By Linetype users of a linetype whose default is the end
    (no pixel truth exists for a missed prepareGeometryChange -- P4 probe:
    scene.items(rect) does not expose stale bounds -- so the spy observes
    the calls themselves)."""
    ms = Model_Space(scene_role="block_editor")
    e = _arrow(ms)
    lt = _lt_with_default(ms, e.id, which="finish")
    direct = scene_line(ms, finish={"end": e.id, "visible": True})
    via_lt = scene_line(ms, (0, 10), (30, 10), linetype=lt.id)
    bystander = scene_line(ms, (0, 20), (30, 20))
    calls = [_spy(direct), _spy(via_lt), _spy(bystander)]
    e.set_end({"size": "fixed", "trim": 2.0})
    ms.block_registry.invalidate(e.id)
    assert "prep" in calls[0] and "update" in calls[0]
    assert "prep" in calls[1] and "update" in calls[1]
    assert calls[2] == []
    assert set(end_users_in(ms, e.id, via_linetype=True)) == {direct, via_lt}


def test_registry_add_captures_that_the_old_block_was_an_end(qapp):
    """Replacing an end by a non-end (library reload) flips its users to
    missing: the old ``end`` is captured before it is gone."""
    ms = Model_Space(scene_role="block_editor")
    e = _arrow(ms)
    ln = scene_line(ms, finish={"end": e.id, "visible": True})
    calls = _spy(ln)
    data = e.to_dict()
    data["end"] = None
    data["version"] = e.version + 1
    ms.register_block_definition(BlockDefinition.from_dict(data))
    assert "prep" in calls and "update" in calls


def test_i1_end_edit_repaints_and_regrows_the_host_block(qapp):
    """Orchestrator I1: a placed block whose line draws an Arrow end; the
    Arrow is edited through the real save path (commit_block_definition ->
    set_primitives -> registry.invalidate). The host instance must get
    prepareGeometryChange (else Qt keeps stale bounds / trails) and its
    boundingRect must now cover the bigger arrow."""
    ms = Model_Space()
    e = _arrow(ms)                                   # V head, half-height 1
    h = _host(ms, _rec(e.id))
    inst = ms.place_block_instance(h.id, (0.0, 0.0))
    before = inst.boundingRect()
    calls = _spy(inst)
    big = v_end("Arrow", length=40.0, half=40.0)
    out = ms.commit_block_definition(
        block_id=e.id, name="Arrow", library="L", series="End Types",
        primitives=list(big.primitives), origin=(0.0, 0.0),
        place_instance=False, capability=("end", e.end))
    assert out is e
    assert "prep" in calls and "update" in calls
    after = inst.boundingRect()
    assert after.contains(before)
    assert after.height() > before.height() + 10.0
