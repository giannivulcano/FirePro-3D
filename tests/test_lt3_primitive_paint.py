"""LT3-6/7 + G1/G2/G-canvas (Block Editor half) -- raw primitives draw dashed."""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import hidden


def _editor():
    ms = Model_Space(scene_role="block_editor")
    return ms, hidden(ms)


def _render(ms, rect, w=400, h=40):
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, w, h), rect)
    p.end()
    return img


def _row(img, y):
    return [QColor(img.pixel(x, y)).lightness() > 128 for x in range(img.width())]


def _line(ms, lt, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b))
    ln.style["linetype"] = lt
    ms.addItem(ln)
    return ln


def test_block_editor_draws_real_size_dashes(qapp):
    ms, lid = _editor()
    _line(ms, lid, (0, 0), (36, 0))
    row = _row(_render(ms, QRectF(0, -2, 40, 4)), 20)       # 10 px per mm
    # Hidden 6/3 at 1:1 -> lit 0-60 px, dark 60-90, lit 90-150 ...
    assert all(row[5:55]) and not any(row[65:85]) and all(row[95:145])


def test_g1_collinear_pieces_match_one_line(qapp):
    # Hidden 6/3: ink 0-6, 9-15, 18-24, 27-33, 36. The split leaves a real gap
    # at 15..18 mm, which is already a pattern gap -> rasters must be identical.
    ms1, l1 = _editor()
    _line(ms1, l1, (0, 0), (36, 0))
    ms2, l2 = _editor()
    _line(ms2, l2, (15, 0), (0, 0))              # drawn reversed
    _line(ms2, l2, (18, 0), (36, 0))             # gapped, drawn forward
    r1 = _row(_render(ms1, QRectF(0, -2, 40, 4)), 20)
    r2 = _row(_render(ms2, QRectF(0, -2, 40, 4)), 20)
    assert r1 == r2


def test_continuous_unchanged_and_lod_solid(qapp):
    ms, lid = _editor()
    _line(ms, lid, (0, 0), (3600, 0))
    row = _row(_render(ms, QRectF(0, -200, 4000, 400)), 20)   # 0.1 px/mm: period 0.9 px
    assert all(row[5:355])                        # LOD -> solid


def test_selected_dashed_highlight_follows_dashes(qapp):
    ms, lid = _editor()
    ln = _line(ms, lid, (0, 0), (36, 0))
    ln.setSelected(True)
    row = _row(_render(ms, QRectF(0, -2, 40, 4)), 20)
    assert not any(row[65:85])                    # gap stays dark when selected
    assert all(row[5:55])                         # dash still lit


def test_g2_trim_keeps_surviving_dashes(qapp):
    ms, lid = _editor()
    full = _line(ms, lid, (0, 0), (36, 0))
    before = _row(_render(ms, QRectF(0, -2, 40, 4)), 20)
    full.set_length(20.0)                          # in-place trim of the far end
    after = _row(_render(ms, QRectF(0, -2, 40, 4)), 20)
    assert not any(after[65:85])                   # still dashed (not solid)
    assert after[:195] == before[:195]
    assert not any(after[205:])                    # the trimmed tail is gone


def test_g2_real_trim_tool_keeps_surviving_dashes(qapp):
    """G2 through the real two-phase Trim tool (scene_tools._handle_trim_click)."""
    from tests._snap_polish_helpers import click, close_view, make_view
    view, scene = make_view(scale=1.0, mode=None)
    try:
        lid = hidden(scene, size="model")          # factor 1 on the plan canvas
        ln = _line(scene, lid, (0, 0), (36, 0))
        scene._draw_lines.append(ln)
        edge = LineItem(QPointF(20, -100), QPointF(20, 100))
        scene.addItem(edge)
        scene._draw_lines.append(edge)
        before = _row(_render(scene, QRectF(0, -2, 40, 4)), 20)
        scene.set_mode("trim")
        click(view, QPointF(20, 80))               # cutting edge
        click(view, QPointF(30, 0))                # remove the far piece
        assert abs(ln.line().p2().x() - 20.0) < 1e-6   # really trimmed
        after = _row(_render(scene, QRectF(0, -2, 40, 4)), 20)
        assert not any(after[65:85])               # still dashed (not solid)
        assert after[:195] == before[:195]
        assert not any(after[215:])
    finally:
        close_view(view, scene)


def _all_primitives():
    from firepro3d.geometry_2d import (ArcItem, CircleItem, EllipseItem, PolylineItem,
                                       RectangleItem, RegularPolygonItem, SplineItem)
    pl = PolylineItem(QPointF(-15, -15))
    for p in ((15, -15), (15, 10), (-10, 15)):
        pl.append_point(QPointF(*p))
    rect = RectangleItem(QPointF(-12, -8), QPointF(12, 8))
    rect.set_angle(30.0)                          # rotation baked as data
    return {
        "line": LineItem(QPointF(-15, -10), QPointF(15, 12)),
        "polyline": pl,
        "rect": rect,
        "circle": CircleItem(QPointF(0, 0), 14.0),
        "arc": ArcItem(QPointF(0, 0), 14.0, 20.0, 250.0),
        "polygon": RegularPolygonItem(QPointF(0, 0), 6, 14.0),
        "ellipse": EllipseItem(QPointF(0, 0), 16.0, 9.0, 25.0),
        "spline": SplineItem([QPointF(-15, 0), QPointF(-5, 15), QPointF(5, -15),
                              QPointF(15, 0)]),
    }


def _lit(ms):
    img = _render(ms, QRectF(-20, -20, 40, 40), 400, 400)
    return {(x, y) for y in range(400) for x in range(400)
            if QColor(img.pixel(x, y)).lightness() > 128}


import pytest  # noqa: E402


@pytest.mark.parametrize("kind", ["line", "polyline", "rect", "circle", "arc",
                                  "polygon", "ellipse", "spline"])
def test_every_styled_primitive_draws_dashes_on_its_stroke(qapp, kind):
    """H3-f: all 8 paint()s route through paint_stroke; dashes lie on the
    plain stroke (rotated Rect included) and leave real gaps."""
    ms_c = Model_Space(scene_role="block_editor")
    ms_c.addItem(_all_primitives()[kind])
    solid = _lit(ms_c)
    ms_d, lid = _editor()
    it = _all_primitives()[kind]
    it.style["linetype"] = lid
    ms_d.addItem(it)
    dashed = _lit(ms_d)
    assert solid and dashed
    assert len(dashed) < 0.85 * len(solid)        # gaps (Hidden = 6/9 ink)
    near = {(x + dx, y + dy) for x, y in solid for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    off = dashed - near                           # 1 px AA rasterisation slack
    assert len(off) <= 0.02 * len(dashed), len(off)   # on the plain stroke
