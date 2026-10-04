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
