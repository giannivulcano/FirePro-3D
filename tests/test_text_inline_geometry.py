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
    """_line_for_position(99), far past a 5-char document's end, resolves to
    the same block-relative position as the document's real end — and caret
    geometry built through the public caret_rect_local() is identical whether
    the cursor is set to the document end or to 99 (Qt's own
    QTextCursor.setPosition guard leaves an out-of-range cursor at its
    previous — here, the end — position, so this also holds through the
    public path, not just the internal clamp)."""
    t = _text(scene, "Hello")
    end_pos = len(t.toPlainText())
    assert t._line_for_position(99)[2] == end_pos
    _set_pos(t, end_pos)
    r_end = t.caret_rect_local()
    _set_pos(t, 99)
    r_99 = t.caret_rect_local()
    assert r_end == r_99


# ── Painting (live failure mode simulated: QGraphicsTextItem.paint is a no-op) ──

def _render(t, w=800, h=300, pad=20):
    from PyQt6.QtGui import QImage, QPainter, QColor
    from PyQt6.QtWidgets import QStyleOptionGraphicsItem
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    p.translate(pad, pad)
    t.paint(p, QStyleOptionGraphicsItem(), None)
    p.end()
    return img


def _bright_in_column(img, x, y0, y1):
    return sum(1 for y in range(max(0, y0), min(img.height(), y1))
               for dx in (-1, 0, 1)
               if 0 <= x + dx < img.width() and img.pixelColor(x + dx, y).lightness() > 128)


@pytest.fixture
def no_doc_render(monkeypatch):
    from PyQt6.QtWidgets import QGraphicsTextItem
    monkeypatch.setattr(QGraphicsTextItem, "paint", lambda self, p, o, w=None: None)


def test_caret_paints_without_document_renderer(scene, no_doc_render):
    t = _text(scene, "Hi   ")               # trailing spaces → caret column is blank
    t.begin_edit()
    _set_pos(t, 4)
    t._caret_on = True
    r = t.caret_rect_local()
    img = _render(t)
    n = _bright_in_column(img, round(r.x()) + 20, round(r.top()) + 20, round(r.bottom()) + 20)
    assert n > 0.5 * r.height(), f"caret not painted ({n}px)"


def test_caret_hidden_in_off_blink_phase(scene, no_doc_render):
    t = _text(scene, "Hi   ")
    t.begin_edit()
    _set_pos(t, 4)
    t._caret_on = False
    r = t.caret_rect_local()
    img = _render(t)
    n = _bright_in_column(img, round(r.x()) + 20, round(r.top()) + 20, round(r.bottom()) + 20)
    assert n < 0.2 * r.height()


def test_selection_highlight_paints_without_document_renderer(scene, no_doc_render):
    t = _text(scene, "Hello")
    t.begin_edit()
    t._caret_on = False
    plain = _render(t)
    _set_pos(t, 5, anchor=0)
    sel = _render(t)
    rect = t.selection_rects_local()[0].translated(20, 20)
    changed = sum(1 for y in range(int(rect.top()), int(rect.bottom()))
                  for x in range(int(rect.left()), int(rect.right()))
                  if plain.pixel(x, y) != sel.pixel(x, y))
    assert changed > 0.2 * rect.width() * rect.height()


def test_model_surface_never_calls_document_renderer(scene, monkeypatch):
    """The engine==0 source is gone: model paint never reaches super().paint().

    Selection + caret-on are both armed so every editing paint branch (
    selection highlight, glyph outline, caret) actually executes this pass —
    otherwise a caret-only regression could hide behind the default
    ``_caret_on == False`` and slip past this guard undetected."""
    from PyQt6.QtWidgets import QGraphicsTextItem
    calls = []
    monkeypatch.setattr(QGraphicsTextItem, "paint",
                        lambda self, p, o, w=None: calls.append(1))
    t = _text(scene, "Hi")
    t.begin_edit()
    _set_pos(t, 2, anchor=0)
    t._caret_on = True
    _render(t)
    assert calls == []


def test_blink_timer_runs_only_while_editing(scene):
    t = _text(scene, "Hi")
    t.begin_edit()
    t._start_caret_blink()
    assert t._caret_timer is not None and t._caret_timer.isActive()
    t._stop_caret_blink()
    assert not t._caret_timer.isActive()
    assert t._caret_on is False
