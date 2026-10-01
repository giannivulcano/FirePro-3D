"""Slice 9 guards: spline click-near-first closes as a periodic spline (DD8).

Real Model_Space(scene_role="block_editor") + shown Model_View (deaf to the
real OS mouse), with posted presses, moves and keys. The control loop is kept
away from the origin so the origin snap (Slice 2) cannot take the cursor.
"""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

from tests._modify_tools_helpers import ignore_os_mouse
from tests._snap_polish_helpers import click, close_view, make_view, move

PTS = [(200, 200), (1000, 200), (1000, -600), (200, -600)]
NEAR_FIRST = QPointF(206, 194)          # ~8.5 mm = ~2 px at m11 0.25


def _view():
    view, scene = make_view()
    ignore_os_mouse(view)
    return view, scene


def _draw(view, scene, pts=PTS):
    scene.set_mode("draw_spline")
    for p in pts:
        click(view, QPointF(*p))
    assert len(scene._spline_points) == len(pts)


def _key(view, key):
    for et in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(view.viewport(), QKeyEvent(
            et, key, Qt.KeyboardModifier.NoModifier))
    QApplication.processEvents()


def _seam_turn_deg(path, eps=1e-4):
    p0, p1 = path.pointAtPercent(0.0), path.pointAtPercent(1.0)
    a, b = path.pointAtPercent(eps), path.pointAtPercent(1.0 - eps)
    t_out = (a.x() - p0.x(), a.y() - p0.y())
    t_in = (p1.x() - b.x(), p1.y() - b.y())
    c = ((t_out[0] * t_in[0] + t_out[1] * t_in[1])
         / (math.hypot(*t_out) * math.hypot(*t_in)))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def test_hover_near_first_shows_ring_and_periodic_preview(qapp):
    view, scene = _view()
    try:
        _draw(view, scene)
        move(view, NEAR_FIRST)
        ring = scene._polyline_close_indicator
        assert ring is not None and ring.isVisible()                    # [RED]
        assert math.hypot(ring.pos().x() - 200, ring.pos().y() - 200) < 0.5
        prev = scene._spline_preview
        assert prev.is_periodic() and len(prev._control_points) == 4    # [RED]
        move(view, QPointF(600, 600))                       # away again
        assert not ring.isVisible() and not scene._spline_preview.is_periodic()
    finally:
        close_view(view, scene)


def test_click_near_first_commits_a_periodic_spline_then_select(qapp):
    view, scene = _view()
    try:
        scene.push_undo_state()      # baseline (a fresh scene's stack is empty)
        p0 = scene._undo_pos
        _draw(view, scene)
        move(view, NEAR_FIRST)
        click(view, NEAR_FIRST)
        assert len(scene._draw_splines) == 1
        s = scene._draw_splines[0]
        assert s.is_periodic()                                          # [RED]
        got = [c for p in s.grip_points() for c in (p.x(), p.y())]
        assert got == pytest.approx([c for xy in PTS for c in xy], abs=0.5)  # no extra point
        assert _seam_turn_deg(s.path()) < 0.5
        assert scene.mode == "select" and scene.selectedItems() == [s]
        assert scene._undo_pos == p0 + 1                     # one undo step
        assert scene._spline_preview is None and scene._spline_points == []
        assert not scene._polyline_close_indicator.isVisible()
        scene.undo()
        assert scene._draw_splines == []
    finally:
        close_view(view, scene)


def test_enter_near_first_still_finishes_open(qapp):
    view, scene = _view()
    try:
        _draw(view, scene)
        move(view, NEAR_FIRST)                   # ring showing
        assert scene._polyline_close_indicator.isVisible()
        _key(view, Qt.Key.Key_Return)
        s = scene._draw_splines[-1]
        assert not s.is_periodic() and len(s.grip_points()) == 4
        assert not scene._polyline_close_indicator.isVisible()
    finally:
        close_view(view, scene)


def test_two_points_never_close(qapp):
    view, scene = _view()
    try:
        _draw(view, scene, PTS[:2])
        move(view, NEAR_FIRST)
        assert (scene._polyline_close_indicator is None
                or not scene._polyline_close_indicator.isVisible())
        assert not scene._spline_preview.is_periodic()
        click(view, NEAR_FIRST)
        assert len(scene._spline_points) == 3    # a third control point, no close
        assert scene._draw_splines == []
    finally:
        close_view(view, scene)


def test_delete_pop_below_three_points_drops_the_closed_cue(qapp):
    """Slice 8 review M3: SplineItem enforces "closed needs >= 3 control
    points" only in __init__. The gesture flips the live preview's flag, so a
    Delete-pop from 3 to 2 points must clear it (and the ring), and no closed
    spline is ever committed below 3 points."""
    view, scene = _view()
    try:
        _draw(view, scene, PTS[:3])
        move(view, NEAR_FIRST)
        assert scene._spline_preview.is_periodic()
        assert scene._polyline_close_indicator.isVisible()
        _key(view, Qt.Key.Key_Delete)
        assert len(scene._spline_points) == 2
        assert not scene._spline_preview.is_periodic()                  # [RED]
        assert not scene._polyline_close_indicator.isVisible()          # [RED]
        click(view, NEAR_FIRST)                  # 2 points: appends, no close
        assert len(scene._spline_points) == 3
        assert scene._draw_splines == []
        _key(view, Qt.Key.Key_Return)            # finish open
        s = scene._draw_splines[-1]
        assert not s.is_periodic() and len(s.grip_points()) == 3
    finally:
        close_view(view, scene)


def test_escape_with_the_ring_up_hides_it(qapp):
    view, scene = _view()
    try:
        _draw(view, scene)
        move(view, NEAR_FIRST)
        assert scene._polyline_close_indicator.isVisible()
        _key(view, Qt.Key.Key_Escape)
        assert scene._draw_splines == []
        assert not scene._polyline_close_indicator.isVisible()
    finally:
        close_view(view, scene)
