"""MW (linetypes.md "MW") -- weight data, mapping, migration, defaults.

Guards G4 (old-factory project untouched + template migration), G5 (defaults
and missing names by mm), G7 (Fixed linetypes decoupled), plus the mapping
half of G1. QSettings is isolated per test by conftest; the project table,
Thin Lines and the factor are reset per test (_reset_project_line_weights).
"""
import json

import pytest
from PyQt6.QtCore import QSettings

from firepro3d import paper_display as pd
from firepro3d.paper_display import LineWeightDef

_NEW = [("Thinnest", 0.18), ("Thinner", 0.25), ("Thin", 0.35),
        ("Thick", 0.50), ("Thickest", 0.70)]
_OLD = [("Very Light", 0.13), ("Light", 0.18), ("Medium", 0.25),
        ("Heavy", 0.35), ("Very Heavy", 0.50)]
_USER = [("Hair Line", 0.13), ("Very Light", 0.18), ("Light", 0.25),
         ("Medium", 0.35), ("Heavy", 0.50), ("Very Heavy", 0.70)]


def _defs(rows):
    return [LineWeightDef(n, mm) for n, mm in rows]


def _store_template(rows):
    QSettings("GV", "FirePro3D").setValue(
        "paper/line_weights",
        json.dumps([{"name": n, "width_mm": mm} for n, mm in rows]))


def test_factory_table_is_the_user_standard():
    assert [(d.name, d.width_mm) for d in pd.FACTORY_LINE_WEIGHTS] == _NEW


def test_model_px_round_trips_and_is_omitted_when_auto():
    pd.set_project_line_weights([LineWeightDef("Thin", 0.35, 3),
                                 LineWeightDef("Thick", 0.50)])
    saved = pd.get_paper_display_for_save()["line_weights"]
    assert saved == [{"name": "Thin", "width_mm": 0.35, "model_px": 3},
                     {"name": "Thick", "width_mm": 0.50}]
    pd.set_project_line_weights(_defs(_NEW))
    pd.apply_project_weights({"line_weights": saved})
    got = {d.name: d.model_px for d in pd.project_line_weights()}
    assert got == {"Thin": 3, "Thick": None}


def test_invalid_model_px_loads_as_auto():
    pd.apply_project_weights({"line_weights": [
        {"name": "A", "width_mm": 0.35, "model_px": 0},
        {"name": "B", "width_mm": 0.35, "model_px": 21},
        {"name": "C", "width_mm": 0.35, "model_px": "x"}]})
    assert all(d.model_px is None for d in pd.project_line_weights())


def test_g4_old_factory_project_table_untouched():
    pd.apply_project_weights({"line_weights": [
        {"name": n, "width_mm": mm} for n, mm in _OLD]})
    assert [(d.name, d.width_mm, d.model_px)
            for d in pd.project_line_weights()] == [(n, mm, None) for n, mm in _OLD]


def test_g4_old_factory_template_is_replaced_and_rewritten():
    _store_template(_OLD)
    assert [(d.name, d.width_mm) for d in pd.load_line_weights()] == _NEW
    raw = json.loads(QSettings("GV", "FirePro3D").value("paper/line_weights"))
    assert [(e["name"], e["width_mm"]) for e in raw] == _NEW


def test_g4_customised_template_is_kept():
    _store_template(_USER)
    assert [(d.name, d.width_mm) for d in pd.load_line_weights()] == _USER


def test_auto_rule_whole_px_round_half_up():
    pd.set_project_line_weights(_defs(_NEW))
    assert [pd.canvas_px_for_weight(n) for n, _ in _NEW] == [1, 2, 3, 4, 6]
    pd.set_model_weight_factor(6.0)
    # 1.08 -> 1, 1.5 -> 2 (half up), 2.1 -> 2, 3.0 -> 3, 4.2 -> 4
    assert [pd.canvas_px_for_weight(n) for n, _ in _NEW] == [1, 2, 2, 3, 4]


def test_override_wins_thin_lines_beats_override():
    pd.set_project_line_weights([LineWeightDef("Thin", 0.35, 5)])
    assert pd.canvas_px_for_weight("Thin") == 5
    pd.set_thin_lines(True)
    assert pd.canvas_px_for_weight("Thin") == 1


def test_factor_out_of_range_falls_back_to_factory():
    pd.set_model_weight_factor(99.0)
    assert pd.model_weight_factor() == 8.0
    pd.set_model_weight_factor("junk")
    assert pd.model_weight_factor() == 8.0


def test_g5_category_defaults_land_by_mm_new_factory():
    pd.set_project_line_weights(_defs(_NEW))
    cats = pd.factory_paper_categories()
    assert cats["Wall"]["line_weight"] == "Thin"          # 0.35
    assert cats["Pipe"]["line_weight"] == "Thinner"       # 0.25
    assert cats["Room"]["line_weight"] == "Thinnest"      # 0.13 -> nearest 0.18
    assert cats["Blocks"]["line_weight"] == "Thinnest"    # 0.18
    assert pd.model_blocks_weight() == "Thinnest"


def test_g5_category_defaults_land_by_mm_user_template():
    pd.set_project_line_weights(_defs(_USER))
    cats = pd.factory_paper_categories()
    assert cats["Wall"]["line_weight"] == "Medium"        # user's 0.35
    assert cats["Room"]["line_weight"] == "Hair Line"     # exact 0.13
    assert pd.model_blocks_weight() == "Very Light"       # user's 0.18


def test_g5_missing_factory_names_resolve_by_mm_both_ways():
    pd.set_project_line_weights(_defs(_OLD))
    assert pd.resolve_line_weight_mm("Thin") == 0.35       # new name, old table
    pd.set_project_line_weights(_defs(_NEW))
    assert pd.resolve_line_weight_mm("Heavy") == 0.35      # old name, new table
    assert pd.resolve_line_weight_mm("Very Light") == 0.18 # 0.13 -> nearest
    assert pd.resolve_line_weight_mm("Foo") == 0.25        # unknown


def test_g5_missing_name_takes_the_resolved_rows_override():
    pd.set_project_line_weights([*_defs([("Thinnest", 0.18), ("Thinner", 0.25)]),
                                 LineWeightDef("Thin", 0.35, 5)])
    assert pd.canvas_px_for_weight("Heavy") == 5           # old 0.35 -> Thin row


def test_g5_new_text_border_defaults_by_mm():
    from firepro3d.text_item import TextAnnotationData
    pd.set_project_line_weights(_defs(_USER))
    assert TextAnnotationData(text="x").border_weight == "Light"   # user's 0.25
    pd.set_project_line_weights(_defs(_NEW))
    assert TextAnnotationData(text="x").border_weight == "Thinner"
    assert TextAnnotationData.from_dict({"text": "x"}).border_weight == "Thinner"


def test_g7_fixed_dash_px_ignores_the_weight_factor(qapp):
    from PyQt6.QtCore import QRectF
    from tests.test_lts_canvas import _editor, _line, _render, _row, _inner
    ms, lid = _editor("fixed")
    _line(ms, lid, (0, 0), (200, 0))
    before = _inner(_row(_render(ms, QRectF(0, -1, 20, 2)), 20), True)
    pd.set_model_weight_factor(20.0)
    after = _inner(_row(_render(ms, QRectF(0, -1, 20, 2)), 20), True)
    assert before and before == after
    assert all(abs(n - 36) <= 2 for n in after)        # 6 mm x 6 px/mm


def test_fpdb_carries_overrides_and_project_wins(qapp, tmp_path):
    from firepro3d import block_library
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.model_space import Model_Space
    from firepro3d.text_item import TextAnnotationData, TextItem
    pd.set_project_line_weights([*_defs(_NEW), LineWeightDef("X40", 0.40, 7)])
    prim = TextItem(TextAnnotationData(text="X", border=True,
                                       border_weight="X40")).to_dict()
    d = BlockDefinition.new(name="Tag", library="Lib", series="S",
                            primitives=[prim], origin=(0.0, 0.0))
    path = block_library.save_to_library(d)
    with open(path, encoding="utf-8") as fh:
        rec = json.load(fh)
    assert rec["weights"] == {"X40": 0.40} and rec["weight_model_px"] == {"X40": 7}
    pd.set_project_line_weights(_defs(_NEW))
    Model_Space().load_blocks_from_files([path])
    assert {x.name: x.model_px for x in pd.project_line_weights()}["X40"] == 7


def test_factor_restored_on_startup(qapp, tmp_path, monkeypatch):
    import main as _main_module
    from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
    _main_module.View3D = View3D
    from main import MainWindow
    recovery = str(tmp_path / "recovery.FPD")   # a real recovery file can't pop a modal
    monkeypatch.setattr(MainWindow, "_autosave_path", staticmethod(lambda: recovery))
    QSettings("GV", "FirePro3D").setValue("view/model_weight_factor", 12.5)
    w = MainWindow()
    try:
        assert pd.model_weight_factor() == 12.5
    finally:
        w._modified = False
        w.close()
        w.deleteLater()


# -- MW-6 extended to the saved / applied current weight (2026-10-06 ruling)

def _store_current_weight(name):
    QSettings("GV", "FirePro3D").setValue("template/geometry/weight", name)


def test_mw6_saved_current_factory_name_maps_by_mm():
    from firepro3d import stroke_style as ss
    pd.set_project_line_weights(_defs(_NEW))
    _store_current_weight("Heavy")                     # old factory 0.35 mm
    ss.current_from_settings(QSettings("GV", "FirePro3D"))
    assert ss.current_style()["weight"] == "Thin"


def test_mw6_saved_current_unknown_name_is_by_linetype():
    from firepro3d import stroke_style as ss
    pd.set_project_line_weights(_defs(_NEW))
    _store_current_weight("Foo")
    ss.current_from_settings(QSettings("GV", "FirePro3D"))
    assert ss.current_style()["weight"] == ss.BY_LINETYPE


def test_mw6_applied_current_factory_name_maps_by_mm(qapp):
    from PyQt6.QtCore import QPointF
    from firepro3d import stroke_style as ss
    from firepro3d.geometry_2d import LineItem
    from firepro3d.model_space import Model_Space
    pd.set_project_line_weights(_defs(_NEW))
    ms = Model_Space()
    ln = LineItem(QPointF(0, 0), QPointF(100, 0))
    ms.addItem(ln)
    ss.set_current(weight="Heavy")
    ss.apply_current(ln, ms)
    assert ln.style["weight"] == "Thin"


def test_auto_rule_half_up_at_decimal_factor():
    # 1.16 x 12.5 = 14.5 and 2.28 x 12.5 = 28.5 exactly; float noise must
    # not round them down (MW-3 round-half-up).
    pd.set_model_weight_factor(12.5)
    assert pd.auto_model_px(1.16) == 15
    assert pd.auto_model_px(2.28) == 29
