"""Nested block constraint handles (design NB1-NB9) -- headless guards.

Drives a real ``Model_Space(scene_role="block_editor")`` with the Snap block
(tests/_block_snap_helpers) placed as a nested instance plus loose
primitives; observable scene geometry is the ground truth.
"""
from __future__ import annotations

import math

import numpy as np
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import CircleItem, LineItem
from firepro3d.model_space import Model_Space
from firepro3d.sketch_adapters import adapter_for
from tests._block_snap_helpers import oracle, register_snap_block


def _scene():
    return Model_Space(scene_role="block_editor")


def _line(sc, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b))
    sc.addItem(ln)
    sc._draw_lines.append(ln)
    return ln


def _circle(sc, c, r):
    it = CircleItem(QPointF(*c), r)
    sc.addItem(it)
    sc._draw_circles.append(it)
    return it


def _key(d, i):
    return d.primitives[i].get("uid") or f"#{i}"


def _instance(sc, pos=(40.0, 20.0), rot=0.0, mirrored=False, scale=1.0):
    d = register_snap_block(sc, nested=True)
    inst = sc.place_block_instance(d.id, pos, rotation=rot, mirrored=mirrored, scale=scale)
    sc.push_undo_state()
    return d, inst


def _with_uids(d):
    """Give every record of *d* a stable ``uid`` (editor-authored records have
    them; the Snap helper's hand-written ones are positional ``#i``) so that
    deleting one record cannot re-point another record's handle names."""
    d.set_primitives([{**r, "uid": f"u{i}"} for i, r in enumerate(d.primitives)])


def _near(p: QPointF, q: QPointF, tol=1e-5) -> bool:
    return math.hypot(p.x() - q.x(), p.y() - q.y()) <= tol


def _status(sc):
    """Capture status-bar messages (the controller's ``_status`` calls
    ``scene._show_status``) -- the test_constraint_controller idiom."""
    msgs = []
    sc._show_status = lambda m, *a, **k: msgs.append(m)
    return msgs


# ── Task 4 guards ────────────────────────────────────────────────────────────

def test_pick_candidates_include_interior_handles_with_midpoint_triangles(qapp):
    """NB8 / AC7: pick mode offers the child handles; midpoints tagged "mid";
    hidden child handles (polygon radius, ellipse rx/ry) never; a curve's
    radius comes from the constant."""
    from firepro3d.constraint_controller import PickState
    sc = _scene()
    d, inst = _instance(sc)
    pk = PickState(sc.constraint_ctl, "coincident")
    cands = list(pk._candidates())
    names = {(k, r.get("h")) for k, r, _a, _b in cands if isinstance(r, dict) and r.get("uid") == inst._uid}
    assert ("point", f"{_key(d, 0)}:p1") in names
    assert ("edge", f"{_key(d, 0)}:edge") in names
    assert ("curve", f"{_key(d, 2)}:curve") in names
    mid = [b for k, r, a, b in cands if isinstance(r, dict) and r.get("h") == f"{_key(d, 0)}:mid"]
    assert mid == ["mid"]
    (rad,) = [b for k, r, a, b in cands if isinstance(r, dict) and r.get("h") == f"{_key(d, 2)}:curve"]
    assert rad[0] == pytest.approx(40.0)


def test_driving_radius_dim_on_a_nested_curve_is_refused_reference_measures(qapp):
    """NB7 / AC8."""
    from firepro3d.constraint_controller import INVALID_STATUS
    sc = _scene()
    d, inst = _instance(sc)
    ctl = sc.constraint_ctl
    msgs = _status(sc)
    ref = {"uid": inst._uid, "h": f"{_key(d, 2)}:curve"}
    assert ctl.add("dim_radius", [ref], value=45.0) is None
    assert INVALID_STATUS in msgs
    c = ctl.add("dim_radius", [ref])              # current measure, then Reference
    assert c is not None
    ctl.set_driving(c.id, False)
    assert ctl.measure(c) == pytest.approx(40.0)
    assert c in ctl.constraints and c.id not in {x.id for x in ctl.active()}


def test_dof_of_a_nested_instance_is_three(qapp):
    """AC7: x y rot."""
    sc = _scene()
    d, inst = _instance(sc)
    ad = adapter_for(inst)
    assert ad.nvars(inst) == 3


def test_symmetric_of_a_nested_curve_and_a_loose_circle_is_refused(qapp):
    """R1: a nested curve has a fixed radius (r is None), so the radius alias
    of a two-curve Symmetric has nothing to alias -- refused as invalid."""
    from firepro3d.constraint_controller import INVALID_STATUS
    sc = _scene()
    d, inst = _instance(sc)
    loose = _circle(sc, (200.0, 200.0), 15.0)
    axis = _line(sc, (0.0, -500.0), (0.0, 500.0))
    ctl = sc.constraint_ctl
    msgs = _status(sc)
    c = ctl.add("symmetric", [{"uid": inst._uid, "h": f"{_key(d, 2)}:curve"},
                              {"uid": loose._uid, "h": "curve"},
                              {"uid": axis._uid, "h": "edge"}])
    assert c is None
    assert INVALID_STATUS in msgs


# ── Task 5 guards: solving ───────────────────────────────────────────────────

def test_coincident_to_a_nested_arc_centre_moves_the_block(qapp):
    """AC1: loose p1 -> nested circle C centre (100, 60); the loose line is
    W_EDIT-free so the lighter block moves (least change on both)."""
    sc = _scene()
    d, inst = _instance(sc, pos=(40.0, 20.0))
    ln = _line(sc, (300.0, 300.0), (400.0, 300.0))
    ctl = sc.constraint_ctl
    c = ctl.add("coincident", [{"uid": ln._uid, "h": "p1"},
                               {"uid": inst._uid, "h": f"{_key(d, 2)}:center"}])
    assert c is not None and c.id in {x.id for x in ctl.active()} and c.id not in ctl.red
    assert _near(ln._pt1, oracle(inst, 100.0, 60.0))
    assert inst.block_pos() != (40.0, 20.0)                      # the block moved


def test_coincident_to_a_grandchild_centre_and_a_nested_origin(qapp):
    """AC1 depth: the Inner circle centre (grandchild) and the nested record's
    origin are both targets."""
    from tests._block_snap_helpers import nested_oracle
    sc = _scene()
    d, inst = _instance(sc)
    inner = d._resolve_nested(d.primitives[5])
    ik = f"{_key(d, 5)}/{inner.primitives[0].get('uid') or '#0'}"
    ln = _line(sc, (300.0, 300.0), (400.0, 300.0))
    ctl = sc.constraint_ctl
    assert ctl.add("coincident", [{"uid": ln._uid, "h": "p1"}, {"uid": inst._uid, "h": f"{ik}:center"}])
    assert _near(ln._pt1, nested_oracle(inst, 20.0, 0.0))
    ln2 = _line(sc, (300.0, 200.0), (400.0, 200.0))
    assert ctl.add("coincident", [{"uid": ln2._uid, "h": "p1"}, {"uid": inst._uid, "h": f"{_key(d, 5)}:ins"}])
    assert _near(ln2._pt1, nested_oracle(inst, 0.0, 0.0))


def test_parallel_to_a_nested_edge_rotates_the_block(qapp):
    """AC2: Fix the loose line; Parallel(loose edge, nested L1 edge) can only
    be met by rotating the instance (rotation is a variable, NB1)."""
    sc = _scene()
    d, inst = _instance(sc, pos=(40.0, 20.0), rot=0.0)
    ln = _line(sc, (300.0, 300.0), (400.0, 400.0))               # 45 deg in Y-down scene
    ctl = sc.constraint_ctl
    assert ctl.add("fix", [{"uid": ln._uid, "h": "item"}])
    c = ctl.add("parallel", [{"uid": ln._uid, "h": "edge"},
                             {"uid": inst._uid, "h": f"{_key(d, 0)}:edge"}])
    assert c is not None and c.id not in ctl.red
    a, b = oracle(inst, 60.0, -80.0), oracle(inst, 180.0, -80.0)
    d1 = (ln._pt2.x() - ln._pt1.x(), ln._pt2.y() - ln._pt1.y())
    d2 = (b.x() - a.x(), b.y() - a.y())
    cross = d1[0] * d2[1] - d1[1] * d2[0]
    assert abs(cross) / (math.hypot(*d1) * math.hypot(*d2)) < 1e-6
    assert abs(inst.block_rotation()) > 1.0                         # it rotated
    assert (ln._pt1, ln._pt2) == (QPointF(300.0, 300.0), QPointF(400.0, 400.0))


def test_typed_rotation_on_a_constrained_instance_is_exact_or_rolled_back(qapp):
    """AC2 / D31: with Parallel(nested edge, X axis) the instance cannot turn;
    a typed Rotation 10 rolls back with the conflict status; with the Parallel
    deleted it is honoured exactly."""
    from firepro3d.constraint_controller import CONFLICT_STATUS
    sc = _scene()
    d, inst = _instance(sc, rot=0.0)
    ctl = sc.constraint_ctl
    c = ctl.add("parallel", [{"uid": inst._uid, "h": f"{_key(d, 0)}:edge"}, {"ref": "x_axis"}])
    assert c is not None and c.id not in ctl.red
    msgs = _status(sc)
    with ctl.edit([inst], typed=True):
        inst.set_property("Rotation", 10.0)
    assert inst.block_rotation() == pytest.approx(0.0)
    assert any(CONFLICT_STATUS in m for m in msgs)
    ctl.delete([c.id])
    with ctl.edit([inst], typed=True):
        inst.set_property("Rotation", 10.0)
    assert inst.block_rotation() == pytest.approx(10.0)


# ── Task 6 guards: NB4 re-validation, NB6 Fix migration ──────────────────────

def test_deleted_child_primitive_makes_the_constraint_inert_and_undo_revives(qapp):
    """NB4 / AC4: drop L1 from the child definition -> the parent constraint
    on L1:p1 is inert (Unsupported, out of DOF, kept verbatim); putting the
    primitives back revives it."""
    sc = _scene()
    d, inst = _instance(sc)
    _with_uids(d)
    k0 = _key(d, 0)
    ln = _line(sc, (300.0, 300.0), (400.0, 300.0))
    ctl = sc.constraint_ctl
    c = ctl.add("coincident", [{"uid": ln._uid, "h": "p1"}, {"uid": inst._uid, "h": f"{k0}:p1"}])
    assert c is not None
    full = list(d.primitives)
    d.set_primitives(full[1:])                       # the child edit (another tab / disk)
    assert [x.id for x in ctl.active()] == []
    assert c.inert and c.invalid
    assert ctl.to_records()[0]["refs"][1]["h"] == f"{k0}:p1"   # verbatim
    assert ctl.kind_text(c) == "Unsupported constraint"      # the panel row name (§6.4)
    d.set_primitives(full)                           # the child's undo
    assert [x.id for x in ctl.active()] == [c.id]
    assert not c.inert and c.raw is None


def test_moved_child_primitive_re_solves_at_the_parents_next_edit(qapp):
    """NB4 / AC4: L1 moves inside the child; the parent's next edit pulls the
    loose point onto the new handle position."""
    sc = _scene()
    d, inst = _instance(sc)
    ln = _line(sc, (300.0, 300.0), (400.0, 300.0))
    ctl = sc.constraint_ctl
    assert ctl.add("coincident", [{"uid": ln._uid, "h": "p1"}, {"uid": inst._uid, "h": f"{_key(d, 0)}:p1"}])
    assert ctl.add("fix", [{"uid": inst._uid, "h": "item"}])
    recs = list(d.primitives)
    recs[0] = {**recs[0], "pt1": [60.0, -120.0]}      # L1.p1 moves 40 mm up (local)
    d.set_primitives(recs)
    with ctl.edit([ln]):                              # the next parent edit touching the group
        ln.translate(1.0, 0.0)                        # (an unrelated item's edit solves its own group only)
    assert _near(ln._pt1, oracle(inst, 60.0, -120.0))


def test_legacy_two_value_instance_fix_migrates_on_load(qapp):
    """NB6 / AC6: a saved Fix with v0 [x, y] on a block_instance gains the
    current rotation on load and still pins position + rotation."""
    sc = _scene()
    d, inst = _instance(sc, pos=(40.0, 20.0), rot=25.0)
    ctl = sc.constraint_ctl
    legacy = [{"id": "f1", "type": "fix", "refs": [{"uid": inst._uid, "h": "item"}],
               "value": None, "driving": True, "enabled": True,
               "helper": {"v0": [40.0, 20.0]}}]
    ctl.load(legacy)
    (c,) = ctl.constraints
    assert not c.inert
    assert c.helper["v0"] == pytest.approx([40.0, 20.0, math.radians(25.0)])
    assert ctl.to_records()[0]["helper"]["v0"] == pytest.approx([40.0, 20.0, math.radians(25.0)])
    assert [x.id for x in ctl.active()] == [c.id]
    ln = _line(sc, (300.0, 300.0), (400.0, 300.0))
    # a Coincident onto a nested handle must move the LINE, not the fixed block
    assert ctl.add("coincident", [{"uid": ln._uid, "h": "p1"}, {"uid": inst._uid, "h": f"{_key(d, 0)}:p1"}])
    assert inst.block_pos() == (40.0, 20.0) and inst.block_rotation() == pytest.approx(25.0)
    assert _near(ln._pt1, oracle(inst, 60.0, -80.0))


def test_legacy_ins_record_still_loads_and_solves(qapp):
    sc = _scene()
    d, inst = _instance(sc)
    ln = _line(sc, (300.0, 300.0), (400.0, 300.0))
    ctl = sc.constraint_ctl
    ctl.load([{"id": "h1", "type": "horizontal",
               "refs": [{"uid": inst._uid, "h": "ins"}, {"uid": ln._uid, "h": "p1"}],
               "value": None, "driving": True, "enabled": True, "helper": {}}])
    assert [x.id for x in ctl.active()] == ["h1"]
    assert ln._pt1.y() == pytest.approx(inst.block_pos()[1])


# ── Task 7 guards: NB5 Explode ───────────────────────────────────────────────

def test_explode_remaps_interior_refs_and_drops_ins_refs(qapp, monkeypatch):
    """NB5 / AC5: this level only -- L1:p1 -> the exploded line's p1; the
    nested Inner record -> the new child instance ("<inner uid>:center");
    the ins ref drops and is the only one counted; undo restores all."""
    from firepro3d.constraint_controller import removed_status
    monkeypatch.setattr("firepro3d.themed_message.themed_choice", lambda *a, **k: "level")
    sc = _scene()
    sc.push_undo_state()
    d, inst = _instance(sc)
    inner = d._resolve_nested(d.primitives[5])
    ik = inner.primitives[0].get("uid") or "#0"
    ln = _line(sc, (300.0, 300.0), (400.0, 300.0))
    ln2 = _line(sc, (300.0, 200.0), (400.0, 200.0))
    ln3 = _line(sc, (300.0, 100.0), (400.0, 100.0))
    ctl = sc.constraint_ctl
    c1 = ctl.add("coincident", [{"uid": ln._uid, "h": "p1"}, {"uid": inst._uid, "h": f"{_key(d, 0)}:p1"}])
    c2 = ctl.add("coincident", [{"uid": ln2._uid, "h": "p1"}, {"uid": inst._uid, "h": f"{_key(d, 5)}/{ik}:center"}])
    c3 = ctl.add("horizontal", [{"uid": inst._uid, "h": "ins"}, {"uid": ln3._uid, "h": "p1"}])
    assert c1 and c2 and c3
    p1_before = QPointF(ln._pt1)
    msgs = _status(sc)
    sc.clearSelection()
    inst.setSelected(True)
    new = sc.explode_selected_blocks()           # nested prompt patched to "level" (monkeypatch above)
    assert new and inst.scene() is None
    assert c3 not in ctl.constraints and removed_status(1) in msgs
    ids = {x.id for x in ctl.active()}
    assert c1.id in ids and c2.id in ids
    (child,) = sc._block_instances
    assert c2.refs[1] == {"uid": child._uid, "h": f"{ik}:center"}
    new_line = next(it for it in new if isinstance(it, LineItem) and _near(it._pt1, p1_before))
    assert c1.refs[1] == {"uid": new_line._uid, "h": "p1"}
    # still solving: move the exploded line's p1 (the remapped handle) -- the loose line follows
    start = QPointF(new_line._pt1)
    with ctl.edit([new_line]):
        new_line._pt1 = QPointF(new_line._pt1.x() + 10.0, new_line._pt1.y())
        new_line.setLine(new_line._pt1.x(), new_line._pt1.y(), new_line._pt2.x(), new_line._pt2.y())
    assert _near(new_line._pt1, QPointF(start.x() + 10.0, start.y()), tol=0.05)   # W_EDIT is stiff, not rigid
    assert _near(ln._pt1, new_line._pt1)
    sc.undo()
    (back,) = sc._block_instances
    assert back._uid == inst._uid
    assert sorted(x.type for x in ctl.active()) == ["coincident", "coincident", "horizontal"]
    assert {x.refs[1].get("uid") for x in ctl.constraints if x.type == "coincident"} == {inst._uid}


def test_explode_flatten_remaps_to_loose_items(qapp, monkeypatch):
    """NB5 flatten: L1:p1 -> the loose line; the grandchild circle centre ->
    the loose circle's bare ``center``; ins drops (counted once); undo restores."""
    from firepro3d.constraint_controller import removed_status
    monkeypatch.setattr("firepro3d.themed_message.themed_choice", lambda *a, **k: "all")
    sc = _scene()
    sc.push_undo_state()
    d, inst = _instance(sc)
    inner = d._resolve_nested(d.primitives[5])
    ik = inner.primitives[0].get("uid") or "#0"
    ln = _line(sc, (300.0, 300.0), (400.0, 300.0))
    ln2 = _line(sc, (300.0, 200.0), (400.0, 200.0))
    ln3 = _line(sc, (300.0, 100.0), (400.0, 100.0))
    ctl = sc.constraint_ctl
    c1 = ctl.add("coincident", [{"uid": ln._uid, "h": "p1"}, {"uid": inst._uid, "h": f"{_key(d, 0)}:p1"}])
    c2 = ctl.add("coincident", [{"uid": ln2._uid, "h": "p1"}, {"uid": inst._uid, "h": f"{_key(d, 5)}/{ik}:center"}])
    c3 = ctl.add("horizontal", [{"uid": inst._uid, "h": "ins"}, {"uid": ln3._uid, "h": "p1"}])
    assert c1 and c2 and c3
    p1_before = QPointF(ln._pt1)
    msgs = _status(sc)
    sc.clearSelection()
    inst.setSelected(True)
    new = sc.explode_selected_blocks()
    assert new and sc._block_instances == []
    assert c3 not in ctl.constraints and msgs.count(removed_status(1)) == 1
    ids = {x.id for x in ctl.active()}
    assert c1.id in ids and c2.id in ids
    new_line = next(it for it in new if isinstance(it, LineItem) and _near(it._pt1, p1_before))
    assert c1.refs[1] == {"uid": new_line._uid, "h": "p1"}
    new_circle = next(it for it in new if isinstance(it, CircleItem) and _near(it._center, ln2._pt1))
    assert c2.refs[1] == {"uid": new_circle._uid, "h": "center"}
    sc.undo()
    assert [i._uid for i in sc._block_instances] == [inst._uid]
    assert sorted(x.type for x in ctl.active()) == ["coincident", "coincident", "horizontal"]
    assert {x.refs[1].get("uid") for x in ctl.constraints if x.type == "coincident"} == {inst._uid}


# ── NB7 ruling: nested-curve dims are Reference-only through Smart Dimension ──

def test_smart_dimension_on_nested_curves_classifies_and_adds_a_reference(qapp):
    from firepro3d.constraint_controller import DIM_NESTED_REFERENCE_STATUS
    from firepro3d.constraint_dims import classify_dim
    sc = _scene()
    d, inst = _instance(sc)
    ctl = sc.constraint_ctl
    by = ctl.item_by_uid()
    circ = {"uid": inst._uid, "h": f"{_key(d, 2)}:curve"}
    arc = {"uid": inst._uid, "h": f"{_key(d, 4)}:curve"}
    assert classify_dim([circ], by) == ("dim_diameter", [circ])
    assert classify_dim([arc], by) == ("dim_radius", [arc])
    msgs = _status(sc)
    assert ctl.dim_precheck([arc]) == ("dim_radius", [arc])
    assert msgs == []
    c = ctl.add("dim_radius", [arc])
    assert c is not None and c.driving is False and not c.inert
    assert DIM_NESTED_REFERENCE_STATUS in msgs


def test_driving_on_a_nested_curve_dim_is_refused_without_an_undo_step(qapp):
    from firepro3d.constraint_controller import DIM_NESTED_REFERENCE_STATUS
    sc = _scene()
    d, inst = _instance(sc)
    ctl = sc.constraint_ctl
    c = ctl.add("dim_radius", [{"uid": inst._uid, "h": f"{_key(d, 4)}:curve"}])
    assert c is not None and c.driving is False
    msgs = _status(sc)
    n = len(sc._undo_stack)
    ctl.set_driving(c.id, True)
    assert c.driving is False and not c.inert
    assert msgs == [DIM_NESTED_REFERENCE_STATUS]
    assert len(sc._undo_stack) == n


def test_paint_ref_geom_of_a_nested_curve_uses_the_constant_radius(qapp):
    from firepro3d.constraint_paint import _ref_geom
    sc = _scene()
    d, inst = _instance(sc, scale=1.0)
    ctl = sc.constraint_ctl
    kind, (centre, r) = _ref_geom({"uid": inst._uid, "h": f"{_key(d, 2)}:curve"},
                                  ctl.item_by_uid(), None)
    assert kind == "curve"
    assert _near(centre, oracle(inst, 100.0, 60.0))
    assert r == pytest.approx(40.0)
