"""ET1 G3 (paint half) / G4 / G5 on raw primitives: per-end Scale doubles the
head and the trim; a Fixed-size end is FIXED_END_PX_PER_MM px per printed mm
at any zoom on plan and in a Block Editor and prints true mm; a stroke
shorter on screen than its Fixed-size trims draws plain, no ends."""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.constants import FIXED_END_PX_PER_MM
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.lt5_support import arrow, set_ends
from tests.test_lt1_block_paper import _export
from tests.test_lt5_render_raw import _S, _fills


def _render(ms, rect, w=400, h=40):
    """*rect* of *ms* onto a w x h black image; the scene's origin cross
    (two screen-constant lines through (0, 0)) is hidden so only the line
    and its ends light pixels."""
    for it in getattr(ms, "_origin_cross_items", ()):
        it.setVisible(False)
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, w, h), rect)
    p.end()
    return img


def _lit_cols(img, y0=0, y1=None):
    y1 = img.height() if y1 is None else y1
    return sorted({x for x in range(img.width()) for y in range(y0, y1)
                   if QColor(img.pixel(x, y)).lightness() > 128})


def _head_width(img):
    """Width in px of the finish arrow head: from its base (the first lit
    column OFF the line's own row band) to the crop's right edge, where the
    finish attach point sits in every scene here (the triangle tapers into
    the row band over its last few px, so its own lit extent under-reads);
    0 when nothing lights off the band."""
    mid = img.height() // 2
    cols = sorted({x for x in range(img.width()) for y in range(img.height())
                   if abs(y - mid) > 2 and QColor(img.pixel(x, y)).lightness() > 128})
    return (img.width() - cols[0]) if cols else 0


def _plan(role="plan", screen="scale", scale=None, length=2000.0):
    ms = Model_Space(scene_role=role)
    a = arrow(length=3.0, half=1.0, screen=screen)
    ms.register_block_definition(a)
    ln = LineItem(QPointF(0.0, 0.0), QPointF(length, 0.0))
    set_ends(ln, finish=a.id, scale=scale)
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    return ms, ln, a


def test_g3_per_end_scale_doubles_head_and_trim_on_plan(qapp):
    # 1:100 plan, 0.2 px/mm: 3 mm arrow = 300 mm = 60 px; 2x = 120 px.
    ms1, ln1, _ = _plan()
    ms2, ln2, _ = _plan(scale=2.0)
    crop = QRectF(0.0, -400.0, 2000.0, 800.0)
    h1, h2 = _head_width(_render(ms1, crop, 400, 160)), _head_width(_render(ms2, crop, 400, 160))
    assert abs(h1 - 60) <= 3 and abs(h2 - 120) <= 3, (h1, h2)
    # the stroke stops at the head's base: the line's own row ends 60 / 120 px before x=400
    row1 = _lit_cols(_render(ms1, crop, 400, 160), 79, 82)
    row2 = _lit_cols(_render(ms2, crop, 400, 160), 79, 82)
    assert abs(max(c for c in row1 if c < 340) - (400 - 60)) <= 4 or len(row1) < 340
    assert max(row2) >= 390 and abs(len([c for c in row2 if c < 280]) - 280) <= 4


def test_g3_per_end_scale_prints_double(qapp, tmp_path):
    ms = Model_Space()
    a = arrow()
    ms.register_block_definition(a)
    ln = LineItem(QPointF(-1500.0, 0.0), QPointF(1500.0, 0.0))
    set_ends(ln, finish=a.id, scale=2.0)
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    fills = _fills(_export(tmp_path, ms, _S, "g3.pdf"))
    assert len(fills) == 1, fills
    x0, y0, x1, y1 = fills[0]
    assert abs((x1 - x0) - 6.0) <= 0.05 and abs((y1 - y0) - 3.0) <= 0.05


def test_g4_fixed_size_end_is_constant_px_on_plan_and_in_editor(qapp):
    for role in ("plan", "block_editor"):
        ms, _, _ = _plan(role=role, screen="fixed")
        near = _head_width(_render(ms, QRectF(1800.0, -100.0, 200.0, 100.0), 400, 200))   # 2 px/mm
        far = _head_width(_render(ms, QRectF(0.0, -1000.0, 2000.0, 1000.0), 400, 200))     # 0.2 px/mm
        want = 3.0 * FIXED_END_PX_PER_MM
        assert abs(near - want) <= 2 and abs(far - want) <= 2, (role, near, far)


def test_g4_fixed_size_times_scale_and_scale_with_zoom_doubles(qapp):
    ms, _, _ = _plan(screen="fixed", scale=2.0)
    far = _head_width(_render(ms, QRectF(0.0, -1000.0, 2000.0, 1000.0), 400, 200))
    assert abs(far - 2.0 * 3.0 * FIXED_END_PX_PER_MM) <= 2
    ms, _, _ = _plan(screen="scale")
    near = _head_width(_render(ms, QRectF(1000.0, -500.0, 1000.0, 500.0), 400, 200))   # 0.4 px/mm
    far = _head_width(_render(ms, QRectF(0.0, -1000.0, 2000.0, 1000.0), 400, 200))     # 0.2 px/mm
    assert abs(near - 2 * far) <= 4 and far >= 50


def test_g4_fixed_size_end_prints_true_mm(qapp, tmp_path):
    ms = Model_Space()
    a = arrow(screen="fixed")
    ms.register_block_definition(a)
    ln = LineItem(QPointF(-1500.0, 0.0), QPointF(1500.0, 0.0))
    set_ends(ln, finish=a.id)
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    fills = _fills(_export(tmp_path, ms, _S, "g4.pdf"))
    assert len(fills) == 1 and abs((fills[0][2] - fills[0][0]) - 3.0) <= 0.05


def test_g5_short_stroke_draws_plain_and_no_ends(qapp):
    ms = Model_Space()
    a = arrow(screen="fixed")                              # trim 3 mm -> 18 px each end
    ms.register_block_definition(a)
    ln = LineItem(QPointF(0.0, 0.0), QPointF(100.0, 0.0))
    set_ends(ln, start=a.id, finish=a.id)
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    # 0.1 px/mm: the line is 10 px, the trims 36 px -> plain stroke, no heads
    img = _render(ms, QRectF(-100.0, -100.0, 400.0, 200.0), 40, 20)
    assert _head_width(img) == 0
    row = _lit_cols(img, 9, 12)
    assert row and row[0] <= 11 and row[-1] >= 18               # the plain 10 px stroke
    # 1 px/mm: 100 px line, 36 px of trims -> both heads and the trimmed stroke
    img = _render(ms, QRectF(-20.0, -20.0, 140.0, 40.0), 140, 40)
    assert _head_width(img) >= 100
