"""Editor/Build slice 2 Task 5: plan constraints persist in the .fpd, round
trip undo / redo, cascade-delete with their wall in one undo step, copy as
internal constraints (D30). Legacy files load with 0 (G9). Guards T5, T6
(legacy half), T10 (copy half). Record content is compared, not counts."""
from __future__ import annotations

import json
import logging

import pytest
from PyQt6.QtCore import QPointF, QSettings

from firepro3d.constants import AUTO_CONSTRAIN_KEY
from firepro3d.gridline import GridlineItem
from firepro3d.model_space import Model_Space
from firepro3d.wall import WallSegment


def _wall(sc, a, b):
    w = WallSegment(QPointF(*a), QPointF(*b))
    sc.addItem(w)
    sc._walls.append(w)
    return w


def _grid(sc, a, b, label):
    gl = GridlineItem(QPointF(*a), QPointF(*b), label=label)
    sc._gridlines.append(gl)
    sc.addItem(gl)
    return gl


def _records(sc):
    return [c.to_dict() for c in sc.constraint_ctl.constraints]


def _constrained(sc):
    w1 = _wall(sc, (0, 0), (3000, 0))
    w2 = _wall(sc, (3000, 0), (3000, 2000))
    gl = _grid(sc, (-500, -1000), (4000, -1000), "A")
    ctl = sc.constraint_ctl
    for ctype, refs in (
            ("dim_distance", [{"uid": w1._uid, "h": "edge"}]),
            ("coincident", [{"uid": w1._uid, "h": "p2"}, {"uid": w2._uid, "h": "p1"}]),
            ("perpendicular", [{"uid": w1._uid, "h": "edge"}, {"uid": w2._uid, "h": "edge"}]),
            ("dim_point_line", [{"uid": w1._uid, "h": "p1"}, {"uid": gl._uid, "h": "edge"}])):
        assert ctl.add(ctype, refs) is not None, ctype
    return w1, w2, gl


def test_t5_save_reopen_round_trips_record_content(qapp, tmp_path):
    a = Model_Space()
    b = Model_Space()
    try:
        _constrained(a)
        want = _records(a)
        assert len(want) == 4
        f = tmp_path / "plan.fpd"
        a.save_to_file(str(f))
        assert json.loads(f.read_text())["constraints"] == want
        b.load_from_file(str(f))
        assert _records(b) == want
        assert {w._uid for w in b._walls} == {w._uid for w in a._walls}
    finally:
        a.cleanup()
        b.cleanup()


def test_t5_undo_redo_round_trips_a_plan_constraint(qapp):
    sc = Model_Space()
    try:
        w1 = _wall(sc, (0, 0), (3000, 0))
        sc.push_undo_state()                       # baseline: wall, no constraint
        uid = w1._uid
        c = sc.constraint_ctl.add("dim_distance", [{"uid": uid, "h": "edge"}])
        assert c is not None
        want = _records(sc)
        sc.undo()
        assert _records(sc) == []
        assert [w._uid for w in sc._walls] == [uid]  # the uid survives the snapshot
        sc.redo()
        assert _records(sc) == want
    finally:
        sc.cleanup()


def test_cascade_delete_is_one_undo_step(qapp):
    sc = Model_Space()
    try:
        w1, _w2, _gl = _constrained(sc)
        want = _records(sc)
        sc.clearSelection()
        w1.setSelected(True)
        sc.delete_selected_items()
        assert w1 not in sc._walls
        assert _records(sc) == []                 # every record touched w1
        sc.undo()
        assert _records(sc) == want
    finally:
        sc.cleanup()


def _payload_with(tmp_path, constraints):
    """A save of one wall + one gridline, with *constraints* spliced in."""
    sc = Model_Space()
    try:
        w = _wall(sc, (0, 0), (3000, 0))
        gl = _grid(sc, (0, -1000), (3000, -1000), "A")
        f = tmp_path / "base.fpd"
        sc.save_to_file(str(f))
        data = json.loads(f.read_text())
        data["constraints"] = constraints(w._uid, gl._uid)
        if data["constraints"] is None:
            data.pop("constraints")
        f.write_text(json.dumps(data))
        return f
    finally:
        sc.cleanup()


def test_t6_legacy_file_loads_with_zero_constraints(qapp, tmp_path):
    f = _payload_with(tmp_path, lambda w, g: None)      # pre-slice-2: no key
    sc = Model_Space()
    try:
        sc.load_from_file(str(f))
        assert sc.constraint_ctl.constraints == []
        assert len(sc._walls) == 1
    finally:
        sc.cleanup()


def test_unresolvable_records_drop_and_resolvable_unknown_type_stays_inert(
        qapp, tmp_path, caplog):
    """design s2 Persistence: a record whose refs do not ALL resolve to a
    loaded wall / gridline is dropped and counted in the clean-drop line; a
    record of an unknown type whose refs resolve is kept inert (s6.4)."""
    def cons(w, g):
        return [
            {"id": "keep", "type": "dim_point_line",
             "refs": [{"uid": w, "h": "p1"}, {"uid": g, "h": "edge"}], "value": 1000.0},
            {"id": "future", "type": "x_future_kind",
             "refs": [{"uid": w, "h": "edge"}]},
            {"id": "stale", "type": "horizontal",               # loose geometry, pre-C8
             "refs": [{"uid": "0" * 32, "h": "edge"}]},
            {"id": "ground", "type": "coincident",              # origin ground: never in plan
             "refs": [{"uid": w, "h": "p1"}, {"ref": "origin"}]},
        ]
    f = _payload_with(tmp_path, cons)
    sc = Model_Space()
    try:
        with caplog.at_level(logging.INFO):
            sc.load_from_file(str(f))
        ids = [c.id for c in sc.constraint_ctl.constraints]
        assert ids == ["keep", "future"]
        future = sc.constraint_ctl.constraints[1]
        assert future.inert
        assert any("Clean-drop: discarded 2 " in r.getMessage() for r in caplog.records)
    finally:
        sc.cleanup()


def test_t10_copy_keeps_internal_constraints_on_the_copies(qapp):
    """D30: the paste path (commit_duplicate / commit_paste feed paste_items
    with internal_records) re-creates a constrained wall pair's and gridline
    pair's internal constraints on the copies' new uids. Auto Constrain is
    off: pasted gridlines' own joins (R8) are guarded in
    test_gridline_auto_constrain.py."""
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, False)
    sc = Model_Space()
    try:
        w1 = _wall(sc, (0, 0), (3000, 0))
        w2 = _wall(sc, (3000, 0), (3000, 2000))
        g1 = _grid(sc, (0, -1000), (3000, -1000), "A")
        g2 = _grid(sc, (0, -2000), (3000, -2000), "B")
        ctl = sc.constraint_ctl
        assert ctl.add("perpendicular", [{"uid": w1._uid, "h": "edge"},
                                         {"uid": w2._uid, "h": "edge"}]) is not None
        assert ctl.add("parallel", [{"uid": g1._uid, "h": "edge"},
                                    {"uid": g2._uid, "h": "edge"}]) is not None
        src = [w1, w2, g1, g2]
        cons = ctl.internal_records(src)
        assert len(cons) == 2
        new = sc.paste_items(QPointF(0, 5000), data=sc._clipboard_item_dicts(src),
                             constraints=cons)
        new_uids = {it._uid for it in new if isinstance(it, (WallSegment, GridlineItem))}
        assert len(new_uids) == 4 and not (new_uids & {it._uid for it in src})
        copied = [c for c in ctl.constraints
                  if {r["uid"] for r in c.refs} <= new_uids]
        assert sorted(c.type for c in copied) == ["parallel", "perpendicular"]
        assert not any(c.inert for c in copied)
    finally:
        QSettings("GV", "FirePro3D").remove(AUTO_CONSTRAIN_KEY)
        sc.cleanup()


def _resolves_live(sc, uid):
    """The constraint's ref resolves to the live wall item; it is solvable."""
    live = [w for w in sc._walls if w._uid == uid]
    assert len(live) == 1
    assert sc.constraint_ctl.item_by_uid()[uid] is live[0]
    for c in sc.constraint_ctl.constraints:
        assert not c.inert and not c.invalid


def test_wall_uid_and_constraint_resolve_after_undo_and_redo(qapp):
    """The constraint outlives a snapshot restore (_restore_network): after
    undo and after redo its ref still names a live wall in sc._walls."""
    sc = Model_Space()
    try:
        w1 = _wall(sc, (0, 0), (3000, 0))
        ctl = sc.constraint_ctl
        assert ctl.add("dim_distance", [{"uid": w1._uid, "h": "edge"}]) is not None
        want = _records(sc)
        sc.push_undo_state()                       # baseline holds wall + constraint
        _wall(sc, (0, 2000), (3000, 2000))         # the undoable change
        sc.push_undo_state()                       # history holds post-change states
        assert len(sc._walls) == 2
        sc.undo()
        assert len(sc._walls) == 1
        assert _records(sc) == want
        assert {r["uid"] for c in sc.constraint_ctl.constraints for r in c.refs} \
            <= {w._uid for w in sc._walls}
        assert sc._walls[0]._uid == w1._uid
        _resolves_live(sc, w1._uid)
        sc.redo()
        assert len(sc._walls) == 2
        assert _records(sc) == want
        assert w1._uid in {w._uid for w in sc._walls}
        _resolves_live(sc, w1._uid)
    finally:
        sc.cleanup()


def test_malformed_constraint_records_drop_instead_of_crashing_the_load(
        qapp, tmp_path, caplog):
    good = {"id": "good", "type": "dim_distance", "value": 1500.0}
    junk = [
        {"id": "r5", "type": "dim_distance", "refs": 5},
        {"id": "ul", "type": "dim_distance", "refs": [{"uid": ["x"], "h": "edge"}]},
        "junk",
    ]

    def cons(w, g):
        return [dict(good, refs=[{"uid": w, "h": "edge"}])] + junk
    f = _payload_with(tmp_path, cons)
    sc = Model_Space()
    try:
        with caplog.at_level(logging.INFO):
            sc.load_from_file(str(f))
        assert [c.id for c in sc.constraint_ctl.constraints] == ["good"]
        assert sc.constraint_ctl.constraints[0].value == 1500.0
        assert any("Clean-drop: discarded %d " % len(junk) in r.getMessage()
                   for r in caplog.records)
    finally:
        sc.cleanup()
