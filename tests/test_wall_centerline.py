"""Tests for WallSegment true-centerline accessors (centerline_pt1/pt2/midpoint).

These are pure geometry tests — no scene required; WallSegment falls back to
``half_mm`` (= thickness_mm / 2) when not attached to a scene.
"""
from __future__ import annotations

import math
import pytest
from PyQt6.QtCore import QPointF
from firepro3d.wall import WallSegment, ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT


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
