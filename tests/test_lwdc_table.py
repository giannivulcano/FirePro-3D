"""LW-DC T1: factory Defaults, legacy merge-by-width map, picker order."""
from firepro3d import paper_display as pd


def test_factory_defaults_lwdc1():
    assert [(d.name, d.width_mm, d.model_px) for d in pd.DEFAULT_LINE_WEIGHTS] == [
        ("Extra Thin", .13, 1), ("Thin", .18, 2), ("Fine", .25, 3), ("Medium", .35, 4),
        ("Wide", .50, 5), ("Thick", .70, 6), ("Extra Thick", 1.00, 8)]
    assert pd.FACTORY_LINE_WEIGHTS is pd.DEFAULT_LINE_WEIGHTS


def _t(rows):
    return [pd.LineWeightDef(n, w) for n, w in rows]


def test_mw_project_merges_by_width():
    mw = _t([("Thinnest", .18), ("Thinner", .25), ("Thin", .35), ("Thick", .50),
             ("Thickest", .70)])
    defs, m = pd.legacy_weight_migration(mw)
    five = ("Thinnest", "Thinner", "Thin", "Thick", "Thickest")
    assert m == {"Thinnest": "Thin", "Thinner": "Fine", "Thin": "Medium",
                 "Thick": "Wide", "Thickest": "Thick",
                 **{k: v for k, v in pd._STATIC_LEGACY_MAP.items() if k not in five}}
    assert sorted(d.name for d in defs) == sorted(d.name for d in pd.DEFAULT_LINE_WEIGHTS)


def test_legacy_project_merges_by_width():
    old = _t([("Very Light", .13), ("Light", .18), ("Medium", .25), ("Heavy", .35),
              ("Very Heavy", .50)])
    defs, m = pd.legacy_weight_migration(old)
    assert (m["Medium"], m["Heavy"], m["Light"]) == ("Fine", "Medium", "Thin")
    assert len(defs) == 7


def test_custom_clash_gets_old_suffix_and_keeps_mm():
    defs, m = pd.legacy_weight_migration(_t([("Thin", .30), ("My Pen", .40)]))
    assert m["Thin"] == "Thin (old)"
    by = {d.name: d.width_mm for d in defs}
    assert by["Thin (old)"] == .30 and by["My Pen"] == .40 and by["Thin"] == .18


def test_old_suffix_is_uniquified():
    defs, m = pd.legacy_weight_migration(_t([("Thin", .30), ("Thin (old)", .31)]))
    assert m["Thin"] == "Thin (old 2)"
    assert {d.name: d.width_mm for d in defs}["Thin (old)"] == .31


def test_merged_row_keeps_model_px_override():
    defs, _ = pd.legacy_weight_migration([pd.LineWeightDef("Thin", .35, 7)])
    assert {d.name: d.model_px for d in defs}["Medium"] == 7


def test_picker_order_defaults_then_custom():
    pd.set_project_line_weights([*pd.DEFAULT_LINE_WEIGHTS, pd.LineWeightDef("Pen X", .40),
                                 pd.LineWeightDef("Pen A", .05)])
    try:
        names = pd.weight_names()
        assert names[:7] == [d.name for d in pd.DEFAULT_LINE_WEIGHTS]
        assert names[7:] == ["Pen A", "Pen X"] and pd.weight_separator_index() == 7
    finally:
        pd.reset_project_line_weights()


def test_default_helpers_and_name_validation():
    assert pd.is_default_weight("Fine") and not pd.is_default_weight("Pen")
    f = pd.factory_default("Wide")
    assert (f.name, f.width_mm, f.model_px) == ("Wide", .50, 5)
    f.width_mm = 9
    assert pd.factory_default("Wide").width_mm == .50
    assert pd.factory_default("Nope") is None
    assert not pd.validate_line_weight_name("Thin", [])
    assert pd.validate_line_weight_name("Pen", [])
    miss = pd.ensure_defaults([pd.LineWeightDef("Pen", .4)])
    assert {d.name for d in miss} == {"Pen", *(d.name for d in pd.DEFAULT_LINE_WEIGHTS)}


def test_old_factory_names_still_resolve_by_mm():
    pd.set_project_line_weights(pd.DEFAULT_LINE_WEIGHTS)
    try:
        assert pd.live_weight_name("Thinnest") == "Thin"       # .18
        assert pd.live_weight_name("Very Heavy") == "Wide"     # .50
        assert pd.live_weight_name("Thin") == "Thin"           # Default row by name
    finally:
        pd.reset_project_line_weights()


def test_load_template_mw_or_legacy_factory_becomes_defaults():
    from PyQt6.QtCore import QSettings
    import json
    for rows in ([("Thinnest", .18), ("Thinner", .25), ("Thin", .35), ("Thick", .50),
                  ("Thickest", .70)],
                 [("Very Light", .13), ("Light", .18), ("Medium", .25), ("Heavy", .35),
                  ("Very Heavy", .50)]):
        s = QSettings("GV", "FirePro3D")
        s.setValue("paper/line_weights", json.dumps(
            [{"name": n, "width_mm": w} for n, w in rows]))
        assert [d.name for d in pd.load_line_weights(s)] == [
            d.name for d in pd.DEFAULT_LINE_WEIGHTS]
    s.setValue("paper/line_weights", json.dumps([{"name": "Solo", "width_mm": .4}]))
    assert [d.name for d in pd.load_line_weights(s)] == ["Solo"]
