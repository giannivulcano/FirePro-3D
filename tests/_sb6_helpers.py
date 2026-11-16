"""Shared builders for the SB6 placed-tag guards (tests/test_sb6_*.py).

Ground truth (``expected_pose``) is re-derived from the raw wall endpoints and
the opening's stored ``_offset_along`` (scene Y-down; a = atan2(dy, dx);
n = (-sin a, cos a), wall.py normal()) -- never read from firepro3d.hosted_tag."""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF

U, V = 500.0, -800.0          # the placed host-frame offset, mm (ppm 1.0: ScaleManager default)


def add_wall(scene, p1=(-2000.0, 0.0), p2=(2000.0, 0.0), mark="W1"):
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(*p1), QPointF(*p2), thickness_mm=200.0)
    w._mark = mark
    scene.addItem(w)
    scene._walls.append(w)
    return w


def add_door(scene, wall, along=1000.0, feature="door_914", mark="101"):
    from firepro3d.wall_opening import WallOpening
    op = WallOpening(wall, feature_id=feature, offset_along=along)
    op.level = wall.level
    op._mark = mark
    wall.openings.append(op)
    scene.addItem(op)
    return op


def place_tag(scene, host, orientation="horizontal", leader=False, u=U, v=V):
    """A tag on *host* through ``place_block_instance(host_uid=, tag=)`` and one
    committed step (whose ``refresh_all_bound`` poses it, Task 4)."""
    from firepro3d import element_params
    d = scene.annotation_block(element_params.category_of(host))
    assert d is not None, "needs the real_system_library fixture"
    rec = {"offset": [u, v], "orientation": orientation,
           "leader": {"knee": None} if leader else None, "block": None}
    if leader:          # the End is loaded first, as the tool / Leader row do (Task 6 onward)
        from firepro3d.capabilities import ensure_end_available
        from firepro3d.paper_display import tag_leader_end
        ensure_end_available(tag_leader_end(), scene, outside_history=True)
    tag = scene.place_block_instance(d.id, (0.0, 0.0), level=host.level,
                                     host_uid=host._uid, tag=rec)
    scene.push_undo_state()
    return tag


def raw_anchor(host):
    """``(ax, ay, a)``: the anchor and scene angle from the raw endpoints (centre
    alignment; an opening = pt1 + offset_along * dir, cross offset 0)."""
    from firepro3d.wall_opening import WallOpening
    w = host.wall if isinstance(host, WallOpening) else host
    x1, y1, x2, y2 = w.pt1.x(), w.pt1.y(), w.pt2.x(), w.pt2.y()
    a = math.atan2(y2 - y1, x2 - x1)
    if isinstance(host, WallOpening):
        return (x1 + host._offset_along * math.cos(a),
                y1 + host._offset_along * math.sin(a), a)
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0, a


def expected_pose(host, orientation="horizontal", u=U, v=V, ppm=1.0):
    """``(x, y, rotation)`` of a tag at host-frame (u, v): anchor + ppm * (u * dir + v * n);
    rotation 0 (Horizontal) or -degrees(a) (Aligned, Y-up)."""
    ax, ay, a = raw_anchor(host)
    c, s = math.cos(a), math.sin(a)
    rot = -math.degrees(a) if orientation == "aligned" else 0.0
    return (ax + ppm * (u * c - v * s), ay + ppm * (u * s + v * c), rot)


def pose_of(tag):
    x, y = tag.block_pos()
    return (x, y, tag.block_rotation())


def tags_of(scene):
    return [b for b in scene._block_instances if b.tag is not None]


def panel_for(item, tmp_path):
    """A real PropertyManager showing *item* (tests/_ph1_helpers.py ``panel`` body)."""
    from PyQt6.QtWidgets import QApplication
    from firepro3d.property_manager import PropertyManager
    from firepro3d.sprinkler_db import SprinklerDatabase
    pm = PropertyManager()
    pm.set_sprinkler_db(SprinklerDatabase(path=str(tmp_path / "sprinklers.json")))
    pm.show_properties(item)
    QApplication.processEvents()
    return pm


def drop_panel(pm):
    if pm is not None:
        pm._refresh_timer.stop()
        pm.deleteLater()
