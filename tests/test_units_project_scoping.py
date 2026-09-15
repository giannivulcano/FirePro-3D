"""Tests: units are project-scoped (not written to / restored from QSettings).

Part of U5 Leg B — settings dialog phase.
"""
import pytest


def test_unitspane_apply_does_not_write_qsettings(qapp, model_scene, tmp_settings, monkeypatch):
    import firepro3d.settings.panes as panes
    monkeypatch.setattr(panes, "QSettings", lambda *a, **k: tmp_settings)
    from firepro3d.settings.panes import UnitsPane
    scene = model_scene()
    p = UnitsPane(scale_manager=scene.scale_manager)
    p.load(); p._precision_spin.setValue(4); p.apply()
    assert scene.scale_manager.precision == 4          # live write kept
    assert tmp_settings.value("display/precision", None) is None   # NOT persisted


def test_unitspane_apply_fires_on_changed(qapp, model_scene):
    from firepro3d.settings.panes import UnitsPane
    scene = model_scene(); fired = {"n": 0}
    p = UnitsPane(scale_manager=scene.scale_manager, on_changed=lambda: fired.__setitem__("n", fired["n"]+1))
    p.load(); p._precision_spin.setValue(1); p.apply()
    assert fired["n"] == 1


def test_units_round_trip_through_fpd(qapp, model_scene, tmp_path):
    from firepro3d.scale_manager import DisplayUnit
    scene = model_scene(); scene.scale_manager.display_unit = DisplayUnit("m")
    proj = str(tmp_path / "p.fpd"); scene.save_to_file(proj)
    scene2 = model_scene(); scene2.load_from_file(proj)
    assert scene2.scale_manager.display_unit == DisplayUnit("m")


def test_legacy_fpd_without_scale_falls_back(qapp, model_scene, tmp_path):
    import json
    proj = str(tmp_path / "legacy.fpd")
    json.dump({"version": 1, "nodes": [], "pipes": []}, open(proj, "w"))
    scene = model_scene(); scene.load_from_file(proj)   # must not raise
    assert scene.scale_manager is not None
