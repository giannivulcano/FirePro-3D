"""SB6 D2 / D5 / D6 -- hosted_tag maths. Every expected value is derived in this file
from the raw wall endpoints (scene Y-down; a = atan2(dy, dx); n = (-sin a, cos a),
wall.py normal()) and the door's stored offset_along."""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import hosted_tag as ht


def _wall(p1, p2):
    from firepro3d.wall import WallSegment
    return WallSegment(QPointF(*p1), QPointF(*p2), thickness_mm=200.0)


def _raw(p1, p2, u, v, ppm):
    """anchor (centreline midpoint) + ppm * (u * dir + v * n), from the endpoints."""
    a = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    mx, my = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
    return (mx + ppm * (u * math.cos(a) - v * math.sin(a)),
            my + ppm * (u * math.sin(a) + v * math.cos(a)), a)


@pytest.mark.parametrize("p1,p2,u,v,ppm", [
    ((1000.0, 500.0), (4000.0, 2500.0), 600.0, -250.0, 1.0),
    ((1000.0, 500.0), (4000.0, 2500.0), 600.0, -250.0, 2.0),
    ((0.0, 0.0), (0.0, -4000.0), 500.0, 200.0, 1.0),          # points up on screen
    ((2000.0, -1000.0), (-2000.0, 1000.0), -300.0, 900.0, 1.0),
])
def test_pose_is_anchor_plus_rotated_offset(qapp, p1, p2, u, v, ppm):
    w = _wall(p1, p2)
    x, y, a = _raw(p1, p2, u, v, ppm)
    rec = ht.new_record((u, v))
    assert ht.pose(rec, w, ppm) == pytest.approx((x, y, 0.0), abs=1e-9)        # Horizontal
    rec["orientation"] = "aligned"
    assert ht.pose(rec, w, ppm) == pytest.approx((x, y, -math.degrees(a)), abs=1e-9)


def test_vertical_wall_numbers_written_out(qapp):
    # wall (0,0)->(0,-4000): mid (0,-2000), a = -90 deg, dir (0,-1), n (1,0)
    w = _wall((0.0, 0.0), (0.0, -4000.0))
    rec = ht.new_record((500.0, 200.0), "aligned")
    assert ht.pose(rec, w, 1.0) == pytest.approx((200.0, -2500.0, 90.0), abs=1e-9)


@pytest.mark.parametrize("ppm", [1.0, 2.5])
def test_offset_from_scene_inverts_pose(qapp, ppm):
    p1, p2 = (1000.0, 500.0), (4000.0, 2500.0)
    w = _wall(p1, p2)
    pt = QPointF(3100.0, 900.0)
    a = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    dx, dy = (3100.0 - 2500.0) / ppm, (900.0 - 1500.0) / ppm
    want = [dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a)]
    assert ht.offset_from_scene(w, ppm, pt) == pytest.approx(want, abs=1e-9)


def test_door_anchor_is_its_centre_on_the_wall(qapp):
    from firepro3d.wall_opening import WallOpening
    w = _wall((0.0, 0.0), (4000.0, 0.0))
    op = WallOpening(w, feature_id="door_914", offset_along=1000.0)
    # centre = pt1 + offset_along * dir (cross offset 0, centred): (1000, 0); a = 0
    assert ht.pose(ht.new_record((0.0, -500.0)), op, 1.0) == pytest.approx((1000.0, -500.0, 0.0))


def test_detached_opening_has_no_pose(qapp):
    from firepro3d.wall_opening import WallOpening
    op = WallOpening(None, feature_id="door_914")
    assert ht.anchor(op) is None
    assert ht.pose(ht.new_record(), op, 1.0) is None
    assert ht.offset_from_scene(op, 1.0, QPointF(1.0, 1.0)) is None


def test_normalise_cleans_or_refuses():
    assert ht.normalise(None) is None
    assert ht.normalise({"offset": "x"}) is None
    assert ht.normalise({"offset": [1.0, float("nan")]}) is None
    rec = ht.normalise({"offset": [1, 2], "orientation": "sideways",
                        "leader": {"knee": [1.0, 2.0]}, "block": ""})          # no edge: cannot draw
    assert rec == {"offset": [1.0, 2.0], "orientation": "horizontal",
                   "leader": None, "block": None}
    rec = ht.normalise({"offset": [1, 2], "leader": {"edge": "L", "tip": ["a", 1]}})
    assert rec["leader"] == {"edge": "L", "t": 0.5, "shoulder_mm": 2.0, "tip": [0.0, 0.0],
                             "end": "system-endtypes-arrow", "weight": ""}   # min shoulder, tip at anchor
    src = {"offset": [1.0, 2.0], "orientation": "aligned",
           "leader": {"edge": "B", "t": 0.25, "shoulder_mm": 8.0, "tip": [3.0, 4.0],
                      "end": "none", "weight": "Thin"},
           "block": "b"}
    out = ht.normalise(src)
    assert out == src and out["leader"] is not src["leader"]          # a copy


def test_tip_scene_uses_the_host_frame(qapp):
    w = _wall((0.0, 0.0), (0.0, -4000.0))                           # dir (0,-1), n (1,0)
    assert ht.tip_scene(ht.new_record((0.0, 0.0)), w, 1.0) is None  # no leader
    rec = ht.new_record((0.0, 0.0), leader=True)
    t = ht.tip_scene(rec, w, 1.0)
    assert (t.x(), t.y()) == pytest.approx((0.0, -2000.0))          # a new tip: the host anchor
    rec["leader"]["tip"] = [100.0, 300.0]
    t = ht.tip_scene(rec, w, 1.0)
    assert (t.x(), t.y()) == pytest.approx((300.0, -2100.0))        # (0,-2000) + 100*(0,-1) + 300*(1,0)


def test_leader_op_shape():
    from firepro3d.render_op import STROKE
    op = ht.leader_op([QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(10.0, 10.0)],
                      "system-endtypes-arrow", "Thin")
    assert op.kind == STROKE and op.weight == "Thin"
    assert op.ends[0]["end"] == "none" and op.ends[1]["end"] == "system-endtypes-arrow"
    assert len(op.pieces) == 2


def test_resolve_drops_an_ineligible_swap(qapp, real_system_library):
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    ms._level_manager = LevelManager()
    try:
        w = _wall((0.0, 0.0), (4000.0, 0.0))
        ms.addItem(w)
        ms._walls.append(w)
        rec = ht.new_record()
        assert ht.resolve(rec, w, ms) == "system-tags-walltag"      # WallTag.fpdb id
        assert ms.ensure_system_block("system-tags-doortag") is not None
        rec["block"] = "system-tags-doortag"                          # a Door tag on a wall
        assert ht.resolve(rec, w, ms) == "system-tags-walltag"
        assert rec["block"] is None                                   # D6 / R8: dropped
    finally:
        ms.cleanup()


def test_moves_with_host(qapp):
    from firepro3d.model_space import Model_Space
    from firepro3d.wall_opening import WallOpening
    ms = Model_Space()
    try:
        w = _wall((0.0, 0.0), (4000.0, 0.0))
        ms.addItem(w)
        op = WallOpening(w, feature_id="door_914", offset_along=1000.0)
        ms.addItem(op)
        assert not ht.moves_with_host(w) and not ht.moves_with_host(op)
        w.setSelected(True)
        assert ht.moves_with_host(w) and ht.moves_with_host(op)      # an opening rides its wall
    finally:
        ms.cleanup()
