import math

from PyQt6.QtCore import QPointF

from firepro3d.construction_geometry import RectangleItem


def test_set_angle_stores_and_applies(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    r.set_angle(37.0, QPointF(0, 0))
    assert abs(r._angle - 37.0) < 1e-9              # stored as the Y-up display angle
    # Bake-at-rest (selection-manipulator.md): the angle is DATA, no held Qt
    # item transform — rotation() stays 0.  The rotated footprint comes from
    # _rotation_transform() (paint/shape/map*), not setRotation.
    assert r.rotation() == 0.0
    assert r._pivot == QPointF(0, 0)


def test_positive_angle_rotates_ccw_like_yup_convention(qapp):
    # A +90° rect must turn CCW (like line/arc angles), so a corner due-east of
    # the pivot swings UP (scene -y), not down — this is the direction the readout
    # promises.  RED before the Y-up→Qt negation: setRotation(+90) turned it CW
    # and the corner went down (+y).
    r = RectangleItem(QPointF(0, 0), QPointF(100, 0))
    r.set_angle(90.0, QPointF(0, 0))
    east = r.mapToScene(QPointF(100, 0))            # local +x corner
    assert east.y() < -1.0                          # swung UP (CCW)
    assert abs(east.x()) < 1e-6


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
    assert r.rotation() == 0.0            # no held transform at any angle


# ── Serialisation round-trips ─────────────────────────────────────────────────

def test_to_dict_includes_angle_and_pivot(qapp):
    r = RectangleItem(QPointF(10, 20), QPointF(110, 70))
    r.set_angle(37.0, QPointF(10, 20))
    d = r.to_dict()
    assert abs(d["angle"] - 37.0) < 1e-9
    assert d["pivot"] == [10.0, 20.0]


def test_from_dict_restores_angle_and_pivot(qapp):
    d = {"type": "draw_rectangle", "x": 10, "y": 20, "w": 100, "h": 50,
         "angle": 37.0, "pivot": [10.0, 20.0]}
    r = RectangleItem.from_dict(d)
    assert abs(r._angle - 37.0) < 1e-9
    assert r.rotation() == 0.0                 # baked-at-rest: angle is data
    assert r._pivot.x() == 10.0 and r._pivot.y() == 20.0


def test_from_dict_backcompat_no_angle(qapp):
    r = RectangleItem.from_dict({"type": "draw_rectangle", "x": 0, "y": 0,
                                 "w": 100, "h": 50})
    assert r._angle == 0.0
    assert r.rotation() == 0.0            # renders axis-aligned exactly as before


def test_centre_following_pivot_serialises_as_null_and_round_trips(qapp):
    # No explicit pivot: the rotation follows the rect centre (_pivot is None).
    # That tracking semantic must survive the round-trip, so pivot persists as
    # null (not the resolved centre, which would pin it and break re-centring on
    # a later resize — reachable via undo, which uses this same path).
    r = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    r.set_angle(15.0)                     # pivot=None -> origin tracks centre
    d = r.to_dict()
    assert d["pivot"] is None
    # Render is still faithful (origin = current centre) and tracking survives.
    r2 = RectangleItem.from_dict(d)
    assert r2._pivot is None
    # Centre-following pivot re-derives from the rect centre on demand.
    assert r2._rotation_origin() == QPointF(50.0, 25.0)
    assert abs(r2._angle - 15.0) < 1e-9


def test_scene_io_round_trip_preserves_angle_pivot(qapp, tmp_path):
    from firepro3d.model_space import Model_Space
    scene = Model_Space()
    r = RectangleItem(QPointF(10, 20), QPointF(110, 70))
    r.set_angle(37.0, QPointF(10, 20))
    scene.addItem(r)
    scene._draw_rects.append(r)
    f = tmp_path / "rect.fpd"
    scene.save_to_file(str(f))

    scene2 = Model_Space()
    scene2.load_from_file(str(f))
    assert len(scene2._draw_rects) == 1
    r2 = scene2._draw_rects[0]
    assert abs(r2._angle - 37.0) < 1e-9
    assert r2.rotation() == 0.0                 # baked-at-rest through file I/O
    assert r2._pivot.x() == 10.0
    assert r2._pivot.y() == 20.0


def test_undo_path_preserves_angle_pivot(qapp):
    from firepro3d.model_space import Model_Space
    scene = Model_Space()
    r = RectangleItem(QPointF(10, 20), QPointF(110, 70))
    r.set_angle(37.0, QPointF(10, 20))
    scene.addItem(r)
    scene._draw_rects.append(r)
    snap = scene._capture_network()
    scene._restore_network(snap)
    assert len(scene._draw_rects) == 1
    r2 = scene._draw_rects[0]
    assert abs(r2._angle - 37.0) < 1e-9
    assert r2.rotation() == 0.0                 # baked-at-rest through undo capture
    assert r2._pivot.x() == 10.0
    assert r2._pivot.y() == 20.0


def test_translate_moves_rotated_rect_with_its_pivot(qapp):
    # Move bug: a rotated rect has an explicit pivot (rotate step sets one), and
    # translate must carry the pivot with the rect — else the committed rotated
    # rect swings about a stale origin and lands away from the ghost.
    r = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    r.set_angle(30.0, QPointF(0, 0))                    # explicit pivot at origin
    br_before = r.mapToScene(r.rect().bottomRight())    # scene pos of the BR corner
    r.translate(200, 100)
    br_after = r.mapToScene(r.rect().bottomRight())      # BR corner at its new local pos
    # the rotated corner must move by exactly the offset (ghost == committed)
    assert abs(br_after.x() - (br_before.x() + 200)) < 1e-6
    assert abs(br_after.y() - (br_before.y() + 100)) < 1e-6
