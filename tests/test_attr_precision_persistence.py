"""Attribute override + project hydraulic precision through .fpd save / load;
an old file moves nothing (text-sizing-wrap design D8 / D9; AC7)."""
import json

from firepro3d.model_space import Model_Space
from tests.test_attr_precision_e2e import _edit, _label_block
from tests.test_sb4a_pipe_label import _scene

_HYD = ("pressure_precision", "flow_precision", "velocity_precision")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_override_and_project_precision_survive_save_and_load(qapp, tmp_path):
    ms = _scene()
    ms.scale_manager.pressure_precision = 2
    w, defn = _label_block(ms)
    _edit(w, [(1, "unit", "mm"), (1, "precision", "2")])
    path = str(tmp_path / "p.fpd")
    assert ms.save_to_file(path)
    scale = _read(path)["scale"]
    assert scale["pressure_precision"] == 2
    assert "flow_precision" not in scale and "velocity_precision" not in scale
    ms2 = Model_Space()
    ms2.load_from_file(path)
    sm2 = ms2.scale_manager
    assert (sm2.pressure_precision, sm2.flow_precision, sm2.velocity_precision) == (2, 0, 1)
    recs = ms2.get_block_definition(defn.id).attributes
    assert (recs[1]["unit"], recs[1]["display_precision"], recs[1]["precision"]) == ("mm", 2, 0)
    assert "unit" not in recs[0] and "display_precision" not in recs[0]


def test_default_project_writes_no_new_keys_and_old_files_load_unchanged(qapp, tmp_path):
    ms = _scene()
    path = str(tmp_path / "d.fpd")
    assert ms.save_to_file(path)
    assert not set(_HYD) & set(_read(path)["scale"])
    legacy = tmp_path / "legacy.fpd"
    legacy.write_text(json.dumps({"version": 1, "nodes": [], "pipes": [],
                                  "scale": {"display_unit": "imperial", "precision": 3}}),
                      encoding="utf-8")
    ms2 = Model_Space()
    ms2.load_from_file(str(legacy))
    sm = ms2.scale_manager
    assert (sm.pressure_precision, sm.flow_precision, sm.velocity_precision) == (1, 0, 1)
    assert (sm.format_pressure(16.04), sm.format_flow(22.4),
            sm.format_velocity(5.56)) == ("16.0 psi", "22 gpm", "5.6 ft/s")
