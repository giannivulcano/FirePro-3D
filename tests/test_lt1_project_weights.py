"""LT1 guard T3 — the named-weight table is project-scoped (linetypes.md LT1-3)."""
import json

from PyQt6.QtCore import QSettings

from firepro3d import paper_display as pd
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import LineWeightDef


def _template(defs):
    pd.save_line_weights(defs)            # the QSettings template


def _names_widths(defs):
    return [(d.name, round(d.width_mm, 3)) for d in defs]


def test_project_table_seeds_from_template(qapp):
    _template([LineWeightDef("T1", 0.11), LineWeightDef("T2", 0.22)])
    pd._PROJECT_LW = None
    assert _names_widths(pd.project_line_weights()) == [("T1", 0.11), ("T2", 0.22)]
    assert pd.resolve_line_weight_mm("T2") == 0.22


def test_fpd_round_trip_and_open_never_writes_qsettings(qapp, tmp_path):
    ms = Model_Space()
    pd.set_project_line_weights([*pd.FACTORY_LINE_WEIGHTS,
                                 LineWeightDef("Site", 0.40)])
    path = str(tmp_path / "w.fpd")
    ms.save_to_file(path)
    on_disk = json.load(open(path, encoding="utf-8"))["paper_display"]["line_weights"]
    assert {"name": "Site", "width_mm": 0.40} in on_disk

    _template([LineWeightDef("Other", 0.9)])            # template differs
    before = QSettings("GV", "FirePro3D").value("paper/line_weights")
    pd.set_project_line_weights([LineWeightDef("Junk", 1.0)])

    ms2 = Model_Space()
    ms2.load_from_file(path)
    pd.apply_paper_display_from_project(ms2._loaded_paper_display)   # main._load_project path
    assert pd.resolve_line_weight_mm("Site") == 0.40
    assert "Junk" not in pd.weight_names()
    assert QSettings("GV", "FirePro3D").value("paper/line_weights") == before


def test_old_file_without_table_copies_template(qapp):
    _template([LineWeightDef("Tmpl", 0.33)])
    pd.set_project_line_weights([LineWeightDef("Stale", 1.0)])
    pd.apply_paper_display_from_project({"color_mode": "bw", "categories": {}})
    assert pd.weight_names() == ["Tmpl"]
    pd.set_project_line_weights([LineWeightDef("Stale", 1.0)])
    pd.apply_paper_display_from_project(None)            # no paper_display at all
    assert pd.weight_names() == ["Tmpl"]


def test_reset_project_line_weights_copies_template(qapp):
    _template([LineWeightDef("N1", 0.5)])
    pd.set_project_line_weights([LineWeightDef("Old", 0.1)])
    pd.reset_project_line_weights()
    assert pd.weight_names() == ["N1"]


def test_weight_names_sorted_by_width(qapp):
    pd.set_project_line_weights([LineWeightDef("B", 0.5), LineWeightDef("A", 0.1)])
    assert pd.weight_names() == ["A", "B"]


def test_set_project_line_weights_clears_hatch_cache(qapp):
    pd.set_project_line_weights(list(pd.FACTORY_LINE_WEIGHTS))
    first = pd.hatch_line_mm()
    pd.set_project_line_weights([LineWeightDef(n.name, n.width_mm * 2)
                                 for n in pd.FACTORY_LINE_WEIGHTS])
    assert pd.hatch_line_mm() == first * 2
