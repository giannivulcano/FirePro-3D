"""HF5 Task 1 -- fill_types core: table, payload, resolution, overrides."""
from firepro3d import fill_types as ft
from firepro3d.constants import (FILL_TYPE_FALLBACK_NAME, FILL_TYPE_FALLBACK_COLOR,
                                 FILL_TYPE_FALLBACK_OPACITY, TOKEN_ELEMENT)
from firepro3d.fill_layers import BackgroundLayer, FillLayers, PatternLayer, to_record

CONCRETE = FillLayers(BackgroundLayer("#c0c0c0", 1.0), PatternLayer("diag-id", "#000000", 1.0, 2.0))


def test_seed_has_black_and_fallback():
    t = ft.seed_table()
    names = [x.name for x in t.all()]
    assert names == sorted(names, key=str.casefold)
    assert "Solid Black" in names and FILL_TYPE_FALLBACK_NAME in names
    grey = t.by_name(FILL_TYPE_FALLBACK_NAME).layers
    assert grey.background.color == FILL_TYPE_FALLBACK_COLOR
    assert grey.background.opacity == FILL_TYPE_FALLBACK_OPACITY and grey.pattern is None


def test_payload_round_trip_keeps_ids_names_layers():
    t = ft.FillTypeTable()
    a = t.add(ft.FillType(ft.new_id(), "Concrete", CONCRETE))
    back = ft.FillTypeTable.from_payload(t.to_payload())
    got = back.get(a.id)
    assert got.name == "Concrete" and got.layers == CONCRETE
    assert t.to_payload()[0] == {"id": a.id, "name": "Concrete", **to_record(CONCRETE)}


def test_from_payload_drops_invalid_and_duplicate_names():
    rows = [{"id": "a", "name": "X"}, {"id": "b", "name": "x"}, {"id": "", "name": "Y"},
            {"name": "Z"}, "junk", {"id": "c", "name": "W", "pattern": {"ref": "p"}}]
    t = ft.FillTypeTable.from_payload(rows)
    assert sorted(x.id for x in t.all()) == ["a", "c"]      # 'x' dup of 'X' (casefold), first wins


def test_add_refuses_duplicate_name_and_id():
    t = ft.FillTypeTable()
    t.add(ft.FillType("a", "Concrete", CONCRETE))
    for bad in (ft.FillType("b", "concrete", CONCRETE), ft.FillType("a", "Other", CONCRETE)):
        try:
            t.add(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")


def test_resolve_missing_type_is_fallback_and_flagged():
    layers, missing = ft.resolve("nope", None, ft.FillTypeTable())
    assert missing is True
    assert layers.background.color == FILL_TYPE_FALLBACK_COLOR and layers.pattern is None


def test_overrides_merge_field_level_and_layer_off():
    t = ft.FillTypeTable([ft.FillType("c", "Concrete", CONCRETE)])
    layers, missing = ft.resolve("c", {"pattern": {"scale": 4.0}}, t)
    assert not missing and layers.pattern.scale == 4.0
    assert layers.pattern.ref == "diag-id" and layers.background == CONCRETE.background
    off, _ = ft.resolve("c", {"background": None}, t)
    assert off.background is None and off.pattern == CONCRETE.pattern


def test_override_adds_layer_the_type_lacks():
    t = ft.FillTypeTable([ft.FillType("s", "Solid", FillLayers(BackgroundLayer("#ff0000", 1.0)))])
    layers, _ = ft.resolve("s", {"pattern": {"ref": "p2", "color": "#00ff00"}}, t)
    assert layers.pattern == PatternLayer("p2", "#00ff00", 1.0, 1.0)


def test_diff_overrides_is_minimal_and_inverts_merge():
    new = FillLayers(CONCRETE.background, PatternLayer("diag-id", "#000000", 0.5, 2.0))
    ov = ft.diff_overrides(CONCRETE, new)
    assert ov == {"pattern": {"opacity": 0.5}}
    assert ft.merge_overrides(CONCRETE, ov) == new
    assert ft.diff_overrides(CONCRETE, CONCRETE) == {}
    assert ft.diff_overrides(CONCRETE, FillLayers(None, CONCRETE.pattern)) == {"background": None}


def test_record_fill_layers_typed_and_custom():
    ft.set_project_table(ft.FillTypeTable([ft.FillType("c", "Concrete", CONCRETE)]))
    assert ft.record_fill_layers({"fill_type": "c", "fill": {"pattern": {"scale": 3.0}}}).pattern.scale == 3.0
    custom = {"fill": to_record(CONCRETE)}
    assert ft.record_fill_layers(custom) == CONCRETE


def test_element_colour_substitutes_only_the_token():
    assert ft.element_colour(TOKEN_ELEMENT, "#123456") == "#123456"
    assert ft.element_colour("#abcdef", "#123456") == "#abcdef"


def test_ensure_look_dedupes_and_numbers_names():
    t = ft.FillTypeTable()
    a = t.ensure_look("Wall Section", CONCRETE)
    assert t.ensure_look("Wall Section", CONCRETE).id == a.id
    other = FillLayers(BackgroundLayer("#111111", 1.0))
    b = t.ensure_look("Wall Section", other)
    assert b.name == "Wall Section 2" and b.id != a.id


def test_ensure_named_project_wins():
    t = ft.FillTypeTable([ft.FillType("c", "Wall Section", CONCRETE)])
    got = t.ensure_named("wall section", FillLayers(BackgroundLayer("#111111", 1.0)))
    assert got.id == "c" and got.layers == CONCRETE
    added = t.ensure_named("Floor Section", CONCRETE)
    assert t.get(added.id).name == "Floor Section"


def test_store_reset_and_bus():
    hits = []
    ft.fill_type_bus().changed.connect(lambda: hits.append(1))
    ft.set_project_table(ft.FillTypeTable())
    ft.reset_project_table()
    assert ft.project_table().by_name("Solid Black") is not None
    assert len(hits) >= 2


def test_name_duplicate_row_is_aliased_to_the_kept_type():
    """Group A review I1: the dropped duplicate's id resolves to the first type."""
    from firepro3d.filled_region import FilledRegionItem
    rows = [{"id": "keep", "name": "Red", "background": {"color": "#ff0000", "opacity": 1.0}},
            {"id": "dup", "name": "red", "background": {"color": "#0000ff", "opacity": 1.0}},
            {"id": "keep", "name": "Other"}]                 # duplicate id: no alias, dropped
    t = ft.FillTypeTable.from_payload(rows)
    assert [x.id for x in t.all()] == ["keep"]
    assert t.get("dup") is t.get("keep") and t.copy().get("dup").id == "keep"
    assert ft.resolve("dup", {}, t) == (t.get("keep").layers, False)
    ft.set_project_table(t)
    r = FilledRegionItem([])
    r.set_fill_type("dup")
    assert r.fill_layers == t.get("keep").layers and not r.fill_type_missing
    assert r.to_dict()["fill_type"] == "dup"                  # no silent rewrite


def test_resolve_with_an_empty_explicit_table_does_not_fall_back_to_the_project_table():
    ft.set_project_table(ft.FillTypeTable([ft.FillType("x", "X", CONCRETE)]))
    assert ft.resolve("x", {}, ft.FillTypeTable())[1] is True
    assert ft.resolve("x", {})[1] is False


def test_missing_type_label_is_one_spelling_for_panel_and_selectors(qapp):
    """VC9 M7: the region panel and the DM selector spell a missing type alike."""
    from firepro3d.filled_region import FilledRegionItem
    from firepro3d.geometry_2d import LineItem
    from PyQt6.QtCore import QPointF
    assert ft.missing_type_label("deadbeef-1234") == "? deadbeef"
    a, b, c = QPointF(0, 0), QPointF(100, 0), QPointF(100, 100)
    r = FilledRegionItem.from_pieces([[LineItem(a, b), LineItem(b, c), LineItem(c, a)]])
    r._fill_type = "deadbeef-1234"
    assert r.get_properties()["Fill Type"]["value"] == ft.missing_type_label("deadbeef-1234")
    assert ft.reserved_name(ft.missing_type_label("x"))
