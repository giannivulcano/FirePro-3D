"""Plan block constraints (design 2026-10-31) -- headless plan-scene tests.

A real ``Model_Space()`` (scene_role "plan") with the Snap block
(tests/_block_snap_helpers) given stable record uids u0..u5 (u5 = the nested
Inner record) and placed level-scoped; walls / gridlines built directly.
Expected positions come from the fixture geometry -- the Snap block's
definition-local coordinates (L1 p1 = (60, -80), |p1 - ins| = 100) and the
walls' drawn lines -- never from the solver under test.
"""
from __future__ import annotations

import json
import logging
import math

import pytest
from PyQt6.QtCore import QPointF, QSettings

from firepro3d.constants import AUTO_CONSTRAIN_KEY
from firepro3d.model_space import Model_Space
from firepro3d.wall import WallSegment
from tests._block_snap_helpers import register_snap_block
from tests._hosted_blocks_helpers import gridline

HOST = {"offset_mm": 200.0, "along_mm": 1500.0, "elevation_mm": 0.0, "facing": 1}


def snap_def(sc):
    """The Snap block with stable record uids ``u0`` .. ``u5`` (u0 = L1)."""
    d = register_snap_block(sc)
    d.set_primitives([{**r, "uid": f"u{i}"} for i, r in enumerate(d.primitives)])
    return d


def wall(sc, a, b):
    w = WallSegment(QPointF(*a), QPointF(*b))
    sc.addItem(w)
    sc._walls.append(w)
    return w


def wall_xy(w):
    return (w._pt1.x(), w._pt1.y(), w._pt2.x(), w._pt2.y())


def _status(s):
    msgs = []
    s._show_status = lambda m, *a, **k: msgs.append(m)
    return msgs


@pytest.fixture
def sc(qapp):
    s = Model_Space()
    yield s
    s.cleanup()


# ── Task 2: capability (PB1) ────────────────────────────────────────────────

def test_plan_capability_offers_level_scoped_blocks_not_hosted(sc):
    from firepro3d.block_instance import BlockInstance
    from firepro3d.constraint_controller import plan_ref_uids
    from firepro3d.gridline import GridlineItem
    d = snap_def(sc)
    inst = sc.place_block_instance(d.id, (1000.0, 0.0))
    gl = gridline(sc, (0, -3000), (6000, -3000), "B")
    hosted = sc.place_block_instance(d.id, (0, 0), host={"gridline": gl._uid, **HOST})
    ctl = sc.constraint_ctl
    assert hosted is not None and hosted.host
    assert set(ctl.ref_types) == {WallSegment, GridlineItem, BlockInstance}
    assert inst in ctl.items() and hosted not in ctl.items()
    assert ctl.can_ref(inst) and not ctl.can_ref(hosted)
    assert plan_ref_uids(sc) == {inst._uid, gl._uid}
    assert ctl.primitive_uids() == {inst._uid, gl._uid}


def test_a_record_naming_a_hosted_block_is_refused_at_add(sc):
    from firepro3d.constraint_controller import INVALID_STATUS
    d = snap_def(sc)
    w = wall(sc, (0, -1500), (4000, -1500))
    gl = gridline(sc, (0, -3000), (6000, -3000), "B")
    hosted = sc.place_block_instance(d.id, (0, 0), host={"gridline": gl._uid, **HOST})
    msgs = _status(sc)
    assert sc.constraint_ctl.add("coincident", [{"uid": hosted._uid, "h": "ins"},
                                                {"uid": w._uid, "h": "p1"}]) is None
    assert INVALID_STATUS in msgs
    assert sc.constraint_ctl.constraints == []


def test_selection_first_lines_stay_walls_and_gridlines(sc):
    """A selected block is not a plan "line": Horizontal / Vertical / Smart
    Dimension selection-first give None (pick mode follows) instead of an
    ``edge`` ref the block lacks; Fix takes the whole block (AC1)."""
    d = snap_def(sc)
    inst = sc.place_block_instance(d.id, (1000.0, 0.0))
    sc.clearSelection()
    inst.setSelected(True)
    ctl = sc.constraint_ctl
    assert sc.selectedItems() == [inst]
    for ctype in ("horizontal", "vertical", "dim_distance"):
        assert ctl.selection_refs(ctype) is None, ctype
    assert ctl.selection_refs("fix") == [{"uid": inst._uid, "h": "item"}]


def test_load_keeps_block_records_and_drops_hosted_ones(sc, tmp_path, caplog):
    d = snap_def(sc)
    w = wall(sc, (0, -1500), (4000, -1500))
    gl = gridline(sc, (0, -3000), (6000, -3000), "B")
    inst = sc.place_block_instance(d.id, (1000.0, 0.0))
    hosted = sc.place_block_instance(d.id, (0, 0), host={"gridline": gl._uid, **HOST})
    f = tmp_path / "p.fpd"
    sc.save_to_file(str(f))
    data = json.loads(f.read_text())
    data["constraints"] = [
        {"id": "blk", "type": "coincident",
         "refs": [{"uid": inst._uid, "h": "u0:p1"}, {"uid": w._uid, "h": "p1"}]},
        {"id": "hosted", "type": "coincident",
         "refs": [{"uid": hosted._uid, "h": "ins"}, {"uid": w._uid, "h": "p2"}]},
    ]
    f.write_text(json.dumps(data))
    b = Model_Space()
    try:
        with caplog.at_level(logging.INFO):
            b.load_from_file(str(f))
        assert [c.id for c in b.constraint_ctl.constraints] == ["blk"]
        assert any("Clean-drop: discarded 1 " in r.getMessage() for r in caplog.records)
    finally:
        b.cleanup()


# ── Task 3: annotative = ins only (PB2) ─────────────────────────────────────

def _cands(ctl, uid):
    from firepro3d.constraint_controller import PickState
    pk = PickState(ctl, "coincident")
    return sorted(r["h"] for _k, r, _a, _b in pk._candidates()
                  if isinstance(r, dict) and r.get("uid") == uid)


def test_a_definition_turning_annotative_makes_child_handle_records_inert(sc):
    d = snap_def(sc)
    w = wall(sc, (0, -1500), (4000, -1500))
    inst = sc.place_block_instance(d.id, (1000.0, 0.0))
    ctl = sc.constraint_ctl
    c = ctl.add("dim_point_line", [{"uid": inst._uid, "h": "u0:p1"}, {"uid": w._uid, "h": "edge"}])
    k = ctl.add("dim_point_line", [{"uid": inst._uid, "h": "ins"}, {"uid": w._uid, "h": "edge"}])
    assert c is not None and k is not None
    assert "u0:p1" in _cands(ctl, inst._uid)
    d.scale_mode = "annotative"
    ids = [x.id for x in ctl.active()]
    assert c.inert and c.invalid and c.id not in ids
    assert k.id in ids and not k.inert
    assert _cands(ctl, inst._uid) == ["ins"]
    recs = [r for r in ctl.to_records() if r["id"] == c.id]
    assert recs[0]["refs"][0] == {"uid": inst._uid, "h": "u0:p1"}   # verbatim


def test_annotative_nested_instance_in_the_block_editor_keeps_its_handles(qapp):
    be = Model_Space(scene_role="block_editor")
    try:
        d = snap_def(be)
        d.scale_mode = "annotative"
        inst = be.place_block_instance(d.id, (40.0, 20.0))
        hs = _cands(be.constraint_ctl, inst._uid)
        assert "ins" in hs and "u0:p1" in hs
    finally:
        be.cleanup()


# ── Task 4: two-tier stateless solve (PB3) ─────────────────────────────────

W_A = (0.0, -1500.0, 4000.0, -1500.0)          # the usual wall, 1500 above ins (1000, 0)


def _tied(sc, h="u0:p1", target="edge"):
    d = snap_def(sc)
    w = wall(sc, W_A[:2], W_A[2:])
    inst = sc.place_block_instance(d.id, (1000.0, 0.0))
    c = sc.constraint_ctl.add("dim_point_line", [{"uid": inst._uid, "h": h},
                                                 {"uid": w._uid, "h": target}])
    assert c is not None and c.driving
    return d, w, inst, c


def test_wall_edit_carries_a_tied_block(sc):
    _d, w, inst, _c = _tied(sc, target="face_l")
    with sc.constraint_ctl.edit([w]):
        w.translate(0.0, 500.0)
    assert wall_xy(w) == pytest.approx((0.0, -1000.0, 4000.0, -1000.0), abs=1e-9)
    assert inst.block_pos() == pytest.approx((1000.0, 500.0), abs=1e-4)
    assert inst.block_rotation() == pytest.approx(0.0, abs=1e-4)   # solver noise ~1e-6 deg


def test_block_move_slides_along_its_tie_and_never_moves_the_wall(sc):
    _d, w, inst, _c = _tied(sc)
    with sc.constraint_ctl.edit([inst]):
        inst.translate(600.0, 400.0)
    assert inst.block_pos() == pytest.approx((1600.0, 0.0), abs=1e-4)
    assert inst.block_rotation() == pytest.approx(0.0, abs=1e-4)
    assert wall_xy(w) == pytest.approx(W_A, abs=1e-9)


def test_block_tier_add_moves_the_block_onto_the_held_wall(sc):
    d = snap_def(sc)
    w = wall(sc, W_A[:2], W_A[2:])
    inst = sc.place_block_instance(d.id, (1000.0, 0.0))
    assert sc.constraint_ctl.add("coincident", [{"uid": inst._uid, "h": "ins"},
                                                {"uid": w._uid, "h": "p1"}])
    assert inst.block_pos() == pytest.approx((0.0, -1500.0), abs=1e-4)
    assert wall_xy(w) == pytest.approx(W_A, abs=1e-9)


def test_typed_rotation_a_parallel_tie_forbids_is_refused(sc):
    from firepro3d.constraint_controller import CONFLICT_STATUS
    d = snap_def(sc)
    w = wall(sc, W_A[:2], W_A[2:])
    inst = sc.place_block_instance(d.id, (1000.0, 0.0))
    assert sc.constraint_ctl.add("parallel", [{"uid": inst._uid, "h": "u0:edge"},
                                              {"uid": w._uid, "h": "edge"}])
    msgs = _status(sc)
    with sc.constraint_ctl.edit([inst], typed=True):
        inst.set_block_rotation(45.0)
    assert inst.block_rotation() == pytest.approx(0.0, abs=1e-9)
    assert wall_xy(w) == pytest.approx(W_A, abs=1e-9)
    assert CONFLICT_STATUS in msgs


def _two_walls(sc):
    """Wall A 1500 above, wall B 1500 below ins (1000, 0); t1 = L1 p1 -> A,
    t2 = ins -> B. L1 p1 sits 80 above ins and 100 from it, so following A
    by dy is reachable only while |dy - 80| <= 100."""
    d = snap_def(sc)
    a = wall(sc, (0.0, -1500.0), (4000.0, -1500.0))
    b = wall(sc, (0.0, 1500.0), (4000.0, 1500.0))
    inst = sc.place_block_instance(d.id, (1000.0, 0.0))
    ctl = sc.constraint_ctl
    t1 = ctl.add("dim_point_line", [{"uid": inst._uid, "h": "u0:p1"}, {"uid": a._uid, "h": "edge"}])
    t2 = ctl.add("dim_point_line", [{"uid": inst._uid, "h": "ins"}, {"uid": b._uid, "h": "edge"}])
    assert t1 is not None and t2 is not None
    return a, b, inst, t1, t2


def test_wall_edit_a_block_cannot_follow_commits_and_reds_the_tie(sc):
    from firepro3d.constraint_controller import CONFLICT_STATUS
    a, b, inst, t1, t2 = _two_walls(sc)
    msgs = _status(sc)
    with sc.constraint_ctl.edit([a]):
        a.translate(0.0, 600.0)
    assert wall_xy(a) == pytest.approx((0.0, -900.0, 4000.0, -900.0), abs=1e-9)
    assert inst.block_pos() == pytest.approx((1000.0, 0.0), abs=1e-9)
    assert inst.block_rotation() == 0.0
    assert t1.id in sc.constraint_ctl.red and t2.id not in sc.constraint_ctl.red
    assert CONFLICT_STATUS not in msgs


def test_mixed_move_walls_lead_and_blocks_keep_the_applied_pose(sc):
    a, b, inst, t1, t2 = _two_walls(sc)
    with sc.constraint_ctl.edit([a, inst]):
        a.translate(0.0, 600.0)
        inst.translate(0.0, 600.0)
    assert wall_xy(a) == pytest.approx((0.0, -900.0, 4000.0, -900.0), abs=1e-9)
    assert inst.block_pos() == pytest.approx((1000.0, 600.0), abs=1e-9)
    assert t2.id in sc.constraint_ctl.red and t1.id not in sc.constraint_ctl.red


def test_building_tier_add_carries_attached_blocks(sc):
    d = snap_def(sc)
    w = wall(sc, (0.0, -1500.0), (4000.0, -1100.0))          # tilted
    inst = sc.place_block_instance(d.id, (1000.0, 0.0))
    ctl = sc.constraint_ctl
    assert ctl.add("dim_point_line", [{"uid": inst._uid, "h": "ins"}, {"uid": w._uid, "h": "edge"}])
    d0 = abs(1000.0 * 400.0 - 1500.0 * 4000.0) / math.hypot(4000.0, 400.0)   # ins to the drawn line
    assert ctl.add("horizontal", [{"uid": w._uid, "h": "edge"}])
    assert w._pt1.y() == pytest.approx(w._pt2.y(), abs=1e-6)
    assert inst.block_pos()[1] - w._pt1.y() == pytest.approx(d0, abs=1e-6)
    assert inst.block_pos()[0] == pytest.approx(1000.0, abs=1e-6)


def test_an_unconstrained_block_never_moves_with_a_wall(sc):
    d, w, _inst, _c = _tied(sc)
    loose = sc.place_block_instance(d.id, (2000.0, -1400.0))
    with sc.constraint_ctl.edit([w]):
        w.translate(0.0, 300.0)
    assert loose.block_pos() == (2000.0, -1400.0)


def test_load_solves_walls_first_then_blocks_against_held_walls(sc):
    _d, w, inst, _c = _tied(sc, h="ins")
    ctl = sc.constraint_ctl
    recs = ctl.to_records()
    recs[0]["value"] = 1000.0                                  # the file disagrees with the geometry
    ctl.load(recs)
    assert inst.block_pos() == pytest.approx((1000.0, -500.0), abs=1e-4)   # 1000 below the held wall
    assert wall_xy(w) == pytest.approx(W_A, abs=1e-9)


def test_typed_value_on_a_block_tier_dim_moves_the_block_not_the_wall(sc):
    d = snap_def(sc)
    w = wall(sc, W_A[:2], W_A[2:])
    inst = sc.place_block_instance(d.id, (1000.0, 0.0))
    ctl = sc.constraint_ctl
    c = ctl.add("dim_point_line", [{"uid": w._uid, "h": "mid"}, {"uid": inst._uid, "h": "u0:edge"}])
    assert c is not None and c.value == pytest.approx(1420.0)   # L1 at y = -80, wall at -1500
    assert ctl.set_value(c.id, 2000.0)
    assert inst.block_pos() == pytest.approx((1000.0, 580.0), abs=5e-3)   # L1 at y = 500
    assert wall_xy(w) == pytest.approx(W_A, abs=1e-9)


def test_mirror_in_place_resolves_with_the_block_as_the_edit(sc):
    _d, w, inst, _c = _tied(sc)
    axis = (QPointF(0.0, 0.0), QPointF(100.0, 0.0))           # y = 0 through ins
    with sc.constraint_ctl.edit([inst], point_map=lambda p: QPointF(p.x(), -p.y())):
        inst.manip_reflect(*axis)
    assert inst.block_mirrored() is True                      # DD3: the flag flips (rotation follows)
    # L1 p1 local (60, -80) reflects to 80 below ins; the tie needs it 80 above -> ins at -160
    assert inst.block_pos() == pytest.approx((1000.0, -160.0), abs=1e-4)
    assert wall_xy(w) == pytest.approx(W_A, abs=1e-9)


# ── Task 5: drag session per tier ───────────────────────────────────────────

def test_drag_frames_carry_the_block_then_a_block_frame_slides(sc):
    _d, w, inst, _c = _tied(sc, target="face_l")
    ctl = sc.constraint_ctl
    ctl.begin_drag([w])
    for dy in (100.0, 250.0, 400.0):
        assert ctl.drag_frame([w], lambda dy=dy: w.translate(0.0, dy), reset=True)
        assert w._pt1.y() == pytest.approx(-1500.0 + dy, abs=1e-9)
        assert inst.block_pos() == pytest.approx((1000.0, dy), abs=1e-4)
    ctl.end_drag()
    ctl.begin_drag([inst])
    assert ctl.drag_frame([inst], lambda: inst.translate(600.0, 400.0), reset=True)
    ctl.end_drag()
    assert inst.block_pos() == pytest.approx((1600.0, 400.0), abs=1e-4)
    assert wall_xy(w) == pytest.approx((0.0, -1100.0, 4000.0, -1100.0), abs=1e-9)


def test_drag_frame_a_block_cannot_follow_puts_it_back_and_end_drag_reds_the_tie(sc):
    a, _b, inst, t1, t2 = _two_walls(sc)
    ctl = sc.constraint_ctl
    ctl.begin_drag([a])
    assert ctl.drag_frame([a], lambda: a.translate(0.0, 10.0), reset=True)   # reachable: it turns
    assert abs(inst.block_rotation()) > 1.0
    assert inst.block_pos()[1] == pytest.approx(0.0, abs=1e-6)               # ins held by t2
    assert ctl.drag_frame([a], lambda: a.translate(0.0, 600.0), reset=True)  # the wall edit applies
    assert a._pt1.y() == pytest.approx(-900.0, abs=1e-9)
    assert inst.block_pos() == pytest.approx((1000.0, 0.0), abs=1e-9)
    assert inst.block_rotation() == pytest.approx(0.0, abs=1e-9)
    assert t1.id not in ctl.red                                              # never per frame
    ctl.end_drag()
    assert t1.id in ctl.red and t2.id not in ctl.red


def test_cancel_drag_restores_wall_and_block(sc):
    _d, w, inst, _c = _tied(sc)
    ctl = sc.constraint_ctl
    ctl.begin_drag([w])
    assert ctl.drag_frame([w], lambda: w.translate(0.0, 300.0), reset=True)
    assert inst.block_pos() == pytest.approx((1000.0, 300.0), abs=1e-4)
    ctl.cancel_drag()
    assert wall_xy(w) == pytest.approx(W_A, abs=1e-9)
    assert inst.block_pos() == pytest.approx((1000.0, 0.0), abs=1e-9)


# ── Task 6: per-tier diagnostics ────────────────────────────────────────────

def test_block_ties_set_the_blocks_dof_only(sc):
    d = snap_def(sc)
    w = wall(sc, W_A[:2], W_A[2:])
    inst = sc.place_block_instance(d.id, (1000.0, 0.0))
    ctl = sc.constraint_ctl
    assert ctl.add("coincident", [{"uid": inst._uid, "h": "ins"}, {"uid": w._uid, "h": "p1"}])
    diag = ctl.diagnostics()
    assert diag.item_dof[inst._uid] == 1      # x, y tied to the held wall end; rotation free (D104)
    assert diag.item_dof[w._uid] == 4         # a block tie never reduces a wall's DOF
    assert diag.dof == 4 + 1


def test_a_block_tie_never_makes_a_wall_constraint_amber(sc):
    from firepro3d.constraint_controller import REDUNDANT_STATUS
    d = snap_def(sc)
    w1 = wall(sc, (0.0, -1500.0), (4000.0, -1500.0))
    w2 = wall(sc, (0.0, -1500.0), (0.0, 1500.0))
    inst = sc.place_block_instance(d.id, (0.0, -1500.0))
    ctl = sc.constraint_ctl
    assert ctl.add("coincident", [{"uid": inst._uid, "h": "ins"}, {"uid": w1._uid, "h": "p1"}])
    assert ctl.add("coincident", [{"uid": inst._uid, "h": "ins"}, {"uid": w2._uid, "h": "p1"}])
    msgs = _status(sc)
    wc = ctl.add("coincident", [{"uid": w1._uid, "h": "p1"}, {"uid": w2._uid, "h": "p1"}])
    assert wc is not None
    assert wc.id not in ctl.diagnostics().redundant
    assert REDUNDANT_STATUS not in msgs


# ── Task 7: definition edit / swap (AC5) ────────────────────────────────────

def test_retarget_to_a_definition_with_a_moved_child_resolves_in_its_step(sc):
    from firepro3d.block_definition import BlockDefinition
    d, w, inst, c = _tied(sc, target="edge")
    prims = [dict(p) for p in d.primitives]
    prims[0] = {**prims[0], "pt1": [60.0, -120.0]}            # L1 p1 40 further from ins (local)
    d2 = BlockDefinition.new(name="Snap2", library="L", series="S", origin=(0.0, 0.0),
                             primitives=prims)
    sc.register_block_definition(d2)
    sc.push_undo_state()
    n = len(sc._undo_stack)
    assert sc.retarget_block_refs(d.id, d2.id) >= 1
    assert len(sc._undo_stack) == n + 1                       # one step, the solve inside it
    assert inst.block_pos() == pytest.approx((1000.0, 40.0), abs=1e-6)   # p1 back at y = -80
    assert wall_xy(w) == pytest.approx(W_A, abs=1e-9)
    assert c.id not in sc.constraint_ctl.red


def test_refused_stage1_frame_keeps_stage2_failed_so_end_drag_reds_the_tie(sc):
    """PB6: ``stage2_failed`` describes the last GOOD frame. Frame 1 (whole-wall
    grip) moves wall A out of the block's reach (stage 2 fails, the frame
    stands); frame 2 collapses the wall to a point (D36 conflict in its
    building tier: stage 1 refused, frame 1 restored); release reds the tie.
    RED: reset ``ctx.stage2_failed`` at the top of ``_solve_two``'s ctx branch."""
    from firepro3d.sketch_adapters import adapter_for
    a, _b, inst, t1, t2 = _two_walls(sc)
    ctl = sc.constraint_ctl
    c = wall(sc, (0.0, -1200.0), (4000.0, -1200.0))              # building tier: 300 clear of wall A
    assert ctl.add("dim_point_line", [{"uid": c._uid, "h": "p1"}, {"uid": a._uid, "h": "edge"}]) is not None
    ctl.begin_drag(a)
    adapter_for(a).write(a, [0.0, -900.0, 4000.0, -900.0])
    ctl.drag(a, 2)
    assert ctl._drag_ctx.stage2_failed                         # non-vacuous: frame 1 failed stage 2
    assert wall_xy(a) == pytest.approx((0.0, -900.0, 4000.0, -900.0), abs=1e-4)
    adapter_for(a).write(a, [0.0, -900.0, 0.0, -900.0])        # collapsed to a point: D36 conflict
    ctl.drag(a, 2)
    assert wall_xy(a) == pytest.approx((0.0, -900.0, 4000.0, -900.0), abs=1e-4)   # refused: frame 1 restored
    assert t1.id not in ctl.red                                # never per frame
    ctl.end_drag()
    assert t1.id in ctl.red and t2.id not in ctl.red
