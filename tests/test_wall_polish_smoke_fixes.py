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
