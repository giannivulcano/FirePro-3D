"""LT2-3 / T-edit -- style survives every derive path; free ends reset."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import (ArcItem, CircleItem, LineItem, PolylineItem,
                                   RectangleItem)
from firepro3d.model_space import Model_Space


def _styled(item):
    item.style["weight"] = "Heavy"
    item.style["linetype"] = "by_block"
    item.style["colour"] = "#ff00ff"
    item.style["start"]["end"] = "by_block"
    item.style["finish"]["end"] = "by_block"
    return item


def _editor():
    return Model_Space(scene_role="block_editor")


def _same_body(a, b):
    for k in ("linetype", "weight", "colour"):
        assert a.style[k] == b.style[k], k


def test_break_line_cut_ends_fresh(qapp):
    ms = _editor()
    ln = _styled(LineItem(QPointF(0, 0), QPointF(100, 0)))
    ms.addItem(ln); ms._draw_lines.append(ln)
    ms._tools._break_item(ln, QPointF(40, 0), QPointF(60, 0))
    l1, l2 = ms._draw_lines
    for piece in (l1, l2):
        _same_body(ln, piece)
    assert l1.style["start"]["end"] == "by_block"
    assert l1.style["finish"]["end"] == "by_linetype"
    assert l2.style["start"]["end"] == "by_linetype"
    assert l2.style["finish"]["end"] == "by_block"


def test_break_circle_to_arc_both_fresh(qapp):
    ms = _editor()
    c = _styled(CircleItem(QPointF(0, 0), 50.0))
    ms.addItem(c); ms._draw_circles.append(c)
    ms._tools._break_item(c, QPointF(50, 0), QPointF(0, 50))
    (arc,) = ms._draw_arcs
    _same_body(c, arc)
    assert arc.style["start"]["end"] == arc.style["finish"]["end"] == "by_linetype"


def test_break_at_point_arc(qapp):
    ms = _editor()
    a = _styled(ArcItem(QPointF(0, 0), 50.0, 0.0, 90.0))
    ms.addItem(a); ms._draw_arcs.append(a)
    ms._tools._break_at_point(a, QPointF(35.355, -35.355))
    a1, a2 = ms._draw_arcs
    assert a1.style["start"]["end"] == "by_block"
    assert a1.style["finish"]["end"] == "by_linetype"
    assert a2.style["start"]["end"] == "by_linetype"
    assert a2.style["finish"]["end"] == "by_block"


def test_explode_and_join_keep_style(qapp):
    ms = _editor()
    r = _styled(RectangleItem(QPointF(0, 0), QPointF(50, 50)))
    ms.addItem(r); ms._draw_rects.append(r); r.setSelected(True)
    ms._tools.explode_selected_items()
    assert len(ms._draw_lines) == 4
    for ln in ms._draw_lines:
        _same_body(r, ln)
    for ln in ms._draw_lines:
        ln.setSelected(True)
    ms._tools.join_selected_items()
    (pl,) = ms._polylines
    _same_body(r, pl)


def test_fillet_new_arc_fresh_and_trimmed_ends_fresh(qapp):
    ms = _editor()
    l1 = _styled(LineItem(QPointF(0, 0), QPointF(100, 0)))
    l2 = _styled(LineItem(QPointF(100, 0), QPointF(100, 100)))
    for ln in (l1, l2):
        ms.addItem(ln); ms._draw_lines.append(ln)
    data = ms._tools._compute_fillet(l1, l2, 10.0)
    assert data is not None
    ms._tools._commit_fillet(data)
    (arc,) = ms._draw_arcs
    _same_body(l1, arc)
    assert arc.style["start"]["end"] == arc.style["finish"]["end"] == "by_linetype"
    end1 = "start" if data["near1"] == "_pt1" else "finish"
    assert l1.style[end1]["end"] == "by_linetype"
    other = "finish" if end1 == "start" else "start"
    assert l1.style[other]["end"] == "by_block"


def test_chamfer_new_line_fresh_and_trimmed_ends_fresh(qapp):
    ms = _editor()
    l1 = _styled(LineItem(QPointF(0, 0), QPointF(100, 0)))
    l2 = _styled(LineItem(QPointF(100, 0), QPointF(100, 100)))
    for ln in (l1, l2):
        ms.addItem(ln); ms._draw_lines.append(ln)
    data = ms._tools._compute_chamfer(l1, l2, 10.0)
    assert data is not None
    ms._tools._commit_chamfer(data)
    bevel = ms._draw_lines[-1]
    assert bevel is not l1 and bevel is not l2
    _same_body(l1, bevel)
    assert bevel.style["start"]["end"] == bevel.style["finish"]["end"] == "by_linetype"
    end2 = "start" if data["near2"] == "_pt1" else "finish"
    assert l2.style[end2]["end"] == "by_linetype"


def test_polyline_two_point_swap_keeps_style(qapp):
    """Reachable path: draw polyline, Enter after 2 points -> LineItem."""
    ms = _editor()
    pl = _styled(PolylineItem(QPointF(0, 0)))
    pl.append_point(QPointF(10, 0))
    ms.addItem(pl); ms._polylines.append(pl)
    ms._polyline_active = pl
    expected = {k: (dict(v) if isinstance(v, dict) else v)
                for k, v in pl.style.items()}
    ms._finish_polyline()
    (ln,) = ms._draw_lines
    assert ln.style == expected


def test_new_primitive_default_style(qapp):
    ms = _editor()
    st = ms._geom_style()
    assert st["linetype"] == "continuous" and st["weight"] == "by_block"


# -- in-place trim free ends (real two-phase _handle_trim_click flow) --------

def _trim(item, attr, edge_pts, edge_click, item_click):
    from tests._snap_polish_helpers import click, close_view, make_view
    view, scene = make_view(scale=1.0, mode=None)
    try:
        _styled(item)
        scene.addItem(item); getattr(scene, attr).append(item)
        edge = LineItem(QPointF(*edge_pts[0]), QPointF(*edge_pts[1]))
        scene.addItem(edge); scene._draw_lines.append(edge)
        scene.set_mode("trim")
        click(view, QPointF(*edge_click))          # cutting edge
        click(view, QPointF(*item_click))          # piece to remove
        return {e: item.style[e]["end"] for e in ("start", "finish")}
    finally:
        close_view(view, scene)


def test_trim_line_pt1_side_start_fresh(qapp):
    ends = _trim(LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines",
                 ((50, -100), (50, 100)), (50, 80), (10, 0))
    assert ends == {"start": "by_linetype", "finish": "by_block"}


def test_trim_line_pt2_side_finish_fresh(qapp):
    ends = _trim(LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines",
                 ((50, -100), (50, 100)), (50, 80), (90, 0))
    assert ends == {"start": "by_block", "finish": "by_linetype"}


def test_trim_arc_start_moves_start_fresh(qapp):
    import math
    r = 100.0
    vis = lambda d: (r * math.cos(math.radians(d)), -r * math.sin(math.radians(d)))
    ends = _trim(ArcItem(QPointF(0, 0), r, 0.0, 180.0), "_draw_arcs",
                 ((50, -200), (50, 200)), (50, 150), vis(20))
    assert ends == {"start": "by_linetype", "finish": "by_block"}


def test_trim_arc_span_shrinks_finish_fresh(qapp):
    import math
    r = 100.0
    vis = lambda d: (r * math.cos(math.radians(d)), -r * math.sin(math.radians(d)))
    ends = _trim(ArcItem(QPointF(0, 0), r, 0.0, 180.0), "_draw_arcs",
                 ((50, -200), (50, 200)), (50, 150), vis(120))
    assert ends == {"start": "by_block", "finish": "by_linetype"}


def test_join_takes_outer_ends_of_sources(qapp):
    """LT2-3: Join = outer ends of the sources (orientation-aware)."""
    ms = _editor()
    # a: (0,0)->(10,0); b is drawn REVERSED: (20,0)->(10,0), so the chain
    # a + reversed(b) ends at b's *start*.  c prepends: (-10,0)->(0,0).
    a = LineItem(QPointF(0, 0), QPointF(10, 0))
    b = LineItem(QPointF(20, 0), QPointF(10, 0))
    c = LineItem(QPointF(0, 0), QPointF(-10, 0))   # reversed prepend
    a.style["start"]["end"] = "A0"; a.style["finish"]["end"] = "A1"
    b.style["start"]["end"] = "B0"; b.style["finish"]["end"] = "B1"
    c.style["start"]["end"] = "C0"; c.style["finish"]["end"] = "C1"
    for ln in (a, b, c):
        ms.addItem(ln); ms._draw_lines.append(ln)
        ln.setSelected(True)
    ms._tools.join_selected_items()
    (pl,) = ms._polylines
    pts = [(round(p.x()), round(p.y())) for p in pl._points]
    # selectedItems() order is unspecified, so the chain may run either way;
    # the outer end at each extreme point is fixed by the geometry:
    # (-10,0) is c's finish, (20,0) is b's start.
    outer = {(-10, 0): "C1", (20, 0): "B0"}
    assert {pts[0], pts[-1]} == set(outer), pts
    assert pl.style["start"]["end"] == outer[pts[0]]
    assert pl.style["finish"]["end"] == outer[pts[-1]]
