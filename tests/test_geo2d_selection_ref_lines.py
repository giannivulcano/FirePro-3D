"""tests/test_geo2d_selection_ref_lines.py — selection-time reference guides.

Contract (user, 2026-09-16): Rectangle and Circle draw dashed reference guides
when selected (matching EllipseItem's axis guides — canonical width-1 dashed):
  * Rectangle → the two corner diagonals;
  * Circle → a radius guide (centre → right edge) plus a bounding box.

The guide GEOMETRY is exposed via ``_selection_ref_segments`` (the observable
ground truth); ``paint`` draws it when selected.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import RectangleItem, CircleItem


def _pt(p):
    return (round(p.x(), 6), round(p.y(), 6))


def test_rectangle_ref_segments_are_the_corner_diagonals():
    rect = RectangleItem(QPointF(0, 0), QPointF(100, 100), "#ffffff", 1.0)
    segs = [(_pt(a), _pt(b)) for a, b in rect._selection_ref_segments()]
    assert ((0.0, 0.0), (100.0, 100.0)) in segs      # TL → BR
    assert ((100.0, 0.0), (0.0, 100.0)) in segs      # TR → BL
    assert len(segs) == 2


def test_circle_ref_segment_is_the_radius_guide():
    circle = CircleItem(QPointF(50, 50), 30.0, "#ffffff", 1.0)
    segs = [(_pt(a), _pt(b)) for a, b in circle._selection_ref_segments()]
    # Centre (50,50) → right edge (80,50).
    assert segs == [((50.0, 50.0), (80.0, 50.0))]
