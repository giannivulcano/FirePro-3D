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


# ── Task 2: Auto Constrain ───────────────────────────────────────────────

def _recs(sc):
    return [(c.type, [(r.get("uid"), r.get("h"), r.get("ref")) for r in c.refs])
            for c in sc.constraint_ctl.constraints]


def _draw(view, sc, a, b):
    sc.set_mode("draw_line")
    move(view, QPointF(*a)); click(view, QPointF(*a))
    move(view, QPointF(*b)); click(view, QPointF(*b))
    return sc._draw_lines[-1]


def _key(view, key):
    view.setFocus()
    QTest.keyClick(view.viewport(), key)
    QApplication.processEvents()


def test_resolve_snap_maps_an_axis_to_its_ground_edge():
    t = ac.resolve_snap(OsnapResult(QPointF(200, 0), "nearest", name="x_axis"))
    assert t == ac.Target("edge", {"ref": "x_axis"}, (200.0, 0.0))
    p = ac.resolve_snap(OsnapResult(QPointF(0, 50), "perpendicular", name="y_axis"))
    assert p == ac.Target("edge", {"ref": "y_axis"}, (0.0, 50.0), perpendicular=False)
    assert ac.resolve_snap(OsnapResult(QPointF(3, 4), "nearest")) is None


def test_line_end_on_x_axis_records_point_on_axis(vs):
    view, sc = vs
    # (230, 4): NEA foot (230, 0) at 4 px; the PER foot from (150, 200) is
    # (150, 0), 80 px away (outside the 15 px aperture) -> NEA.
    n = _draw(view, sc, (150, 200), (230, 4))
    assert _xy(n.grip_points()[2]) == (230.0, 0.0)
    assert _recs(sc) == [("point_on_curve", [(n._uid, "p2", None), (None, None, "x_axis")])]


def test_recorded_axis_relation_holds_under_a_grip_drag(vs):
    view, sc = vs
    n = _draw(view, sc, (150, 200), (230, 4))
    sc.set_mode("select"); sc.clearSelection(); n.setSelected(True)
    QApplication.processEvents()
    drag(view, QPointF(230, 0), QPointF(230, -150))   # 150 px off any snap
    assert n.grip_points()[2].y() == pytest.approx(0.0, abs=1e-6)


def test_per_onto_y_axis_records_point_on_axis_and_horizontal_only(vs):
    view, sc = vs
    # From (150, 200): PER foot on the Y axis (0, 200) at hypot(3, 4) = 5 px
    # (prio 4) beats the NEA foot (0, 196) at 3 px (prio 7) inside the band.
    n = _draw(view, sc, (150, 200), (3, 196))
    assert _xy(n.grip_points()[2]) == (0.0, 200.0)
    assert _recs(sc) == [
        ("point_on_curve", [(n._uid, "p2", None), (None, None, "y_axis")]),
        ("horizontal", [(n._uid, "edge", None)])]


def test_polyline_vertex_on_axis_records_at_finish(vs):
    view, sc = vs
    sc.set_mode("polyline")
    for p in ((150, 200), (260, 5), (330, 180)):
        move(view, QPointF(*p)); click(view, QPointF(*p))
    _key(view, Qt.Key.Key_Return)
    poly = sc._polylines[-1]
    assert _recs(sc) == [("point_on_curve", [(poly._uid, "v1", None), (None, None, "x_axis")])]


def test_circle_centre_on_axis_records_point_on_axis(vs):
    view, sc = vs
    sc.set_mode("draw_circle")
    for p in ((150, 4), (150, 100)):
        move(view, QPointF(*p)); click(view, QPointF(*p))
    c = sc._draw_circles[-1]
    assert _recs(sc) == [("point_on_curve", [(c._uid, "center", None), (None, None, "x_axis")])]


def test_line_and_axis_record_are_one_undo_step(vs):
    view, sc = vs
    sc.push_undo_state()
    n_lines = len(sc._draw_lines)
    _draw(view, sc, (150, 200), (230, 4))
    assert len(sc.constraint_ctl.constraints) == 1
    sc.undo(); QApplication.processEvents()
    assert len(sc._draw_lines) == n_lines and sc.constraint_ctl.constraints == []


def test_shift_on_the_axis_click_records_nothing(vs):
    view, sc = vs
    shift = Qt.KeyboardModifier.ShiftModifier
    sc.set_mode("draw_line")
    move(view, QPointF(150, 200)); click(view, QPointF(150, 200))
    move(view, QPointF(230, 4), shift); click(view, QPointF(230, 4), shift)
    n = sc._draw_lines[-1]
    assert _xy(n.grip_points()[2]) == (230.0, 0.0)          # still snaps, no relation
    assert _recs(sc) == []


# ── Offset (D9): the source's own axis gives no snap (user ruling 2026-10-31) ──

def _offset_source(sc, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b)); sc.addItem(ln); sc._draw_lines.append(ln)
    sc.clearSelection(); ln.setSelected(True); QApplication.processEvents()
    sc._modify_ctl.start("offset")
    return ln


def test_offset_of_a_line_on_the_x_axis_ignores_that_axis(vs):
    view, sc = vs
    _offset_source(sc, (40, 0), (140, 0))
    move(view, QPointF(90, 4))                          # 4 px off source and X axis
    assert sc._offset_dist == pytest.approx(4.0, abs=0.05)


def test_offset_of_an_off_axis_line_snaps_through_the_x_axis(vs):
    view, sc = vs
    _offset_source(sc, (200, 100), (300, 100))
    move(view, QPointF(250, 3))                         # NEA on the X axis -> (250, 0)
    assert sc._offset_dist == pytest.approx(100.0, abs=0.05)


# ── Task 3: cue + ALIGN identity ─────────────────────────────────────────

def _count_colour(view, scene_pt, hexcol, half=3):
    """Pixels of exactly *hexcol* in a box around *scene_pt* (device px)."""
    view.viewport().repaint()
    img = view.viewport().grab().toImage()
    dpr = img.devicePixelRatio()
    vp = view.viewportTransform().map(scene_pt)
    want = QColor(hexcol).rgb()
    cx, cy = int(round(vp.x() * dpr)), int(round(vp.y() * dpr))
    h = int(math.ceil(half * dpr))
    return sum(1 for x in range(cx - h, cx + h + 1) for y in range(cy - h, cy + h + 1)
               if 0 <= x < img.width() and 0 <= y < img.height()
               and img.pixel(x, y) == want)


def test_snapped_axis_draws_solid_in_the_snap_colour(vs):
    view, sc = vs
    sc.set_mode("draw_line")
    move(view, QPointF(150, 200)); click(view, QPointF(150, 200))
    move(view, QPointF(3, 196))                         # PER on the Y axis (magenta)
    assert sc._snap_result.name == "y_axis"
    far = QPointF(0, -200)                              # on the Y axis, far from the marker
    assert _count_colour(view, far, SNAP_COLORS["perpendicular"]) > 0
    move(view, QPointF(200, -150))                      # off every snap
    assert _count_colour(view, far, SNAP_COLORS["perpendicular"]) == 0


def test_align_dwell_identity_is_one_per_axis(vs):
    view, sc = vs
    a = sc._align_snap_dict(OsnapResult(QPointF(100, 0), "nearest", name="x_axis"))
    b = sc._align_snap_dict(OsnapResult(QPointF(250, 0), "nearest", name="x_axis"))
    y = sc._align_snap_dict(OsnapResult(QPointF(0, 40), "nearest", name="y_axis"))
    assert a["source_id"] == b["source_id"] != y["source_id"]
    assert a["direction"] == (1.0, 0.0) and y["direction"] == (0.0, 1.0)
