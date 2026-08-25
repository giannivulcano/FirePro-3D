"""Tests for WallSegment.alignment_reference_points() — inference provider.

Task 3: WallSegment emits H/V alignment references at its TRUE centerline
(endpoints + midpoint).  Pure-logic: no scene required.
"""
from PyQt6.QtCore import QPointF
from firepro3d.wall import WallSegment, ALIGN_LEFT


def test_provider_emits_centerline_endpoints_and_midpoint():
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    w._alignment = ALIGN_LEFT
    feats = w.alignment_reference_points()
    coords = {(round(f.x, 6), round(f.y, 6)) for f in feats}
    a, b, m = w.centerline_pt1, w.centerline_pt2, w.centerline_midpoint()
    assert (round(a.x(), 6), round(a.y(), 6)) in coords
    assert (round(b.x(), 6), round(b.y(), 6)) in coords
    assert (round(m.x(), 6), round(m.y(), 6)) in coords
    assert {f.source_id for f in feats} == {id(w)}
