"""tests/test_opening_ribbon.py — Architecture-tab Door/Window/Blank ribbon buttons (§7.6).

Verifies that the quick-access buttons on the Architecture tab enter the unified
"opening" placement mode with the correct default Feature id.

MainWindow construction mirrors ``test_dynamic_input_multiview.py``:
import View3D before MainWindow (heavy VTK import), create a module-scoped
singleton, and restore mutated module-globals on teardown.
"""

from __future__ import annotations

import pytest
from PyQt6.QtTest import QTest

from firepro3d import snap_engine

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import, must precede MainWindow()
_main_module.View3D = View3D
from main import MainWindow


@pytest.fixture(scope="module")
def _mw_singleton(qapp):
    """Module-scoped MainWindow shared across tests in this file."""
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    win._modified = False
    win.close()
    win.deleteLater()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


@pytest.fixture
def main_window(_mw_singleton):
    """Per-test wrapper: reset to select mode before and after each test."""
    win = _mw_singleton
    win.scene.set_mode("select")
    yield win
    win.scene.set_mode("select")


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_door_button_enters_opening_mode_with_door_feature(qapp, main_window):
    mw = main_window
    mw._mode_buttons["door"].click()
    assert mw.scene.mode == "opening"
    assert mw.scene._opening_feature_id.startswith("door")


def test_window_button_enters_opening_mode_with_window_feature(qapp, main_window):
    mw = main_window
    mw._mode_buttons["window"].click()
    assert mw.scene.mode == "opening"
    assert mw.scene._opening_feature_id.startswith("window")


def test_blank_button_exists_in_mode_buttons(qapp, main_window):
    mw = main_window
    assert "blank" in mw._mode_buttons


def test_blank_button_enters_opening_mode(qapp, main_window):
    mw = main_window
    assert "blank" in mw._mode_buttons          # new Blank Opening button exists
    mw._mode_buttons["blank"].click()
    assert mw.scene.mode == "opening"
    assert mw.scene._opening_feature_id == "blank_900"


def test_opening_template_surfaces_in_panel_on_mode_entry(qapp, main_window):
    """Entering opening mode via the ribbon emits the WallOpening template to the
    property panel so the user can edit Sill/size BEFORE placing (§7.6)."""
    from firepro3d.wall_opening import WallOpening

    mw = main_window
    captured = []
    mw.scene.requestPropertyUpdate.connect(captured.append)
    mw._mode_buttons["door"].click()
    assert any(isinstance(t, WallOpening) for t in captured), \
        "template not surfaced to panel"
    # The surfaced object is the persistent template (last-used-defaults home).
    assert mw.current_opening_template in captured


def test_template_feature_enum_present_no_wall(qapp, main_window):
    """A wall=None template exposes an editable Feature enum + Sill, no Level/warning."""
    mw = main_window
    props = mw.current_opening_template.get_properties()
    assert "Feature" in props and props["Feature"]["type"] == "enum"
    assert "Sill Height" in props
    assert "Level" not in props          # no wall context on a template
    assert "Fit Warning" not in props


def test_template_sill_edit_applies_to_placed_opening(qapp, main_window):
    """Editing the template's Sill BEFORE placing must reach the placed opening.

    Drives the real placement entry (_press_opening) after entering opening mode
    through the ribbon button, proving panel→template→placement is closed.
    """
    from firepro3d.wall import WallSegment
    from PyQt6.QtCore import QPointF

    mw = main_window
    # Author a window feature + a non-default sill on the persistent template.
    mw.current_opening_template.apply_feature("window_900")
    mw.current_opening_template.set_property("Sill Height", 1234.0)   # mm
    mw._mode_buttons["window"].click()   # enters opening mode carrying the template
    # Button re-applies the last-used feature only when it CHANGES; window is
    # already selected, so the edited sill must survive. Re-assert defensively.
    assert mw.current_opening_template.sill_mm == 1234.0

    w = WallSegment(QPointF(0, 0), QPointF(2000, 0), thickness_mm=200.0)
    mw.scene.addItem(w); mw.scene._walls.append(w)

    snapped = QPointF(1000, 0)
    mw.scene._press_opening(None, snapped, snapped, None, None, None)
    assert len(w.openings) == 1
    assert w.openings[0].sill_mm == 1234.0, \
        "template sill did not reach the placed opening"


def test_wall_opening_maps_to_opening_family(qapp, main_window):
    """§7.15: _family_key_for must resolve WallOpening → 'opening' (contextual tab key)."""
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import WallOpening
    from PyQt6.QtCore import QPointF

    mw = main_window
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    op = WallOpening(wall=w, feature_id="door_914", offset_along=500.0)
    assert mw._family_key_for(op) == "opening"


def test_startup_panel_defaults(qapp, main_window):
    """Startup panel defaults are FIXED (not persisted from the previous
    session): Project Browser + Properties open, Hydraulic Report closed.
    restore_settings() forces these regardless of saved dock/* values."""
    mw = main_window
    assert mw.browser_dock.isVisible() is True
    assert mw.prop_dock.isVisible() is True
    assert mw.hydro_dock.isVisible() is False
