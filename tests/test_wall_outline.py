"""Pure wall-outline geometry (wall polish design D5, D6, D8)."""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF

from firepro3d.wall_outline import (
    JunctionArm, boundary_segments, cluster_union, intersect_lines,
    junction_pie, stroke_segments, visible_corners)


def _faces(a, b, h):
    """(left, right) face lines of a centre-aligned wall a->b, half-thick h.
    Left = +rot90(a->b) side, as WallSegment.quad_points."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    nx, ny = -dy / L * h, dx / L * h
    left = (QPointF(a[0] + nx, a[1] + ny), QPointF(b[0] + nx, b[1] + ny))
    right = (QPointF(a[0] - nx, a[1] - ny), QPointF(b[0] - nx, b[1] - ny))
    return left, right


def _arm(key, far, h, j=(0.0, 0.0)):
    """Arm of a wall running from junction j out to far (pt1 at j)."""
    left, right = _faces(j, far, h)
    dx, dy = far[0] - j[0], far[1] - j[1]
    L = math.hypot(dx, dy)
    return JunctionArm(key, dx / L, dy / L, left, right)


def _poly(*pts):
    return QPolygonF([QPointF(x, y) for x, y in pts])


def _close(a, b, tol=1e-6):
    return math.hypot(a.x() - b.x(), a.y() - b.y()) <= tol


class TestJunctionPie:
    def test_three_way_matches_face_intersections(self, qapp):
        """Parity bar (D5): arm i's ccw face meets arm i+1's cw face."""
        arms = [_arm("a", (900, 0), 50), _arm("b", (-150, 880), 50),
                _arm("c", (-600, -660), 50)]
        corners, hub = junction_pie(arms, QPointF(0, 0), 200.0)
        # a (0 deg) -> next CCW by atan2 is b (~100 deg)
        exp_ab = intersect_lines(*arms[0].ccw_face, *arms[1].cw_face)
        assert _close(corners["a"][0], exp_ab)
        assert _close(corners["b"][1], exp_ab)
        pts = [p for pair in corners.values() for p in pair]
        cx = sum(p.x() for p in pts) / len(pts)
        cy = sum(p.y() for p in pts) / len(pts)
        assert _close(hub, QPointF(cx, cy))

    def test_four_way_cross_gives_square_core(self, qapp):
        arms = [_arm(k, far, 50) for k, far in
                (("e", (900, 0)), ("n", (0, 900)), ("w", (-900, 0)),
                 ("s", (0, -900)))]
        corners, hub = junction_pie(arms, QPointF(0, 0), 200.0)
        core = {(round(p.x(), 6), round(p.y(), 6))
                for pair in corners.values() for p in pair}
        assert core == {(50, 50), (-50, 50), (-50, -50), (50, -50)}
        assert _close(hub, QPointF(0, 0))

    def test_straight_through_pair_uses_face_foot(self, qapp):
        """Edge case (design): parallel facing faces -> foot of the junction
        on each face (pairwise rule), not a Butt fallback."""
        arms = [_arm("e", (900, 0), 50), _arm("n", (0, 900), 50),
                _arm("w", (-900, 0), 50)]
        corners, _hub = junction_pie(arms, QPointF(0, 0), 200.0)
        # w (180 deg) -> next CCW wraps to e (0 deg): faces y=-50 parallel
        assert _close(corners["w"][0], QPointF(0, -50))
        assert _close(corners["e"][1], QPointF(0, -50))

    def test_acute_pair_falls_back_far_arm_stays_mitred(self, qapp):
        """Edge Cases row 1: the offending pair (a, b) falls back on its own;
        the far arm c stays mitred, as the old per-wall pie mitred it."""
        arms = [_arm("a", (900, 0), 50), _arm("b", (900, 20), 50),
                _arm("c", (-900, 300), 50)]
        res = junction_pie(arms, QPointF(0, 0), 200.0)
        assert res is not None
        corners, _hub = res
        assert set(corners) == {"c"}
        by = {a.key: a for a in arms}
        exp_ca = intersect_lines(*by["c"].ccw_face, *by["a"].cw_face)
        exp_bc = intersect_lines(*by["b"].ccw_face, *by["c"].cw_face)
        assert _close(corners["c"][0], exp_ca)
        assert _close(corners["c"][1], exp_bc)

    def test_all_pairs_beyond_max_miter_returns_none(self, qapp):
        arms = [_arm("a", (900, 0), 50), _arm("b", (900, 20), 50),
                _arm("c", (900, 40), 50)]
        assert junction_pie(arms, QPointF(0, 0), 200.0) is None

    def test_fewer_than_three_arms_returns_none(self, qapp):
        arms = [_arm("a", (900, 0), 50), _arm("b", (0, 900), 50)]
        assert junction_pie(arms, QPointF(0, 0), 200.0) is None


class TestUnionAndStrokes:
    def test_tee_union_body_merges_into_host(self, qapp):
        """G0 guard (D8): a stub whose UNION polygon runs to the host
        centerline merges into one outline and splits the host face."""
        host = _poly((0, 50), (2000, 50), (2000, -50), (0, -50))
        stub_union = _poly((650, 0), (650, 900), (750, 900), (750, 0))
        u = cluster_union([host, stub_union])
        assert len(u.toSubpathPolygons()) == 1
        segs = stroke_segments(host, boundary_segments(u))
        on_face = sorted((min(a.x(), b.x()), max(a.x(), b.x()))
                         for a, b in segs
                         if abs(a.y() - 50) < 1e-6 and abs(b.y() - 50) < 1e-6)
        assert on_face == [(0.0, 650.0), (750.0, 2000.0)]

    def test_lone_body_strokes_every_edge(self, qapp):
        body = _poly((0, 50), (1000, 50), (1000, -50), (0, -50))
        segs = stroke_segments(body, boundary_segments(cluster_union([body])))
        assert sum(math.hypot(b.x() - a.x(), b.y() - a.y())
                   for a, b in segs) == pytest.approx(2200.0)

    def test_l_miter_edge_is_not_stroked(self, qapp):
        a = _poly((0, 50), (950, 50), (1050, -50), (0, -50))
        b = _poly((950, 50), (950, 1000), (1050, 1000), (1050, -50))
        segs = stroke_segments(a, boundary_segments(cluster_union([a, b])))
        for p, q in segs:   # no stroked piece runs along the miter diagonal
            assert not (abs((p.x() - 950) + (p.y() - 50)) < 1e-6
                        and abs((q.x() - 950) + (q.y() - 50)) < 1e-6)

    def test_stroke_segments_drop_slivers(self, qapp):
        """Edge case (design): pieces shorter than WALL_OUTLINE_MIN_SEG."""
        body = _poly((0, 50), (1000, 50), (1000, -50), (0, -50))
        sliver = [(QPointF(400, 50), QPointF(400.5, 50))]
        assert stroke_segments(body, sliver) == []

    def test_visible_corners_exclude_hidden_junction_corner(self, qapp):
        a = _poly((0, 50), (950, 50), (1050, -50), (0, -50))
        b = _poly((950, 50), (950, 1000), (1050, 1000), (1050, -50))
        corners = visible_corners(a, boundary_segments(cluster_union([a, b])))
        keys = {(round(p.x(), 6), round(p.y(), 6)) for p in corners}
        assert (950.0, 50.0) in keys          # inner mitred corner: visible
        assert (1050.0, -50.0) in keys        # outer mitred corner: visible
        assert (0.0, 50.0) in keys and (0.0, -50.0) in keys

    def test_visible_corners_drop_collinear_seam_vertex(self, qapp):
        """A union vertex between two collinear boundary edges (the seam of
        a straight-through join, here with float noise) is not a corner."""
        a = _poly((0, 100), (3000, 100), (3000, -100), (0, -100))
        b = _poly((3000, 100.0000001), (6000, 100), (6000, -100),
                  (3000, -100))
        boundary = [
            (QPointF(0, 100), QPointF(3000, 100.0000001)),
            (QPointF(3000, 100.0000001), QPointF(6000, 100)),
            (QPointF(6000, 100), QPointF(6000, -100)),
            (QPointF(6000, -100), QPointF(0, -100)),
            (QPointF(0, -100), QPointF(0, 100)),
        ]
        for body in (a, b):
            keys = {(round(p.x()), round(p.y()))
                    for p in visible_corners(body, boundary)}
            assert (3000, 100) not in keys
        assert (0, 100) in {(round(p.x()), round(p.y()))
                            for p in visible_corners(a, boundary)}
