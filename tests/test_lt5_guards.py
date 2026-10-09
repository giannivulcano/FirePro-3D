"""LT5 seam-coverage guards: E9 paste keeps the end records (mirrored
included) and the pasted line draws its end; Q14 ends never grow the pick
shape but do grow the bounds; Q8 text and hatch-fill end content render in
the using line's colour. Real scenes, real paste data (never the OS
clipboard), observable pixels."""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.model_space import Model_Space
from firepro3d.text_item import TextAnnotationData, TextItem
from tests.lt5_support import half_arrow

_W, _H = 300, 250
_RED = "#ff0000"


def _render(ms, rect):
    img = QImage(_W, _H, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, _W, _H), rect)
    p.end()
    return img


def _offband(a, b, band=4):
    """Pixels that differ outside the line's own rows (the end's content)."""
    return [(x, y) for y in range(_H) if abs(y - _H // 2) > band
            for x in range(_W) if a.pixel(x, y) != b.pixel(x, y)]


def _frame(ms):
    """Line length and a crop around its finish (50 px per printed mm)."""
    s = ms.scale_manager.drawing_scale or 1.0
    L = 20.0 * s
    return L, QRectF(L - 5.0 * s, -2.5 * s, 6.0 * s, 5.0 * s)


def _plan(*defs):
    ms = Model_Space()
    for d in defs:
        ms.register_block_definition(d)
    return ms


def _line(ms, L, **style):
    ln = LineItem(QPointF(0.0, 0.0), QPointF(L, 0.0))
    ln.style.update(style)
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    return ln


# ── E9: paste ───────────────────────────────────────────────────────────────

def test_e9_paste_keeps_end_records_and_draws_the_end(qapp):
    h = half_arrow()                       # asymmetric: mirrored shows
    START = {"end": "none", "visible": True}
    FIN_M = {"end": h.id, "visible": True, "mirrored": True}
    FIN = {"end": h.id, "visible": True}

    def pasted(start, finish):
        src_ms = _plan(h)
        L, rect = _frame(src_ms)
        src = LineItem(QPointF(0.0, 0.0), QPointF(L, 0.0))
        src.style["start"], src.style["finish"] = dict(start), dict(finish)
        data = [src.to_dict()]
        ms = _plan(h)
        (it,) = ms.paste_items(QPointF(0.0, 0.0), data=data)
        ms.clearSelection()
        return ms, it, rect

    ms_m, it_m, rect = pasted(START, FIN_M)
    assert it_m.style["start"] == START and it_m.style["finish"] == FIN_M
    ms_p, it_p, _ = pasted(START, FIN)
    assert it_p.style["finish"] == FIN
    ms_n, _, _ = pasted(START, {"end": "none", "visible": True})
    none, plain, mirrored = (_render(m, rect) for m in (ms_n, ms_p, ms_m))
    assert _offband(none, plain)                  # the pasted end draws
    assert _offband(plain, mirrored)              # ... flipped when mirrored


# ── Q14: pick shape vs bounds ───────────────────────────────────────────────

def test_q14_ends_grow_bounds_never_the_pick_shape(qapp):
    h = half_arrow()
    ms = _plan(h)
    L, _ = _frame(ms)
    bare = _line(ms, L)
    capped = _line(ms, L, finish={"end": h.id, "visible": True})
    assert capped.shape() == bare.shape()
    bb, cb = bare.boundingRect(), capped.boundingRect()
    assert cb.contains(bb) and cb.height() > bb.height()


# ── Q8: text + hatch-fill end content in the line colour ────────────────────

def _end_of(name, prims):
    return BlockDefinition.new(name=name, library="L", series="End Types",
                               primitives=prims, origin=(0.0, 0.0),
                               end={"size": "fixed", "trim": 0.0})


def _text_end():
    tx = TextItem(TextAnnotationData(text="W", x=-2.0, y=-1.5, height_mm=1.5))
    return _end_of("TextEnd", [tx.to_dict()])


def _hatch_end():
    r = RectangleItem(QPointF(-3.0, -1.5), QPointF(0.0, 1.5))
    r.fill_type = "hatch"
    return _end_of("HatchEnd", [r.to_dict()])


def _reddish(c: QColor) -> bool:
    """The line's red hue at any opacity (a hatch background tints it)."""
    r, g, b, _ = c.getRgb()
    return r >= 20 and r > 2 * g and r > 2 * b


def test_q8_text_and_hatch_end_content_render_in_the_line_colour(qapp):
    for end in (_text_end(), _hatch_end()):
        ms = _plan(end)
        L, rect = _frame(ms)
        ln = _line(ms, L, colour=_RED, finish={"end": end.id, "visible": True})
        ms.clearSelection()
        drawn = _render(ms, rect)
        ln.style["finish"] = {"end": "none", "visible": True}
        ln.update()
        bare = _render(ms, rect)
        diff = _offband(bare, drawn)
        assert len(diff) > 10, end.name                       # the content drew
        red = sum(1 for x, y in diff if _reddish(QColor(drawn.pixel(x, y))))
        assert red >= len(diff) * 9 // 10, (end.name, red, len(diff))  # line colour
        full = sum(1 for x, y in diff if QColor(drawn.pixel(x, y)).name() == _RED)
        assert full > 10, end.name            # glyph / hatch lines at full ink
