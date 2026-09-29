"""Selection dimension readouts follow a held-preview drag live, plus two
readout-adjacent panel/menu fixes (selection-mode.md §15, 2d-geometry.md §8).

Real Block Editor scene, shown Model_View, real mouse / key input.
"""
import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.dimension_edit import DimensionEdit
from firepro3d.geometry_2d import ArcItem, LineItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.scale_manager import ScaleManager


@pytest.fixture
def be(qapp):
    """(view, scene) — shown Block Editor scene at 1 px / mm, centred."""
    sc = Model_Space(scene_role="block_editor")
    sc.scale_manager = ScaleManager()
    v = Model_View(sc)
    v.resize(900, 700)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.resetTransform()
    v.centerOn(0, 0)
    v.setFocus()
    sc.set_mode("select")
    QApplication.processEvents()
    yield v, sc
    if sc.readouts.is_editing():
        sc.readouts.cancel_edit()
    sc.cleanup()
    v.close()
    v.deleteLater()
    QApplication.processEvents()


def _add_line(sc, x0=-150, x1=150, y=0):
    ln = LineItem(QPointF(x0, y), QPointF(x1, y))
    sc.addItem(ln)
    sc._draw_lines.append(ln)
    return ln


def _spec(v, sc, key):
    return next(e.spec for e in sc.readouts.layouts(v) if e.spec.key == key)


def _drag_hold(v, scene_from, steps):
    """Press at *scene_from* and move by *steps* (viewport px) — button held."""
    vp = v.viewport()
    p0 = v.mapFromScene(scene_from)
    QTest.mousePress(vp, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, p0)
    for dx, dy in steps:
        QTest.mouseMove(vp, p0 + QPoint(dx, dy))
        QApplication.processEvents()
    return p0


def _release(v, pt):
    QTest.mouseRelease(v.viewport(), Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier, pt)
    QApplication.processEvents()


def _close(p, x, y):
    return abs(p.x() - x) < 1e-6 and abs(p.y() - y) < 1e-6


# ── A: readouts track the held preview mid-drag ─────────────────────────
def test_body_drag_readout_follows_mid_drag(be):
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    QApplication.processEvents()
    p0 = _drag_hold(v, QPointF(40, 0), [(k * 10, -k * 10) for k in range(1, 11)])
    try:
        assert ln.transform().dx() == pytest.approx(100.0)   # held preview live
        s = _spec(v, sc, "length")
        assert _close(s.a, -50, -100) and _close(s.b, 250, -100), (s.a, s.b)
        assert s.value == pytest.approx(300.0)
    finally:
        _release(v, p0 + QPoint(100, -100))
    s = _spec(v, sc, "length")                                 # baked: same
    assert _close(s.a, -50, -100) and _close(s.b, 250, -100)


def test_midpoint_grip_drag_readout_follows_mid_drag(be):
    """Regression only: the translate grip edits geometry live (no held
    transform), so readouts already followed it before the fix."""
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    QApplication.processEvents()
    p0 = _drag_hold(v, QPointF(0, 0), [(k * 10, -k * 7) for k in range(1, 6)])
    try:
        s = _spec(v, sc, "length")
        assert _close(s.a, -100, -35) and _close(s.b, 200, -35), (s.a, s.b)
    finally:
        _release(v, p0 + QPoint(50, -35))


def test_arc_body_drag_moves_angular_readout_mid_drag(be):
    v, sc = be
    a = ArcItem(QPointF(0, 0), 100.0, 0.0, 90.0)
    sc.addItem(a)
    sc._draw_arcs.append(a)
    a.setSelected(True)
    QApplication.processEvents()
    # grab the arc body at 45 deg (Y-up) -> scene (70.7, -70.7)
    p0 = _drag_hold(v, QPointF(70.71, -70.71),
                    [(k * 10, k * 5) for k in range(1, 7)])
    try:
        s = _spec(v, sc, "angle")
        assert _close(s.center, 60, 30), s.center
        assert s.start_deg == pytest.approx(0.0, abs=1e-6)
        assert s.span_deg == pytest.approx(90.0) and s.value == pytest.approx(90.0)
        assert s.ref_radius == pytest.approx(100.0)
    finally:
        _release(v, p0 + QPoint(60, 30))


def test_readouts_at_rest_are_unmapped(be):
    """No drag in flight: specs are the primitive's own, untouched."""
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    QApplication.processEvents()
    s = _spec(v, sc, "length")
    assert _close(s.a, -150, 0) and _close(s.b, 150, 0)


@pytest.mark.parametrize("xf", ["rotate", "mirror", "scale"])
@pytest.mark.parametrize("span", [90.0, -90.0, 300.0])
def test_map_spec_angular_legs_land_on_transformed_points(xf, span):
    """Observable ground truth: the mapped sweep's start/end legs are the
    transformed original leg points, whatever the transform's handedness."""
    from PyQt6.QtGui import QTransform
    from firepro3d.arc_math import point_at
    from firepro3d.selection_readouts import DimSpec, map_spec
    t = {"rotate": QTransform().translate(30, -20).rotate(37),
         "mirror": QTransform().scale(-1, 1),
         "scale": QTransform().scale(2, 2)}[xf]
    c = QPointF(10, 5)
    s = DimSpec(kind="angular", key="angle", field="Angle", prefix="",
                value=span, field_kind="span", apply=lambda v: None,
                center=c, ref_radius=100.0, start_deg=20.0, span_deg=span)
    out = map_spec(s, t)
    for deg0, deg1 in ((20.0, out.start_deg),
                       (20.0 + span, out.start_deg + out.span_deg)):
        want = t.map(point_at(c, 100.0, deg0))
        got = point_at(out.center, out.ref_radius, deg1)
        assert _close_tol(got, want), (xf, span, got, want)
    # the sweep passes through the transformed mid-leg (not the complement)
    want_mid = t.map(point_at(c, 100.0, 20.0 + span / 2))
    got_mid = point_at(out.center, out.ref_radius,
                       out.start_deg + out.span_deg / 2)
    assert _close_tol(got_mid, want_mid), (xf, span)
    assert out.value == pytest.approx(out.span_deg)
    assert abs(out.span_deg) == pytest.approx(abs(span))


def _close_tol(p, q, tol=1e-6):
    return abs(p.x() - q.x()) < tol and abs(p.y() - q.y()) < tol


def test_map_spec_linear_scales_value():
    from PyQt6.QtGui import QTransform
    from firepro3d.selection_readouts import DimSpec, map_spec
    s = DimSpec(kind="linear", key="length", field="Length", prefix="",
                value=300.0, field_kind="dimension", apply=lambda v: None,
                a=QPointF(0, 0), b=QPointF(300, 0), away=QPointF(0, 10))
    out = map_spec(s, QTransform().translate(5, 5).scale(2, 2))
    assert _close(out.a, 5, 5) and _close(out.b, 605, 5)
    assert _close(out.away, 5, 25)
    assert out.value == pytest.approx(600.0)


# ── :288 right-click while a readout edit is open ─────────────────────────
def _right_click_window(v, scene_pt):
    win = v.window().windowHandle()
    pt = v.viewport().mapTo(v.window(), v.mapFromScene(scene_pt))
    QTest.mouseClick(win, Qt.MouseButton.RightButton,
                     Qt.KeyboardModifier.NoModifier, pt)
    QApplication.processEvents()


def test_right_click_cancelling_edit_opens_no_menu(be, monkeypatch):
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    QApplication.processEvents()
    built = []

    class _Menu:
        def exec(self, *_a):
            pass

    monkeypatch.setattr(v, "_build_plan_context_menu",
                        lambda *a: built.append(a) or _Menu())
    e = next(x for x in sc.readouts.layouts(v) if x.spec.key == "length")
    sc.readouts.begin_edit(v, e)
    QApplication.processEvents()
    _right_click_window(v, QPointF(0, 200))
    assert not sc.readouts.is_editing()
    assert built == []                       # the cancelling click is consumed
    _right_click_window(v, QPointF(0, 200))
    assert len(built) == 1                   # the next right-click is normal


def test_right_click_on_entity_cancelling_edit_opens_no_entity_menu(
        be, monkeypatch):
    """The entity-menu branch (scene._find_entity_at hit) is swallowed too."""
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    QApplication.processEvents()
    shown = []
    monkeypatch.setattr(sc, "_show_entity_context_menu",
                        lambda *a: shown.append(a))
    e = next(x for x in sc.readouts.layouts(v) if x.spec.key == "length")
    sc.readouts.begin_edit(v, e)
    QApplication.processEvents()
    _right_click_window(v, QPointF(-100, 0))           # on the line body
    assert not sc.readouts.is_editing()
    assert shown == []
    _right_click_window(v, QPointF(-100, 0))
    assert len(shown) == 1                   # precondition: the hit is real


# ── :290 Arc Span >= 360 in the property panel ────────────────────────────
def _span_edit(pm):
    return next(w for w in pm.findChildren(DimensionEdit) if "°" in w.text())


def test_panel_arc_span_rejects_360_and_over(qapp):
    from firepro3d.property_manager import PropertyManager
    sc = Model_Space(scene_role="block_editor")
    sc.scale_manager = ScaleManager()
    a = ArcItem(QPointF(0, 0), 50.0, 0.0, 90.0)
    sc.addItem(a)
    pm = PropertyManager()
    pm.show()
    try:
        pm.show_properties([a])
        QApplication.processEvents()
        for bad in ("400", "360"):
            ed = _span_edit(pm)
            ed.setFocus()
            ed.selectAll()
            QTest.keyClicks(ed, bad)
            QTest.keyClick(ed, Qt.Key.Key_Return)
            QApplication.processEvents()
            assert a._span_deg == pytest.approx(90.0)
            assert _span_edit(pm).value_mm() == pytest.approx(90.0), bad
        ed = _span_edit(pm)
        ed.setFocus()
        ed.selectAll()
        QTest.keyClicks(ed, "359")
        QTest.keyClick(ed, Qt.Key.Key_Return)
        QApplication.processEvents()
        assert a._span_deg == pytest.approx(359.0)
    finally:
        pm.close()
        pm.deleteLater()
        sc.cleanup()
        QApplication.processEvents()


def test_dimension_edit_maximum_is_inclusive(qapp):
    ed = DimensionEdit(None, initial_mm=10.0, maximum=20.0)
    ed.setText("20")
    assert ed.try_commit() and ed.value_mm() == pytest.approx(20.0)
    ed.setText("20.5")
    assert not ed.try_commit() and ed.value_mm() == pytest.approx(20.0)
