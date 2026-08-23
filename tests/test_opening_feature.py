from firepro3d.feature import (
    FeatureDef, FEATURE_REGISTRY, features_by_category, get_feature, DEFAULT_FEATURE_FOR_TYPE,
)


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
