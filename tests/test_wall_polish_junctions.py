"""Wall polish junction guards: G3 (per-level joins, D4) and the outline
cache (D2/D6); G1/G2 pixel guards are added in Task 4."""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.level_manager import LevelManager
from firepro3d.wall import WallSegment


def _ms():
    """Model_Space with Levels 1-5, 3 m apart (Level 1/2 elevations as the
    LevelManager defaults them)."""
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    s._level_manager = LevelManager()
    lm = s._level_manager
    e1 = lm.get("Level 1").elevation
    if lm.get("Level 2") is None:
        lm.add_level("Level 2", elevation=e1 + 3000.0)
    e2 = lm.get("Level 2").elevation
    for i, name in enumerate(("Level 3", "Level 4", "Level 5"), start=1):
        lm.add_level(name, elevation=e2 + 3000.0 * i)
    return s


def _view(s, level):
    """Apply a plan view of *level* whose range excludes adjacent floors."""
    e = s._level_manager.get(level).elevation
    s._level_manager.apply_to_scene(s, active_level=level,
                                    view_height=e + 1200.0,
                                    view_depth=e - 300.0)


def _wall(s, p1, p2, base="Level 1", top="Level 2", th=200.0):
    w = WallSegment(QPointF(*p1), QPointF(*p2), thickness_mm=th)
    w._base_level, w._top_level = base, top
    s.addItem(w)
    s._walls.append(w)
    # precondition for the literal mm coordinates below: default calibration
    # (ScaleManager.paper_to_scene = paper_mm * px_per_mm(1) * drawing_scale)
    assert abs(w.half_thickness_scene() - th / 2.0) < 1e-9
    return w


def _on_segment(pt, a, b, tol=1e-3):
    dx, dy = b.x() - a.x(), b.y() - a.y()
    L = math.hypot(dx, dy)
    if L == 0.0:
        return False
    t = ((pt.x() - a.x()) * dx + (pt.y() - a.y()) * dy) / L
    d = abs((pt.x() - a.x()) * dy - (pt.y() - a.y()) * dx) / L
    return d <= tol and -tol <= t <= L + tol


def _stroked(wall, pt):
    return any(_on_segment(pt, a, b) for a, b in wall.outline().stroke_segments)


class TestPerLevelJoins:
    def test_offlevel_wall_never_joins(self, qapp):
        s = _ms()
        upper = _wall(s, (0, 0), (2000, 0), "Level 3", "Level 4")
        lower = _wall(s, (2000, 0), (2000, 1500), "Level 1", "Level 2")
        _view(s, "Level 3")
        assert not lower.isVisible() and upper.isVisible()   # precondition
        o = upper.outline()
        assert o.solid[1] is False
        p1l, p1r, p2r, p2l = o.quad
        end_mid = QPointF((p2l.x() + p2r.x()) / 2, (p2l.y() + p2r.y()) / 2)
        assert _stroked(upper, end_mid)                       # end edge drawn

    def test_both_visible_still_join(self, qapp):
        """Positive control: a view range spanning both walls joins them."""
        s = _ms()
        upper = _wall(s, (0, 0), (2000, 0), "Level 1", "Level 4")
        lower = _wall(s, (2000, 0), (2000, 1500), "Level 1", "Level 2")
        _view(s, "Level 1")
        assert upper.isVisible() and lower.isVisible()
        assert upper.outline().solid[1] is True

    def test_shaft_tee_breaks_only_where_visible(self, qapp):
        s = _ms()
        shaft = _wall(s, (0, 0), (4000, 0), "Level 1", "Level 5")
        tee = _wall(s, (2000, 0), (2000, 2000), "Level 3", "Level 4", th=150.0)
        near_face_at_tee = QPointF(2000, 100)      # shaft left face, y=+100
        _view(s, "Level 3")
        assert shaft.isVisible() and tee.isVisible()
        assert not _stroked(shaft, near_face_at_tee)   # T-break on L3
        _view(s, "Level 1")
        assert shaft.isVisible() and not tee.isVisible()
        assert _stroked(shaft, near_face_at_tee)       # continuous on L1


class TestOutlineCache:
    def test_tee_union_end_reaches_host_centerline(self, qapp):
        s = _ms()
        host = _wall(s, (0, 0), (4000, 0))
        stub = _wall(s, (2000, 0), (2600, 1500))
        o = stub.outline_geometry()
        assert o.solid[0] is True                       # coped body
        ys = sorted(round(o.union_body.at(i).y(), 6)
                    for i in range(o.union_body.count()))
        assert ys[0] == pytest.approx(0.0, abs=1e-6)    # union end on y=0
        assert min(o.body.at(i).y()
                   for i in range(o.body.count())) == pytest.approx(100.0)

    def test_alignment_set_after_construction_rebuilds(self, qapp):
        """D3: the _alignment property setter invalidates (placement and
        from_dict assign it after __init__)."""
        s = _ms()
        w = _wall(s, (0, 0), (3000, 0))
        before = w.path().boundingRect()
        w._alignment = "Left"
        after = w.path().boundingRect()
        assert after.top() == pytest.approx(0.0, abs=1e-6)
        assert before.top() < -1.0

    def test_removed_neighbour_releases_join(self, qapp):
        s = _ms()
        a = _wall(s, (0, 0), (2000, 0))
        b = _wall(s, (2000, 0), (2000, 1500))
        assert a.outline().solid[1] is True
        s._walls.remove(b)
        s.removeItem(b)                         # Model_Space delete order
        assert a.outline().solid[1] is False
        assert len(a.outline().caps) == 2

    def test_unjoined_overlap_strokes_full_body(self, qapp):
        """AC1: crossing walls that do not join each stroke their full body."""
        s = _ms()
        a = _wall(s, (0, 0), (4000, 0))
        b = _wall(s, (2000, -2000), (2000, 2000))
        for w in (a, b):
            total = sum(math.hypot(q.x() - p.x(), q.y() - p.y())
                        for p, q in w.outline().stroke_segments)
            assert total == pytest.approx(2 * 4000 + 2 * 200, abs=1e-6)
