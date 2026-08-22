from firepro3d import snap_engine
from firepro3d.preferences_dialog import PreferencesDialog, SettingsPane, SnappingPane, UnitsPane


class _StubPane(SettingsPane):
    def __init__(self):
        super().__init__("Stub")
        self.log = []

    def load(self):    self.log.append("load")
    def apply(self):   self.log.append("apply")
    def revert(self):  self.log.append("revert")


def test_dialog_loads_all_panes_on_open(qapp):
    p = _StubPane()
    dlg = PreferencesDialog(panes=[p])
    assert p.log == ["load"]


def test_apply_commits_all_panes(qapp):
    p = _StubPane()
    dlg = PreferencesDialog(panes=[p])
    dlg._apply_all()
    assert "apply" in p.log


def test_reject_reverts_all_panes(qapp):
    p = _StubPane()
    dlg = PreferencesDialog(panes=[p])
    dlg.reject()
    assert "revert" in p.log


def test_snapping_pane_apply_writes_engine(qapp, monkeypatch):
    monkeypatch.setattr(snap_engine, "SNAP_TOLERANCE_PX", 40, raising=False)
    pane = SnappingPane()
    pane.load()
    pane._tol_spin.setValue(12)
    pane.apply()
    assert snap_engine.SNAP_TOLERANCE_PX == 12


def test_snapping_pane_revert_restores(qapp, monkeypatch):
    monkeypatch.setattr(snap_engine, "SNAP_TOLERANCE_PX", 40, raising=False)
    pane = SnappingPane()
    pane.load()
    pane._tol_spin.setValue(5)
    pane.revert()
    assert snap_engine.SNAP_TOLERANCE_PX == 40


# ── Live-apply regression tests (Task D2 parity) ─────────────────────────────

class _StubEngine:
    def __init__(self):
        self.snap_endpoint      = True
        self.snap_midpoint      = True
        self.snap_intersection  = True
        self.snap_center        = True
        self.snap_quadrant      = True
        self.snap_nearest       = True
        self.snap_perpendicular = True
        self.snap_tangent       = True


class _StubScene:
    def __init__(self):
        self._snap_engine        = _StubEngine()
        self._grip_tolerance_px  = 200  # within spinbox range (100–1000)
        self._snap_angle_deg     = 45
        self._inference_enabled  = True
        self._inference          = True  # mirrors set_inference_enabled result

    def set_inference_enabled(self, v):
        self._inference_enabled = v
        self._inference = v


class _StubView:
    def __init__(self):
        self._grid_visible = True
        self._grid_size    = 100.0

    def set_grid(self, visible, size):
        self._grid_visible = visible
        self._grid_size    = size


def test_snapping_pane_applies_live_to_scene(qapp):
    """apply() must write directly to the live scene/engine objects."""
    scene = _StubScene()
    view  = _StubView()
    pane  = SnappingPane(scene=scene, view=view)
    pane.load()

    # Mutate widget state before apply (300 is within spinbox range 100–1000)
    pane._snap_cbs["snap_endpoint"].setChecked(False)
    pane._grip_spin.setValue(300)

    pane.apply()

    assert scene._snap_engine.snap_endpoint is False
    assert scene._grip_tolerance_px == 300


def test_snapping_pane_revert_restores_live(qapp):
    """revert() must roll back the live scene/engine to the load()-time snapshot."""
    scene = _StubScene()
    view  = _StubView()
    pane  = SnappingPane(scene=scene, view=view)
    pane.load()

    # Simulate a prior apply that changed live state (300 is within range 100–1000)
    pane._grip_spin.setValue(300)
    pane.apply()
    assert scene._grip_tolerance_px == 300  # sanity: apply worked

    pane.revert()
    assert scene._grip_tolerance_px == 200  # original snapshot value restored


# ── UnitsPane tests (Task D3) ─────────────────────────────────────────────────

def test_units_pane_persists_to_qsettings(qapp):
    pane = UnitsPane()
    pane.load()
    pane._precision_spin.setValue(3)
    pane.apply()
    from PyQt6.QtCore import QSettings
    assert int(QSettings("GV", "FirePro3D").value("display/precision", 2)) == 3


def test_units_pane_applies_live_precision(qapp):
    class _SM:
        def __init__(self):
            self.precision = 2
            self._display_unit = None

        @property
        def display_unit(self):
            return self._display_unit

        @display_unit.setter
        def display_unit(self, unit):
            self._display_unit = unit

    sm = _SM()
    pane = UnitsPane(scale_manager=sm)
    pane.load()
    pane._precision_spin.setValue(4)
    pane.apply()
    assert sm.precision == 4


def test_units_pane_applies_live_unit(qapp):
    """apply() must write the selected DisplayUnit to the live ScaleManager."""
    from firepro3d.scale_manager import DisplayUnit

    class _SM:
        def __init__(self):
            self._display_unit = DisplayUnit.METRIC_MM
            self.precision = 2

        @property
        def display_unit(self):
            return self._display_unit

        @display_unit.setter
        def display_unit(self, unit):
            self._display_unit = unit

    sm = _SM()
    pane = UnitsPane(scale_manager=sm)
    pane.load()
    # Select the IMPERIAL entry (index 0)
    pane._unit_combo.setCurrentIndex(0)
    pane.apply()
    assert sm.display_unit == DisplayUnit.IMPERIAL


def test_units_pane_persists_unit_to_qsettings(qapp):
    """apply() must persist the unit string value to QSettings display/unit."""
    from PyQt6.QtCore import QSettings
    pane = UnitsPane()
    pane.load()
    # Force METRIC_M (index 1) selection
    pane._unit_combo.setCurrentIndex(1)
    pane.apply()
    saved = QSettings("GV", "FirePro3D").value("display/unit")
    assert saved == "m"  # DisplayUnit.METRIC_M.value


def test_units_pane_revert_restores_live(qapp):
    """revert() must restore the scale manager to load()-time state."""
    from firepro3d.scale_manager import DisplayUnit

    class _SM:
        def __init__(self):
            self._display_unit = DisplayUnit.METRIC_MM
            self.precision = 2

        @property
        def display_unit(self):
            return self._display_unit

        @display_unit.setter
        def display_unit(self, unit):
            self._display_unit = unit

    sm = _SM()
    pane = UnitsPane(scale_manager=sm)
    pane.load()

    pane._precision_spin.setValue(5)
    pane._unit_combo.setCurrentIndex(0)  # IMPERIAL
    pane.apply()
    assert sm.precision == 5
    assert sm.display_unit == DisplayUnit.IMPERIAL

    pane.revert()
    assert sm.precision == 2
    assert sm.display_unit == DisplayUnit.METRIC_MM


def test_units_pane_on_changed_called(qapp):
    """apply() must fire on_changed callback."""
    called = []
    pane = UnitsPane(on_changed=lambda: called.append(1))
    pane.load()
    pane.apply()
    assert called == [1]


# ── ImportPane tests (Task D4) ────────────────────────────────────────────────

from firepro3d.preferences_dialog import ImportPane, GeneralPane
from PyQt6.QtCore import QSettings


def test_import_pane_persists_oda_path(qapp):
    pane = ImportPane()
    pane.load()
    pane._oda_edit.setText(r"C:\tools\ODAFileConverter.exe")
    pane.apply()
    assert QSettings("GV", "FirePro3D").value("dwg/oda_converter_path") == r"C:\tools\ODAFileConverter.exe"


def test_import_pane_revert_restores(qapp):
    pane = ImportPane()
    pane.load()
    original_path = pane._oda_edit.text()
    pane._oda_edit.setText(r"C:\changed\path.exe")
    pane.revert()
    assert pane._oda_edit.text() == original_path


# ── GeneralPane tests (Task D4) ───────────────────────────────────────────────

def test_general_pane_roundtrips_dock_default(qapp):
    pane = GeneralPane()
    pane.load()
    pane._dock_checks["browser"].setChecked(False)
    pane.apply()
    val = QSettings("GV", "FirePro3D").value("dock/browser")
    assert str(val).lower() in ("false", "0")


def test_general_pane_roundtrips_all_docks(qapp):
    pane = GeneralPane()
    pane.load()
    pane._dock_checks["browser"].setChecked(True)
    pane._dock_checks["properties"].setChecked(False)
    pane._dock_checks["hydraulics"].setChecked(True)
    pane._dock_checks["radiation"].setChecked(False)
    pane.apply()
    s = QSettings("GV", "FirePro3D")
    assert str(s.value("dock/browser")).lower() in ("true", "1")
    assert str(s.value("dock/properties")).lower() in ("false", "0")
    assert str(s.value("dock/hydraulics")).lower() in ("true", "1")
    assert str(s.value("dock/radiation")).lower() in ("false", "0")


def test_general_pane_revert_restores(qapp):
    pane = GeneralPane()
    pane.load()
    original_browser = pane._dock_checks["browser"].isChecked()
    pane._dock_checks["browser"].setChecked(not original_browser)
    pane.revert()
    assert pane._dock_checks["browser"].isChecked() == original_browser


# ── ProjectInfoPane tests (Task D5) ──────────────────────────────────────────

from firepro3d.preferences_dialog import ProjectInfoPane


def test_project_info_apply_calls_set_info(qapp):
    saved = {}
    def get_info(): return {"name": "Old"}
    def set_info(d): saved.update(d); saved["_called"] = True
    pane = ProjectInfoPane(get_info=get_info, set_info=set_info)
    pane.load()
    pane._set_field("name", "New")
    pane.apply()
    assert saved.get("_called") is True
    assert saved.get("name") == "New"


def test_project_info_revert_does_not_call_set_info(qapp):
    calls = []
    pane = ProjectInfoPane(get_info=lambda: {"name": "Old"},
                           set_info=lambda d: calls.append(d))
    pane.load()
    pane._set_field("name", "Changed")
    pane.revert()
    assert calls == []   # revert must not persist


def test_project_info_no_arg_construction(qapp):
    """No-arg construction must work — pane builds and loads empty."""
    pane = ProjectInfoPane()
    pane.load()
    pane.apply()   # must not raise even with no set_info


def test_project_info_revert_restores_widget(qapp):
    """revert() must restore the widget back to the load-time value."""
    pane = ProjectInfoPane(get_info=lambda: {"name": "Snapshot"})
    pane.load()
    pane._set_field("name", "Dirtied")
    pane.revert()
    assert pane._get_field("name") == "Snapshot"


def test_project_info_custom_rows_roundtrip(qapp):
    """Custom key/value rows survive an apply() round-trip."""
    initial = {
        "custom": [{"key": "Revision", "value": "A"}]
    }
    saved = {}
    pane = ProjectInfoPane(
        get_info=lambda: dict(initial),
        set_info=lambda d: saved.update(d),
    )
    pane.load()
    pane.apply()
    assert saved.get("custom") == [{"key": "Revision", "value": "A"}]


def test_project_info_all_standard_keys_present(qapp):
    """apply() must include all 11 standard keys in the dict passed to set_info."""
    _EXPECTED_KEYS = [
        "name", "number",
        "address1", "address2", "address3",
        "client", "client_address1", "client_address2", "client_address3",
        "designer", "description",
    ]
    saved = {}
    pane = ProjectInfoPane(
        get_info=lambda: {},
        set_info=lambda d: saved.update(d),
    )
    pane.load()
    pane.apply()
    for key in _EXPECTED_KEYS:
        assert key in saved, f"Missing key: {key}"
