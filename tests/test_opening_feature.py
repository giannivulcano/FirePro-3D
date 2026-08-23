import math
from PyQt6.QtCore import QPointF

from firepro3d.feature import (
    FeatureDef, FEATURE_REGISTRY, features_by_category, get_feature, DEFAULT_FEATURE_FOR_TYPE,
)
from firepro3d.wall_opening import WallOpening
from firepro3d.wall import WallSegment
from firepro3d import constants as C


def test_registry_has_three_seed_doors():
    doors = [f for f in FEATURE_REGISTRY.values()
             if f.category == "Openings" and f.type == "door"]
    widths = sorted(f.default_width_mm for f in doors)
    assert widths == [813.0, 914.0, 1829.0]
    assert all(f.host_type == "Wall" for f in doors)


def test_double_leaf_flag_on_wide_door():
    f = get_feature("door_1829")
    assert f.default_width_mm == 1829.0
    assert f.leaves == 2


def test_features_by_category_groups_feature_category_type():
    tree = features_by_category()
    assert "Openings" in tree
    assert set(tree["Openings"].keys()) >= {"door", "window", "blank"}
    assert any(f.id == "door_914" for f in tree["Openings"]["door"])


def test_default_feature_per_type():
    assert DEFAULT_FEATURE_FOR_TYPE["door"] == "door_914"
    assert DEFAULT_FEATURE_FOR_TYPE["window"] in FEATURE_REGISTRY
    assert DEFAULT_FEATURE_FOR_TYPE["blank"] in FEATURE_REGISTRY


# ── Task-2 tests: WallOpening placement frame ─────────────────────────────────

def _horiz_wall(model_scene, length_scene=1000.0, thickness_mm=200.0):
    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(length_scene, 0), thickness_mm=thickness_mm)
    scene.addItem(w)
    scene._walls.append(w)
    return scene, w


def test_centered_offset_zero_sits_on_centerline(qapp, model_scene):
    scene, w = _horiz_wall(model_scene)
    op = WallOpening(wall=w, feature_id="door_914", offset_along=500.0)
    op.alignment = C.OPENING_ALIGN_CENTER
    op.cross_offset_mm = 0.0
    op._reposition()
    assert abs(op.center_on_wall().y()) < 1e-6
    assert abs(op.center_on_wall().x() - 500.0) < 1e-6


def test_positive_cross_offset_moves_off_centerline(qapp, model_scene):
    scene, w = _horiz_wall(model_scene)
    op = WallOpening(wall=w, feature_id="door_914", offset_along=500.0)
    op.cross_offset_mm = 100.0
    op._reposition()
    assert op.center_on_wall().y() > 0.0


def test_facing_mirror_negates_world_offset_proud_stays_proud(qapp, model_scene):
    scene, w = _horiz_wall(model_scene)
    op = WallOpening(wall=w, feature_id="door_914", offset_along=500.0)
    op.cross_offset_mm = 300.0
    op._reposition()
    y_before = op.center_on_wall().y()
    op.mirror_facing = not op.mirror_facing
    op._reposition()
    y_after = op.center_on_wall().y()
    assert y_after == -y_before
    assert abs(y_after) == abs(y_before)


def test_alignment_cycle_preserves_typed_offset(qapp, model_scene):
    scene, w = _horiz_wall(model_scene)
    op = WallOpening(wall=w, feature_id="door_914", offset_along=500.0)
    op.cross_offset_mm = 25.0
    op.alignment = C.OPENING_ALIGN_BACK
    op._reposition()
    op.alignment = C.OPENING_ALIGN_CENTER
    op._reposition()
    assert op.cross_offset_mm == 25.0


def test_along_wall_offset_clamped_but_cross_offset_not(qapp, model_scene):
    scene, w = _horiz_wall(model_scene, length_scene=1000.0)
    op = WallOpening(wall=w, feature_id="door_914", offset_along=5000.0)
    op.cross_offset_mm = 9999.0
    op._reposition()
    assert op._offset_along <= 1000.0
    assert op.cross_offset_mm == 9999.0


def test_z_range_from_assigned_level_and_sill(qapp, model_scene):
    scene, w = _horiz_wall(model_scene)
    op = WallOpening(wall=w, feature_id="window_900", offset_along=500.0)
    op.sill_mm = 900.0
    op.height_mm = 1200.0
    op.level = w.level
    zr = op.z_range_mm()
    lvl_elev = scene._level_manager.get(op.level).elevation
    assert zr == (lvl_elev + 900.0, lvl_elev + 900.0 + 1200.0)
