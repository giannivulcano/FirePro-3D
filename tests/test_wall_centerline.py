"""Tests for WallSegment true-centerline accessors (centerline_pt1/pt2/midpoint).

These are pure geometry tests — no scene required; WallSegment falls back to
``half_mm`` (= thickness_mm / 2) when not attached to a scene.
"""
from __future__ import annotations

import math
import pytest
from PyQt6.QtCore import QPointF
from firepro3d.wall import WallSegment, ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT
from firepro3d.wall_opening import WallOpening


def _wall(align):
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    w._alignment = align
    return w


def test_center_alignment_centerline_equals_click_line(qapp):
    w = _wall(ALIGN_CENTER)
    assert w.centerline_pt1 == QPointF(0, 0)
    assert w.centerline_pt2 == QPointF(1000, 0)


def test_left_alignment_centerline_offset_by_plus_normal_half(qapp):
    w = _wall(ALIGN_LEFT)
    nx, ny = w.normal()
    h = w.half_thickness_scene()
    assert w.centerline_pt1 == QPointF(0 + nx * h, 0 + ny * h)
    assert w.centerline_pt2 == QPointF(1000 + nx * h, 0 + ny * h)


def test_right_alignment_centerline_offset_by_minus_normal_half(qapp):
    w = _wall(ALIGN_RIGHT)
    nx, ny = w.normal()
    h = w.half_thickness_scene()
    assert w.centerline_pt1 == QPointF(0 - nx * h, 0 - ny * h)


def test_left_centerline_lies_at_geometric_center_of_quad(qapp):
    w = _wall(ALIGN_LEFT)
    p1l, p1r, p2r, p2l = w.quad_points()
    cx = (p1l.x() + p1r.x() + p2r.x() + p2l.x()) / 4
    cy = (p1l.y() + p1r.y() + p2r.y() + p2l.y()) / 4
    m = w.centerline_midpoint()
    assert math.isclose(m.x(), cx, abs_tol=1e-6)
    assert math.isclose(m.y(), cy, abs_tol=1e-6)


# ── Opening-on-centerline tests ───────────────────────────────────────────────
# These tests verify that center_on_wall() returns a position on the wall's true
# geometric centerline, not the click/face line (the bug for Left/Right walls).
#
# Construction pattern: build the opening without a wall so _reposition() is
# not triggered before we can set _offset_along; then assign the wall (which
# calls _reposition() once, clamping against centerline_length).

def _wall_with_opening(align):
    """Return (wall, opening) with the opening centred along the wall."""
    w = WallSegment(QPointF(0, 0), QPointF(2000, 0), thickness_mm=300.0)
    w._alignment = align
    # Build without a wall first so we can set _offset_along freely.
    op = WallOpening(feature_id="door_914")
    half_len = w.centerline_length() / 2.0
    op._offset_along = half_len
    op.cross_offset_mm = 0.0
    # Assigning wall triggers _reposition() → clamping uses centerline_length (2000).
    op._wall = w
    w.openings.append(op)
    return w, op


def test_opening_on_left_wall_sits_at_true_centerline_midpoint(qapp):
    """center_on_wall() for a Left-aligned wall must land on the geometric
    center of the wall, NOT the click-face midpoint (the pre-fix bug)."""
    w, op = _wall_with_opening(ALIGN_LEFT)
    c = op.center_on_wall()
    m = w.centerline_midpoint()
    assert abs(c.x() - m.x()) < 1e-6, (
        f"x: got {c.x()}, expected {m.x()} (centerline midpoint)"
    )
    assert abs(c.y() - m.y()) < 1e-6, (
        f"y: got {c.y()}, expected {m.y()} (centerline midpoint)"
    )


def test_opening_on_center_wall_sits_at_true_centerline_midpoint(qapp):
    """Center-aligned walls: centerline == click-line, so result is unchanged
    by the fix.  This test must stay GREEN before and after the fix."""
    w, op = _wall_with_opening(ALIGN_CENTER)
    c = op.center_on_wall()
    m = w.centerline_midpoint()
    assert abs(c.x() - m.x()) < 1e-6, (
        f"x: got {c.x()}, expected {m.x()}"
    )
    assert abs(c.y() - m.y()) < 1e-6, (
        f"y: got {c.y()}, expected {m.y()}"
    )
