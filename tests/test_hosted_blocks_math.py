"""hosted_blocks frame math (design D2/D4/D8/D9)."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d import hosted_blocks as hb
from firepro3d.section_marker import SectionBasis
from tests._hosted_blocks_helpers import gridline


# A cut along +x from (0,0) to (10000,0), look_sign +1 -> N = (0, 1)
# (from_cut: N = s*(-dy, dx) = (0, 1)), depth 8000.
BASIS = SectionBasis.from_cut((0.0, 0.0), (10000.0, 0.0), 1, 8000.0)


def _gl_world_y(ms, y_world, label="B", reverse=False):
    # world y -> plan scene y = -y (ppm 1); gridline runs along x
    p, q = (0, -y_world), (6000, -y_world)
    return gridline(ms, q if reverse else p, p if reverse else q, label)


def test_parallel_and_facing(qapp, make_model_space):
    ms = make_model_space()
    gl = _gl_world_y(ms, 3000)                   # angle 0 -> u=(1,0), n=(0,1)
    assert hb.is_parallel(BASIS, gl)
    assert hb.facing_of(BASIS, gl) == 1          # N.n = 1
    assert hb.h_sign(BASIS, gl) == 1             # D.u = 1
    rev = _gl_world_y(ms, 3000, "C", reverse=True)   # angle 180 -> n=(0,-1)
    assert hb.is_parallel(BASIS, rev) and hb.facing_of(BASIS, rev) == -1
    assert hb.h_sign(BASIS, rev) == -1
    perp = gridline(ms, (500, 0), (500, -6000), "1")  # runs along +y world
    assert not hb.is_parallel(BASIS, perp)


def test_world_point_and_scene_pos(qapp, make_model_space):
    ms = make_model_space()
    gl = _gl_world_y(ms, 3000)                   # origin world (0, 3000)
    host = {"gridline": gl._uid, "offset_mm": 200.0, "along_mm": 1500.0,
            "elevation_mm": 2400.0, "facing": 1}
    assert hb.world_point(gl, host, 1.0) == pytest.approx((1500.0, 3200.0))
    assert hb.scene_pos(gl, host, 1.0) == pytest.approx((1500.0, -3200.0))


def test_host_at_section_point(qapp, make_model_space):
    ms = make_model_space()
    gl = _gl_world_y(ms, 3000)
    host = hb.host_at(BASIS, gl, 2500.0, 1200.0, 1.0)
    assert host == {"gridline": gl._uid, "offset_mm": 0.0,
                    "along_mm": pytest.approx(2500.0), "elevation_mm": 1200.0,
                    "facing": 1}
    rev = _gl_world_y(ms, 3000, "C", reverse=True)   # origin world (6000, 3000)
    assert hb.host_at(BASIS, rev, 2500.0, 0.0, 1.0)["along_mm"] == pytest.approx(3500.0)


def test_choose_host_nearest_in_depth(qapp, make_model_space):
    ms = make_model_space()
    _gl_world_y(ms, 5000, "F")
    near = _gl_world_y(ms, 3000, "N")
    _gl_world_y(ms, -100, "BEHIND_CUT")          # d = -100 < 0
    _gl_world_y(ms, 9000, "BEYOND")              # d = 9000 > depth
    assert hb.choose_host(BASIS, ms._gridlines, 1.0) is near
    ms2 = make_model_space()
    gridline(ms2, (500, 0), (500, -6000), "1")
    assert hb.choose_host(BASIS, ms2._gridlines, 1.0) is None


def test_origin_shift_along(qapp, make_model_space):
    ms = make_model_space()
    gl = _gl_world_y(ms, 3000)
    assert hb.origin_shift_along(gl, QPointF(0, -3000), QPointF(400, -3000), 1.0) \
        == pytest.approx(400.0)


def test_section_pose_front_back(qapp, make_model_space):
    ms = make_model_space()
    gl = _gl_world_y(ms, 3000)
    host = {"gridline": gl._uid, "offset_mm": 0.0, "along_mm": 1000.0,
            "elevation_mm": 500.0, "facing": 1}
    h, v, d, mir, rot = hb.section_pose(BASIS, gl, host, 30.0, False, 1.0)
    assert (h, v, d, rot) == pytest.approx((1000.0, -500.0, 3000.0, 30.0))
    assert mir is False
    back = SectionBasis.from_cut((10000.0, 6000.0), (0.0, 6000.0), 1, 8000.0)
    # D = (-1, 0), N = (0, -1): looks toward -y; gridline at y=3000 is d=3000.
    h, v, d, mir, rot = hb.section_pose(back, gl, host, 30.0, False, 1.0)
    assert (h, d, rot) == pytest.approx((-1000.0, 3000.0, -30.0))
    assert mir is True
    assert hb.section_pose(BASIS, gl, dict(host, offset_mm=-3500.0), 0.0, False, 1.0) is None


def test_section_pose_reversed_gridline_own_facing(qapp, make_model_space):
    """Anti-parallel gridline (Edge Case): facing is read against ITS n.

    Reversed gridline: origin = bubble1 = world (6000, 3000), u = (-1, 0),
    n = (0, -1). along 1000 -> x = 6000 - 1000 = 5000; offset 200 -> y =
    3000 + 200 * (-1) = 2800. Placed by a section looking along +y (N.n =
    -1), so facing = -1 and the BASIS view (N = (0, 1)) is NOT a back view.
    """
    ms = make_model_space()
    rev = _gl_world_y(ms, 3000, reverse=True)
    host = {"gridline": rev._uid, "offset_mm": 200.0, "along_mm": 1000.0,
            "elevation_mm": 500.0, "facing": -1}
    h, v, d, mir, rot = hb.section_pose(BASIS, rev, host, 30.0, False, 1.0)
    # BASIS: D = (1, 0), A = (0, 0), N = (0, 1): h = x = 5000, d = y = 2800.
    assert (h, v, d, rot) == pytest.approx((5000.0, -500.0, 2800.0, 30.0))
    assert mir is False
    back = SectionBasis.from_cut((10000.0, 6000.0), (0.0, 6000.0), 1, 8000.0)
    # back: D = (-1, 0), A = (10000, 6000), N = (0, -1): h = -x = -5000,
    # d = (y - 6000) * -1 = 3200; N.n = +1 != facing -1 -> back view.
    h, v, d, mir, rot = hb.section_pose(back, rev, host, 30.0, False, 1.0)
    assert (h, d, rot) == pytest.approx((-5000.0, 3200.0, -30.0))
    assert mir is True
