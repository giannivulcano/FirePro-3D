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
