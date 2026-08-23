from PyQt6.QtCore import QPointF
from firepro3d.wall_opening import WallOpening
from firepro3d.wall import WallSegment
from firepro3d import constants as C


def test_roundtrip_preserves_new_fields(qapp, model_scene):
    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    op = WallOpening(wall=w, feature_id="door_1829", offset_along=400.0)
    op.cross_offset_mm = 30.0
    op.alignment = C.OPENING_ALIGN_BACK
    op.mirror_hinge = True
    op.mirror_facing = True
    op.level = w.level
    d = op.to_dict()
    op2 = WallOpening.from_dict(d, wall=w)
    assert op2.feature_id == "door_1829"
    assert op2._offset_along == 400.0
    assert op2.cross_offset_mm == 30.0
    assert op2.alignment == C.OPENING_ALIGN_BACK
    assert op2.mirror_hinge is True and op2.mirror_facing is True


def test_legacy_kind_door_migrates_to_type_and_feature(qapp, model_scene):
    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    legacy = {"kind": "door", "width_mm": 920.0, "height_mm": 2040.0,
              "sill_mm": 0.0, "offset_along": 500.0, "level": "Level 1"}
    op = WallOpening.from_dict(legacy, wall=w)
    assert op._type == "door"
    assert op.feature_id == "door_914"          # nearest registry door to 920
    assert op.cross_offset_mm == 0.0
    assert op.alignment == C.OPENING_ALIGN_CENTER
    assert op.mirror_hinge is False and op.mirror_facing is False


def test_legacy_kind_window_keeps_sill(qapp, model_scene):
    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    legacy = {"kind": "window", "width_mm": 900.0, "height_mm": 1200.0,
              "sill_mm": 900.0, "offset_along": 200.0, "level": "Level 1"}
    op = WallOpening.from_dict(legacy, wall=w)
    assert op._type == "window"
    assert op._sill_mm == 900.0


def test_scene_io_roundtrip_opening(qapp, model_scene):
    """_capture_network / _restore_network round-trips all opening fields (§7.11)."""
    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w)
    scene._walls.append(w)
    op = WallOpening(wall=w, feature_id="door_1829", offset_along=400.0)
    op.cross_offset_mm = 30.0
    op.mirror_facing = True
    scene.addItem(op)
    w.openings.append(op)

    # Capture via the undo/redo dict path (same fields as save_to_file "walls" key)
    payload = scene._capture_network()

    # Restore into a fresh scene
    scene2 = model_scene()
    scene2._restore_network(payload)

    assert len(scene2._walls) == 1
    w2 = scene2._walls[0]
    assert len(w2.openings) == 1
    assert w2.openings[0].feature_id == "door_1829"
    assert w2.openings[0].cross_offset_mm == 30.0
    assert w2.openings[0].mirror_facing is True


def test_place_then_undo_removes_opening(qapp, model_scene):
    """push_undo_state / undo / redo correctly tracks opening placement (§7.15)."""
    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w)
    scene._walls.append(w)

    scene.push_undo_state()                         # baseline: wall with no opening

    op = WallOpening(wall=w, feature_id="door_914", offset_along=500.0)
    scene.addItem(op)
    w.openings.append(op)
    scene.push_undo_state()                         # after placing the opening

    scene.undo()
    assert len(scene._walls[0].openings) == 0       # restored to pre-place state

    scene.redo()
    assert len(scene._walls[0].openings) == 1       # opening is back
