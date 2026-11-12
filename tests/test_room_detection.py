"""room_detection engine (room-detection rework design §1). Walls added directly and
settled; every expected value is hand-computed from wall coordinates and thickness (see the
comments) or taken from the 1b truth table (.todo/room-detect-1b.md §2)."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d import room_detection as rd
from tests._room_detect_helpers import add_wall, settle


@pytest.fixture
def scene(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    yield s
    s.clear()


def _rect(scene, x0, y0, x1, y1, th=200.0):
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for i in range(4):
        add_wall(scene, pts[i], pts[(i + 1) % 4], th=th)


def _bounds(ring):
    xs = [p.x() for p in ring]
    ys = [p.y() for p in ring]
    return (min(xs), min(ys), max(xs), max(ys))


class TestDetect:
    def test_mid_span_tee_left_bay_exact(self, scene):
        # 6000 x 4000 Center 200 rect + partition x=3000: left bay x 100..2900, y 100..3900
        _rect(scene, 0, 0, 6000, 4000)
        add_wall(scene, (3000, 0), (3000, 4000))
        settle(scene)
        face = rd.detect(list(scene._walls), QPointF(1500, 2000))
        assert isinstance(face, rd.RoomFace)
        assert face.holes == []
        assert face.area_mm2 == pytest.approx(2800 * 3800, abs=1.0)        # 10.64e6 (1b b_tee Center)
        assert _bounds(face.outer) == pytest.approx((100, 100, 2900, 3900), abs=1e-6)

    @pytest.mark.parametrize("click", [(3700, 4000), (1000, 1000)], ids=["near", "far"])
    def test_island_becomes_one_hole_ring(self, scene, click):
        # outer 10000x8000 + inner 2000x2000 at (4000,3000), Center 200 (1b case d):
        # outer ring 9800*7800 = 76.44e6; hole = inner walls' outline 2200*2200 = 4.84e6
        _rect(scene, 0, 0, 10000, 8000)
        _rect(scene, 4000, 3000, 6000, 5000)
        settle(scene)
        face = rd.detect(list(scene._walls), QPointF(*click))
        assert isinstance(face, rd.RoomFace)
        assert rd.ring_area(face.outer) == pytest.approx(76.44e6, abs=1.0)
        assert len(face.holes) == 1
        assert rd.ring_area(face.holes[0]) == pytest.approx(4.84e6, abs=1.0)
        assert _bounds(face.holes[0]) == pytest.approx((3900, 2900, 6100, 5100), abs=1e-6)
        assert face.area_mm2 == pytest.approx(71.6e6, abs=2.0)              # 1b truth net

    def test_inside_the_island(self, scene):
        _rect(scene, 0, 0, 10000, 8000)
        _rect(scene, 4000, 3000, 6000, 5000)
        settle(scene)
        face = rd.detect(list(scene._walls), QPointF(5000, 4000))
        assert isinstance(face, rd.RoomFace) and face.holes == []
        assert face.area_mm2 == pytest.approx(1800 * 1800, abs=1.0)        # 3.24e6

    def test_click_in_wall_body_refused(self, scene):
        _rect(scene, 0, 0, 6000, 4000)
        settle(scene)
        res = rd.detect(list(scene._walls), QPointF(3000, 50))             # bottom body y -100..100
        assert isinstance(res, rd.Refusal) and res.reason == "in_wall"

    def test_open_u_refused_with_nearest_free_end(self, scene):
        # Gap 1 / D-R6: U (0,4000)->(0,0)->(6000,0)->(6000,4000); the free ends'
        # caps are centred on the endpoints (0,4000) / (6000,4000); (0,4000) is nearer
        add_wall(scene, (0, 4000), (0, 0))
        add_wall(scene, (0, 0), (6000, 0))
        add_wall(scene, (6000, 0), (6000, 4000))
        settle(scene)
        res = rd.detect(list(scene._walls), QPointF(1000, 2000))
        assert isinstance(res, rd.Refusal) and res.reason == "open"
        assert res.open_end is not None
        assert (res.open_end.x(), res.open_end.y()) == pytest.approx((0.0, 4000.0), abs=1e-6)

    def test_no_walls_is_open_without_end(self):
        res = rd.detect([], QPointF(0, 0))
        assert isinstance(res, rd.Refusal) and res.reason == "open" and res.open_end is None


class TestRings:
    def test_same_ring_tolerance(self, qapp):
        a = [QPointF(0, 0), QPointF(1000, 0), QPointF(1000, 1000), QPointF(0, 1000)]
        b = [QPointF(0, 0), QPointF(1000, 0), QPointF(1000, 1004), QPointF(0, 1004)]    # +0.4 %
        c = [QPointF(0, 0), QPointF(1000, 0), QPointF(1000, 1020), QPointF(0, 1020)]    # +2 %
        assert rd.same_ring(a, b) and not rd.same_ring(a, c)

    def test_ring_sample_of_a_u_lies_inside(self, qapp):
        # U ring: vertex mean (1500, 1750) falls in the notch x 1000..2000, y > 1000;
        # fallback = first edge (0,0)->(3000,0) midpoint pushed 1 mm inward -> (1500, 1)
        u = [QPointF(0, 0), QPointF(3000, 0), QPointF(3000, 3000), QPointF(2000, 3000),
             QPointF(2000, 1000), QPointF(1000, 1000), QPointF(1000, 3000), QPointF(0, 3000)]
        s = rd.ring_sample(u)
        assert (s.x(), s.y()) == pytest.approx((1500.0, 1.0), abs=1e-9)
