"""region_finder guards (HF4 design, Verification Checklist). Later tasks append classes."""
import math

import pytest
from PyQt6.QtCore import QPointF, QRectF


def _bez_pt(b, t):
    u = 1.0 - t
    return (u**3 * b[0][0] + 3*u*u*t * b[1][0] + 3*u*t*t * b[2][0] + t**3 * b[3][0],
            u**3 * b[0][1] + 3*u*u*t * b[1][1] + 3*u*t*t * b[2][1] + t**3 * b[3][1])


class TestBezierSub:
    def test_sub_bezier_matches_source_curve(self):
        from firepro3d.geometry_2d import bezier_sub
        b = ((0.0, 0.0), (30.0, 80.0), (70.0, -40.0), (100.0, 10.0))
        sub = bezier_sub(b, 0.25, 0.75)
        assert len(sub) == 4
        for k in range(11):
            s = k / 10
            x, y = _bez_pt(sub, s)
            ex, ey = _bez_pt(b, 0.25 + 0.5 * s)
            assert math.hypot(x - ex, y - ey) < 1e-9

    def test_constants_exist(self):
        from firepro3d import constants as c
        assert c.REGION_FINDER_SAGITTA_MM == 0.1
        assert c.REGION_FINDER_POLYLINE_MM == 0.2
        assert c.REGION_FINDER_WINDOW_MM == 50.0
        assert c.REGION_FINDER_NUDGE_MM == 0.5
        assert c.REGION_FINDER_DEBOUNCE_MS == 150
        assert c.REGION_FINDER_BUCKETS == 32
