"""LW-DC T4 -- one-time app-settings migration (LW-DC-9).

Uses an isolated IniFormat QSettings (tmp_path); never the user's settings.
Expected names / mm are hand-written from the LW-DC-1 / MW-4 tables.
"""
import json

import pytest
from PyQt6.QtCore import QSettings

from firepro3d import paper_display as pd

_MW = [("Thinnest", .18), ("Thinner", .25), ("Thin", .35), ("Thick", .50), ("Thickest", .70)]


@pytest.fixture
def st(tmp_path):
    return QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)


def _template(st, rows):
    st.setValue("paper/line_weights",
                json.dumps([{"name": n, "width_mm": mm} for n, mm in rows]))


def _seed(st):
    st.setValue("paper/categories/Wall/line_weight", "Thin")
    st.setValue("display/Blocks/line_weight", "Thinnest")
    st.setValue("display/Blocks/default_line_weight", "Thinner")
    st.setValue("template/geometry/weight", "Thick")


def test_mw_settings_merge_by_width_and_second_call_is_noop(st):
    _template(st, _MW)
    _seed(st)
    assert pd.migrate_settings_weights(st) is True
    assert st.value("paper/categories/Wall/line_weight") == "Medium"
    assert pd.resolve_line_weight_mm("Medium", st) == pytest.approx(.35)
    assert st.value("display/Blocks/line_weight") == "Thin"
    assert pd.resolve_line_weight_mm("Thin", st) == pytest.approx(.18)
    assert st.value("display/Blocks/default_line_weight") == "Fine"          # .25
    assert st.value("template/geometry/weight") == "Wide"
    assert pd.resolve_line_weight_mm("Wide", st) == pytest.approx(.50)
    assert int(st.value("paper/line_weight_schema")) == 2
    tmpl = json.loads(st.value("paper/line_weights"))
    assert [e["name"] for e in tmpl] == [d.name for d in pd.DEFAULT_LINE_WEIGHTS]
    snap = {k: st.value(k) for k in st.allKeys()}
    assert pd.migrate_settings_weights(st) is False
    assert {k: st.value(k) for k in st.allKeys()} == snap


def test_no_template_stored_uses_the_static_map(st):
    """No template: the old factory was the MW table, so 'Thin' meant .35."""
    st.setValue("paper/categories/Wall/line_weight", "Thin")
    st.setValue("paper/categories/Pipe/line_weight", "Light")
    assert pd.migrate_settings_weights(st)
    assert st.value("paper/categories/Wall/line_weight") == "Medium"
    assert st.value("paper/categories/Pipe/line_weight") == "Thin"           # Light .18
    assert st.value("paper/line_weights") is None                            # nothing invented


def test_custom_template_thin_clash_becomes_thin_old_at_030(st):
    _template(st, [("Thin", .30)])
    st.setValue("paper/categories/Wall/line_weight", "Thin")
    assert pd.migrate_settings_weights(st)
    assert st.value("paper/categories/Wall/line_weight") == "Thin (old)"
    assert pd.resolve_line_weight_mm("Thin (old)", st) == pytest.approx(.30)
    assert pd.resolve_line_weight_mm("Thin", st) == pytest.approx(.18)       # the Default


def test_keyword_and_unrelated_values_are_untouched(st):
    _template(st, _MW)
    st.setValue("template/geometry/weight", "by_linetype")
    st.setValue("paper/categories/Wall/line_weight", "Nope")
    assert pd.migrate_settings_weights(st)
    assert st.value("template/geometry/weight") == "by_linetype"
    assert st.value("paper/categories/Wall/line_weight") == "Nope"


def test_mainwindow_runs_it_once_before_restore(qapp, monkeypatch):
    """The real entry point: constructing MainWindow migrates the app
    settings (a stored MW 'Thin' Wall weight prints 0.35 still)."""
    import main as _m
    from firepro3d.view_3d import View3D
    _m.View3D = View3D
    from tests._mainwindow_helpers import dispose_main_window
    s = QSettings("GV", "FirePro3D")
    s.setValue("paper/categories/Wall/line_weight", "Thin")
    s.setValue("paper/line_weights", json.dumps(
        [{"name": n, "width_mm": mm} for n, mm in _MW]))
    s.remove("paper/line_weight_schema")
    monkeypatch.setattr(_m.MainWindow, "_maybe_offer_template_push", lambda self: None)
    w = _m.MainWindow()
    try:
        s2 = QSettings("GV", "FirePro3D")
        assert s2.value("paper/categories/Wall/line_weight") == "Medium"
        assert pd.resolve_line_weight_mm("Medium", s2) == pytest.approx(.35)
        assert int(s2.value("paper/line_weight_schema")) == 2
    finally:
        dispose_main_window(w)


def test_f6_template_read_before_the_migration_does_not_hide_old_names(st):
    """Any load_line_weights() before migrate_settings_weights (the template
    read by a lazy project seed, a DM, a test) used to rewrite an untouched MW
    template to Defaults, so stored "Thin" (0.35 mm) then mapped to itself."""
    _template(st, _MW)
    st.setValue("paper/categories/Wall/line_weight", "Thin")
    raw_thin_mm = {n: mm for n, mm in _MW}["Thin"]                    # 0.35
    pd.load_line_weights(st)                  # the order hazard, before migration
    pd.migrate_settings_weights(st)
    wall = st.value("paper/categories/Wall/line_weight")
    assert pd.resolve_line_weight_mm(wall, st) == pytest.approx(raw_thin_mm)
    assert wall == "Medium"
