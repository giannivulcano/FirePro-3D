import math
from PyQt6.QtCore import QPointF

from firepro3d.feature import (
    FeatureDef, FEATURE_REGISTRY, features_by_hierarchy, get_feature,
    DEFAULT_FEATURE_FOR_TYPE, feature_label,
)
from firepro3d.wall_opening import WallOpening
from firepro3d.wall import WallSegment
from firepro3d import constants as C


def test_registry_has_three_seed_doors():
    doors = [f for f in FEATURE_REGISTRY.values() if f.kind == "door"]
    widths = sorted(f.default_width_mm for f in doors)
    assert widths == [813.0, 914.0, 1829.0]
    assert all(f.host_type == "Wall" for f in doors)


def test_double_leaf_flag_on_wide_door():
    f = get_feature("door_1829")
    assert f.default_width_mm == 1829.0
    assert f.leaves == 2


def test_features_by_hierarchy_groups_feature_family_type():
    """Tree is Feature → Family → Type-leaf (docs/specs/feature-system.md F4)."""
    tree = features_by_hierarchy()
    assert {"Door", "Window", "Opening"} <= set(tree.keys())
    # Doors split into Single-Flush / Double-Flush families
    assert {"Single-Flush", "Double-Flush"} <= set(tree["Door"].keys())
    assert any(f.id == "door_914" for f in tree["Door"]["Single-Flush"])
    assert any(f.id == "door_1829" for f in tree["Door"]["Double-Flush"])


def test_feature_label_maps_kind_to_canonical_name():
    """The blank opening is the canonical 'Opening' Feature; door/window map 1:1."""
    assert feature_label(get_feature("blank_900")) == "Opening"
    assert feature_label(get_feature("door_914")) == "Door"
    assert feature_label(get_feature("window_900")) == "Window"


def test_feature_ids_are_stable_for_migration():
    """feature_id is serialized in .fpd — these ids must never be re-keyed."""
    assert set(FEATURE_REGISTRY.keys()) == {
        "door_813", "door_914", "door_1829", "window_900", "blank_900",
    }
    # Every Type carries a family + a sized Type-name leaf.
    for f in FEATURE_REGISTRY.values():
        assert f.family and f.type_name


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


def test_properties_expose_placement_fields(qapp, model_scene):
    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    op = WallOpening(wall=w, feature_id="window_900", offset_along=500.0)
    scene.addItem(op); w.openings.append(op)
    props = op.get_properties()
    assert props["Alignment"]["type"] == "enum"
    assert set(props["Alignment"]["options"]) == set(C.OPENING_ALIGNMENTS)
    assert props["Cross Offset"]["type"] == "dimension"
    assert props["Hinge Flip"]["type"] == "bool"
    assert props["Facing Flip"]["type"] == "bool"
    assert props["Level"]["type"] == "level_ref"


def test_set_alignment_snapshots_undo(qapp, model_scene):
    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    op = WallOpening(wall=w, feature_id="door_914", offset_along=500.0)
    scene.addItem(op); w.openings.append(op)
    n_before = len(scene._undo_stack)
    op.set_property("Alignment", C.OPENING_ALIGN_FRONT)
    assert op.alignment == C.OPENING_ALIGN_FRONT
    assert len(scene._undo_stack) == n_before + 1


# ── Smoke-fix regression: opening z-order above host wall ─────────────────────

def test_opening_renders_above_host_wall_after_z_pass(qapp, model_scene):
    """The elevation z-pass must keep an opening ABOVE its host wall so its plan
    gap cuts the wall. A door (head ~2032) is shorter than the wall (top ~3048);
    naive max-elevation z pushed it below the wall and the gap never cut
    (smoke-test 2026-08-23)."""
    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(3000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    op = WallOpening(wall=w, feature_id="door_914", offset_along=1500.0)
    scene.addItem(op); w.openings.append(op)
    scene._level_manager.apply_to_scene(scene)
    assert op.zValue() > w.zValue()


# ── Task-8 tests: FeatureBrowser widget ──────────────────────────────────────

def test_feature_browser_lists_features_and_activates(qapp):
    from firepro3d.feature_browser import FeatureBrowser
    activated = []
    fb = FeatureBrowser()
    fb.featureActivated.connect(activated.append)
    # Top level is the Feature tier (Door/Window/Opening), not the old umbrella.
    roots = [fb._tree.topLevelItem(i).text(0) for i in range(fb._tree.topLevelItemCount())]
    assert "Door" in roots and "Openings" not in roots
    leaf = fb._find_leaf("door_914")   # a Type leaf under Door → Single-Flush
    assert leaf is not None
    fb._on_item_activated(leaf, 0)
    assert activated == ["door_914"]


def test_feature_browser_bolds_grouping_tiers_only(qapp):
    """Feature + Family tiers render bold (house browser style); Type leaf regular."""
    from firepro3d.feature_browser import FeatureBrowser
    fb = FeatureBrowser()
    door = next(fb._tree.topLevelItem(i)
                for i in range(fb._tree.topLevelItemCount())
                if fb._tree.topLevelItem(i).text(0) == "Door")
    family = door.child(0)                       # Double-Flush / Single-Flush
    type_leaf = family.child(0)                  # e.g. "813 × 2032"
    assert door.font(0).bold() is True
    assert family.font(0).bold() is True
    assert type_leaf.font(0).bold() is False
