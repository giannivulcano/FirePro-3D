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
                 source=QRectF(0.0, 0.0, 420.0, 220.0),
                 bg=Qt.GlobalColor.white) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(bg)
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


class _FakeViewport:
    """Minimal stand-in exposing exactly what _capture reads from the
    viewport widget: rect() and devicePixelRatioF()."""
    def __init__(self, w, h, dpr=1.0):
        from PyQt6.QtCore import QRect
        self._r = QRect(0, 0, w, h)
        self._dpr = dpr

    def rect(self):
        return self._r

    def devicePixelRatioF(self):
        return self._dpr


class _FakeView:
    """Stand-in exposing viewport()/viewportTransform()/mapToScene(QRect).
    Identity transform => scene coords == viewport px coords."""
    def __init__(self, w=400, h=300, dpr=1.0):
        self._vp = _FakeViewport(w, h, dpr)

    def viewport(self):
        return self._vp

    def viewportTransform(self):
        from PyQt6.QtGui import QTransform
        return QTransform()

    def mapToScene(self, rect):
        from PyQt6.QtGui import QPolygonF
        return QPolygonF(QRectF(rect))


class TestCapture:
    def test_capture_contains_underlay_pixels(self, qapp):
        scene, record, group = make_underlay_scene()
        got = scene._underlay_freeze._capture(_FakeView())
        assert got is not None
        pixmap, scene_rect, z = got
        img = pixmap.toImage()
        assert has_bait(img)

    def test_capture_background_is_transparent(self, qapp):
        """Theme constraint: bg alpha 0 so the live theme shows through."""
        scene, record, group = make_underlay_scene()
        pixmap, scene_rect, z = scene._underlay_freeze._capture(_FakeView())
        img = pixmap.toImage()
        corner = img.pixelColor(img.width() - 1, img.height() - 1)
        assert corner.alpha() == 0

    def test_capture_clamped_at_extreme_size(self, qapp):
        """Memory bound: per-axis clamp holds regardless of viewport/DPR."""
        from firepro3d.constants import UNDERLAY_FREEZE_MAX_PX
        scene, record, group = make_underlay_scene()
        got = scene._underlay_freeze._capture(_FakeView(9000, 9000, dpr=2.0))
        assert got is not None
        pixmap, scene_rect, z = got
        assert pixmap.width() <= UNDERLAY_FREEZE_MAX_PX
        assert pixmap.height() <= UNDERLAY_FREEZE_MAX_PX

    def test_capture_skips_hidden_layer(self, qapp):
        scene, record, group = make_underlay_scene()
        scene.set_underlay_layer_hidden(record, group, "L1", True)
        got = scene._underlay_freeze._capture(_FakeView())
        # Whole (only) layer hidden -> nothing to capture
        assert got is None or not has_bait(got[0].toImage())

    def test_capture_none_without_underlays(self, qapp):
        scene = Model_Space()
        assert scene._underlay_freeze._capture(_FakeView()) is None


class TestFreezeLifecycle:
    def test_begin_adds_pixmap_and_render_still_shows_underlay(self, qapp):
        scene, record, group = make_underlay_scene()
        scene._underlay_freeze.begin(_FakeView())
        try:
            assert scene._underlay_freeze.frozen is True
            pm_items = [i for i in scene.items()
                        if isinstance(i, QGraphicsPixmapItem)]
            assert len(pm_items) == 1
            # The user still SEES the underlay (via the pixmap blit).
            # Render 1:1 onto a TRANSPARENT background: the capture bakes
            # antialiased hairlines into the pixmap at partial alpha (the
            # accepted transient bitmap-stretch look), so compositing over
            # white — or resampling at a non-1:1 scale — shifts the bait
            # colour past has_bait's tolerance even though the blit is
            # exactly what a live AA view shows. Transparent bg + 1:1
            # preserves the blitted pixels' own colour for the check.
            assert has_bait(render_scene(
                scene, w=420, h=220, bg=Qt.GlobalColor.transparent))
        finally:
            scene._underlay_freeze.end()

    def test_end_removes_pixmap_and_restores_vectors(self, qapp):
        scene, record, group = make_underlay_scene()
        scene._underlay_freeze.begin(_FakeView())
        scene._underlay_freeze.end()
        assert scene._underlay_freeze.frozen is False
        assert not [i for i in scene.items()
                    if isinstance(i, QGraphicsPixmapItem)]
        assert has_bait(render_scene(scene))

    def test_begin_noop_without_underlays(self, qapp):
        scene = Model_Space()
        scene._underlay_freeze.begin(_FakeView())
        assert scene._underlay_freeze.frozen is False

    def test_pixmap_item_not_serialized(self, qapp, tmp_path):
        scene, record, group = make_underlay_scene()
        scene._underlay_freeze.begin(_FakeView())
        try:
            out = tmp_path / "frozen.fpd"
            scene.save_to_file(str(out))
            payload = json.loads(out.read_text())
            assert len(payload["underlays"]) == 1   # record only, no extras
        finally:
            scene._underlay_freeze.end()
        # Frozen pixmap must not leak into ANY payload collection: an
        # unfrozen save of the very same scene serializes identically.
        out2 = tmp_path / "unfrozen.fpd"
        scene.save_to_file(str(out2))
        payload2 = json.loads(out2.read_text())
        assert (json.dumps(payload, sort_keys=True)
                == json.dumps(payload2, sort_keys=True))

    def test_snap_index_unaffected_while_frozen(self, qapp):
        """Hard constraint: snap queries the geometry index, not paint.

        Real query() parity: the UnderlaySnapIndex (group data slot 4,
        attached by _attach_snap_index) answers a rect over the bait lines
        identically frozen vs unfrozen.
        """
        scene, record, group = make_underlay_scene()
        index = group.data(4)
        assert index is not None
        before = index.query(100.0, 20.0, 50.0, 20.0)
        assert before, "query rect must hit real bait geometry unfrozen"
        scene._underlay_freeze.begin(_FakeView())
        try:
            assert scene._underlay_freeze.frozen is True
            after = index.query(100.0, 20.0, 50.0, 20.0)
            assert after == before
        finally:
            scene._underlay_freeze.end()
