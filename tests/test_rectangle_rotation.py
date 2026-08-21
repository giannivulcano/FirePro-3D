import math

from PyQt6.QtCore import QPointF

from firepro3d.construction_geometry import RectangleItem


def test_set_angle_stores_and_applies(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    r.set_angle(37.0, QPointF(0, 0))
    assert abs(r._angle - 37.0) < 1e-9
    assert abs(r.rotation() - 37.0) < 1e-9          # Qt transform applied
    # transform origin is the pivot (local coords == scene coords at identity pos)
    assert r.transformOriginPoint() == QPointF(0, 0)


def test_grip_points_are_scene_coords_after_rotation(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 0))   # thin rect ok for corner math
    r.set_angle(90.0, QPointF(0, 0))                     # rotate 90° about origin
    grips = r.grip_points()
    tl = grips[0]                                         # TL local (0,0) -> pivot -> stays (0,0)
    assert abs(tl.x()) < 1e-6 and abs(tl.y()) < 1e-6
    # a corner at local (100,0) must equal mapToScene of that local corner
    tr = grips[2]                                         # TR local (100,0)
    exp = r.mapToScene(QPointF(100, 0))
    assert abs(tr.x() - exp.x()) < 1e-6 and abs(tr.y() - exp.y()) < 1e-6


def test_apply_grip_maps_scene_to_local_noop(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    r.set_angle(30.0, QPointF(0, 0))
    before = r.grip_points()[4]                           # BR in scene coords
    r.apply_grip(4, before)                               # drag BR to itself → no geometry change
    after = r.grip_points()[4]
    assert abs(after.x() - before.x()) < 1e-6 and abs(after.y() - before.y()) < 1e-6


def test_apply_grip_resizes_in_rotated_frame(qapp):
    # Dragging a grip to a scene point resizes correctly in the rotated frame.
    r = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    r.set_angle(90.0, QPointF(0, 0))
    br_scene = r.grip_points()[4]
    # move BR outward along the rotated x by mapping a local target to scene
    target_local = QPointF(150, 50)
    r.apply_grip(4, r.mapToScene(target_local))
    assert abs(r.rect().right() - 150) < 1e-6            # local rect grew as expected


def test_default_angle_is_zero(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    assert r._angle == 0.0
    assert abs(r.rotation()) < 1e-9
