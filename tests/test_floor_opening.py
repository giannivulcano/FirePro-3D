"""FloorOpening item + FloorSlab ownership / serialization / cut cache (spec A1-A3, A7).

Expected areas are hand-computed (shown inline); the slab is 4000 x 3000 = 12e6 mm^2.
"""
import pytest
from PyQt6.QtCore import QPointF as P
from PyQt6.QtWidgets import QGraphicsItem

from firepro3d.floor_slab import FloorSlab
from firepro3d.floor_opening import FloorOpening, drop_carried_voids
from tests.test_floor_elevation_model import _FakeLM, _FakeScene


def _rect(x0, y0, x1, y1):
    return [P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)]


def _shoelace(ring):
    n = len(ring)
    return abs(sum(ring[i].x() * ring[(i + 1) % n].y() - ring[(i + 1) % n].x() * ring[i].y()
                   for i in range(n))) / 2.0


def _material_area(slab):
    return sum(_shoelace(o) - sum(_shoelace(h) for h in hs) for o, hs in slab.cut_region())


def _xy(pts):
    return [(p.x(), p.y()) for p in pts]


def _slab_with_void(void=(1000, 1000, 2000, 2000)):
    slab = FloorSlab(points=_rect(0, 0, 4000, 3000))
    op = FloorOpening(_rect(*void), host=slab)
    slab.add_opening(op)
    return slab, op


# Today's FloorSlab.to_dict keys (AC7: a void-less slab writes exactly these).
_SLAB_KEYS = {"type", "points", "color", "name", "top_mode", "top_level", "top_offset_mm",
              "top_abs_z_mm", "bottom_mode", "bottom_level", "bottom_offset_mm",
              "bottom_abs_z_mm", "thickness_mm"}
_VOID_PTS = [(1000, 1000), (2000, 1000), (2000, 2000), (1000, 2000)]


def test_void_fields_and_category(qapp):
    slab, op = _slab_with_void()
    assert op.feature_id == "floor_sketched" and op._mark == ""
    assert op.host is slab and slab.openings == [op]
    assert op.display_category == "Opening"
    assert _xy(op.points) == _VOID_PTS
    assert op.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable


def test_void_z_range_is_its_hosts(qapp):
    slab, op = _slab_with_void()
    slab._scene = _FakeScene(_FakeLM({"Level 1": 0.0}))
    # Top = Level 1 (0.0); bottom = thickness 152.4 (DEFAULT_THICKNESS_MM) -> (-152.4, 0.0)
    assert op.z_range_mm() == (-152.4, 0.0)
    assert op._visibility_by_zrange is True


def test_void_less_slab_serializes_unchanged(qapp):
    assert set(FloorSlab(points=_rect(0, 0, 4000, 3000)).to_dict()) == _SLAB_KEYS


def test_slab_nests_voids_and_round_trips(qapp):
    slab, op = _slab_with_void()
    op._mark = "OP3"
    op._display_overrides = {"color": "#00ff00"}
    d = slab.to_dict()
    assert d["openings"] == [{
        "feature_id": "floor_sketched",
        "points": [[1000.0, 1000.0], [2000.0, 1000.0], [2000.0, 2000.0], [1000.0, 2000.0]],
        "mark": "OP3",
        "display_overrides": {"color": "#00ff00"},
    }]
    s2 = FloorSlab.from_dict(d)
    (op2,) = s2.openings
    assert op2.host is s2 and op2._mark == "OP3"
    assert _xy(op2.points) == _VOID_PTS
    assert s2.to_dict() == d


def test_cut_region_follows_void_edits(qapp):
    slab, op = _slab_with_void()
    assert _material_area(slab) == pytest.approx(11_000_000.0)       # 12e6 - 1000*1000
    op.set_points(_rect(1000, 1000, 3000, 2000))
    assert _material_area(slab) == pytest.approx(10_000_000.0)       # 12e6 - 2000*1000
    op.apply_grip(2, P(3000, 2500))
    # trapezoid x 1000..3000, heights 1000 and 1500: 2000 * (1000 + 1500) / 2 = 2.5e6
    assert _material_area(slab) == pytest.approx(9_500_000.0)
    slab.remove_opening(op)
    assert _material_area(slab) == pytest.approx(12_000_000.0)


def test_slab_reshape_keeps_voids_in_place(qapp):
    slab, op = _slab_with_void()
    assert _material_area(slab) == pytest.approx(11_000_000.0)       # primes the cache
    slab.apply_grip(2, P(5000, 3000))
    slab.insert_point(1, P(2000, -500))
    slab.remove_point(1)
    assert _xy(op.points) == _VOID_PTS
    # (0,0)(4000,0)(5000,3000)(0,3000): 12e6 + 1000*3000/2 = 13.5e6; minus the 1e6 void
    assert _material_area(slab) == pytest.approx(12_500_000.0)


def test_void_vertex_grips(qapp):
    slab, op = _slab_with_void()
    assert len(op.manip_handles()) == 4
    assert _xy(op.grip_points()) == _VOID_PTS
