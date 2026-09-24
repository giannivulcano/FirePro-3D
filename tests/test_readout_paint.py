"""Selection dimension readouts — layout + paint (readout_paint.py)."""
import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from firepro3d import constants, theme
from firepro3d.readout_paint import layout_linear, layout_angular, hit_layout, readable_deg
from firepro3d.selection_readouts import DimSpec


def test_value_font_is_consolas_px(qapp):
    f = theme.value_font(constants.SELDIM_FONT_PX)
    assert f.family() == theme.FONT_VALUE
    assert f.pixelSize() == constants.SELDIM_FONT_PX


def _view(scale=1.0):
    sc = QGraphicsScene(-5000, -5000, 10000, 10000)
    v = QGraphicsView(sc)
    v.resize(800, 600)
    v.resetTransform()
    v.scale(scale, scale)
    v.centerOn(0, 0)
    return v


def _lin(a, b, away=None):
    return DimSpec(kind="linear", key="k", field="L", prefix="", value=1.0,
                   field_kind="dimension", apply=lambda v: None,
                   a=QPointF(*a), b=QPointF(*b),
                   away=QPointF(*away) if away else None)


def test_readable_deg_folds_upside_down():
    assert readable_deg(180.0) == pytest.approx(0.0)
    assert readable_deg(-120.0) == pytest.approx(60.0)
    assert readable_deg(45.0) == pytest.approx(45.0)


def test_linear_offset_away_side_and_fits(qapp):
    v = _view()
    lay = layout_linear(v, _lin((-100, 0), (100, 0), away=(0, 50)), "10'")
    mid = v.mapFromScene(QPointF(0, 0))
    assert lay.fits
    assert lay.center.y() < mid.y()                    # away point is below -> label above
    assert mid.y() - lay.center.y() == pytest.approx(
        constants.SELDIM_LABEL_OFFSET_PX + lay.height / 2, abs=0.5)
    assert lay.angle_deg == pytest.approx(0.0)


def test_linear_hidden_when_segment_too_short(qapp):
    v = _view()
    assert not layout_linear(v, _lin((0, 0), (5, 0)), "10' 6 1/2\"").fits


def test_linear_label_readable_on_leftward_segment(qapp):
    v = _view()
    lay = layout_linear(v, _lin((100, 0), (-100, 0)), "x")
    assert lay.angle_deg == pytest.approx(0.0)         # not 180 (upside down)


def test_hit_layout_rotated(qapp):
    v = _view()
    lay = layout_linear(v, _lin((0, 0), (200, -200)), "123")
    assert hit_layout(lay, lay.center)
    assert not hit_layout(lay, lay.center + QPointF(200, 0))


def test_angular_ref_radius_min_and_fit(qapp):
    v = _view(scale=1.0)
    s = DimSpec(kind="angular", key="a", field="Angle", prefix="", value=90.0,
                field_kind="span", apply=lambda v: None, center=QPointF(0, 0),
                ref_radius=1000.0, start_deg=0.0, span_deg=90.0)
    lay = layout_angular(v, s, "90°")
    assert lay.fits
    assert lay.arc_radius_px == pytest.approx(max(constants.SELDIM_ARC_REF_MIN_PX,
                                                  constants.SELDIM_ARC_REF_FRAC * 1000.0))
    tiny = DimSpec(**{**s.__dict__, "ref_radius": 10.0})
    assert not layout_angular(v, tiny, "90°").fits     # 25 px arc > 10 px leg
    # label sits outside the arc, on the bisector (45° Y-up => up-right on screen)
    c = v.mapFromScene(QPointF(0, 0))
    assert lay.center.x() > c.x() and lay.center.y() < c.y()
    assert math.hypot(lay.center.x() - c.x(), lay.center.y() - c.y()) > lay.arc_radius_px


def test_arrowheads_point_outward_at_0_and_90():
    """For a 0deg->90deg arc (interior swept CCW in Y-up terms from 0 to 90):
    the arrow at 0deg should point toward +y screen (down, i.e. continuing
    the arc *past* 0deg, away from the 0->90 interior); the arrow at 90deg
    should point toward -x screen (left, continuing past 90deg). The tip
    (pointed vertex) sits exactly on the reference arc (radius r); the base
    (flared end) is pulled inward along the arc toward the swept interior,
    so it lands off the arc at a larger radius than the tip."""
    C = QPointF(0, 0)
    r = 100.0
    start_deg, span_deg = 0.0, 90.0
    for deg, sgn, expected_dir in (
        (start_deg, -1.0, (0.0, 1.0)),            # 0 deg -> +y (down) on screen
        (start_deg + span_deg, 1.0, (-1.0, 0.0)),  # 90 deg -> -x (left) on screen
    ):
        a = math.radians(deg)
        tip = QPointF(C.x() + r * math.cos(a), C.y() - r * math.sin(a))
        # CCW tangent on screen at Y-up angle a is (-sin a, -cos a); sgn picks
        # the outward direction at this end of the sweep (see _paint_arc).
        tx, ty = -math.sin(a) * sgn, -math.cos(a) * sgn
        assert tx == pytest.approx(expected_dir[0], abs=1e-9)
        assert ty == pytest.approx(expected_dir[1], abs=1e-9)
        assert math.hypot(tip.x() - C.x(), tip.y() - C.y()) == pytest.approx(r)
        base = QPointF(tip.x() - tx * constants.SELDIM_ARROW_PX,
                        tip.y() - ty * constants.SELDIM_ARROW_PX)
        # base is off the reference arc, at a larger radius than the tip
        assert math.hypot(base.x() - C.x(), base.y() - C.y()) > r
