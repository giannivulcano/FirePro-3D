"""Derive paths carry the reference / printed flags (design RG14).

Each guard drives the real ``SceneTools`` method on a real ``Model_Space``
(block-editor role) and asserts the produced items' flags.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import (ArcItem, CircleItem, LineItem,
                                   PolylineItem, RectangleItem)


@pytest.fixture
def editor_scene(shown_model_view):
    _view, scene = shown_model_view
    scene.scene_role = "block_editor"
    return scene


def _flag(item, ref, printed):
    item.reference, item.printed = ref, printed
    return item


def _add_line(scene, ln):
    scene.addItem(ln)
    scene._draw_lines.append(ln)
    return ln


def _lines(scene):
    return [l for l in scene._draw_lines if l.scene() is scene]


@pytest.mark.parametrize("ref,printed", [(True, True), (True, False)])
def test_break_at_point_on_reference_line_yields_reference_pieces(
        editor_scene, ref, printed):
    scene = editor_scene
    li = _add_line(scene, _flag(LineItem(QPointF(0, 0), QPointF(600, 0)),
                                ref, printed))
    scene._tools._break_at_point(li, QPointF(300, 0))
    pieces = _lines(scene)
    assert len(pieces) == 2 and li not in scene._draw_lines
    assert all(p.reference is ref and p.printed is printed for p in pieces)


def test_break_between_points_on_reference_line(editor_scene):
    scene = editor_scene
    li = _add_line(scene, _flag(LineItem(QPointF(0, 0), QPointF(600, 0)),
                                True, True))
    scene._tools._break_item(li, QPointF(200, 0), QPointF(400, 0))
    pieces = _lines(scene)
    assert len(pieces) == 2
    assert all(p.reference and p.printed for p in pieces)


def test_break_on_reference_circle_yields_reference_arc(editor_scene):
    scene = editor_scene
    c = _flag(CircleItem(QPointF(0, 0), 50.0), True, True)
    scene.addItem(c)
    scene._draw_circles.append(c)
    scene._tools._break_item(c, QPointF(50, 0), QPointF(0, 50))
    arcs = [a for a in scene._draw_arcs if a.scene() is scene]
    assert len(arcs) == 1 and c not in scene._draw_circles
    assert arcs[0].reference is True and arcs[0].printed is True


def test_explode_reference_rectangle_yields_reference_lines(editor_scene):
    scene = editor_scene
    r = _flag(RectangleItem(QPointF(0, 0), QPointF(100, 50)), True, True)
    scene.addItem(r)
    scene._draw_rects.append(r)
    r.setSelected(True)
    scene._tools.explode_selected_items()
    lines = _lines(scene)
    assert len(lines) == 4
    assert all(l.reference and l.printed for l in lines)


def test_explode_reference_closed_polyline_yields_reference_lines(
        editor_scene):
    scene = editor_scene
    pl = PolylineItem(QPointF(0, 0))
    for p in (QPointF(100, 0), QPointF(100, 50), QPointF(0, 50)):
        pl.append_point(p)
    pl.close()
    _flag(pl, True, False)
    scene.addItem(pl)
    scene._polylines.append(pl)
    pl.setSelected(True)
    scene._tools.explode_selected_items()
    lines = _lines(scene)
    assert lines and len(lines) >= len(pl._points) - 1
    assert all(l.reference is True and l.printed is False for l in lines)


def test_join_two_reference_lines_yields_reference_polyline(editor_scene):
    scene = editor_scene
    a = _add_line(scene, _flag(LineItem(QPointF(0, 0), QPointF(100, 0)),
                               True, True))
    b = _add_line(scene, _flag(LineItem(QPointF(100, 0), QPointF(100, 80)),
                               True, True))
    a.setSelected(True)
    b.setSelected(True)
    scene._tools.join_selected_items()
    assert len(scene._polylines) == 1
    pl = scene._polylines[0]
    assert pl.reference is True and pl.printed is True


def test_normal_sources_yield_normal_pieces(editor_scene):
    scene = editor_scene
    li = _add_line(scene, LineItem(QPointF(0, 0), QPointF(600, 0)))
    scene._tools._break_at_point(li, QPointF(300, 0))
    pieces = _lines(scene)
    assert len(pieces) == 2
    assert all(p.reference is False and p.printed is False for p in pieces)
    c = CircleItem(QPointF(0, 0), 50.0)
    scene.addItem(c)
    scene._draw_circles.append(c)
    scene._tools._break_item(c, QPointF(50, 0), QPointF(0, 50))
    arc = [a for a in scene._draw_arcs if a.scene() is scene][0]
    assert arc.reference is False and arc.printed is False


def test_mixed_join_reports_current_behaviour(editor_scene):
    """Characterisation only (not a contract): copy_style copies from items[0]."""
    scene = editor_scene
    a = _add_line(scene, _flag(LineItem(QPointF(0, 0), QPointF(100, 0)),
                               True, True))
    b = _add_line(scene, LineItem(QPointF(100, 0), QPointF(100, 80)))
    a.setSelected(True)
    b.setSelected(True)
    scene._tools.join_selected_items()
    pl = scene._polylines[0]
    print("MIXED JOIN ->", pl.reference, pl.printed,
          "order:", [i.reference for i in (a, b)])
