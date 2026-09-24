"""Pure arc construction helpers — Y-up angles, Qt scene coords."""
import math
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.arc_math import (yup_angle, point_at, chord_frame,
                                project_to_bisector, arc_through_chord,
                                center_for_radius)


def _close(p, q, tol=1e-6):
    return abs(p.x() - q.x()) < tol and abs(p.y() - q.y()) < tol


def test_yup_angle_and_point_at_roundtrip():
    c = QPointF(10, 10)
    p = point_at(c, 5.0, 90.0)            # Y-up 90° = screen up
    assert _close(p, QPointF(10, 5))
    assert yup_angle(c, p) == pytest.approx(90.0)


def test_chord_frame_left_normal_is_screen_up_for_eastward_chord():
    m, n, h = chord_frame(QPointF(0, 0), QPointF(10, 0))
    assert _close(m, QPointF(5, 0))
    assert n == pytest.approx((0.0, -1.0))
    assert h == pytest.approx(5.0)
    assert chord_frame(QPointF(1, 1), QPointF(1, 1)) is None


def test_project_to_bisector_signed_distance():
    c, t = project_to_bisector(QPointF(0, 0), QPointF(10, 0), QPointF(3, -4))
    assert _close(c, QPointF(5, -4))
    assert t == pytest.approx(4.0)        # -y (screen up) is +n
    c, t = project_to_bisector(QPointF(0, 0), QPointF(10, 0), QPointF(8, 7))
    assert _close(c, QPointF(5, 7)) and t == pytest.approx(-7.0)


@pytest.mark.parametrize("bulge", [+1, -1])
@pytest.mark.parametrize("center_y", [-3.0, 0.0, 4.0])
def test_arc_through_chord_passes_through_both_ends_and_bulges(bulge, center_y):
    a, b = QPointF(0, 0), QPointF(10, 0)
    c = QPointF(5, center_y)
    r, st, sp = arc_through_chord(a, b, c, bulge)
    assert _close(point_at(c, r, st), a) or _close(point_at(c, r, st), b)
    assert _close(point_at(c, r, st + sp), a) or _close(point_at(c, r, st + sp), b)
    mid = point_at(c, r, st + sp / 2.0)
    assert (-(mid.y() - 0.0) > 0) == (bulge > 0)   # side along n = (0,-1)


def test_minor_and_major_spans_sum_to_360():
    a, b, c = QPointF(0, 0), QPointF(10, 0), QPointF(5, 3)
    _, _, s1 = arc_through_chord(a, b, c, +1)
    _, _, s2 = arc_through_chord(a, b, c, -1)
    assert s1 + s2 == pytest.approx(360.0)


def test_center_for_radius():
    a, b = QPointF(0, 0), QPointF(10, 0)
    c = center_for_radius(a, b, 13.0, +1)
    assert _close(c, QPointF(5, -12))
    assert center_for_radius(a, b, 4.9, +1) is None      # < half chord
    assert _close(center_for_radius(a, b, 5.0, -1), QPointF(5, 0))
