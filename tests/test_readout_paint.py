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


# ── Task 14: pixel-sampled render in both themes (real Block Editor scene) ──
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from firepro3d import theme as th_mod
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.scale_manager import ScaleManager
from firepro3d.geometry_2d import LineItem, ArcItem


def _near(c, t, tol=60):
    return (abs(c.red() - t.red()) <= tol and abs(c.green() - t.green()) <= tol
            and abs(c.blue() - t.blue()) <= tol)


def _count(img, rect, target):
    n = 0
    for x in range(max(0, int(rect.left())), min(img.width(), int(rect.right()))):
        for y in range(max(0, int(rect.top())), min(img.height(), int(rect.bottom()))):
            if _near(img.pixelColor(x, y), target):
                n += 1
    return n


@pytest.fixture(params=["DARK", "LIGHT"])
def themed_be(request, qapp, monkeypatch):
    t = getattr(th_mod, request.param)
    monkeypatch.setattr(th_mod, "detect", lambda: t)
    sc = Model_Space(scene_role="block_editor")
    sc.scale_manager = ScaleManager()
    # Without the app's stylesheet the bare view paints the platform palette
    # (#1e1e1e in BOTH themes), which is within tolerance of LIGHT ink
    # (#1c2024): every background pixel would count as "ink". Paint the
    # theme's canvas ground instead, as the app canvas does.
    sc.setBackgroundBrush(QBrush(QColor(t.canvas_bg)))
    v = Model_View(sc)
    v.resize(700, 500)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.resetTransform()
    v.centerOn(0, 0)
    sc.set_mode("select")
    # Non-vacuity: the canvas background must not itself read as ink/muted.
    bg = v.viewport().grab().toImage().pixelColor(3, 3)
    assert not _near(bg, t.color("ink")) and not _near(bg, t.color("muted")), bg.name()
    yield v, sc, t
    sc.cleanup()
    v.close()
    v.deleteLater()
    QApplication.processEvents()


def test_label_ink_pixels_only_when_selected(themed_be):
    v, sc, t = themed_be
    ln = LineItem(QPointF(-200, 100), QPointF(200, 100), color="#808080")
    sc.addItem(ln)
    ln.setSelected(True)
    QApplication.processEvents()
    lay = sc.readouts.layouts(v)[0].layout
    assert lay.fits
    box = QRectF(lay.center.x() - lay.width / 2, lay.center.y() - lay.height / 2,
                 lay.width, lay.height)
    on = _count(v.viewport().grab().toImage(), box, t.color("ink"))
    ln.setSelected(False)
    QApplication.processEvents()
    off = _count(v.viewport().grab().toImage(), box, t.color("ink"))
    assert on > 0 and off == 0


def test_reference_arc_muted_pixels(themed_be):
    v, sc, t = themed_be
    a = ArcItem(QPointF(0, 0), 250.0, 0.0, 90.0, color="#808080")
    sc.addItem(a)
    a.setSelected(True)
    QApplication.processEvents()
    lay = next(e.layout for e in sc.readouts.layouts(v) if e.spec.key == "angle")
    C, r = lay.arc_center, lay.arc_radius_px
    # sample a small box on the arc at 45° (Y-up) — the dashed arc passes there
    px = QPointF(C.x() + r * math.cos(math.radians(45)), C.y() - r * math.sin(math.radians(45)))
    box = QRectF(px.x() - 8, px.y() - 8, 16, 16)     # spans >= one dash period
    on = _count(v.viewport().grab().toImage(), box, t.color("muted"))
    a.setSelected(False)
    QApplication.processEvents()
    off = _count(v.viewport().grab().toImage(), box, t.color("muted"))
    assert on > off


from PyQt6.QtCore import QEvent, QObject


class _PaintRegionSpy(QObject):
    """Records the region of every paint event the viewport receives."""

    def __init__(self):
        super().__init__()
        self.regions = []

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Paint:
            self.regions.append(ev.region())
        return False


def test_moved_label_leaves_no_stale_ghost(themed_be):
    """Stale-ghost guard for the region repaint.

    ``grab()`` always renders the whole widget, so it can't see staleness on
    its own. Emulate the backing store instead: pixels inside a received paint
    region come from a fresh grab, all others keep the pre-move frame.
    """
    v, sc, t = themed_be
    ln = LineItem(QPointF(-200, 0), QPointF(200, 0), color="#808080")
    sc.addItem(ln)
    ln.setSelected(True)
    QApplication.processEvents()
    img0 = v.viewport().grab().toImage()

    def box_of():
        lay = sc.readouts.layouts(v)[0].layout
        return QRectF(lay.center.x() - lay.width / 2, lay.center.y() - lay.height / 2,
                      lay.width, lay.height)
    old_box = box_of()
    assert _count(img0, old_box, t.color("ink")) > 0  # precondition: label drawn
    spy = _PaintRegionSpy()
    v.viewport().installEventFilter(spy)
    try:
        ln.apply_grip(1, QPointF(0, 150))             # translate the line down
        for _ in range(3):
            QApplication.processEvents()
    finally:
        v.viewport().removeEventFilter(spy)
    new_box = box_of()
    assert not new_box.intersects(old_box)            # precondition: label moved
    img1 = v.viewport().grab().toImage()
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QRegion
    painted = QRegion()
    for reg in spy.regions:
        painted = painted.united(reg)
    screen = img0.copy()
    for box in (old_box, new_box):
        for x in range(max(0, int(box.left())), min(img1.width(), int(box.right()) + 1)):
            for y in range(max(0, int(box.top())), min(img1.height(), int(box.bottom()) + 1)):
                if painted.contains(QPoint(x, y)):
                    screen.setPixelColor(x, y, img1.pixelColor(x, y))
    assert _count(screen, old_box, t.color("ink")) == 0, "stale label ghost"
    assert _count(screen, new_box, t.color("ink")) > 0
