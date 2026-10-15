"""Guards: a placed block's primitives snap like the same primitives drawn
loose (snapping-engine §5 BlockInstance row; Phase 2 ruling: full parity).

Real path: shown Model_View over a real Model_Space, posted mouse moves in
draw_line mode (get_effective_position -> find()). Ground truth: (a) the same
block Exploded into loose items in a twin scene (parity), (b) hand-written
definition-local points through the instance's own full pose (oracle).
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.block_explode import explode_instances
from firepro3d.geometry_2d import LineItem
from tests._block_snap_helpers import (C_C, C_R, INT_DY, POSE_IDS, POSES,
                                       V_X, near, nested_oracle, oracle,
                                       register_snap_block)
from tests._snap_polish_helpers import click, close_view, make_view, move

_RESET = QPointF(-395.0, 295.0)          # empty corner of the +-400 x +-300 view


def _scene_with(pose, explode=False, nested=True):
    view, scene = make_view(role="block_editor", scale=1.0, mode=None)
    scene.set_align_enabled(False)
    d = register_snap_block(scene, nested=nested)
    pos, rot, mir, s = pose
    inst = scene.place_block_instance(d.id, pos, rotation=rot,
                                      mirrored=mir, scale=s)
    if explode:
        explode_instances(scene, [inst], flatten=True)
    scene.set_mode("draw_line")
    return view, scene, inst


def _snap_at(view, scene, p):
    move(view, _RESET)
    assert scene._snap_result is None          # the reset point is empty
    move(view, p)
    r = scene._snap_result
    return None if r is None else (r.snap_type, round(r.point.x(), 2),
                                   round(r.point.y(), 2))


def _samples(inst, step=20.0, skip_r=25.0):
    """Cursor grid over the posed block, minus the insertion origin's reach
    (its CEN exists only on the block; Explode leaves no origin)."""
    b = inst.sceneBoundingRect().adjusted(-10, -10, 10, 10)
    ox, oy = inst.block_pos()
    pts, y = [], b.top()
    while y <= b.bottom():
        x = b.left()
        while x <= b.right():
            if (x - ox) ** 2 + (y - oy) ** 2 > skip_r ** 2:
                pts.append(QPointF(x, y))
            x += step
        y += step
    return pts


@pytest.mark.parametrize("pose", POSES, ids=POSE_IDS)
def test_block_snaps_match_the_exploded_block(qapp, pose):
    va, sa, ia = _scene_with(pose)
    vb, sb, _ib = _scene_with(pose, explode=True)
    try:
        assert not sb._block_instances                  # the twin is all loose
        pts = _samples(ia)
        assert len(pts) > 100
        diffs, hits = [], 0
        for p in pts:
            a, b = _snap_at(va, sa, p), _snap_at(vb, sb, p)
            hits += b is not None
            if a != b:
                diffs.append((p.x(), p.y(), a, b))
        assert hits > len(pts) // 4                     # non-vacuous comparison
        assert diffs == []                                              # [RED]
    finally:
        close_view(va, sa)
        close_view(vb, sb)


@pytest.mark.parametrize("pose", POSES, ids=POSE_IDS)
def test_block_snap_points_land_on_the_posed_geometry(qapp, pose):
    view, scene, inst = _scene_with(pose)
    s = pose[3]
    try:
        cases = [
            ("midpoint", oracle(inst, 120.0, -80.0)),          # L1 mid
            ("center", oracle(inst, *C_C)),                    # C centre
            ("intersection", oracle(inst, V_X, C_C[1] - INT_DY)),  # V x C
            ("nearest", oracle(inst, -160.0, 20.0)),           # R left edge
            ("center", nested_oracle(inst, 20.0, 0.0)),        # nested circle
        ]
        c = oracle(inst, *C_C)
        cases.append(("quadrant", QPointF(c.x() + C_R * s, c.y())))   # C 0 deg
        for kind, want in cases:
            # NEA is the cursor's own foot: put the cursor ON the edge.
            off = 0.0 if kind == "nearest" else 1.0
            res = _snap_at(view, scene, QPointF(want.x() + off, want.y() + off))
            assert res is not None and res[0] == kind, (kind, res)      # [RED]
            got = QPointF(res[1], res[2])
            if kind == "nearest":
                # Posted events land on whole pixels, so the foot is the
                # quantised cursor's: on R's left edge, within a pixel.
                e1, e2 = oracle(inst, -160.0, -40.0), oracle(inst, -160.0, 40.0)
                ex, ey = e2.x() - e1.x(), e2.y() - e1.y()
                off_line = abs(ex * (got.y() - e1.y()) - ey * (got.x() - e1.x()))
                assert off_line / (ex * ex + ey * ey) ** 0.5 < 0.02, res
                assert near(got, want, 1.0), (kind, res)
            else:
                assert near(got, want, 0.02), (kind, res)
            assert scene._snap_result.source_item is inst
    finally:
        close_view(view, scene)


def test_nested_insertion_point_is_not_a_snap(qapp):
    view, scene, inst = _scene_with(POSES[1])
    try:
        p = nested_oracle(inst, 0.0, 0.0)                  # Inner's origin
        res = _snap_at(view, scene, QPointF(p.x() + 1.0, p.y() + 1.0))
        assert res is None or not (res[0] == "center"
                                   and near(QPointF(res[1], res[2]), p, 0.02))
    finally:
        close_view(view, scene)


def test_a_snap_toggle_gates_block_points(qapp):
    # Sanity guard (passes before the change too -- no block MID existed);
    # it pins that block points honour the per-type toggles afterwards.
    view, scene, inst = _scene_with(POSES[0], nested=False)
    try:
        scene._snap_engine.snap_midpoint = False
        want = oracle(inst, 120.0, -80.0)
        res = _snap_at(view, scene, QPointF(want.x() + 1.0, want.y() + 1.0))
        assert res is None or res[0] != "midpoint"
    finally:
        close_view(view, scene)


def test_perpendicular_from_a_start_point_onto_a_block_edge(qapp):
    view, scene, inst = _scene_with(POSES[1], nested=False)
    vb, sb, _ = _scene_with(POSES[1], explode=True, nested=False)
    try:
        assert not sb._block_instances                  # the twin is all loose
        start = QPointF(-300.0, -250.0)
        click(view, start)
        click(vb, start)
        diffs, pers = [], 0
        for p in _samples(inst):
            a, b = _snap_at(view, scene, p), _snap_at(vb, sb, p)
            pers += b is not None and b[0] == "perpendicular"
            if a != b:
                diffs.append((p.x(), p.y(), a, b))
        assert pers > 0                                 # PER-from actually occurs
        assert diffs == []                                              # [RED]
    finally:
        close_view(view, scene)
        close_view(vb, sb)


def test_block_line_crossing_a_loose_line_is_an_intersection(qapp):
    view, scene, inst = _scene_with(POSES[1], nested=False)
    try:
        # Off-centre so the loose line's own midpoint (120,-95) is not the crossing.
        a, b = oracle(inst, 120.0, -130.0), oracle(inst, 120.0, -60.0)
        loose = LineItem(a, b, "#ffffff", 1.0)
        scene.addItem(loose)
        want = oracle(inst, 120.0, -80.0)          # L1 x the loose line
        res = _snap_at(view, scene, QPointF(want.x() + 1.0, want.y() + 1.0))
        assert res is not None and res[0] == "intersection", res        # [RED]
        assert near(QPointF(res[1], res[2]), want, 0.02)
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("pose", POSES, ids=POSE_IDS)
def test_align_anchor_follows_a_block_edge(qapp, pose):
    view, scene, inst = _scene_with(pose, nested=False)
    try:
        scene.set_align_enabled(True)
        p = oracle(inst, 90.0, -80.0)                  # on L1, not an end/mid
        click(view, p)
        u = scene._align_anchor_dir
        a, b = oracle(inst, 60.0, -80.0), oracle(inst, 180.0, -80.0)
        ex, ey = b.x() - a.x(), b.y() - a.y()
        n = (ex * ex + ey * ey) ** 0.5
        assert u is not None                                            # [RED]
        assert abs(abs(u[0] * ex / n + u[1] * ey / n) - 1.0) < 1e-6
    finally:
        close_view(view, scene)


def test_flip_axis_picks_a_block_edge_but_not_its_arc(qapp):
    from firepro3d.axis_picker import pick_axis
    view, scene, inst = _scene_with(POSES[1], nested=False)
    try:
        p = oracle(inst, -160.0, 20.0)                  # R left edge
        pick = pick_axis(scene, p, 3.0)
        assert pick is not None and pick.source is inst                 # [RED]
        e1, e2 = oracle(inst, -160.0, -40.0), oracle(inst, -160.0, 40.0)
        for q in (pick.p1, pick.p2):                    # collinear with the edge
            cross = ((e2.x() - e1.x()) * (q.y() - e1.y())
                     - (e2.y() - e1.y()) * (q.x() - e1.x()))
            assert abs(cross) < 1e-3
        arc_pt = oracle(inst, -100.0, 70.0)             # A's apex (90 deg)
        assert pick_axis(scene, arc_pt, 3.0) is None
    finally:
        close_view(view, scene)
