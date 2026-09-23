"""Inline-edit geometry for model-surface TextItem (spec: text-annotation-system
§ Inline edit). Caret / selection / hit-test all derive from _line_origin, the
same per-line origin the glyph outlines use, so they cannot drift."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QFontMetricsF, QPainterPath, QTextCursor


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


@pytest.mark.parametrize("align", ["L", "C", "R"])
def test_caret_matches_glyph_left_edge_on_wrapped_lines(scene, align):
    """Each soft-wrapped line's caret-at-line-start x lines up with that
    line's own glyph-outline left edge (isolated by that line's y band) —
    for every horizontal alignment. Also round-trips hit-testing on lines
    2 and 3 (both a line-start and a mid-line position)."""
    t = _text(scene, "aaa bbb ccc ddd eee", align=align, w=250.0)
    doc = t.document()
    doc.documentLayout().documentSize()
    block = doc.begin()
    layout = block.layout()
    assert layout.lineCount() >= 3, "fixture must wrap to >= 3 lines"
    outline = t._glyph_outline_local()

    for i in range(layout.lineCount()):
        line = layout.lineAt(i)
        pos = block.position() + line.textStart()
        _set_pos(t, pos)
        r = t.caret_rect_local()
        tol = 0.15 * r.height()          # side-bearing slack
        # Isolate this line's own glyphs by clipping the unified outline to
        # its painted y band (an independent, purely geometric check — it
        # does not reuse any of _line_origin/_layout_offsets internals).
        clip = QPainterPath()
        clip.addRect(QRectF(-1_000_000.0, r.top(), 2_000_000.0, r.height()))
        sub = outline.intersected(clip)
        assert not sub.isEmpty(), (align, i)
        assert abs(r.x() - sub.boundingRect().left()) < tol, \
            (align, i, r.x(), sub.boundingRect().left())

    for i in (1, 2):
        line = layout.lineAt(i)
        for rel in (line.textStart(), line.textStart() + line.textLength() // 2):
            pos = block.position() + rel
            _set_pos(t, pos)
            r = t.caret_rect_local()
            got = t.cursor_position_at(QPointF(r.x() + 0.01, r.center().y()))
            assert got == pos, (align, i, pos, got)


def test_selection_across_block_boundary_includes_newline_rect(scene):
    """Selecting across a block boundary ("ab\\ncd", 1→4) covers 'b' on line 1,
    the joining newline (a narrow sliver, since it has no glyph), and 'c' on
    line 2 — three rects on two distinct y's."""
    t = _text(scene, "ab\ncd")
    _set_pos(t, 4, anchor=1)
    rects = t.selection_rects_local()
    assert len(rects) == 3
    ys = sorted({round(r.top(), 3) for r in rects})
    assert len(ys) == 2
    newline_w = QFontMetricsF(t.font()).horizontalAdvance(" ")
    widths = [r.width() for r in rects]
    assert any(abs(w - newline_w) < 1e-6 for w in widths)


def test_hit_test_off_text_extremes(scene):
    """Points outside the text's own bounds resolve to the nearest line/edge,
    matching common editor hit-testing (not a hard failure/clamp-to-zero)."""
    t = _text(scene, "ab\ncd")
    # Above the first line -> a position on line 1 ("ab").
    top_pos = t.cursor_position_at(QPointF(0.0, -1000.0))
    assert 0 <= top_pos <= 2
    # Below the last line -> a position on line 2 ("cd").
    bottom_pos = t.cursor_position_at(QPointF(0.0, 100000.0))
    assert 3 <= bottom_pos <= 5
    _set_pos(t, 0)
    y0 = t.caret_rect_local().center().y()
    # Far left of a line -> that line's start.
    assert t.cursor_position_at(QPointF(-100000.0, y0)) == 0
    # Far right of a line -> that line's end (before its newline).
    assert t.cursor_position_at(QPointF(100000.0, y0)) == 2


def test_line_for_position_past_end_clamps_to_document_end(scene):
    """_line_for_position(pos) for a pos far past the document end resolves
    to the same block/line/rel as the document's actual end position, and
    the caret geometry built from either is identical."""
    t = _text(scene, "Hello")
    end_pos = len(t.toPlainText())
    block_a, line_a, rel_a = t._line_for_position(99)
    block_b, line_b, rel_b = t._line_for_position(end_pos)
    assert block_a.blockNumber() == block_b.blockNumber()
    assert rel_a == rel_b
    offsets = t._layout_offsets()
    origin_a = t._line_origin(block_a, line_a, offsets)
    origin_b = t._line_origin(block_b, line_b, offsets)
    xa, _ = line_a.cursorToX(rel_a)
    xb, _ = line_b.cursorToX(rel_b)
    caret_x_a = origin_a.x() + (xa - line_a.x())
    caret_x_b = origin_b.x() + (xb - line_b.x())
    assert abs(caret_x_a - caret_x_b) < 1e-6
