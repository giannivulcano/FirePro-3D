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


def _square(x0, y0, size):
    from firepro3d.geometry_2d import LineItem
    a, b = QPointF(x0, y0), QPointF(x0 + size, y0)
    c, d = QPointF(x0 + size, y0 + size), QPointF(x0, y0 + size)
    return [LineItem(a, b), LineItem(b, c), LineItem(c, d), LineItem(d, a)]


def _loop_pts(pieces):
    return [(p.x0, p.y0) for p in pieces]


class TestWeld:
    def test_gap_within_weld_closes(self, qapp):
        from firepro3d.geometry_2d import LineItem
        from firepro3d.region_finder import Arrangement
        a, b, c, d = QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)
        items = [LineItem(a, b), LineItem(b, c), LineItem(c, d), LineItem(d, QPointF(0, 0.8))]
        arr = Arrangement.build(items, QRectF(-10, -10, 120, 120))
        face = arr.face_at(QPointF(50, 50))
        assert face is not None and not face.islands
        assert arr.nearest_open_end(QPointF(50, 50)) is None

    def test_t_gap_welds_dangling_end_into_edge_interior(self, qapp):
        from firepro3d.geometry_2d import LineItem
        from firepro3d.region_finder import Arrangement
        # a square whose top edge overshoots; the left edge stops 0.6 mm short of the top edge
        items = [LineItem(QPointF(-20, 0), QPointF(120, 0)), LineItem(QPointF(100, 0), QPointF(100, 100)),
                 LineItem(QPointF(100, 100), QPointF(0, 100)), LineItem(QPointF(0, 100), QPointF(0, 0.6))]
        arr = Arrangement.build(items, QRectF(-30, -10, 160, 120))
        face = arr.face_at(QPointF(50, 50))
        assert face is not None
        assert abs(face.area - 100 * 100) < 100 * 1.0 * 2   # within the 1 mm weld slack


class TestFaces:
    def test_circle_two_lines_four_quadrants(self, qapp):
        from firepro3d.geometry_2d import CircleItem, LineItem
        from firepro3d.region_finder import Arrangement
        items = [CircleItem(QPointF(0, 0), 40.0),
                 LineItem(QPointF(-60, 0), QPointF(60, 0)), LineItem(QPointF(0, -60), QPointF(0, 60))]
        arr = Arrangement.build(items, QRectF(-70, -70, 140, 140))
        faces = [arr.face_at(QPointF(sx * 15, sy * 15)) for sx in (1, -1) for sy in (1, -1)]
        assert all(f is not None for f in faces)
        for f in faces:
            assert abs(f.area - math.pi * 40 * 40 / 4) < 5.0   # flattened at 0.1 mm sagitta
            assert not f.islands
        # the four faces are distinct (different piece sets)
        assert len({frozenset(id(p.tag) for p in f.outer) for f in faces}) == 4
        # outside the circle: unbounded -> None, and nothing to leak
        assert arr.face_at(QPointF(55, 55)) is None
        assert arr.nearest_open_end(QPointF(55, 55)) is not None   # the line stubs past the circle are open ends

    def test_ring_between_concentric_circles_has_island(self, qapp):
        from firepro3d.geometry_2d import CircleItem
        from firepro3d.region_finder import Arrangement
        arr = Arrangement.build([CircleItem(QPointF(0, 0), 40.0), CircleItem(QPointF(0, 0), 15.0)],
                                QRectF(-50, -50, 100, 100))
        ring = arr.face_at(QPointF(30, 0))
        assert ring is not None and len(ring.islands) == 1
        from firepro3d.constants import REGION_FINDER_SAGITTA_MM
        # face.area is the inscribed flattened polygon: its deficit is bounded by sagitta x perimeter
        assert 0 < math.pi * 40 * 40 - ring.area < REGION_FINDER_SAGITTA_MM * 2 * math.pi * 40
        assert ring.path.contains(QPointF(30, 0)) and not ring.path.contains(QPointF(0, 0))
        inner = arr.face_at(QPointF(0, 0))
        assert inner is not None and not inner.islands

    def test_one_level_islands(self, qapp):
        from firepro3d.region_finder import Arrangement
        items = _square(0, 0, 100) + _square(30, 30, 40) + _square(45, 45, 10)
        arr = Arrangement.build(items, QRectF(-10, -10, 120, 120))
        outer = arr.face_at(QPointF(10, 10))
        assert outer is not None and len(outer.islands) == 1
        assert abs(abs(_signed_area(_loop_pts(outer.islands[0]))) - 40 * 40) < 1e-6

    def test_gap_over_weld_leaks_with_open_end(self, qapp):
        from firepro3d.geometry_2d import LineItem
        from firepro3d.region_finder import Arrangement
        a, b, c, d = QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)
        items = [LineItem(a, b), LineItem(b, c), LineItem(c, d), LineItem(d, QPointF(0, 1.5))]
        arr = Arrangement.build(items, QRectF(-10, -10, 120, 120))
        assert arr.face_at(QPointF(50, 50)) is None
        end = arr.nearest_open_end(QPointF(50, 50))
        assert end is not None
        assert min(math.hypot(end.x() - 0, end.y() - 0), math.hypot(end.x() - 0, end.y() - 1.5)) < 1e-6

    def test_open_space_has_no_face_and_no_open_end(self, qapp):
        from firepro3d.region_finder import Arrangement
        arr = Arrangement.build(_square(0, 0, 100), QRectF(-200, -200, 500, 500))
        assert arr.face_at(QPointF(150, 150)) is None
        assert arr.nearest_open_end(QPointF(150, 150)) is None

    def test_zero_area_face_refused(self, qapp):
        from firepro3d.geometry_2d import LineItem
        from firepro3d.region_finder import Arrangement
        # two coincident lines -> one welded edge, no face anywhere near it
        items = [LineItem(QPointF(0, 0), QPointF(100, 0)), LineItem(QPointF(0, 0), QPointF(100, 0))]
        arr = Arrangement.build(items, QRectF(-10, -10, 120, 20))
        assert arr.face_at(QPointF(50, 0.2)) is None

    def test_nudge_moves_point_off_edge(self, qapp):
        from firepro3d.constants import REGION_FINDER_NUDGE_MM
        from firepro3d.region_finder import Arrangement
        arr = Arrangement.build(_square(0, 0, 100), QRectF(-10, -10, 120, 120))
        on_edge = QPointF(50, 100.0)                     # exactly on the bottom edge
        inward = arr.nudge(on_edge, motion=QPointF(0, 2))   # cursor was moving +y: it came from inside
        assert abs(inward.y() - (100.0 - REGION_FINDER_NUDGE_MM)) < 1e-9
        assert arr.face_at(inward) is not None
        outward = arr.nudge(on_edge, motion=QPointF(0, -2))
        assert abs(outward.y() - (100.0 + REGION_FINDER_NUDGE_MM)) < 1e-9
        assert arr.nudge(QPointF(50, 50), motion=QPointF(0, 2)) == QPointF(50, 50)   # far from any edge


def _signed_area(pts):
    s = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        s += x0 * y1 - x1 * y0
    return s / 2

