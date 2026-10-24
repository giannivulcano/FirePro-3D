"""Wall polish smoke round 1 (S1): F1 tall-wall snapping, F2 tee reach +
mutual-tee guard, F3 overhanging tee stub, F4 miter fill seam."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import (QGraphicsEllipseItem, QGraphicsLineItem,
                             QGraphicsPathItem, QGraphicsRectItem)

from firepro3d.level_manager import LevelManager
from firepro3d.snap_engine import SnapEngine, is_snap_target
from firepro3d.wall import WallSegment, ALIGN_LEFT


def _ms():
    from firepro3d.model_space import Model_Space
    return Model_Space()


def _add(s, p1, p2, th=200.0, align=ALIGN_LEFT):
    w = WallSegment(QPointF(*p1), QPointF(*p2), thickness_mm=th)
    w._alignment = align
    s.addItem(w)
    s._walls.append(w)
    return w


# ── F1: walls above z 150 stay snap targets ─────────────────────────────────

def test_f1_tall_wall_corner_snaps_after_level_z(qapp):
    s = _ms()
    s._level_manager = LevelManager()
    lm = s._level_manager
    lm.add_level("Level 99", elevation=72000.0)
    w = _add(s, (1000, 1000), (6000, 1000), align="Center")
    w._base_level, w._top_level = "Level 1", "Level 99"
    lm.apply_to_scene(s, active_level="Level 1", view_height=80000.0,
                      view_depth=-1000.0)
    assert w.zValue() > 150, w.zValue()
    corner = w.quad_points()[0]
    r = SnapEngine().find(QPointF(corner), s, QTransform())
    assert r is not None
    assert (r.point - corner).manhattanLength() < 1e-6
    assert r.name == "face-left-corner-A"


def _overlays():
    from firepro3d.node import Node
    from firepro3d.pipe import Pipe
    out = []
    for z in (200, 201, 250, 999, 9999):
        for cls in (QGraphicsLineItem, QGraphicsRectItem,
                    QGraphicsEllipseItem, QGraphicsPathItem):
            it = cls()
            it.setZValue(z)
            out.append(it)
    # preview pipe / preview node: real model classes at overlay z
    n1, n2 = Node(0, 0), Node(1000, 0)
    pp = Pipe(n1, n2)
    pp.setZValue(200)
    nn = Node(5, 5)
    nn.setZValue(200)
    out += [pp, nn]
    return out


def test_f1_overlays_stay_excluded(qapp):
    s = _ms()
    for it in _overlays():
        s.addItem(it)
        assert not is_snap_target(it, skip_pipes=False), (
            type(it).__name__, it.zValue())


def test_f1_find_ignores_overlay_line(qapp):
    s = _ms()
    it = QGraphicsLineItem(3000, 3000, 5000, 3000)
    it.setZValue(200)
    s.addItem(it)
    r = SnapEngine().find(QPointF(3000, 3000), s, QTransform())
    assert r is None or r.source_item is not it


# ── F2 / F3: tee reach, mutual-tee guard, overhanging stub ──────────────────

import math  # noqa: E402

from firepro3d.wall_outline import cluster_union  # noqa: E402


def _on_seg(pt, a, b, tol=1e-3):
    dx, dy = b.x() - a.x(), b.y() - a.y()
    L = math.hypot(dx, dy)
    if L == 0.0:
        return False
    t = ((pt.x() - a.x()) * dx + (pt.y() - a.y()) * dy) / L
    d = abs((pt.x() - a.x()) * dy - (pt.y() - a.y()) * dx) / L
    return d <= tol and -tol <= t <= L + tol


def _stroked(wall, pt):
    return any(_on_seg(pt, a, b) for a, b in wall.outline().stroke_segments)


def _subpaths(walls):
    path = cluster_union([w.outline_geometry().union_body for w in walls])
    return len(path.toSubpathPolygons())


def test_f2_stub_near_host_end_tees_into_host(qapp):
    """Walls 42/41/45: stub on the host face at t~0.002 beside the host's L."""
    s = _ms()
    host = _add(s, (16381.47, 11363.77), (10836.15, 11363.77), align="Right")
    l41 = _add(s, (16381.47, 9113.12), (16381.47, 11363.77), align="Right")
    stub = _add(s, (16370.83, 17128.35), (16370.83, 11563.77), align="Right")
    t = (16381.47 - 16370.83) / 5545.32
    assert t < 0.05                                      # precondition
    o = stub.outline()
    assert o.solid[1] is True                            # coped to the host
    assert len(o.caps) == 1                              # only the free pt1 cap
    assert host in o.neighbours
    assert not _stroked(host, QPointF(16270.83, 11563.77))   # face is split
    assert _subpaths([host, l41, stub]) == 1


def _walls_33_37(s):
    w32 = _add(s, (21938.76, 16889.92), (21938.76, 11333.01), align="Right")
    w33 = _add(s, (21938.76, 11333.01), (18884.84, 11333.01), align="Right")
    w37 = _add(s, (18884.84, 11533.01), (18884.84, 9044.15), align="Left")
    return w32, w33, w37


def test_f2_mutual_tee_leaves_no_notch(qapp):
    """Walls 33/37: each end lies on the other's face at their L.  Neither
    tees; the bodies still cover the corner square."""
    s = _ms()
    w32, w33, w37 = _walls_33_37(s)
    path = cluster_union([w.outline_geometry().union_body
                          for w in (w32, w33, w37)])
    cx, cy = 18984.84, 11433.01
    for dx in (-95.0, 0.0, 95.0):
        for dy in (-95.0, 0.0, 95.0):
            assert path.contains(QPointF(cx + dx, cy + dy)), (dx, dy)
    assert w33._join_ends()["hosts"][1] is None
    assert w37._join_ends()["hosts"][0] is None


def test_f3_overhanging_stub_end_is_stroked_and_cornered(qapp):
    """Walls 44/45/47: a 505 mm stub wider than what is left of the host."""
    s = _ms()
    w44 = _add(s, (13812.74, 17128.35), (16370.83, 17128.35), align="Right")
    w45 = _add(s, (16370.83, 17128.35), (16370.83, 11563.77), align="Right")
    w47 = _add(s, (16162.0, 17064.96), (16162.0, 19401.93), th=505.0,
               align="Right")
    o = w47.outline()
    assert o.solid[0] is True and w44 in o.neighbours       # coped tee
    assert _stroked(w47, QPointF(16520.0, 17128.35))        # overhang edge
    corner = QPointF(16667.0, 17128.35)
    assert any(abs(c.x() - corner.x()) < 1e-3 and abs(c.y() - corner.y()) < 1e-3
               for c in o.corners), o.corners
    assert _subpaths([w44, w45, w47]) == 1


def test_f2_placement_pass2_tees_near_host_end(qapp):
    """The placement tee snap uses the same rule: a new wall ending 11 mm
    from the host's end (t ~ 0.002) snaps onto the host centerline."""
    s = _ms()
    host = _add(s, (0, 0), (5545.0, 0), align="Center")
    new = _add(s, (11.0, 2000.0), (11.0, 30.0), align="Center")
    s._auto_join_wall(new)
    assert new.pt2.x() == pytest.approx(11.0, abs=1e-6)
    assert new.pt2.y() == pytest.approx(0.0, abs=1e-6)     # on the centerline
    assert host in new.outline().neighbours
