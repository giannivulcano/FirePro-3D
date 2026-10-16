"""AC1 AD6/AD7 -- resolve_snap on REAL engine snaps (shown view, posted
moves in draw_line mode -> scene._snap_result), plan_joins records."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import auto_constrain as ac
from firepro3d.geometry_2d import (CircleItem, LineItem, PolylineItem,
                                   RectangleItem, SplineItem)
from firepro3d.snap_engine import OsnapResult
from tests._snap_polish_helpers import close_view, make_view, move

_RESET = QPointF(-395.0, 295.0)


@pytest.fixture
def vs(qapp):
    view, sc = make_view(role="block_editor", scale=1.0, mode=None)
    sc.set_align_enabled(False)
    sc.set_mode("draw_line")
    yield view, sc
    close_view(view, sc)


def _add(sc, it, bucket):
    sc.addItem(it)
    getattr(sc, bucket).append(it)
    return it


def _snap(view, sc, p):
    move(view, _RESET)
    move(view, p)
    return sc._snap_result


def test_endpoint_resolves_to_the_line_end(vs):
    view, sc = vs
    ln = _add(sc, LineItem(QPointF(0, 0), QPointF(200, 0)), "_draw_lines")
    t = ac.resolve_snap(_snap(view, sc, QPointF(200, 0)))
    assert t == ac.Target("point", {"uid": ln._uid, "h": "p2"}, (200.0, 0.0))


def test_midpoint_resolves_to_mid(vs):
    view, sc = vs
    ln = _add(sc, LineItem(QPointF(0, 0), QPointF(200, 0)), "_draw_lines")
    r = _snap(view, sc, QPointF(100, 0))
    assert r.snap_type == "midpoint"
    assert ac.resolve_snap(r).ref == {"uid": ln._uid, "h": "mid"}


def test_polyline_vertex_and_segment(vs):
    view, sc = vs
    pl = PolylineItem(QPointF(0, 0))
    for p in ((200, 0), (200, 200)):
        pl.append_point(QPointF(*p))
    pl.finalize()
    _add(sc, pl, "_polylines")
    assert ac.resolve_snap(_snap(view, sc, QPointF(200, 0))).ref == {"uid": pl._uid, "h": "v1"}
    r = _snap(view, sc, QPointF(200, 63))                 # NEA on s1
    assert r.snap_type == "nearest"
    t = ac.resolve_snap(r)
    assert (t.kind, t.ref) == ("edge", {"uid": pl._uid, "h": "s1"})


def test_rect_corner_and_side(vs):
    view, sc = vs
    rc = RectangleItem(QPointF(50, 50), QPointF(250, 150))   # off the origin snap
    _add(sc, rc, "_draw_rects")
    t = ac.resolve_snap(_snap(view, sc, QPointF(50, 50)))
    assert t.kind == "point" and t.ref["uid"] == rc._uid
    r = _snap(view, sc, QPointF(113, 50))
    assert r.snap_type == "nearest"
    t2 = ac.resolve_snap(r)
    assert t2.kind == "edge" and t2.ref["uid"] == rc._uid


def test_circle_centre_and_rim(vs):
    view, sc = vs
    c = _add(sc, CircleItem(QPointF(300, 0), 80.0), "_draw_circles")
    assert ac.resolve_snap(_snap(view, sc, QPointF(300, 0))).ref == {"uid": c._uid, "h": "center"}
    r = _snap(view, sc, QPointF(340.0, 69.2820323))       # 60 deg on the rim: NEA (45 deg reports tangent)
    assert r.snap_type == "nearest"
    t = ac.resolve_snap(r)
    assert (t.kind, t.ref) == ("curve", {"uid": c._uid, "h": "curve"})


def test_origin_resolves_to_the_ground(vs):
    view, sc = vs
    r = _snap(view, sc, QPointF(0, 0))
    assert r.snap_type == "origin"
    assert ac.resolve_snap(r) == ac.Target("point", {"ref": "origin"}, (0.0, 0.0))


def test_silent_nothing_kinds(vs):
    view, sc = vs
    _add(sc, LineItem(QPointF(100, 200), QPointF(300, 200)), "_draw_lines")
    _add(sc, LineItem(QPointF(200, 100), QPointF(200, 300)), "_draw_lines")
    r = _snap(view, sc, QPointF(200.4, 200.4))            # crossing, off the origin
    assert r.snap_type == "intersection"
    assert ac.resolve_snap(r) is None
    assert ac.resolve_snap(None) is None
    sp = SplineItem([QPointF(300, 0), QPointF(350, 50), QPointF(400, 0)])
    sc.addItem(sp)
    # Property under test: a source with no adapter resolves to nothing (D5);
    # the snap kind is irrelevant, so the result is built directly.
    r2 = OsnapResult(point=QPointF(300, 0), snap_type="endpoint", source_item=sp)
    assert ac.resolve_snap(r2) is None


def test_plan_joins_records():
    p = ac.Target("point", {"uid": "B", "h": "p2"}, (1.0, 2.0))
    e = ac.Target("edge", {"uid": "B", "h": "edge"}, (1.0, 2.0))
    per = ac.Target("edge", {"uid": "B", "h": "edge"}, (1.0, 2.0), perpendicular=True)
    assert ac.plan_joins("N", "p1", "edge", p) == [
        ("coincident", [{"uid": "N", "h": "p1"}, {"uid": "B", "h": "p2"}])]
    assert ac.plan_joins("N", "p2", "edge", e) == [
        ("point_on_curve", [{"uid": "N", "h": "p2"}, {"uid": "B", "h": "edge"}])]
    assert ac.plan_joins("N", "v2", "s1", per) == [
        ("point_on_curve", [{"uid": "N", "h": "v2"}, {"uid": "B", "h": "edge"}]),
        ("perpendicular", [{"uid": "N", "h": "s1"}, {"uid": "B", "h": "edge"}])]
    assert ac.plan_joins("N", "v0", None, per) == [
        ("point_on_curve", [{"uid": "N", "h": "v0"}, {"uid": "B", "h": "edge"}])]


def test_matches_and_remap():
    t = ac.Target("point", {"ref": "origin"}, (0.0, 0.0))
    assert ac.matches(t, QPointF(0.0004, 0.0))
    assert not ac.matches(t, QPointF(0.01, 0.0))
    assert not ac.matches(None, QPointF(0, 0))
    assert [ac.remap_handle(h) for h in ("v0", "v1", "s0", "m0", "v2")] == [
        "p1", "p2", "edge", "mid", None]
