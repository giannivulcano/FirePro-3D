"""Block Editor X / Y axes as NEA / PER snap targets (snapping-engine s4.2) and
their Auto Constrain records (parametric-constraint-system s13).

Real path: a shown Model_View over a real ``block_editor`` Model_Space, posted
mouse events (cursor snap via get_effective_position -> find()). Ground truth:
the published snap, the recorded constraints, where geometry lands, pixels.
"""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF, QSettings, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d import auto_constrain as ac
from firepro3d.constants import AUTO_CONSTRAIN_KEY
from firepro3d.geometry_2d import LineItem
from firepro3d.snap_engine import SNAP_COLORS, OsnapResult, snap_tangent_deg
from tests._snap_polish_helpers import click, close_view, drag, make_view, move

NONE = Qt.KeyboardModifier.NoModifier


@pytest.fixture
def vs(qapp):
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, True)
    view, sc = make_view(role="block_editor", scale=1.0, mode=None)
    sc.set_align_enabled(False)
    yield view, sc
    QSettings("GV", "FirePro3D").remove(AUTO_CONSTRAIN_KEY)
    close_view(view, sc)


def _find(view, sc, x, y, from_point=None):
    return sc._snap_engine.find(QPointF(x, y), sc, view.transform(),
                                from_point=from_point)


def _xy(p):
    return (round(p.x(), 6), round(p.y(), 6))


# ── Task 1: engine ───────────────────────────────────────────────────────

def test_nearest_on_x_axis_away_from_origin(vs):
    view, sc = vs
    r = _find(view, sc, 200, 6)                 # 6 px off the X axis, 200 px from (0,0)
    assert r is not None and r.snap_type == "nearest"
    assert _xy(r.point) == (200.0, 0.0)
    assert r.name == "x_axis" and r.source_item is None


def test_nearest_on_y_axis(vs):
    view, sc = vs
    r = _find(view, sc, -7, -150)
    assert (r.snap_type, r.name, _xy(r.point)) == ("nearest", "y_axis", (0.0, -150.0))


def test_perpendicular_from_start_onto_x_axis(vs):
    view, sc = vs
    # NEA foot (125, 0) at 3 px (prio 7); PER foot from (120, 200) = (120, 0) at
    # hypot(5, 3) = 5.83 px (prio 4) -> within the 12 px band PER wins.
    r = _find(view, sc, 125, 3, from_point=QPointF(120, 200))
    assert (r.snap_type, r.name, _xy(r.point)) == ("perpendicular", "x_axis", (120.0, 0.0))


@pytest.mark.parametrize("dy", [0.0, -1e-7])
def test_geometry_on_the_axis_keeps_the_snap(vs, dy):
    """dy = -1e-7: float noise puts the line a hair off the axis, on the far side
    from the cursor, so the axis foot is strictly closer -- the line still wins."""
    view, sc = vs
    ln = LineItem(QPointF(0, dy), QPointF(300, dy)); sc.addItem(ln); sc._draw_lines.append(ln)
    r = _find(view, sc, 77, 4)
    assert r.source_item is ln and r.snap_type == "nearest" and _xy(r.point) == (77.0, 0.0)


def test_nearest_toggle_off_drops_the_axis_foot(vs):
    view, sc = vs
    sc._snap_engine.snap_nearest = False
    assert _find(view, sc, 200, 6) is None


def test_plan_scene_has_no_axis_snap(qapp):
    view, sc = make_view(role="plan", scale=1.0, mode=None)
    try:
        assert _find(view, sc, 200, 6) is None
    finally:
        close_view(view, sc)


def test_axis_marker_lies_along_the_axis(vs):
    view, sc = vs
    assert snap_tangent_deg(_find(view, sc, 200, 6)) == pytest.approx(0.0)
    assert snap_tangent_deg(_find(view, sc, -7, -150)) == pytest.approx(90.0)
