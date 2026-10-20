"""Pick point mode guards (HF4 design §2) -- real scene + shown view, posted events."""
import math

import pytest
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from tests._snap_polish_helpers import click, close_view, make_view, move


def _statuses(scene):
    log = []
    orig = scene._show_status
    scene._show_status = lambda msg, timeout=5000: (log.append(msg), orig(msg, timeout))
    return log


def _add(scene, items):
    for it in items:
        scene.addItem(it)
    return items


def _square(x0, y0, size):
    from firepro3d.geometry_2d import LineItem
    a, b = QPointF(x0, y0), QPointF(x0 + size, y0)
    c, d = QPointF(x0 + size, y0 + size), QPointF(x0, y0 + size)
    return [LineItem(a, b), LineItem(b, c), LineItem(c, d), LineItem(d, a)]


def _circle_two_lines(scene):
    from firepro3d.geometry_2d import CircleItem, LineItem
    return _add(scene, [CircleItem(QPointF(0, 0), 40.0),
                        LineItem(QPointF(-60, 0), QPointF(60, 0)),
                        LineItem(QPointF(0, -60), QPointF(0, 60))])


@pytest.fixture
def pick(qapp):
    view, scene = make_view(role="block_editor", scale=2.0, mode=None)
    yield view, scene
    close_view(view, scene)


class TestMode:
    def test_fill_empty_selection_enters_mode(self, pick):
        view, scene = pick
        log = _statuses(scene)
        assert scene.fill_selected_items() is None
        assert scene.mode == "pick_region"
        assert log[-1] == "Click inside an enclosed area (Esc to finish)"

    def test_fill_non_candidates_only_enters_mode(self, pick):
        from firepro3d.text_item import TextAnnotationData, TextItem
        view, scene = pick
        txt = TextItem(TextAnnotationData(text="x", x=10.0, y=10.0, height_mm=100.0))
        scene.addItem(txt); scene._texts.append(txt); txt.setSelected(True)
        assert scene.fill_selected_items() is None
        assert scene.mode == "pick_region" and scene.selectedItems() == []

    def test_fill_with_candidates_runs_hf3(self, pick):
        view, scene = pick
        for ln in _add(scene, _square(0, 0, 100)):
            scene._draw_lines.append(ln); ln.setSelected(True)
        region = scene.fill_selected_items()
        assert region is not None and scene.mode != "pick_region"
        assert scene._filled_regions == [region] and scene.selectedItems() == [region]

    def test_plan_scene_refuses_mode(self, qapp):
        from firepro3d.model_space import Model_Space
        scene = Model_Space()        # scene_role "plan"
        assert scene.fill_selected_items() is None and scene.mode != "pick_region"

    def test_escape_and_right_click_end_mode(self, pick):
        view, scene = pick
        _circle_two_lines(scene)
        scene.set_mode("pick_region")
        move(view, QPointF(15, 15))
        assert scene._pick_region_preview is not None
        QTest.keyClick(view, Qt.Key.Key_Escape)
        QApplication.processEvents()
        assert scene.mode in (None, "select") and scene._pick_region_preview is None
        scene.set_mode("pick_region")
        move(view, QPointF(15, 15))
        vp = view.viewportTransform().map(QPointF(15, 15))
        ev = QMouseEvent(QEvent.Type.MouseButtonPress, vp, view.viewport().mapToGlobal(vp),
                         Qt.MouseButton.RightButton, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(view.viewport(), ev)
        from PyQt6.QtGui import QContextMenuEvent
        cev = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, vp.toPoint(), view.viewport().mapToGlobal(vp).toPoint())
        QApplication.sendEvent(view.viewport(), cev)
        QApplication.processEvents()
        assert scene.mode in (None, "select") and scene._pick_region_preview is None


class TestClick:
    def test_four_quadrant_clicks_four_regions_four_undo_steps(self, pick):
        from firepro3d.geometry_2d import ArcItem, LineItem
        view, scene = pick
        _circle_two_lines(scene)
        scene.set_mode("pick_region")
        pos0 = scene._undo_pos
        log = _statuses(scene)
        for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
            move(view, QPointF(sx * 15, sy * 15))
            click(view, QPointF(sx * 15, sy * 15))
            assert scene.mode == "pick_region"                       # AC6 stay in mode
        assert len(scene._filled_regions) == 4
        assert scene._undo_pos == pos0 + 4
        assert scene.selectedItems() == [scene._filled_regions[-1]]
        r0 = scene._filled_regions[0]
        assert sorted(type(p).__name__ for p in r0.pieces) == ["ArcItem", "LineItem", "LineItem"]
        assert log[-1] == "Filled Region created (1 loops)"
        assert abs(abs(_area(r0.path())) - math.pi * 40 * 40 / 4) < 5.0

    def test_ring_pick_fills_ring_not_centre(self, pick):
        from PyQt6.QtGui import QColor, QImage, QPainter
        from firepro3d.geometry_2d import CircleItem
        view, scene = pick
        _add(scene, [CircleItem(QPointF(0, 0), 40.0), CircleItem(QPointF(0, 0), 15.0)])
        scene.set_mode("pick_region")
        move(view, QPointF(30, 0)); click(view, QPointF(30, 0))
        assert len(scene._filled_regions) == 1 and len(scene._filled_regions[0]._loops) == 2
        img = QImage(100, 100, QImage.Format.Format_ARGB32); img.fill(QColor("white"))
        p = QPainter(img); scene.render(p, QRectF(0, 0, 100, 100), QRectF(-50, -50, 100, 100)); p.end()
        assert QColor(img.pixel(80, 50)).lightness() < 250     # in the ring: filled
        assert QColor(img.pixel(50, 50)).lightness() > 250     # centre: empty

    def test_leak_click_creates_nothing(self, pick):
        from firepro3d.geometry_2d import LineItem
        view, scene = pick
        a, b, c, d = QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)
        _add(scene, [LineItem(a, b), LineItem(b, c), LineItem(c, d), LineItem(d, QPointF(0, 1.5))])
        scene.set_mode("pick_region")
        log = _statuses(scene)
        pos0 = scene._undo_pos
        move(view, QPointF(50, 50))
        path, open_end, enclosed, covered = scene._pick_region_preview
        assert not enclosed and open_end is not None and open_end.y() <= 1.5 + 1e-6 and abs(open_end.x()) < 1e-6
        click(view, QPointF(50, 50))
        assert log[-1] == "Not enclosed" and scene._filled_regions == [] and scene._undo_pos == pos0

    def test_already_filled_refused(self, pick):
        view, scene = pick
        _add(scene, _square(0, 0, 100))
        scene.set_mode("pick_region")
        move(view, QPointF(50, 50)); click(view, QPointF(50, 50))
        assert len(scene._filled_regions) == 1
        log = _statuses(scene)
        pos0 = scene._undo_pos
        move(view, QPointF(50, 50))
        assert scene._pick_region_preview[3] is True                 # covered -> no tint
        click(view, QPointF(50, 50))
        assert log[-1] == "This area already has a Filled Region"
        assert len(scene._filled_regions) == 1 and scene._undo_pos == pos0

    def test_block_instance_edge_closes_face(self, pick):
        """A placed instance (rotated 30 deg) supplies an arc edge; a line closes against it.
        Construction idiom: tests/test_block_snap_geometry.py::_placed."""
        from firepro3d.block_definition import BlockDefinition
        from firepro3d.geometry_2d import ArcItem, LineItem
        from firepro3d.halo import halo_scene_path
        view, scene = pick
        # definition: one semicircle arc r=40 about the origin (0..180 deg y-up)
        arc = ArcItem(QPointF(0, 0), 40.0, 0.0, 180.0)
        defn = BlockDefinition.new(name="hf4-arc", library="L", series="S",
                                   origin=(0.0, 0.0), primitives=[arc.to_dict()])
        scene.register_block_definition(defn)
        inst = scene.place_block_instance(defn.id, (0.0, 0.0), rotation=30.0)   # pos tuple, as tests/_block_snap_helpers.POSES
        prims = [it for _b, it in inst.snap_primitives()]
        assert len(prims) == 1 and isinstance(prims[0], ArcItem)
        # close the half-disc with the chord between the posed arc's ends
        hp = halo_scene_path(prims[0])
        e0, e1 = hp.pointAtPercent(0.0), hp.pointAtPercent(1.0)
        _add(scene, [LineItem(e0, e1)])
        scene.set_mode("pick_region")
        mid = QPointF((e0.x() + e1.x()) / 2, (e0.y() + e1.y()) / 2)
        # a point inside the half-disc: chord midpoint pushed toward the arc's bulge
        bulge = hp.pointAtPercent(0.5)
        inside = QPointF((mid.x() + bulge.x()) / 2, (mid.y() + bulge.y()) / 2)
        move(view, inside); click(view, inside)
        assert len(scene._filled_regions) == 1
        kinds = sorted(type(p).__name__ for p in scene._filled_regions[0].pieces)
        assert kinds == ["ArcItem", "LineItem"]

    def test_face_larger_than_window_is_found(self, pick):
        view, scene = pick
        _add(scene, _square(-200, -200, 400))        # 400 mm square >> 50 mm window
        scene.set_mode("pick_region")
        move(view, QPointF(0, 0)); click(view, QPointF(0, 0))
        assert len(scene._filled_regions) == 1

    def test_undo_invalidates_arrangement_cache(self, pick):
        view, scene = pick
        lines = _add(scene, _square(0, 0, 100))
        for ln in lines:
            scene._draw_lines.append(ln)
        scene.push_undo_state()
        scene.set_mode("pick_region")
        move(view, QPointF(50, 50))
        assert scene._pick_region_preview[2] is True
        scene.removeItem(lines[0]); scene._draw_lines.remove(lines[0])
        scene.push_undo_state()
        move(view, QPointF(50, 50.5))
        assert scene._pick_region_preview[2] is False            # rebuilt: the gap is seen


def _area(path):
    from PyQt6.QtGui import QTransform
    k = 64.0                      # production flatten scale (LINETYPE_CURVE_FLATTEN_SCALE)
    polys = path.toSubpathPolygons(QTransform.fromScale(k, k))
    s = 0.0
    for poly in polys:
        pts = [(p.x() / k, p.y() / k) for p in poly]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
            s += x0 * y1 - x1 * y0
    return s / 2


class TestHover:
    def _px(self, view, scene_pt):
        img = view.grab().toImage()
        vp = view.viewportTransform().map(scene_pt)
        vo = view.viewport().mapTo(view, vp.toPoint())
        return QColor(img.pixel(vo.x(), vo.y()))

    def test_hover_face_sets_preview_and_paints_tint(self, pick):
        view, scene = pick
        _add(scene, _square(-40, -40, 80))
        scene.set_mode("pick_region")
        QApplication.processEvents()
        self._px(view, QPointF(0, 0))                            # discard the first-paint grab
        before = self._px(view, QPointF(0, 0))
        before_out = self._px(view, QPointF(100, 100))
        move(view, QPointF(0, 0))
        path, open_end, enclosed, covered = scene._pick_region_preview
        assert enclosed and not covered and path is not None and path.contains(QPointF(0, 0))
        QApplication.processEvents()
        inside = self._px(view, QPointF(0, 0))
        outside = self._px(view, QPointF(100, 100))
        assert inside != before and inside != outside            # accent tint painted inside only
        assert outside == before_out

    def _vp_px(self, view, vp_x, vp_y):
        """Pixel of the grabbed view at viewport coords (vp_x, vp_y)."""
        from PyQt6.QtCore import QPoint
        img = view.grab().toImage()
        vo = view.viewport().mapTo(view, QPoint(int(vp_x), int(vp_y)))
        return QColor(img.pixel(vo.x(), vo.y()))

    def test_hover_gap_sets_label_and_ring(self, pick):
        from firepro3d.geometry_2d import LineItem
        view, scene = pick
        a, b, c, d = QPointF(-40, -40), QPointF(40, -40), QPointF(40, 40), QPointF(-40, 40)
        _add(scene, [LineItem(a, b), LineItem(b, c), LineItem(c, d), LineItem(d, QPointF(-40, -38.5))])
        scene.set_mode("pick_region")
        inside_before = self._px(view, QPointF(20, 20))
        move(view, QPointF(0, 0))
        path, open_end, enclosed, covered = scene._pick_region_preview
        assert not enclosed and not covered and open_end is not None
        assert abs(open_end.x() + 40.0) < 1e-6 and -40.0 - 1e-6 <= open_end.y() <= -38.5 + 1e-6
        QApplication.processEvents()
        # 6 px ring (pen 2 px) around the open end: sample 6 px to its right in viewport space
        c = view.viewportTransform().map(open_end)
        ring = self._vp_px(view, c.x() + 6.0, c.y())
        assert ring.red() > 150 and ring.green() < 100                     # red ring stroke
        # label background: 2 px left of the text origin (inside the 4 px padding, no glyph there)
        vp = view._last_vp_pos
        label_bg = self._vp_px(view, vp.x() + 14 - 2, vp.y() - 24)
        assert label_bg.red() > 150 and label_bg.green() < 100             # red "Not enclosed" background
        # no accent tint inside the leaking area (a pixel away from the label)
        assert self._px(view, QPointF(20, 20)) == inside_before

    def test_covered_face_paints_nothing(self, pick):
        view, scene = pick
        _add(scene, _square(-40, -40, 80))
        scene.set_mode("pick_region")
        move(view, QPointF(0, 0)); click(view, QPointF(0, 0))
        QApplication.processEvents()
        filled = self._px(view, QPointF(0, 0))
        move(view, QPointF(1, 1))
        QApplication.processEvents()
        assert scene._pick_region_preview[3] is True
        assert self._px(view, QPointF(0, 0)) == filled          # region fill only, no accent tint on top
