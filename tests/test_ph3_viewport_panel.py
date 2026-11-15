"""PH3 AC5 / DD5 / R6: the viewport Phasing + Show rows (D-PH8) on plan / detail /
elevation / section viewports, never schematic; one undo step each; saved.

Raw sources: status names / order = phase_registry.factory_statuses() (D-PH10 built-ins);
the undo text = ChangeViewportPropertiesCommand ("Edit Viewport", paper_commands.py).
"""
import pytest
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d import phase_registry as pr
from firepro3d.constants import PHASE_DEMOLITION
from firepro3d.paper_space import Sheet, SheetViewData, ViewportProperties
from firepro3d.phase_display import PhaseDisplay
from tests import _ph1_helpers as h
from tests._ph1_helpers import ph1_cleanup  # noqa: F401  (autouse: ends every scene)
from tests._ph3_helpers import make_viewport
from tests.test_sb4f_data import panels  # noqa: F401  (shown panels, closed at teardown)
from tests.test_sv2_viewport import _place, env  # noqa: F401  (a real schematic viewport)

SHOW_ROWS = [f"Show {r['name']}" for r in pr.factory_statuses()]   # registry order


@pytest.mark.parametrize("kind", ["plan", "detail", "elevation", "section"])
def test_ac5_phasing_row_on_every_sheet_view_kind_show_rows_only_while_on(qapp, kind):
    ms = h.scene()
    ps, vp = make_viewport(ms, kind=kind)
    props = ViewportProperties(ps, vp).get_properties()
    assert props["Phasing"] == {"type": "bool", "value": False}
    assert not [k for k in props if k in SHOW_ROWS]                 # R6: hidden while off
    ViewportProperties(ps, vp).set_property("Phasing", True)
    props = ViewportProperties(ps, vp).get_properties()
    assert list(props)[-4:] == ["Phasing", *SHOW_ROWS]
    assert all(props[k] == {"type": "bool", "value": True} for k in SHOW_ROWS)


def test_ac5_no_phasing_rows_on_a_schematic_viewport(env):
    vp = _place(env)
    vp.data.phase_display = PhaseDisplay(enabled=True)     # even a stored one (design edge case)
    props = ViewportProperties(env["ps"], vp).get_properties()
    assert "Phasing" not in props
    assert not [k for k in props if k in SHOW_ROWS]


def test_ac5_each_tick_is_one_undo_step(qapp):
    ms = h.scene()
    ps, vp = make_viewport(ms)
    vpp = ViewportProperties(ps, vp)
    n = ps.undo_stack.count()
    vpp.set_property("Phasing", True)
    vpp.set_property(SHOW_ROWS[2], False)                   # "Show Demolition"
    assert vp.data.phase_display == PhaseDisplay(True, frozenset({PHASE_DEMOLITION}))
    assert ps.undo_stack.count() == n + 2
    assert ps.undo_stack.command(n).text() == "Edit Viewport"
    ps.undo_stack.undo()
    assert vp.data.phase_display == PhaseDisplay(True, frozenset())
    ps.undo_stack.undo()
    assert vp.data.phase_display == PhaseDisplay()


def test_ac5_phase_display_is_saved_and_a_legacy_record_loads_off(qapp):
    d = SheetViewData("plan", "Plan: Level 1", "T", 0.01, 0.0, 0.0, 10.0, 10.0,
                      phase_display=PhaseDisplay(True, frozenset({PHASE_DEMOLITION})))
    sheet = Sheet.create_default()
    sheet.sheet_views = [d]
    back = Sheet.from_dict(sheet.to_dict()).sheet_views[0]
    assert back.phase_display == d.phase_display
    rec = d.to_dict()
    assert rec["phase_display"] == {"enabled": True, "hidden": [PHASE_DEMOLITION]}
    del rec["phase_display"]                                  # saved before phasing (D-PH6)
    assert SheetViewData.from_dict(rec).phase_display == PhaseDisplay()


def test_ac5_panel_rows_drive_the_viewport_through_the_property_panel(qapp, panels,
                                                                     monkeypatch):
    from firepro3d.paper_space import SheetViewport
    from firepro3d.property_manager import PropertyManager
    ms = h.scene()
    ps, vp = make_viewport(ms)
    dirty = []
    monkeypatch.setattr(SheetViewport, "mark_dirty", lambda self: dirty.append(self))
    pm = PropertyManager()
    panels.append(pm)
    pm.resize(400, 600)
    pm.show()
    QTest.qWaitForWindowExposed(pm)
    pm.show_properties(ViewportProperties(ps, vp))
    QApplication.processEvents()
    assert not [k for k in pm._prop_widgets if k in SHOW_ROWS]
    pm._prop_widgets["Phasing"].click()
    QTest.qWait(300)                                          # past the debounced refresh
    assert vp.data.phase_display.enabled
    assert vp in dirty                                        # the viewport repaint was asked
    assert all(k in pm._prop_widgets for k in SHOW_ROWS)
    pm._prop_widgets[SHOW_ROWS[2]].click()                    # Show Demolition off
    QTest.qWait(300)
    assert vp.data.phase_display.hidden == frozenset({PHASE_DEMOLITION})
    ps.undo_stack.undo()
    ps.undo_stack.undo()
    assert vp.data.phase_display == PhaseDisplay()
