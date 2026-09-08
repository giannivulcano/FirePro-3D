import math
import pytest
from PyQt6.QtCore import QPointF
from firepro3d.model_space import Model_Space


@pytest.fixture
def scene(qapp):
    return Model_Space()


def test_three_click_ellipse_placement(scene):
    scene.set_mode("draw_ellipse")
    ctl = scene._geom_ctl
    c = QPointF(0, 0); major = QPointF(100, 0); minor = QPointF(0, -40)
    ctl._press_draw_ellipse(None, c, c, None, None, None)
    ctl._press_draw_ellipse(None, major, major, None, None, None)
    ctl._press_draw_ellipse(None, minor, minor, None, None, None)
    assert len(scene._draw_ellipses) == 1
    e = scene._draw_ellipses[0]
    assert e._center == QPointF(0, 0)
    assert e._rx == pytest.approx(100, abs=1e-6)
    assert e._ry == pytest.approx(40, abs=1e-6)
    assert e._rotation_deg == pytest.approx(0, abs=1e-6)
    assert scene.mode == "draw_ellipse"          # re-armed


def test_rotated_ellipse_from_angled_major(scene):
    scene.set_mode("draw_ellipse")
    ctl = scene._geom_ctl
    c = QPointF(0, 0)
    ang = math.radians(30)
    major = QPointF(100 * math.cos(ang), -100 * math.sin(ang))
    minor = QPointF(0, -40)
    ctl._press_draw_ellipse(None, c, c, None, None, None)
    ctl._press_draw_ellipse(None, major, major, None, None, None)
    ctl._press_draw_ellipse(None, minor, minor, None, None, None)
    e = scene._draw_ellipses[0]
    assert e._rotation_deg == pytest.approx(30, abs=1e-3)


def test_subepsilon_major_refused(scene):
    scene.set_mode("draw_ellipse")
    ctl = scene._geom_ctl
    c = QPointF(0, 0)
    ctl._press_draw_ellipse(None, c, c, None, None, None)
    ctl._press_draw_ellipse(None, QPointF(0.1, 0), QPointF(0.1, 0), None, None, None)
    assert len(scene._draw_ellipses) == 0
    assert scene._ellipse_step == 1              # still awaiting a valid major


def test_mode_switch_clears_ellipse_state(scene):
    scene.set_mode("draw_ellipse")
    ctl = scene._geom_ctl
    c = QPointF(0, 0)
    ctl._press_draw_ellipse(None, c, c, None, None, None)
    assert scene._ellipse_step == 1
    scene.set_mode("select")
    assert scene._ellipse_step == 0
    assert scene._ellipse_center is None


# ── Spline draw tool (appended) ─────────────────────────────────────────────
from firepro3d.construction_geometry import SplineItem


def test_nclick_spline_placement(scene):
    scene.set_mode("draw_spline")
    ctl = scene._geom_ctl
    pts = [QPointF(0, 0), QPointF(10, 20), QPointF(30, -10), QPointF(40, 5)]
    for p in pts:
        ctl._press_draw_spline(None, p, p, None, None, None)
    ctl._finish_draw_spline()
    assert len(scene._draw_splines) == 1
    assert len(scene._draw_splines[0]._control_points) == 4
    assert scene._draw_splines[0]._degree == 3


def test_spline_finish_early_lowers_degree(scene):
    scene.set_mode("draw_spline")
    ctl = scene._geom_ctl
    for p in (QPointF(0, 0), QPointF(10, 10), QPointF(20, 0)):
        ctl._press_draw_spline(None, p, p, None, None, None)
    ctl._finish_draw_spline()
    assert scene._draw_splines[0]._degree == 2


def test_spline_single_point_cancels(scene):
    scene.set_mode("draw_spline")
    ctl = scene._geom_ctl
    ctl._press_draw_spline(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    ctl._finish_draw_spline()
    assert len(scene._draw_splines) == 0


def test_spline_delete_pops_control_point(scene):
    scene.set_mode("draw_spline")
    ctl = scene._geom_ctl
    for p in (QPointF(0, 0), QPointF(10, 10), QPointF(20, 0)):
        ctl._press_draw_spline(None, p, p, None, None, None)
    assert len(scene._spline_points) == 3
    ctl._pop_draw_spline_vertex()
    assert len(scene._spline_points) == 2


def test_spline_mode_switch_clears_state(scene):
    scene.set_mode("draw_spline")
    ctl = scene._geom_ctl
    ctl._press_draw_spline(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    assert len(scene._spline_points) == 1
    scene.set_mode("select")
    assert scene._spline_points == []
