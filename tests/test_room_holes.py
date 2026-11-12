"""Room holes (room-detection rework §2): model, paint, persistence. Geometry is the 1b
island case: outer ring = inner faces of a 10000x8000 Center-200 rect, hole = the outline of
a 2000x2000 inner rect's walls (hand: 9800*7800 = 76.44e6, 2200*2200 = 4.84e6)."""
import json
import math
from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.room import Room

OUTER = [(100.0, 100.0), (9900.0, 100.0), (9900.0, 7900.0), (100.0, 7900.0)]
HOLE = [(3900.0, 2900.0), (6100.0, 2900.0), (6100.0, 5100.0), (3900.0, 5100.0)]


def _pts(xy):
    return [QPointF(x, y) for x, y in xy]


def _outer_room():
    return Room(_pts(OUTER), holes=[_pts(HOLE)])


def _render(scene, src: QRectF):
    img = QImage(100, 100, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, 100, 100), src)
    p.end()
    return img


class TestModel:
    def test_net_area_and_perimeter(self, qapp):
        r = _outer_room()
        assert r._compute_area_mm2() == pytest.approx(76.44e6 - 4.84e6)            # 71.6e6
        # D-R2: outer 2*(9800+7800) = 35200 + hole 4*2200 = 8800
        assert r._compute_perimeter_mm() == pytest.approx(44000.0)

    def test_contains_point_excludes_the_hole(self, qapp):
        r = _outer_room()
        assert r.contains_point(QPointF(1000, 1000))
        assert not r.contains_point(QPointF(5000, 4000))        # inside HOLE
        assert not r.contains_point(QPointF(20000, 0))          # outside OUTER

    def test_holes_property_returns_copies(self, qapp):
        r = _outer_room()
        r.holes[0][0].setX(0.0)
        assert r.holes[0][0].x() == 3900.0

    def test_hole_less_room_keeps_full_shape_and_record(self, qapp):
        r = Room(_pts(OUTER))
        assert r.holes == [] and r.shape().contains(QPointF(5000, 4000))
        assert "holes" not in r.to_dict()

    def test_shape_excludes_the_hole(self, qapp):
        r = _outer_room()
        assert r.shape().contains(QPointF(1000, 1000))
        assert not r.shape().contains(QPointF(5000, 4000))

    def test_translate_and_rotate_carry_the_holes(self, qapp):
        r = _outer_room()
        r.translate(8000.0, 0.0)
        assert [(p.x(), p.y()) for p in r.holes[0]] == [(x + 8000.0, y) for x, y in HOLE]
        r = _outer_room()
        r.manip_rotate(180.0, QPointF(0, 0))      # 180 deg about the origin: (x, y) -> (-x, -y)
        got = sorted((round(p.x(), 6), round(p.y(), 6)) for p in r.holes[0])
        assert got == sorted((-x, -y) for x, y in HOLE)

    def test_tag_anchor_leaves_the_hole(self, qapp):
        # D-R3: vertex mean (5000, 4000) is in HOLE; y = 4000 crosses 100 | 3900, 6100 | 9900
        # -> two 3800-wide inside intervals, the first wins -> anchor x = (100+3900)/2 = 2000
        r = _outer_room()
        r.name = "A"
        r._update_label()
        assert (r._tag.pos().x(), r._tag.pos().y()) == pytest.approx((2000.0, 4000.0))
        assert (r._centroid().x(), r._centroid().y()) == pytest.approx((2000.0, 4000.0))

    def test_sprinkler_in_the_hole_is_not_the_rooms(self, qapp, make_model_space):
        ms = make_model_space()                    # no LevelManager: XY test only (z skipped)
        r = _outer_room()
        ms.addItem(r)
        ms._rooms.append(r)
        n_hole = ms.add_node(5000, 4000)
        ms.add_sprinkler(n_hole)
        n_net = ms.add_node(1000, 1000)
        ms.add_sprinkler(n_net)
        assert {id(s) for s in r._detect_sprinklers()} == {id(n_net.sprinkler)}


class TestPaint:
    def test_paint_leaves_the_hole_unfilled(self, qapp):
        from firepro3d.model_space import Model_Space
        ms, ctl = Model_Space(), Model_Space()
        r = _outer_room()
        ms.addItem(r)
        ms._rooms.append(r)
        hole_src = QRectF(4500, 3500, 1000, 1000)   # wholly inside HOLE
        net_src = QRectF(8000, 6000, 1000, 1000)    # wholly in the net area, far from the origin glyph
        assert _render(ms, net_src).pixel(50, 50) != _render(ctl, net_src).pixel(50, 50)   # premise
        assert _render(ms, hole_src).pixel(50, 50) == _render(ctl, hole_src).pixel(50, 50)

    def test_selection_outline_traces_the_hole_ring(self, qapp):
        from firepro3d.model_space import Model_Space
        ms = Model_Space()
        r = _outer_room()
        ms.addItem(r)
        ms._rooms.append(r)
        r.setSelected(True)
        img = _render(ms, QRectF(3850, 3950, 100, 100))   # 1 px/mm; hole edge x = 3900 -> column 50
        cols = [QColor(img.pixel(x, 50)) for x in range(46, 55)]
        assert any(c.red() > 180 and c.green() < 90 and c.blue() < 90 for c in cols)


class TestPersistence:
    def test_holes_round_trip_through_save_and_load(self, qapp, shown_model_view, tmp_path):
        view, scene = shown_model_view
        r = _outer_room()
        r.name = "A"
        scene.addItem(r)
        scene._rooms.append(r)
        f = tmp_path / "holes.fpd"
        scene.save_to_file(str(f))
        rec = json.loads(f.read_text(encoding="utf-8"))
        assert rec["rooms"][0]["holes"] == [[list(p) for p in HOLE]]
        scene.load_from_file(str(f))
        (room,) = scene._rooms
        assert [(p.x(), p.y()) for p in room.holes[0]] == HOLE
        assert room._compute_area_mm2() == pytest.approx(71.6e6)

    def test_old_file_room_loads_and_resaves_unchanged(self, qapp, shown_model_view, tmp_path):
        view, scene = shown_model_view
        src = Path(__file__).parent / "fixtures" / "ph1_pre_phasing_v12.fpd"
        old = json.loads(src.read_text(encoding="utf-8"))
        assert len(old["rooms"]) == 1 and "holes" not in old["rooms"][0]      # premise: old record
        scene.load_from_file(str(src))
        assert scene._rooms[0].holes == []
        out = tmp_path / "resaved.fpd"
        scene.save_to_file(str(out))
        new = json.loads(out.read_text(encoding="utf-8"))
        assert new["rooms"][0] == old["rooms"][0]          # byte-identical room record (§2.6)
