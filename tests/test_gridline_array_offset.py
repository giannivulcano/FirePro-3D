"""
test_gridline_array_offset.py
==============================
Unit tests for GridlineItem.offset_copy() and GridlineItem.array_copies().

These methods produce parallel copies of a gridline (pure geometry — no
scene mutation, no label assignment, no counter side-effects).
"""

import math
from PyQt6.QtCore import QPointF
from firepro3d.gridline import GridlineItem


def test_offset_copy_translates_perpendicular(qapp):
    src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")  # vertical
    cp = src.offset_copy(1000.0)
    # vertical line dir (0,1); perpendicular normal (-dy,dx)=(-1,0) → origin x -= 1000
    assert round(cp.grip_points()[0].x(), 1) == -1000.0
    assert round(cp._length, 1) == 5000.0
    assert round(cp._angle_deg, 3) == round(src._angle_deg, 3)
    assert cp.locked is False


def test_array_copies_count_and_spacing(qapp):
    src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
    cps = src.array_copies(spacing=1000.0, count=3)
    assert len(cps) == 3
    xs = [round(c.grip_points()[0].x(), 1) for c in cps]
    assert xs == [-1000.0, -2000.0, -3000.0]


def test_array_copies_angled_source_is_perpendicular(qapp):
    src = GridlineItem(QPointF(0.0, 0.0), QPointF(3000.0, -3000.0), label="1")  # dir (1,-1)/√2
    cps = src.array_copies(spacing=1000.0, count=1)
    o = cps[0].grip_points()[0]
    # perpendicular normal of dir (1,-1)/√2 is (-(-1),1)/√2 = (1,1)/√2
    assert round(o.x(), 1) == round(1000.0 * (1 / math.sqrt(2)), 1)
    assert round(o.y(), 1) == round(1000.0 * (1 / math.sqrt(2)), 1)


def test_copies_inherit_bubble_offsets_and_visibility(qapp):
    src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
    src.set_bubble_offset(1, 1500.0)
    src.set_bubble_visible(2, False)
    cp = src.offset_copy(500.0)
    assert round(cp._bubble1_offset, 1) == 1500.0
    assert cp.bubble2.isVisible() is False


def test_copies_inherit_display_overrides_as_copy(qapp):
    src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
    src._display_overrides["color"] = "#ff0000"
    cp = src.offset_copy(500.0)
    assert cp._display_overrides == {"color": "#ff0000"}
    cp._display_overrides["color"] = "#00ff00"   # mutating copy must not affect src
    assert src._display_overrides["color"] == "#ff0000"


def test_array_copies_zero_count_is_empty(qapp):
    src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
    assert src.array_copies(1000.0, 0) == []
