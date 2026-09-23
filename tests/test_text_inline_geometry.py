"""Inline-edit geometry for model-surface TextItem (spec: text-annotation-system
§ Inline edit). Caret / selection / hit-test all derive from _line_origin, the
same per-line origin the glyph outlines use, so they cannot drift."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTextCursor


def _text(scene, text="Hello world", align="L", valign="T", box_h=0.0, w=600.0):
    from firepro3d.text_item import TextItem, TextAnnotationData
    d = TextAnnotationData(text=text, x=0.0, y=0.0, height_mm=40.0, wrap_width_mm=w)
    d.color = "#ffffff"
    d.align = align
    d.valign = valign
    d.box_height_mm = box_h
    t = TextItem(d)
    scene.addItem(t)
    t._apply_format()
    return t


@pytest.fixture
def scene(qapp):
    from firepro3d.model_space import Model_Space
    return Model_Space(scene_role="block_editor")


def _set_pos(t, pos, anchor=None):
    c = t.textCursor()
    if anchor is not None:
        c.setPosition(anchor)
        c.setPosition(pos, QTextCursor.MoveMode.KeepAnchor)
    else:
        c.setPosition(pos)
    t.setTextCursor(c)


@pytest.mark.parametrize("align", ["L", "C", "R"])
def test_caret_x_matches_glyph_outline_edges(scene, align):
    """Caret at pos 0 sits at the outline's left edge; at end, at its right edge
    (within a glyph side-bearing) — for every horizontal alignment."""
    t = _text(scene, "Hello", align=align)
    ob = t._glyph_outline_local().boundingRect()
    _set_pos(t, 0)
    x0 = t.caret_rect_local().x()
    _set_pos(t, 5)
    x1 = t.caret_rect_local().x()
    tol = 0.15 * t.caret_rect_local().height()     # side-bearing slack
    assert abs(x0 - ob.left()) < tol, (align, x0, ob.left())
    assert abs(x1 - ob.right()) < tol, (align, x1, ob.right())


@pytest.mark.parametrize("align", ["L", "C", "R"])
def test_hit_test_round_trips_caret(scene, align):
    """cursor_position_at(caret point) returns the same position (pos→x→pos)."""
    t = _text(scene, "Hello world", align=align)
    for pos in (0, 3, 6, 11):
        _set_pos(t, pos)
        r = t.caret_rect_local()
        got = t.cursor_position_at(QPointF(r.x() + 0.01, r.center().y()))
        assert got == pos, (align, pos, got)


def test_caret_follows_valign(scene):
    """Bottom-aligned text in a tall box puts the caret in the lower half."""
    t = _text(scene, "Hi", valign="B", box_h=600.0)
    _set_pos(t, 0)
    box = t._box_rect_local()
    assert t.caret_rect_local().top() > box.center().y()


def test_caret_on_second_line(scene):
    """A caret after a newline sits one line lower than one on line 1."""
    t = _text(scene, "ab\ncd")
    _set_pos(t, 1)
    y1 = t.caret_rect_local().top()
    _set_pos(t, 4)
    y2 = t.caret_rect_local().top()
    assert y2 > y1 + 0.5 * t.caret_rect_local().height()


def test_caret_exists_for_empty_text(scene):
    t = _text(scene, "")
    r = t.caret_rect_local()
    assert r.height() > 0


def test_selection_rects_cover_selected_run(scene):
    t = _text(scene, "Hello world")
    _set_pos(t, 5, anchor=0)            # select "Hello"
    rects = t.selection_rects_local()
    assert len(rects) == 1
    _set_pos(t, 0)
    x0 = t.caret_rect_local().x()
    _set_pos(t, 5)
    x5 = t.caret_rect_local().x()
    assert abs(rects[0].left() - x0) < 1e-6
    assert abs(rects[0].right() - x5) < 1e-6


def test_no_selection_no_rects(scene):
    t = _text(scene, "Hello")
    _set_pos(t, 2)
    assert t.selection_rects_local() == []
