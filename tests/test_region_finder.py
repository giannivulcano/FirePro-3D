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


class TestFlattenSplit:
    def test_rect_flattens_to_four_line_segments_with_tags(self, qapp):
        from firepro3d.geometry_2d import LineItem
        from firepro3d.region_finder import _flatten
        a, b, c, d = QPointF(0, 0), QPointF(100, 0), QPointF(100, 50), QPointF(0, 50)
        items = [LineItem(a, b), LineItem(b, c), LineItem(c, d), LineItem(d, a)]
        pieces = _flatten(items, QRectF(-10, -10, 120, 70))
        assert len(pieces) == 4
        assert all(p.tag.kind == "line" and p.tag.t0 == 0.0 and p.tag.t1 == 1.0 for p in pieces)
        assert {p.tag.item for p in pieces} == set(items)

    def test_circle_flattens_within_sagitta_and_keeps_cubics(self, qapp):
        from firepro3d.constants import REGION_FINDER_SAGITTA_MM
        from firepro3d.geometry_2d import CircleItem
        from firepro3d.region_finder import _flatten
        circ = CircleItem(QPointF(0, 0), 40.0)
        pieces = _flatten([circ], QRectF(-50, -50, 100, 100))
        assert len(pieces) >= 16
        assert all(p.tag.kind == "curve" and p.tag.bez is not None for p in pieces)
        # every flattened chord's midpoint lies within the sagitta of the circle
        for p in pieces:
            mx, my = (p.x0 + p.x1) / 2, (p.y0 + p.y1) / 2
            assert abs(math.hypot(mx, my) - 40.0) <= REGION_FINDER_SAGITTA_MM + 1e-6
        # the chain is continuous and closed
        for p, q in zip(pieces, pieces[1:]):
            assert math.hypot(p.x1 - q.x0, p.y1 - q.y0) < 1e-9
        assert math.hypot(pieces[-1].x1 - pieces[0].x0, pieces[-1].y1 - pieces[0].y0) < 1e-9

    def test_segments_outside_window_dropped(self, qapp):
        from firepro3d.geometry_2d import LineItem
        from firepro3d.region_finder import _flatten
        inside = LineItem(QPointF(0, 0), QPointF(10, 0))
        outside = LineItem(QPointF(500, 500), QPointF(510, 500))
        pieces = _flatten([inside, outside], QRectF(-20, -20, 40, 40))
        assert [p.tag.item for p in pieces] == [inside]

    def test_cross_splits_both_segments_and_interpolates_tags(self, qapp):
        from firepro3d.geometry_2d import LineItem
        from firepro3d.region_finder import _flatten, _split_all
        h = LineItem(QPointF(0, 50), QPointF(100, 50))
        v = LineItem(QPointF(25, 0), QPointF(25, 100))
        win = QRectF(-10, -10, 120, 120)
        pieces = _split_all(_flatten([h, v], win), win)
        assert len(pieces) == 4
        hp = sorted((p for p in pieces if p.tag.item is h), key=lambda p: p.x0)
        assert (hp[0].x0, hp[0].x1) == (0.0, 25.0) and (hp[1].x0, hp[1].x1) == (25.0, 100.0)
        assert hp[0].tag.t0 == 0.0 and abs(hp[0].tag.t1 - 0.25) < 1e-9
        assert abs(hp[1].tag.t0 - 0.25) < 1e-9 and hp[1].tag.t1 == 1.0

    def test_split_count_matches_five_by_five_grid(self, qapp):
        from firepro3d.geometry_2d import LineItem
        from firepro3d.region_finder import _flatten, _split_all
        items = [LineItem(QPointF(0, 20 * i), QPointF(100, 20 * i)) for i in range(5)]
        items += [LineItem(QPointF(20 * i, 0), QPointF(20 * i, 100)) for i in range(5)]
        win = QRectF(-5, -5, 110, 110)
        pieces = _split_all(_flatten(items, win), win)
        # each of the 10 lines meets 6 grid points (x or y = 0,20,...,100, both ends
        # included), so it is cut into 5 pieces: 10 lines x 5 pieces = 50
        assert len(pieces) == 50
