"""AC2 E2E: an exactly axis-aligned committed segment records H / V (any
cause), on the finishing press's toggle XOR Shift; typed follows the toggle."""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF, QSettings, Qt
from PyQt6.QtWidgets import QApplication

from firepro3d.constants import AUTO_CONSTRAIN_KEY
from firepro3d.geometry_2d import LineItem
from tests._snap_polish_helpers import click, close_view, make_view, move

SHIFT = Qt.KeyboardModifier.ShiftModifier
CTRL = Qt.KeyboardModifier.ControlModifier
NONE = Qt.KeyboardModifier.NoModifier


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


def _line(sc, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b)); sc.addItem(ln); sc._draw_lines.append(ln)
    return ln


def _draw(view, sc, a, b, ma=NONE, mb=NONE):
    sc.set_mode("draw_line")
    move(view, QPointF(*a), ma); click(view, QPointF(*a), ma)
    move(view, QPointF(*b), mb); click(view, QPointF(*b), mb)
    return sc._draw_lines[-1]


# ── line / reference line ────────────────────────────────────────────────

def test_coincident_clicks_horizontal_and_vertical(vs):
    view, sc = vs
    h = _draw(view, sc, (310, 120), (470, 120))          # same pixel row, no snaps
    v = _draw(view, sc, (-310, 40), (-310, 260))
    assert _recs(sc) == [("horizontal", [(h._uid, "edge", None)]),
                         ("vertical", [(v._uid, "edge", None)])]


def test_one_degree_off_records_nothing(vs):
    view, sc = vs
    # tip 1 deg above +x over 160 mm: (310 + 160cos1, 120 - 160sin1) -> dy 2.79 mm
    tip = (310 + 160 * math.cos(math.radians(1)), 120 - 160 * math.sin(math.radians(1)))
    _draw(view, sc, (310, 120), tip)
    assert _recs(sc) == []


def test_ctrl_lock_at_90(vs):
    view, sc = vs
    n = _draw(view, sc, (310, 120), (318, 300), mb=CTRL)  # ~87.5 deg -> locked 90
    assert abs(n._pt2.x() - 310) < 1e-6                  # precondition: lock applied
    assert _recs(sc) == [("vertical", [(n._uid, "edge", None)])]


def test_typed_tip_at_0_follows_the_toggle(vs):
    view, sc = vs
    sc.set_mode("draw_line")
    move(view, QPointF(310, 120)); click(view, QPointF(310, 120))
    assert sc._geom_ctl._commit_draw_line_at(QPointF(500, 120))   # HUD applier = typed
    n = sc._draw_lines[-1]
    assert _recs(sc) == [("horizontal", [(n._uid, "edge", None)])]


def test_typed_tip_with_toggle_off_records_nothing(vs):
    view, sc = vs
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, False)
    sc.set_mode("draw_line")
    move(view, QPointF(310, 120)); click(view, QPointF(310, 120))
    assert sc._geom_ctl._commit_draw_line_at(QPointF(500, 120))
    assert _recs(sc) == []


def test_shift_on_the_finishing_click_suppresses(vs):
    view, sc = vs
    _draw(view, sc, (310, 120), (470, 120), mb=SHIFT)
    assert _recs(sc) == []
    n = _draw(view, sc, (310, 220), (470, 220), ma=SHIFT)  # Shift on click 1 only
    assert _recs(sc) == [("horizontal", [(n._uid, "edge", None)])]


def test_align_hv_ray(vs):
    view, sc = vs
    sc.set_align_enabled(True)
    sc.set_mode("draw_line")
    move(view, QPointF(310, 200)); click(view, QPointF(310, 200))   # anchor on y = 200
    # Acquire a point on y = 200 (dwell crossed; tests/test_align_seam.py's
    # controller call), then click 4 px off its H path.
    sc._align_controller.on_move(
        (0.0, 200.0), {"point": (0.0, 200.0), "snap_type": "endpoint",
                       "source_id": 1, "direction": None}, elapsed_ms=500)
    move(view, QPointF(480, 204)); click(view, QPointF(480, 204))
    n = sc._draw_lines[-1]
    assert abs(n._pt2.y() - 200) < 1e-9                 # precondition: ALIGN projected
    assert ("horizontal", [(n._uid, "edge", None)]) in _recs(sc)


def test_joins_win_a_redundant_hv(vs):
    """R3: both ends coincident with two Fixed lines' ends at one height ->
    the new line's H is implied, so the H (added last) is the one dropped."""
    view, sc = vs
    a = _line(sc, (0, 300), (100, 300))
    b = _line(sc, (400, 300), (500, 300))
    ctl = sc.constraint_ctl
    ctl.add("fix", [{"uid": a._uid, "h": "item"}]); ctl.add("fix", [{"uid": b._uid, "h": "item"}])
    n0 = len(ctl.constraints)
    n = _draw(view, sc, (100, 300), (400, 300))
    assert _recs(sc)[n0:] == [
        ("coincident", [(n._uid, "p1", None), (a._uid, "p2", None)]),
        ("coincident", [(n._uid, "p2", None), (b._uid, "p1", None)])]


def test_line_and_hv_are_one_undo_step(vs):
    view, sc = vs
    sc.push_undo_state()
    n_lines = len(sc._draw_lines)
    _draw(view, sc, (310, 120), (470, 120))
    assert len(sc.constraint_ctl.constraints) == 1
    sc.undo(); QApplication.processEvents()
    assert len(sc._draw_lines) == n_lines and sc.constraint_ctl.constraints == []


def test_gridline_gets_no_hv(vs):
    view, sc = vs
    sc.set_mode("draw_gridline")
    if sc.mode != "draw_gridline":
        pytest.skip("draw_gridline is refused in this scene role")
    move(view, QPointF(310, 120)); click(view, QPointF(310, 120))
    move(view, QPointF(470, 120)); click(view, QPointF(470, 120))
    assert _recs(sc) == []


# ── polyline ─────────────────────────────────────────────────────────────

from PyQt6.QtTest import QTest  # noqa: E402


def _key(view, key):
    view.setFocus()
    QTest.keyClick(view.viewport(), key)
    QApplication.processEvents()


def _poly(view, sc, *pts, mods=None, finish=Qt.Key.Key_Return):
    sc.set_mode("polyline")
    for i, p in enumerate(pts):
        m = (mods or {}).get(i, NONE)
        move(view, QPointF(*p), m); click(view, QPointF(*p), m)
    if finish is not None:
        _key(view, finish)


def test_polyline_segments_including_closing(vs):
    view, sc = vs
    # s0 H, s1 V, s2 oblique, closing s3 = (310,320)->(310,120) V (close click)
    _poly(view, sc, (310, 120), (470, 120), (470, 260), (310, 320), (310, 120),
          finish=None)
    pl = sc._polylines[-1]
    assert pl.is_closed()
    assert _recs(sc) == [("horizontal", [(pl._uid, "s0", None)]),
                         ("vertical", [(pl._uid, "s1", None)]),
                         ("vertical", [(pl._uid, "s3", None)])]


def test_polyline_shift_on_the_ending_vertex_skips_that_segment(vs):
    view, sc = vs
    _poly(view, sc, (310, 120), (470, 120), (470, 260), mods={1: SHIFT})
    pl = sc._polylines[-1]
    assert _recs(sc) == [("vertical", [(pl._uid, "s1", None)])]


def test_two_vertex_polyline_hv_lands_on_the_line_edge(vs):
    view, sc = vs
    _poly(view, sc, (310, 120), (470, 120))
    ln = sc._draw_lines[-1]
    assert _recs(sc) == [("horizontal", [(ln._uid, "edge", None)])]


def test_delete_pop_drops_that_vertex_hv(vs):
    view, sc = vs
    sc.set_mode("polyline")
    for p in ((310, 120), (470, 120)):                    # s0 H (flag on v1)
        move(view, QPointF(*p)); click(view, QPointF(*p))
    _key(view, Qt.Key.Key_Delete)                         # pop v1 -> its flag goes too
    move(view, QPointF(470, 120), SHIFT); click(view, QPointF(470, 120), SHIFT)
    move(view, QPointF(520, 300)); click(view, QPointF(520, 300))
    _key(view, Qt.Key.Key_Return)
    assert _recs(sc) == []


# ── rect / polygon / ellipse / arc End Points ────────────────────────────

def _clicks(view, sc, *pts, mods=None):
    for i, p in enumerate(pts):
        m = (mods or {}).get(i, NONE)
        move(view, QPointF(*p), m); click(view, QPointF(*p), m)


def test_rect_corner_records_on_the_drawn_side(vs):
    from firepro3d import auto_constrain as ac
    view, sc = vs
    sc.set_mode("draw_rectangle"); sc._draw_rect_from_center = False
    _clicks(view, sc, (310, 120), (310, 300), (200, 210))   # first side vertical
    r = sc._draw_rects[-1]
    (ct, refs), = _recs(sc)
    assert ct == "vertical" and refs[0][0] == r._uid
    # Ground truth: the named edge is the drawn x = 310 side (the depth side is x = 200).
    edges = {ref["h"]: (a, b) for k, ref, a, b in ac.item_handles(r) if k == "edge"}
    a, b = edges[refs[0][1]]
    assert abs(a.x() - 310) < 1e-6 and abs(b.x() - 310) < 1e-6
    assert abs(r._angle) > 1.0                               # rotated rect: not "left"


def test_rect_centre_records_on_the_clicked_side(vs):
    view, sc = vs
    sc.set_mode("draw_rectangle"); sc._draw_rect_from_center = True
    _clicks(view, sc, (310, 120), (400, 120), (330, 170))   # H radial -> V facing side
    r = sc._draw_rects[-1]
    (ct, refs), = _recs(sc)
    assert ct == "vertical" and refs[0][0] == r._uid
    # Ground truth: the named edge is the clicked x = 400 side (its opposite is x = 220).
    from firepro3d import auto_constrain as ac
    edges = {ref["h"]: (a, b) for k, ref, a, b in ac.item_handles(r) if k == "edge"}
    a, b = edges[refs[0][1]]
    assert abs(a.x() - 400) < 1e-6 and abs(b.x() - 400) < 1e-6


def test_rect_shift_on_the_side_click_suppresses(vs):
    view, sc = vs
    sc.set_mode("draw_rectangle"); sc._draw_rect_from_center = False
    _clicks(view, sc, (310, 120), (470, 120), (400, 220), mods={1: SHIFT})
    assert _recs(sc) == []


def test_rect_oblique_records_nothing(vs):
    view, sc = vs
    sc.set_mode("draw_rectangle"); sc._draw_rect_from_center = False
    _clicks(view, sc, (310, 120), (470, 180), (400, 300))
    assert _recs(sc) == []


def test_polygon_inscribed_center_v0(vs):
    view, sc = vs
    sc.set_mode("polygon"); sc._polygon_inscribed = True
    _clicks(view, sc, (310, 120), (370, 120), (310, 300))   # rotate click due south
    pg = sc._draw_polygons[-1]
    assert _recs(sc) == [("vertical", [(pg._uid, "center", None), (pg._uid, "v0", None)])]


def test_polygon_circumscribed_facing_side(vs):
    view, sc = vs
    sc.set_mode("polygon"); sc._polygon_inscribed = False
    _clicks(view, sc, (310, 120), (370, 120), (480, 120))   # rotate click due east
    pg = sc._draw_polygons[-1]
    n = pg._sides
    assert _recs(sc) == [("vertical", [(pg._uid, f"s{n - 1}", None)])]


def test_polygon_typed_rotation_90(vs):
    view, sc = vs
    sc.set_mode("polygon"); sc._polygon_inscribed = True
    _clicks(view, sc, (310, 120), (370, 150))
    assert sc._geom_ctl._commit_polygon_rotated(90.0)        # rotation HUD = typed
    pg = sc._draw_polygons[-1]
    assert _recs(sc) == [("vertical", [(pg._uid, "center", None), (pg._uid, "v0", None)])]


def test_ellipse_axis(vs):
    view, sc = vs
    sc.set_mode("draw_ellipse")
    _clicks(view, sc, (310, 120), (470, 120), (310, 170))
    el = sc._draw_ellipses[-1]
    assert _recs(sc) == [("horizontal", [(el._uid, "a0", None), (el._uid, "a1", None)])]


def test_arc_end_points_chord(vs):
    view, sc = vs
    sc.set_mode("draw_arc"); sc._arc_variant = "endpoints"
    _clicks(view, sc, (310, 120), (470, 120), (390, 60))
    arc = sc._draw_arcs[-1]
    assert _recs(sc) == [("horizontal", [(arc._uid, "start", None), (arc._uid, "end", None)])]


def test_arc_end_points_shift_on_chord_click_suppresses(vs):
    view, sc = vs
    sc.set_mode("draw_arc"); sc._arc_variant = "endpoints"
    _clicks(view, sc, (310, 120), (470, 120), (390, 60), mods={1: SHIFT})
    assert len(sc._draw_arcs) >= 1 and _recs(sc) == []


def test_arc_centre_variant_radials_never(vs):
    view, sc = vs
    sc.set_mode("draw_arc"); sc._arc_variant = "center"
    _clicks(view, sc, (310, 120), (470, 120), (310, 0))
    assert len(sc._draw_arcs) >= 1 and _recs(sc) == []


def test_circle_rim_never(vs):
    view, sc = vs
    sc.set_mode("draw_circle")
    _clicks(view, sc, (310, 120), (470, 120))
    assert len(sc._draw_circles) >= 1 and _recs(sc) == []


def test_polyline_shift_on_the_close_click_skips_the_closing_side(vs):
    view, sc = vs
    _poly(view, sc, (310, 120), (470, 120), (470, 260), (310, 320), (310, 120),
          mods={4: SHIFT}, finish=None)
    pl = sc._polylines[-1]
    assert pl.is_closed()
    assert _recs(sc) == [("horizontal", [(pl._uid, "s0", None)]),
                         ("vertical", [(pl._uid, "s1", None)])]


def test_typed_polyline_vertex_at_0_follows_the_toggle(vs):
    view, sc = vs
    sc.set_mode("polyline")
    move(view, QPointF(310, 120)); click(view, QPointF(310, 120))
    move(view, QPointF(400, 300)); click(view, QPointF(400, 300))   # s0 oblique
    assert sc._geom_ctl._commit_polyline_at(QPointF(560, 300))     # typed v2: s1 H
    _key(view, Qt.Key.Key_Return)
    pl = sc._polylines[-1]
    assert _recs(sc) == [("horizontal", [(pl._uid, "s1", None)])]


def test_polyline_and_hv_are_one_undo_step(vs):
    view, sc = vs
    sc.push_undo_state()
    n_pl = len(sc._polylines)
    _poly(view, sc, (310, 120), (470, 120), (520, 300))
    assert len(sc.constraint_ctl.constraints) == 1
    sc.undo(); QApplication.processEvents()
    assert len(sc._polylines) == n_pl and sc.constraint_ctl.constraints == []
