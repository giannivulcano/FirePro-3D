"""AC3: rect / circle / arc / polygon / ellipse placement clicks on real
snaps record the AC1 join on the new shape's handle at that click (spec §13).
Shown view, posted presses (mods on the event), real snap engine."""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF, QSettings, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d import auto_constrain as ac
from firepro3d.constants import AUTO_CONSTRAIN_KEY
from firepro3d.geometry_2d import CircleItem, LineItem
from firepro3d.sketch_adapters import adapter_for
from tests._snap_polish_helpers import click, close_view, make_view, move

SHIFT = Qt.KeyboardModifier.ShiftModifier
NONE = Qt.KeyboardModifier.NoModifier


# ── pure helpers ──────────────────────────────────────────────────────────

def test_point_handle_at_returns_the_handle_on_the_point(qapp):
    c = CircleItem(QPointF(10, 20), 30.0)
    assert ac.point_handle_at(c, (10, 20)) == "center"
    assert ac.point_handle_at(c, (40, 20)) is None          # rim: no point handle


def test_point_handle_at_needs_a_uid_and_adapter(qapp):
    c = CircleItem(QPointF(10, 20), 30.0)
    c._uid = None
    assert ac.point_handle_at(c, (10, 20)) is None


def test_plan_rim_is_point_first_for_a_point_target():
    t = ac.Target("point", {"uid": "L", "h": "p2"}, (1.0, 2.0))
    assert ac.plan_rim("C", "curve", t) == [
        ("point_on_curve", [{"uid": "L", "h": "p2"}, {"uid": "C", "h": "curve"}])]


def test_plan_rim_ignores_edge_and_curve_targets():
    assert ac.plan_rim("C", "curve", ac.Target("edge", {"uid": "L", "h": "edge"}, (0, 0))) == []
    assert ac.plan_rim("C", "curve", ac.Target("curve", {"uid": "K", "h": "curve"}, (0, 0))) == []


# ── E2E fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def vs(qapp):
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, True)
    view, sc = make_view(role="block_editor", scale=1.0, mode=None)
    sc.set_align_enabled(False)
    yield view, sc
    QSettings("GV", "FirePro3D").remove(AUTO_CONSTRAIN_KEY)
    close_view(view, sc)


def _recs(sc):
    return [(c.type, [(r.get("uid"), r.get("h"), r.get("ref")) for r in c.refs])
            for c in sc.constraint_ctl.constraints]


def _stub(sc, p):
    """A line ENDING at *p* (its ``p2`` = the endpoint snap), leaving up-left
    so it passes near no other click."""
    ln = LineItem(QPointF(p[0] - 40, p[1] - 100), QPointF(*p))
    sc.addItem(ln); sc._draw_lines.append(ln)
    return ln


def _clicks(view, sc, *pts, mods=None):
    for i, p in enumerate(pts):
        m = (mods or {}).get(i, NONE)
        move(view, QPointF(*p), m); click(view, QPointF(*p), m)


def _pos(item, h):
    """Ground truth: handle *h*'s scene position, read off the adapter."""
    ad = adapter_for(item)
    import numpy as np
    x = np.array(ad.read(item), dtype=float)
    q = ad.points(item, 0)[h].eval(x)[0]
    return float(q[0]), float(q[1])


def _at(item, h, xy):
    px, py = _pos(item, h)
    return abs(px - xy[0]) < 1e-6 and abs(py - xy[1]) < 1e-6


# ── rect ──────────────────────────────────────────────────────────────────

def test_rect_corner_both_clicks_join_then_v(vs):
    view, sc = vs
    a, b = _stub(sc, (310, 120)), _stub(sc, (310, 300))
    sc.set_mode("draw_rectangle"); sc._draw_rect_from_center = False
    _clicks(view, sc, (310, 120), (310, 300), (200, 210))
    r = sc._draw_rects[-1]
    recs = _recs(sc)
    assert [t for t, _ in recs] == ["coincident", "coincident", "vertical"]
    (_, (n1, o1)), (_, (n2, o2)) = recs[0], recs[1]
    assert o1 == (a._uid, "p2", None) and o2 == (b._uid, "p2", None)
    assert n1[0] == n2[0] == r._uid
    assert _at(r, n1[1], (310, 120)) and _at(r, n2[1], (310, 300))


def test_rect_centre_variant_center_and_side_mid(vs):
    view, sc = vs
    a, b = _stub(sc, (310, 120)), _stub(sc, (400, 120))
    sc.set_mode("draw_rectangle"); sc._draw_rect_from_center = True
    _clicks(view, sc, (310, 120), (400, 120), (330, 170))
    r = sc._draw_rects[-1]
    recs = _recs(sc)
    assert recs[0] == ("coincident", [(r._uid, "center", None), (a._uid, "p2", None)])
    (t1, (n1, o1)) = recs[1]
    assert t1 == "coincident" and o1 == (b._uid, "p2", None)
    assert n1[1] in ("tm", "rm", "bm", "lm") and _at(r, n1[1], (400, 120))
    assert recs[2][0] == "vertical" and len(recs) == 3


def test_rect_depth_click_never_joins(vs):
    view, sc = vs
    _stub(sc, (400, 300))
    sc.set_mode("draw_rectangle"); sc._draw_rect_from_center = False
    _clicks(view, sc, (310, 120), (470, 180), (400, 300))    # oblique side: no H/V
    assert len(sc._draw_rects) == 1 and _recs(sc) == []


def test_shift_on_rect_base_suppresses_only_that_join(vs):
    view, sc = vs
    _stub(sc, (310, 120)); b = _stub(sc, (470, 180))
    sc.set_mode("draw_rectangle"); sc._draw_rect_from_center = False
    _clicks(view, sc, (310, 120), (470, 180), (400, 300), mods={0: SHIFT})
    r = sc._draw_rects[-1]
    (t, (n, o)), = _recs(sc)
    assert t == "coincident" and o == (b._uid, "p2", None) and _at(r, n[1], (470, 180))


def _key(view, key):
    view.setFocus()
    QTest.keyClick(view.viewport(), key)
    QApplication.processEvents()


def test_esc_then_new_rect_reuses_no_target(vs):
    """A cancelled placement's targets never reach the next one: its base
    re-placed at the old base's point (Shift: no inference) records nothing."""
    view, sc = vs
    _stub(sc, (310, 120))
    sc.set_mode("draw_rectangle"); sc._draw_rect_from_center = False
    _clicks(view, sc, (310, 120), (470, 180))             # joined base + side
    _key(view, Qt.Key.Key_Escape)
    sc.set_mode("draw_rectangle"); sc._draw_rect_from_center = False
    _clicks(view, sc, (310, 120), (470, 180), (400, 300), mods={0: SHIFT})
    assert len(sc._draw_rects) == 1 and _recs(sc) == []


def test_rect_joins_and_hv_are_one_undo_step(vs):
    view, sc = vs
    _stub(sc, (310, 120))
    sc.push_undo_state()
    n0 = len(sc._draw_rects)
    sc.set_mode("draw_rectangle"); sc._draw_rect_from_center = False
    _clicks(view, sc, (310, 120), (310, 300), (200, 210))
    assert len(sc.constraint_ctl.constraints) == 2        # coincident + vertical
    sc.undo(); QApplication.processEvents()
    assert len(sc._draw_rects) == n0 and sc.constraint_ctl.constraints == []
    sc.redo(); QApplication.processEvents()
    assert len(sc._draw_rects) == n0 + 1 and len(sc.constraint_ctl.constraints) == 2


# ── circle ────────────────────────────────────────────────────────────────

def test_circle_centre_joins(vs):
    view, sc = vs
    a = _stub(sc, (310, 120))
    sc.set_mode("draw_circle")
    _clicks(view, sc, (310, 120), (470, 120))
    c = sc._draw_circles[-1]
    assert _recs(sc) == [("coincident", [(c._uid, "center", None), (a._uid, "p2", None)])]


def test_circle_rim_on_point_is_point_on_curve(vs):
    view, sc = vs
    a = _stub(sc, (470, 120))
    sc.set_mode("draw_circle")
    _clicks(view, sc, (310, 120), (470, 120))
    c = sc._draw_circles[-1]
    assert abs(c._radius - 160.0) < 1e-6                  # precondition: snapped rim
    assert _recs(sc) == [("point_on_curve", [(a._uid, "p2", None), (c._uid, "curve", None)])]


def test_circle_rim_on_edge_records_nothing(vs):
    view, sc = vs
    ln = LineItem(QPointF(470, 60), QPointF(470, 220))    # mid (470,140) is 20 mm off
    sc.addItem(ln); sc._draw_lines.append(ln)
    sc.set_mode("draw_circle")
    move(view, QPointF(310, 120)); click(view, QPointF(310, 120))
    move(view, QPointF(470, 120))
    assert sc._snap_result is not None and sc._snap_result.snap_type in (
        "nearest", "perpendicular")                       # precondition: an EDGE snap
    click(view, QPointF(470, 120))
    assert len(sc._draw_circles) == 1 and _recs(sc) == []


def test_typed_rim_never_joins_clicked_centre_kept(vs):
    view, sc = vs
    a = _stub(sc, (310, 120)); _stub(sc, (470, 120))
    sc.set_mode("draw_circle")
    _clicks(view, sc, (310, 120))
    move(view, QPointF(470, 120))                         # cursor rests on the rim stub's endpoint
    assert sc._snap_result is not None and sc._snap_result.snap_type == "endpoint"   # precondition
    assert sc._geom_ctl._commit_draw_circle_at(QPointF(470, 120))   # HUD applier = typed
    c = sc._draw_circles[-1]
    assert _recs(sc) == [("coincident", [(c._uid, "center", None), (a._uid, "p2", None)])]


# ── arc ───────────────────────────────────────────────────────────────────

def test_arc_centre_start_join_end_off_radius_none(vs):
    view, sc = vs
    a, b = _stub(sc, (310, 120)), _stub(sc, (470, 120)); _stub(sc, (310, 0))
    sc.set_mode("draw_arc"); sc._arc_variant = "center"
    _clicks(view, sc, (310, 120), (470, 120), (310, 0))   # end 120 from the centre, r 160
    arc = sc._draw_arcs[-1]
    recs = _recs(sc)
    assert recs[0] == ("coincident", [(arc._uid, "center", None), (a._uid, "p2", None)])
    (t, (n, o)) = recs[1]
    assert t == "coincident" and o == (b._uid, "p2", None) and _at(arc, n[1], (470, 120))
    assert len(recs) == 2


def test_arc_end_on_radius_joins(vs):
    view, sc = vs
    e = _stub(sc, (310, -40))
    sc.set_mode("draw_arc"); sc._arc_variant = "center"
    _clicks(view, sc, (310, 120), (470, 120), (310, -40))  # end on the r = 160 circle
    arc = sc._draw_arcs[-1]
    (t, (n, o)), = _recs(sc)
    assert t == "coincident" and o == (e._uid, "p2", None) and _at(arc, n[1], (310, -40))


def test_arc_start_first_variant(vs):
    view, sc = vs
    a, b = _stub(sc, (470, 120)), _stub(sc, (310, 120))
    sc.set_mode("draw_arc"); sc._arc_variant = "start"
    _clicks(view, sc, (470, 120), (310, 120), (310, -100))  # start, centre, end bearing
    arc = sc._draw_arcs[-1]
    recs = _recs(sc)
    (t0, (n0, o0)), (t1, (n1, o1)) = recs
    assert o0 == (a._uid, "p2", None) and _at(arc, n0[1], (470, 120))
    assert (t1, n1, o1) == ("coincident", (arc._uid, "center", None), (b._uid, "p2", None))


def test_arc_ep_ends_join_then_h(vs):
    view, sc = vs
    a, b = _stub(sc, (310, 120)), _stub(sc, (470, 120))
    sc.set_mode("draw_arc"); sc._arc_variant = "endpoints"
    _clicks(view, sc, (310, 120), (470, 120), (450, -20))  # centre off the bisector (-> (390, -20))
    arc = sc._draw_arcs[-1]
    recs = _recs(sc)
    assert [t for t, _ in recs] == ["coincident", "coincident", "horizontal"]
    (_, (n0, o0)), (_, (n1, o1)) = recs[0], recs[1]
    assert o0 == (a._uid, "p2", None) and _at(arc, n0[1], (310, 120))
    assert o1 == (b._uid, "p2", None) and _at(arc, n1[1], (470, 120))


def test_arc_ep_centre_on_bisector_joins(vs):
    view, sc = vs
    c = _stub(sc, (390, 20))                               # t = 100 vs h = 80: no 90 deg pin
    sc.set_mode("draw_arc"); sc._arc_variant = "endpoints"
    _clicks(view, sc, (310, 300), (470, 300), (390, 20), mods={1: SHIFT})   # Shift: no H
    arc = sc._draw_arcs[-1]
    assert _recs(sc) == [("coincident", [(arc._uid, "center", None), (c._uid, "p2", None)])]


def test_arc_ep_bulge_off_bisector_none(vs):
    view, sc = vs
    _stub(sc, (430, 20))
    sc.set_mode("draw_arc"); sc._arc_variant = "endpoints"
    _clicks(view, sc, (310, 300), (470, 300), (430, 20), mods={1: SHIFT})
    assert len(sc._draw_arcs) == 1 and _recs(sc) == []


# ── polygon ───────────────────────────────────────────────────────────────

def test_polygon_inscribed_center_v0_then_h(vs):
    view, sc = vs
    a, b = _stub(sc, (310, 120)), _stub(sc, (370, 120))
    sc.set_mode("polygon"); sc._polygon_inscribed = True
    _clicks(view, sc, (310, 120), (370, 120), (480, 120))  # rotate due east: v0 on the radius click
    pg = sc._draw_polygons[-1]
    assert _recs(sc) == [
        ("coincident", [(pg._uid, "center", None), (a._uid, "p2", None)]),
        ("coincident", [(pg._uid, "v0", None), (b._uid, "p2", None)]),
        ("horizontal", [(pg._uid, "center", None), (pg._uid, "v0", None)])]


def test_polygon_circumscribed_center_and_facing_mid(vs):
    view, sc = vs
    a, b = _stub(sc, (310, 120)), _stub(sc, (370, 120))
    sc.set_mode("polygon"); sc._polygon_inscribed = False
    _clicks(view, sc, (310, 120), (370, 120), (480, 120))
    pg = sc._draw_polygons[-1]
    n = pg._sides
    assert _at(pg, f"m{n - 1}", (370, 120))               # ground truth: v0 at rot + pi/n
    assert _recs(sc) == [
        ("coincident", [(pg._uid, "center", None), (a._uid, "p2", None)]),
        ("coincident", [(pg._uid, f"m{n - 1}", None), (b._uid, "p2", None)]),
        ("vertical", [(pg._uid, f"s{n - 1}", None)])]


def test_polygon_rotate_click_never_joins(vs):
    view, sc = vs
    _stub(sc, (310, 300))
    sc.set_mode("polygon"); sc._polygon_inscribed = True
    _clicks(view, sc, (310, 120), (370, 150), (310, 300))  # rotate click on a snap, 180 off r
    pg = sc._draw_polygons[-1]
    assert _recs(sc) == [("vertical", [(pg._uid, "center", None), (pg._uid, "v0", None)])]


# ── ellipse ───────────────────────────────────────────────────────────────

def test_ellipse_center_a0_then_h(vs):
    view, sc = vs
    a, b = _stub(sc, (310, 120)), _stub(sc, (470, 120))
    sc.set_mode("draw_ellipse")
    _clicks(view, sc, (310, 120), (470, 120), (330, 170))
    el = sc._draw_ellipses[-1]
    assert _recs(sc) == [
        ("coincident", [(el._uid, "center", None), (a._uid, "p2", None)]),
        ("coincident", [(el._uid, "a0", None), (b._uid, "p2", None)]),
        ("horizontal", [(el._uid, "a0", None), (el._uid, "a1", None)])]


def test_ellipse_minor_on_perpendicular_joins_b0(vs):
    view, sc = vs
    m = _stub(sc, (310, 70))                               # rot 0: b0 = centre + ry up (Y-up)
    sc.set_mode("draw_ellipse")
    _clicks(view, sc, (310, 120), (470, 120), (310, 70), mods={1: SHIFT})   # Shift: no H
    el = sc._draw_ellipses[-1]
    assert _at(el, "b0", (310, 70))                        # precondition (ground truth)
    assert _recs(sc) == [("coincident", [(el._uid, "b0", None), (m._uid, "p2", None)])]


def test_ellipse_minor_off_perpendicular_none(vs):
    view, sc = vs
    _stub(sc, (350, 80))
    sc.set_mode("draw_ellipse")
    _clicks(view, sc, (310, 120), (470, 120), (350, 80), mods={1: SHIFT})
    assert len(sc._draw_ellipses) == 1 and _recs(sc) == []
