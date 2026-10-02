"""sketch_model — catalogue, registry, record round-trip (spec §6)."""
from firepro3d import sketch_model as sm


def test_catalogue_declares_every_session_type():
    names = {t.value for t in sm.ConstraintType}
    assert {"horizontal", "vertical", "coincident", "point_on_curve", "concentric",
            "symmetric", "fix", "parallel", "perpendicular", "equal", "tangent",
            "midpoint", "collinear", "dim_distance", "dim_point_line",
            "dim_radius", "dim_diameter", "dim_angle"} == names


def test_only_horizontal_is_implemented_in_cs1():
    assert [t for t, s in sm.REGISTRY.items() if s.implemented] == ["horizontal"]


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
        {"id": "x2", "type": "vertical", "refs": [{"uid": "a", "h": "edge"}]})
    assert built_later.inert          # declared but not implemented in CS1


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
