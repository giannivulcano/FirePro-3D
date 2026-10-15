"""sketch_model — catalogue, registry, record round-trip (spec §6)."""
from firepro3d import sketch_model as sm


def test_catalogue_declares_every_session_type():
    names = {t.value for t in sm.ConstraintType}
    assert {"horizontal", "vertical", "coincident", "point_on_curve", "concentric",
            "symmetric", "fix", "parallel", "perpendicular", "equal", "tangent",
            "midpoint", "collinear", "dim_distance", "dim_point_line",
            "dim_radius", "dim_diameter", "dim_angle", "dim_arc_angle"} == names


def test_built_types_after_cs10():
    assert [t for t, s in sm.REGISTRY.items() if s.implemented] == [
        "horizontal", "vertical", "coincident", "point_on_curve", "dim_distance",
        "dim_radius", "dim_diameter", "dim_angle", "dim_arc_angle", "concentric",
        "symmetric", "fix", "parallel", "perpendicular", "dim_point_line"]


def test_registry_perpendicular_built():
    s = sm.REGISTRY["perpendicular"]
    assert s.implemented and s.label == "Perpendicular" and s.dof == 1
    assert s.patterns == (("edge", "edge"), ("edge", "axis"))
    assert sm.icon_for("perpendicular") == "constraint_perpendicular_icon.svg"


def test_registry_parallel_built():
    s = sm.REGISTRY["parallel"]
    assert s.implemented and s.label == "Parallel" and s.dof == 1
    assert s.patterns == (("edge", "edge"), ("edge", "axis"))
    assert sm.icon_for("parallel") == "constraint_parallel_icon.svg"


def test_registry_symmetric_and_fix_built():
    s = sm.REGISTRY["symmetric"]
    assert s.implemented and s.label == "Symmetric"
    assert s.patterns == (("point", "point", "edge"), ("point", "point", "axis"),
                          ("edge", "edge", "edge"), ("edge", "edge", "axis"),
                          ("curve", "curve", "edge"), ("curve", "curve", "axis"))
    f = sm.REGISTRY["fix"]
    assert f.implemented and f.label == "Fix"
    assert f.patterns == (("point",), ("item",))
    assert sm.HANDLE_ITEM == "item"
    assert sm.icon_for("symmetric") == "constraint_symmetric_icon.svg"
    assert sm.icon_for("fix") == "constraint_fix_icon.svg"


def test_registry_concentric_built():
    spec = sm.REGISTRY["concentric"]
    assert spec.implemented and spec.dof == 2 and spec.label == "Concentric"
    assert spec.patterns == (("curve", "curve"), ("curve", "point"))
    assert sm.icon_for("concentric") == "constraint_concentric_icon.svg"


def test_valued_types_are_the_dims():
    assert sm.VALUED == {"dim_distance", "dim_radius", "dim_diameter",
                         "dim_angle", "dim_arc_angle", "dim_point_line"}


def test_vertical_accepts_edge_or_two_points():
    spec = sm.REGISTRY["vertical"]
    assert spec.patterns == (("edge",), ("point", "point"))
    assert spec.dof == 1 and spec.label == "Vertical"


def test_horizontal_accepts_edge_or_two_points():
    spec = sm.REGISTRY["horizontal"]
    assert spec.patterns == (("edge",), ("point", "point"))
    assert spec.dof == 1


def test_record_round_trip_and_defaults():
    c = sm.Constraint.new("horizontal", [{"uid": "a", "h": "edge"}])
    d = c.to_dict()
    assert d["type"] == "horizontal" and d["value"] is None
    assert d["driving"] is True and d["enabled"] is True and d["helper"] == {}
    assert sm.Constraint.from_dict(d).to_dict() == d


def test_unknown_or_unbuilt_record_is_inert_and_verbatim():
    raw = {"id": "x1", "type": "from_the_future", "refs": [], "extra": [1, 2]}
    c = sm.Constraint.from_dict(raw)
    assert c.inert
    assert c.to_dict() == raw
    built_later = sm.Constraint.from_dict(
        {"id": "x2", "type": "equal",
         "refs": [{"uid": "a", "h": "edge"}, {"uid": "b", "h": "edge"}]})
    assert built_later.inert          # declared but not implemented (CS11)


def test_registry_coincident_types_built():
    assert sm.REGISTRY["coincident"].implemented
    assert sm.REGISTRY["point_on_curve"].implemented
    assert sm.REGISTRY["point_on_curve"].label == "Coincident"


def test_ref_helpers():
    c = sm.Constraint.new("horizontal", [{"uid": "a", "h": "p1"}, {"ref": "origin"}])
    assert sm.ref_uids(c) == {"a"}
    assert sm.is_ground({"ref": "origin"}) and not sm.is_ground({"uid": "a", "h": "p1"})


def test_remap_for_copy_keeps_internal_drops_external_and_grounds():
    inside = sm.Constraint.new("horizontal", [{"uid": "a", "h": "edge"}])
    outside = sm.Constraint.new("horizontal", [{"uid": "a", "h": "p1"}, {"uid": "z", "h": "p1"}])
    grounded = sm.Constraint.new("horizontal", [{"uid": "a", "h": "p1"}, {"ref": "origin"}])
    out = sm.remap_for_copy([inside, outside, grounded], {"a": "A2"})
    assert len(out) == 1
    assert out[0].refs == [{"uid": "A2", "h": "edge"}] and out[0].id != inside.id


def test_built_record_keeps_unknown_top_level_keys():
    raw = {"id": "h1", "type": "horizontal", "refs": [{"uid": "a", "h": "edge"}],
           "value": None, "driving": True, "enabled": True, "helper": {}, "future": 1}
    c = sm.Constraint.from_dict(raw)
    assert not c.inert
    assert c.to_dict()["future"] == 1
    assert c.to_dict() == raw


def test_inert_raw_is_isolated_from_input_mutation():
    raw = {"id": "x1", "type": "from_the_future", "refs": [], "extra": [1, 2]}
    c = sm.Constraint.from_dict(raw)
    raw["extra"].append(3)
    raw["added"] = True
    assert c.to_dict() == {"id": "x1", "type": "from_the_future", "refs": [], "extra": [1, 2]}


def test_new_does_not_alias_helper_or_label():
    helper = {"kind": "x"}
    label = {"pos": [1, 2]}
    c = sm.Constraint.new("horizontal", [], helper=helper, label=label)
    helper["kind"] = "y"
    label["pos"].append(3)
    assert c.helper == {"kind": "x"} and c.label == {"pos": [1, 2]}


def test_remap_two_ref_internal_preserves_h_and_source_unchanged():
    src = sm.Constraint.new("horizontal", [{"uid": "a", "h": "p1"}, {"uid": "b", "h": "p2"}])
    before = src.to_dict()
    out = sm.remap_for_copy([src], {"a": "A2", "b": "B2"})
    assert out[0].refs == [{"uid": "A2", "h": "p1"}, {"uid": "B2", "h": "p2"}]
    assert src.to_dict() == before


def test_catalogue_and_registry_in_sync():
    assert {t.value for t in sm.ConstraintType} == set(sm.REGISTRY)
