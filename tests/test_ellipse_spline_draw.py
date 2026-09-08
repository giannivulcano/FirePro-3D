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


# ── Ellipse HUD + reference lines (UX round) ─────────────────────────────────

def test_ellipse_step1_creates_radius_line(scene):
    scene.set_mode("draw_ellipse")
    ctl = scene._geom_ctl
    ctl._press_draw_ellipse(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    assert scene._ellipse_radius_line is not None      # step-1 radial guide
    assert scene._ellipse_step == 1


def test_ellipse_hud_applier_step1_advances_step2_commits(scene):
    scene.set_mode("draw_ellipse")
    ctl = scene._geom_ctl
    ctl._press_draw_ellipse(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    # Step 1 HUD resolves the major endpoint (line schema Length+Angle → point).
    ok1 = ctl._apply_ellipse_dynamic_input(QPointF(100, 0))
    assert ok1 is True
    assert scene._ellipse_step == 2
    assert scene._ellipse_rx == pytest.approx(100, abs=1e-6)
    assert scene._ellipse_rot == pytest.approx(0, abs=1e-6)
    assert scene._ellipse_ref_major is not None        # step-2 guides laid
    assert scene._ellipse_ref_minor is not None
    # Step 2 HUD resolves the minor rim (circle schema Radius → point; hypot).
    ok2 = ctl._apply_ellipse_dynamic_input(QPointF(0, -40))
    assert ok2 is True
    assert len(scene._draw_ellipses) == 1
    e = scene._draw_ellipses[0]
    assert e._rx == pytest.approx(100, abs=1e-6)
    assert e._ry == pytest.approx(40, abs=1e-6)
    # Guides + preview line all cleared after commit.
    assert scene._ellipse_ref_major is None
    assert scene._ellipse_ref_minor is None
    assert scene._ellipse_radius_line is None


def test_ellipse_schema_is_step_aware(scene):
    scene.set_mode("draw_ellipse")
    ctl = scene._geom_ctl
    assert scene.active_schema() is None               # step 0: no HUD
    ctl._press_draw_ellipse(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    assert scene.active_schema().name == "line"        # step 1: radius + angle
    ctl._apply_ellipse_dynamic_input(QPointF(100, 0))
    assert scene.active_schema().name == "circle"      # step 2: minor radius


def test_ellipse_commit_clears_prior_selection(scene):
    scene.set_mode("draw_ellipse")
    ctl = scene._geom_ctl
    for major in (QPointF(50, 0), QPointF(80, 0)):
        ctl._press_draw_ellipse(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
        ctl._apply_ellipse_dynamic_input(major)
        ctl._apply_ellipse_dynamic_input(QPointF(0, -20))
    # Two ellipses placed, but only the most recent stays selected.
    assert len(scene._draw_ellipses) == 2
    selected = [it for it in scene._draw_ellipses if it.isSelected()]
    assert len(selected) == 1
    assert selected[0] is scene._draw_ellipses[-1]


# ── Spline reference lines + HUD (UX round) ─────────────────────────────────

def test_spline_ref_poly_appears_between_nodes(scene):
    scene.set_mode("draw_spline")
    ctl = scene._geom_ctl
    ctl._press_draw_spline(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    assert scene._spline_ref_poly is None          # 1 point: no polygon yet
    ctl._press_draw_spline(None, QPointF(10, 20), QPointF(10, 20), None, None, None)
    assert scene._spline_ref_poly is not None      # 2 points: control polygon drawn


def test_spline_hud_applier_appends_control_point(scene):
    scene.set_mode("draw_spline")
    ctl = scene._geom_ctl
    ctl._press_draw_spline(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    ctl._apply_spline_dynamic_input(QPointF(30, 10))   # HUD-typed length/angle → point
    ctl._apply_spline_dynamic_input(QPointF(60, -5))
    assert [(p.x(), p.y()) for p in scene._spline_points] == [(0, 0), (30, 10), (60, -5)]


def test_spline_schema_is_line_after_first_point(scene):
    scene.set_mode("draw_spline")
    ctl = scene._geom_ctl
    ctl._press_draw_spline(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    assert scene.active_schema().name == "line"


def test_spline_finish_clears_ref_poly_and_selection(scene):
    scene.set_mode("draw_spline")
    ctl = scene._geom_ctl
    # place a first spline
    for p in (QPointF(0, 0), QPointF(10, 20), QPointF(30, 0)):
        ctl._press_draw_spline(None, p, p, None, None, None)
    ctl._finish_draw_spline()
    assert scene._spline_ref_poly is None
    # place a second; only it stays selected
    for p in (QPointF(40, 0), QPointF(50, 20), QPointF(70, 0)):
        ctl._press_draw_spline(None, p, p, None, None, None)
    ctl._finish_draw_spline()
    selected = [it for it in scene._draw_splines if it.isSelected()]
    assert len(selected) == 1 and selected[0] is scene._draw_splines[-1]


# ── Reference guides persist under the manipulator (reselection bug) ──────────

def _px_count(scene, item, selected):
    """Render pixel-count with a manipulator ALWAYS wrapping the item, at the
    given selection state."""
    from PyQt6.QtCore import QObject, QRectF
    from PyQt6.QtGui import QImage, QPainter

    class _FakeManip(QObject):
        def wraps(self, it):
            return True

    scene._manipulator = _FakeManip()
    item.setSelected(selected)
    img = QImage(200, 160, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, 200, 160), scene.itemsBoundingRect())
    p.end()
    return sum(1 for y in range(160) for x in range(200)
               if img.pixelColor(x, y).alpha() > 0)


def test_ellipse_ref_guides_render_when_manip_wrapped(qapp):
    from PyQt6.QtWidgets import QGraphicsScene
    from firepro3d.construction_geometry import EllipseItem
    sc = QGraphicsScene()
    e = EllipseItem(QPointF(90, 70), 60, 24, 0.0)
    sc.addItem(e)
    # Manipulator wraps the item (reselection). Selecting must still add the
    # dashed axis guides — previously suppressed by the _manip_wraps gate.
    assert _px_count(sc, e, True) > _px_count(sc, e, False)


def test_spline_ref_guides_render_when_manip_wrapped(qapp):
    from PyQt6.QtWidgets import QGraphicsScene
    from firepro3d.construction_geometry import SplineItem
    sc = QGraphicsScene()
    s = SplineItem([QPointF(10, 10), QPointF(60, 90), QPointF(130, 20),
                    QPointF(180, 70)])
    sc.addItem(s)
    assert _px_count(sc, s, True) > _px_count(sc, s, False)
