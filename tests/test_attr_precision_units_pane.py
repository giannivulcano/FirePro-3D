"""Project Settings > Units & Precision: Pressure / Flow / Velocity
precision rows (text-sizing-wrap design D9; AC7)."""
from firepro3d.scale_manager import ScaleManager
from firepro3d.settings.panes import UnitsPane

_HYD = ("pressure_precision", "flow_precision", "velocity_precision")


def _values(pane):
    return [pane._hydraulic_spins[a].value() for a in _HYD]


def test_units_pane_has_the_three_hydraulic_rows(qapp):
    pane = UnitsPane(scale_manager=ScaleManager())
    labels = []
    for a in _HYD:
        spin = pane._hydraulic_spins[a]
        labels.append(spin.parentWidget().layout().labelForField(spin).text())
        assert (spin.minimum(), spin.maximum(), spin.suffix()) == (0, 5, " decimal places")
    assert labels == ["Pressure precision:", "Flow precision:", "Velocity precision:"]


def test_units_pane_loads_applies_and_reverts_hydraulic_precision(qapp):
    sm = ScaleManager()
    fired = []
    pane = UnitsPane(scale_manager=sm, on_changed=lambda: fired.append(1))
    pane.load()
    assert _values(pane) == [1, 0, 1]                 # defaults: today's formats
    for a, v in zip(_HYD, (2, 1, 3)):
        pane._hydraulic_spins[a].setValue(v)
    pane.apply()
    assert (sm.pressure_precision, sm.flow_precision, sm.velocity_precision) == (2, 1, 3)
    assert sm.format_pressure(12.34) == "12.34 psi"
    assert fired == [1]
    pane.revert()
    assert (sm.pressure_precision, sm.flow_precision, sm.velocity_precision) == (1, 0, 1)
    assert _values(pane) == [1, 0, 1]


def test_units_pane_without_a_manager_shows_the_defaults(qapp):
    pane = UnitsPane()
    pane.load()
    assert _values(pane) == [1, 0, 1]
    pane.apply()                                       # no live object: must not raise
