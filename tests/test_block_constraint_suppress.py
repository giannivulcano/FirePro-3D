"""Constraint Points off offers ins only; existing constraints keep working
(D10-D13)."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.constraint_controller import PickState
from firepro3d.model_space import Model_Space
from firepro3d.wall import WallSegment
from tests._block_snap_helpers import register_snap_block


@pytest.fixture
def sc(qapp):
    s = Model_Space()
    yield s
    s.cleanup()


def snap_def(sc):
    """The Snap block with stable record uids u0 .. u5."""
    d = register_snap_block(sc)
    d.set_primitives([{**r, "uid": f"u{i}"} for i, r in enumerate(d.primitives)])
    return d


def wall(sc, a, b):
    w = WallSegment(QPointF(*a), QPointF(*b))
    sc.addItem(w)
    sc._walls.append(w)
    return w


def _cands(ctl, uid):
    pk = PickState(ctl, "coincident")
    return sorted(r["h"] for _k, r, _a, _b in pk._candidates()
                  if isinstance(r, dict) and r.get("uid") == uid)


def test_off_offers_ins_only_for_every_kind(sc):
    inst = sc.place_block_instance(snap_def(sc).id, (1000.0, 0.0))
    ctl = sc.constraint_ctl
    kinds = {k for k, r, _a, _b in PickState(ctl, "coincident")._candidates()
             if isinstance(r, dict) and r.get("uid") == inst._uid}
    assert {"point", "edge"} <= kinds               # the guard needs edges to bite
    before = _cands(ctl, inst._uid)
    assert len(before) > 1
    inst.constraint_points_off = True
    now = [(k, r["h"]) for k, r, _a, _b in PickState(ctl, "coincident")._candidates()
           if isinstance(r, dict) and r.get("uid") == inst._uid]
    assert now == [("point", "ins")]
    inst.constraint_points_off = False
    assert _cands(ctl, inst._uid) == before


def test_an_existing_constraint_keeps_solving(sc):
    """The real solve path: the wall moves, the tie carries the block."""
    d = snap_def(sc)
    w = wall(sc, (0, -1500), (4000, -1500))
    inst = sc.place_block_instance(d.id, (1000.0, 0.0))
    ctl = sc.constraint_ctl
    c = ctl.add("dim_point_line", [{"uid": inst._uid, "h": "u0:p1"},
                                   {"uid": w._uid, "h": "face_l"}])
    assert c is not None and c.driving
    inst.constraint_points_off = True
    with ctl.edit([w]):
        w.translate(0.0, 500.0)
    assert inst.block_pos() == pytest.approx((1000.0, 500.0), abs=1e-4)
    assert not c.inert and c.id in [x.id for x in ctl.active()]
    assert _cands(ctl, inst._uid) == ["ins"]


def test_object_snap_still_finds_the_child_point(sc):
    inst = sc.place_block_instance(snap_def(sc).id, (1000.0, 0.0))
    before = [b for b, _ in inst.snap_primitives()]
    inst.constraint_points_off = True
    assert [b for b, _ in inst.snap_primitives()] == before and before


def test_auto_constrain_joins_no_suppressed_child(sc):
    from firepro3d.auto_constrain import point_handle_at, item_handles
    inst = sc.place_block_instance(snap_def(sc).id, (1000.0, 0.0))
    p = next(a for k, r, a, _b in item_handles(inst) if k == "point" and r["h"] != "ins")
    assert point_handle_at(inst, (p.x(), p.y())) is not None
    inst.constraint_points_off = True
    assert point_handle_at(inst, (p.x(), p.y())) in (None, "ins")


def _nested_parent(be, extra_sibling=None):
    d = snap_def(be)
    rec = {"type": "block_instance", "block_id": d.id, "pos": [0.0, 0.0],
           "rotation": 0.0, "uid": "kid"}
    own = {"type": "block_instance", "block_id": d.id, "pos": [500.0, 0.0],
           "rotation": 0.0, "uid": "keep"}
    recs = [rec, own] + ([extra_sibling] if extra_sibling else [])
    p = BlockDefinition.new(name="P", library="L", series="",
                            primitives=recs, origin=(0.0, 0.0))
    be.register_block_definition(p)
    return p, rec, own


def test_off_on_a_nested_block_removes_it_from_the_parent(qapp):
    be = Model_Space(scene_role="block_editor")
    try:
        p, rec, own = _nested_parent(be)
        inst = be.place_block_instance(p.id, (0.0, 0.0))
        all_h = _cands(be.constraint_ctl, inst._uid)
        assert any(h.startswith("kid/") for h in all_h)    # child handle: "kid/u0:p1"
        assert "kid:ins" in all_h
        p.set_primitives([dict(rec, constraint_points_off=True), own])
        now = _cands(be.constraint_ctl, inst._uid)
        assert not any(h.startswith("kid") for h in now)    # "kid:ins" goes too
        assert any(h.startswith("keep/") for h in now) and "ins" in now
    finally:
        be.cleanup()


def test_a_sibling_path_sharing_a_prefix_is_not_removed(qapp):
    be = Model_Space(scene_role="block_editor")
    try:
        d = snap_def(be)
        rec2 = {"type": "block_instance", "block_id": d.id, "pos": [900.0, 0.0],
                "rotation": 0.0, "uid": "kid2"}
        p, rec, own = _nested_parent(be, rec2)
        inst = be.place_block_instance(p.id, (0.0, 0.0))
        p.set_primitives([dict(rec, constraint_points_off=True), own, rec2])
        now = _cands(be.constraint_ctl, inst._uid)
        assert not any(h.startswith("kid:") or h.startswith("kid/") for h in now)
        assert any(h.startswith("kid2/") for h in now) and "kid2:ins" in now
    finally:
        be.cleanup()
