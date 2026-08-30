"""Behavioral tests for the underlay gesture freeze (freeze-blit, spec §18).

No timing assertions anywhere in this file — state transitions and rendered
pixels only. Perf numbers come from tools/perf_probe_underlay.py.
"""
import json

import pytest
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, QEvent
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene

from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.underlay import Underlay
from firepro3d.underlay_freeze import UnderlayFreezeController, _UnderlayPathItem

BAIT = "#ff0022"          # colour bait — must come from REAL underlay geometry


def make_underlay_scene(n_lines: int = 40):
    """Model_Space with one REAL vector underlay built via the production
    builder (no synthetic stand-in items)."""
    scene = Model_Space()
    record = Underlay(type="pdf", path="synthetic.pdf", colour=BAIT)
    geoms = []
    for i in range(n_lines):
        y = 10.0 + i * 5.0
        geoms.append({"kind": "path_points", "layer": "L1", "width": 0.0,
                      "closed": False,
                      "points": [[10.0, y], [400.0, y]]})
    result = scene._build_batched_underlay_group(geoms, record)
    assert result is not None
    group, layers = result
    scene._apply_underlay_display(group, record)
    scene._attach_snap_index(group, geoms, record)
    scene.underlays.append((record, group))
    return scene, record, group


def render_scene(scene, w=300, h=300,
                 source=QRectF(0.0, 0.0, 420.0, 220.0)) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.white)
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, w, h), source)
    p.end()
    return img


def has_bait(img: QImage) -> bool:
    bait = QColor(BAIT)
    for x in range(0, img.width(), 2):
        for y in range(0, img.height(), 2):
            c = img.pixelColor(x, y)
            if (abs(c.red() - bait.red()) < 40
                    and abs(c.green() - bait.green()) < 40
                    and abs(c.blue() - bait.blue()) < 40):
                return True
    return False


class TestPaintSkipItem:
    def test_children_are_freeze_aware_subclass(self, qapp):
        scene, record, group = make_underlay_scene()
        kids = group.childItems()
        assert kids, "builder produced no children"
        assert all(isinstance(k, _UnderlayPathItem) for k in kids)

    def test_unfrozen_renders_vectors(self, qapp):
        scene, record, group = make_underlay_scene()
        assert has_bait(render_scene(scene))

    def test_frozen_flag_suppresses_vector_paint(self, qapp):
        scene, record, group = make_underlay_scene()
        scene._underlay_freeze.frozen = True     # flag alone, no pixmap
        try:
            assert not has_bait(render_scene(scene))
        finally:
            scene._underlay_freeze.frozen = False
        assert has_bait(render_scene(scene))     # restored


class TestControllerLifecycle:
    def test_scene_owns_controller(self, qapp):
        scene = Model_Space()
        assert isinstance(scene._underlay_freeze, UnderlayFreezeController)
        assert scene._underlay_freeze.frozen is False

    def test_end_when_not_frozen_is_noop(self, qapp):
        scene = Model_Space()
        scene._underlay_freeze.end()             # must not raise
        scene.abort_underlay_freeze()            # public alias, must not raise
        assert scene._underlay_freeze.frozen is False
