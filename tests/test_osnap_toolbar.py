"""Unit tests for the inline footer osnap bar (FooterRail.InlineOsnapBar).

Replaces the retired dockable ``_SnapToolbar`` (chrome revamp). The 8
``SnapEngine.snap_*`` booleans remain the single source of truth; the bar
reads/writes them and persists each under the ``snap/{attr}`` QSettings key
(isolated per-test by conftest's ``_IsolatedQSettings``). The master SNAP
pill's dim-when-off behaviour is exercised via ``FooterRail.set_snap_on``.
Reuses the session-scoped ``qapp`` fixture from tests/conftest.py.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QSettings

from firepro3d.snap_engine import SnapEngine, SNAP_MARKERS
from firepro3d.footer_rail import FooterRail, InlineOsnapBar

_ALL_ATTRS = [
    "snap_endpoint", "snap_midpoint", "snap_intersection", "snap_center",
    "snap_quadrant", "snap_nearest", "snap_perpendicular", "snap_tangent",
]


@pytest.fixture
def bar(qapp):
    """A fresh InlineOsnapBar wired to an isolated SnapEngine."""
    engine = SnapEngine()
    b = InlineOsnapBar(snap_engine_obj=engine)
    yield b, engine
    b.deleteLater()


def test_toggle_updates_engine(bar):
    b, engine = bar
    assert engine.snap_endpoint is True
    b._toggles["snap_endpoint"].setChecked(False)   # drive the widget
    assert engine.snap_endpoint is False
    b._toggles["snap_endpoint"].setChecked(True)
    assert engine.snap_endpoint is True


def test_toggle_persists_to_qsettings(bar):
    b, _engine = bar
    b._toggles["snap_midpoint"].setChecked(False)
    assert QSettings("GV", "FirePro3D").value("snap/snap_midpoint", type=bool) is False
    b._toggles["snap_midpoint"].setChecked(True)
    assert QSettings("GV", "FirePro3D").value("snap/snap_midpoint", type=bool) is True


def test_set_osnap_updates_engine_and_widget(bar):
    b, engine = bar
    b.set_osnap("snap_tangent", False)
    assert engine.snap_tangent is False
    assert b._toggles["snap_tangent"].isChecked() is False


def test_refresh_from_engine(bar):
    b, engine = bar
    engine.snap_center = False  # mutate engine directly
    b.refresh_from_engine()
    assert b._toggles["snap_center"].isChecked() is False
    # refresh must not write back to the engine
    assert engine.snap_center is False


def test_marker_keys_match_snap_markers(bar):
    b, _engine = bar
    assert b.marker_keys() == list(SNAP_MARKERS.keys())
    assert list(SNAP_MARKERS.keys()) == [k[len("snap_"):] for k in _ALL_ATTRS]


def test_master_snap_off_dims_the_bar(qapp):
    """SNAP master-off dims (disables) the whole osnap bar (F3 parity)."""
    rail = FooterRail(snap_engine_obj=SnapEngine())
    rail.set_snap_on(False)
    assert rail.osnap_bar.isEnabled() is False
    rail.set_snap_on(True)
    assert rail.osnap_bar.isEnabled() is True
