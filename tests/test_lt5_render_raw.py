"""LT5 C2 -- ends on raw primitives (Geometry2DMixin): E2 sizes, E3 trim,
E8 missing badge, E12 dash phase (canvas half), selection highlight, LTS-7
short line, LOD, bounds. Real scenes; PDF through paper_export, parsed."""
import math

import fitz
import numpy as np
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QGraphicsView

from firepro3d import paper_display as pd
from firepro3d import path_walk as pw
from firepro3d import theme
from firepro3d.geometry_2d import LineItem, RectangleItem, SplineItem
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from tests.lt3_support import hidden, make_linetype
from tests.lt5_support import arrow, round_end, set_ends
from tests.test_lt1_block_paper import _VP_W, _VP_X, _VP_Y, _export
from tests.test_lt3_pdf import _viewport_hlines
from tests.test_lt3_primitive_paint import _render

PT = 25.4 / 72.0
_S = 0.02                                              # 1:50 sheet
_CX, _CY = _VP_X + _VP_W / 2.0, _VP_Y + _VP_W / 2.0   # paper mm of model (0, 0)


def _paper(x, y):
    """Paper mm of model point (x, y) on the 1:50 _export sheet (nominal:
    the export lands within ~0.1 mm of it -- use ``_line_span`` for exact
    endpoint comparisons)."""
    return _CX + x * _S, _CY + y * _S


def _line_span(tmp_path, x0=-1500.0, x1=1500.0):
    """Measured paper (x0, x1) of an END-LESS LineItem (x0, 0)-(x1, 0) on the
    1:50 _export sheet: the ground truth the ends' positions are judged
    against (the export's own mapping, not the nominal ``_paper``)."""
    ms = _plan()
    _add(ms, LineItem(QPointF(x0, 0.0), QPointF(x1, 0.0)))
    lines = _viewport_hlines(_export(tmp_path, ms, _S, f"span_{x0}_{x1}.pdf"))
    assert len(lines) == 1, lines
    return lines[0][0], lines[0][1]


def _fills(pdf):
    """(x0, y0, x1, y1) paper mm of every filled drawing strictly inside the
    viewport box (the viewport frame / title block fall out)."""
    doc = fitz.open(str(pdf))
    try:
        out = []
        for d in doc[0].get_drawings():
            if "f" not in (d.get("type") or ""):
                continue
            r = d["rect"]
            x0, y0, x1, y1 = (v * PT for v in (r.x0, r.y0, r.x1, r.y1))
            if (_VP_X + 1 < x0 and x1 < _VP_X + _VP_W - 1
                    and _VP_Y + 1 < y0 and y1 < _VP_Y + _VP_W - 1):
                out.append((x0, y0, x1, y1))
        return out
    finally:
        doc.close()


def _close(c, ref, tol=30):
    return all(abs(a - b) < tol for a, b in zip(c.getRgb()[:3], ref.getRgb()[:3]))


def _plan(defs=()):
    ms = Model_Space()
    for d in defs:
        ms.register_block_definition(d)
    return ms


def _add(ms, item):
    ms.addItem(item)
    if isinstance(item, LineItem):
        ms._draw_lines.append(item)
    return item


def _construction(weight):
    cats = pd.load_paper_categories()
    cats["Construction"]["line_weight"] = weight
    pd.save_paper_categories(cats)


@pytest.mark.parametrize("weight", ["Thinnest", "Thin"])   # Light 0.18 / Heavy 0.35 (MW-6)
def test_e2_fixed_arrow_prints_3mm_on_any_weight_and_closed_draws_none(qapp, tmp_path, weight):
    save_paper_color_mode(PaperColorMode.BW)
    _construction(weight)
    a = arrow()
    ms = _plan([a])
    ln = _add(ms, LineItem(QPointF(-1500.0, 0.0), QPointF(1500.0, 0.0)))
    set_ends(ln, finish=a.id)
    rect = _add(ms, RectangleItem(QPointF(-500.0, 500.0), QPointF(500.0, 1500.0)))
    set_ends(rect, start=a.id, finish=a.id)            # closed: never draws ends (Q2)
    pdf = _export(tmp_path, ms, _S, f"e2_{weight}.pdf")
    mm = pd.resolve_line_weight_mm(weight)
    long_ = [l for l in _viewport_hlines(pdf) if l[1] - l[0] > 30.0]
    assert long_ and {round(w, 3) for *_, w in long_} == {round(mm, 3)}  # the weight really differs
    fills = _fills(pdf)
    assert len(fills) == 1, fills                       # the line's arrow only
    x0, y0, x1, y1 = fills[0]
    assert abs((x1 - x0) - 3.0) <= 0.05                 # Fixed 3 mm, any weight
    assert abs((y1 - y0) - 1.5) <= 0.05
    assert abs(x1 - _line_span(tmp_path)[1]) <= 0.05    # tip at the endpoint


@pytest.mark.parametrize("weight", ["Thinnest", "Thin"])
def test_e2_weight_relative_round_radius_is_half_the_weight(qapp, tmp_path, weight):
    save_paper_color_mode(PaperColorMode.BW)
    _construction(weight)
    r = round_end()
    ms = _plan([r])
    ln = _add(ms, LineItem(QPointF(-1500.0, 0.0), QPointF(1500.0, 0.0)))
    set_ends(ln, finish=r.id)
    fills = _fills(_export(tmp_path, ms, _S, f"e2r_{weight}.pdf"))
    assert len(fills) == 1, fills
    radius = (fills[0][2] - fills[0][0]) / 2.0
    assert abs(radius - pd.resolve_line_weight_mm(weight) / 2.0) <= 0.01


def test_e3_stroke_stops_at_the_trim(qapp, tmp_path):
    save_paper_color_mode(PaperColorMode.BW)
    a = arrow()
    ms = _plan([a])
    ln = _add(ms, LineItem(QPointF(-1500.0, 0.0), QPointF(1500.0, 0.0)))
    set_ends(ln, finish=a.id)
    lines = [l for l in _viewport_hlines(_export(tmp_path, ms, _S, "e3.pdf"))
             if l[1] - l[0] > 30.0]
    assert len(lines) == 1, lines
    x0, x1, _ = lines[0]
    e0, e1 = _line_span(tmp_path)                               # the end-less line
    assert abs(x0 - e0) <= 0.05                                 # start: no end, untrimmed
    assert abs(x1 - (e1 - 3.0)) <= 0.05                         # finish: 3 mm trim


def test_e3_over_trim_draws_no_stroke_but_both_ends(qapp, tmp_path):
    save_paper_color_mode(PaperColorMode.BW)
    a = arrow()

    def export(ends, name):
        ms = _plan([a])
        ln = _add(ms, LineItem(QPointF(-50.0, 0.0), QPointF(50.0, 0.0)))  # 2 mm on paper
        if ends:
            set_ends(ln, start=a.id, finish=a.id)                          # trims 3 + 3 mm
        return _export(tmp_path, ms, _S, name)

    assert len(_viewport_hlines(export(False, "e3c.pdf"))) == 1   # composition: probe sees it
    pdf = export(True, "e3o.pdf")
    assert _viewport_hlines(pdf) == []                            # no stroke
    assert len(_fills(pdf)) == 2                                  # both arrows


def test_e8_missing_end_badge_on_canvas_never_on_paper(qapp, tmp_path):
    def scene(finish):
        ms = _plan()
        ln = _add(ms, LineItem(QPointF(-300.0, 0.0), QPointF(300.0, 0.0)))
        set_ends(ln, finish=finish)
        return ms, ln

    ms_m, ln_m = scene("deadbeef")
    ms_n, _ = scene("none")
    crop = QRectF(-400.0, -100.0, 800.0, 200.0)                   # 0.5 px/mm onto 400 x 100
    a, b = _render(ms_m, crop, 400, 100), _render(ms_n, crop, 400, 100)
    diff = [(x, y) for x in range(400) for y in range(100) if a.pixel(x, y) != b.pixel(x, y)]
    assert len(diff) > 20                                          # a badge drew
    assert all(abs(x - 350) <= 10 and abs(y - 50) <= 10 for x, y in diff)  # at the end point
    warn = QColor(theme.detect().warn)
    assert sum(1 for x, y in diff if _close(QColor(a.pixel(x, y)), warn)) > 10
    assert "Missing end type: deadbeef" in ln_m.toolTip()
    save_paper_color_mode(PaperColorMode.BW)
    ex = _paper(300.0, 0.0)[0]
    near = lambda fs: [f for f in fs if abs((f[0] + f[2]) / 2.0 - ex) < 3.0]
    assert near(_fills(_export(tmp_path, ms_m, _S, "e8.pdf"))) == []   # never plots
    ar = arrow()
    ms_m.register_block_definition(ar)
    set_ends(ln_m, finish=ar.id)
    assert len(near(_fills(_export(tmp_path, ms_m, _S, "e8b.pdf")))) == 1  # probe sees ends there


_E12_CROP = QRectF(-5.0, -10.0, 46.0, 20.0)                       # 10 px/mm onto 460 x 200


def _e12_scene(kind, with_ends):
    ms = Model_Space(scene_role="block_editor")
    lid = hidden(ms)                                               # Hidden 6 / 3, 9 mm period
    a = arrow()
    ms.register_block_definition(a)
    if kind == "line":
        it = LineItem(QPointF(0.0, 0.0), QPointF(36.0, 0.0))
    else:
        it = SplineItem([QPointF(0.0, 0.0), QPointF(12.0, 8.0),
                         QPointF(24.0, -8.0), QPointF(36.0, 0.0)])
    it.style["linetype"] = lid
    if with_ends:
        set_ends(it, start=a.id, finish=a.id)
    ms.addItem(it)
    return ms, it


@pytest.mark.parametrize("kind", ["line", "spline"])
def test_e12_dashes_outside_the_trims_are_pixel_identical(qapp, kind):
    ms0, it0 = _e12_scene(kind, False)
    ms1, _ = _e12_scene(kind, True)
    img0 = _render(ms0, _E12_CROP, 460, 200)
    img1 = _render(ms1, _E12_CROP, 460, 200)
    pcs = it0.stroke_pieces()
    tips = [pw.point_at_total(pcs, 0.0), pw.point_at_total(pcs, pw.total_length(pcs))]

    def near_end(x, y):
        mx, my = -5.0 + (x + 0.5) / 10.0, -10.0 + (y + 0.5) / 10.0
        return any(math.hypot(mx - t.x(), my - t.y()) <= 4.5 for t in tips)

    diff = [(x, y) for x in range(460) for y in range(200)
            if img0.pixel(x, y) != img1.pixel(x, y)]
    assert diff, "the ends drew nothing -- not measuring E12"
    off = [d for d in diff if not near_end(*d)]
    assert not off, off[:10]
    lit = [QColor(img0.pixel(x, y)).lightness() > 128
           for x in range(460) for y in range(200) if not near_end(x, y)]
    assert sum(lit) > 100                                          # dashes really drawn
    if kind == "line":
        row = [QColor(img0.pixel(x, 100)).lightness() > 128 for x in range(95, 365)]
        assert any(row) and not all(row)                           # dashed, not solid


def test_selection_highlight_covers_the_ends(qapp):
    def render(selected):
        ms = Model_Space(scene_role="block_editor")
        a = arrow()
        ms.register_block_definition(a)
        ln = LineItem(QPointF(0.0, 0.0), QPointF(36.0, 0.0))
        ln.style["colour"] = "#808080"
        set_ends(ln, finish=a.id)
        ms.addItem(ln)
        # The per-item highlight is the boundary only where no selection
        # manipulator boxes the item (_manip_wraps; headless / pre-manipulator
        # surfaces) -- Model_Space's own manipulator would suppress it.
        ms._manipulator = None
        ln.setSelected(selected)
        return _render(ms, QRectF(0.0, -2.0, 40.0, 4.0), 400, 40), ln, ms

    inside = (345, 20)                       # x = 34.5 mm, on the axis, inside the arrow
    img0, ln0, _ms0 = render(False)      # keep each scene alive: it owns ln
    img1, ln1, _ms1 = render(True)
    c0, c1 = QColor(img0.pixel(*inside)), QColor(img1.pixel(*inside))
    assert c0.getRgb()[:3] == ln0.pen().color().getRgb()[:3]
    assert c1.getRgb()[:3] == ln1.pen().color().lighter(150).getRgb()[:3]


def test_lts_short_line_drawn_continuous_still_draws_its_ends(qapp):
    def render(with_ends):
        ms = Model_Space(scene_role="block_editor")
        lt = make_linetype(screen="fixed")   # 9 mm x 6 px/mm = 5.4 mm at 10 px/mm
        ms.register_block_definition(lt)
        a = arrow()
        ms.register_block_definition(a)
        ln = LineItem(QPointF(0.0, 0.0), QPointF(4.0, 0.0))   # < 1 period: solid (LTS-7)
        ln.style["linetype"] = lt.id
        if with_ends:
            set_ends(ln, finish=a.id)
        ms.addItem(ln)
        return _render(ms, QRectF(-2.0, -5.0, 10.0, 10.0), 100, 100)

    lit = lambda img, x, y: QColor(img.pixel(x, y)).lightness() > 128
    img0, img1 = render(False), render(True)
    assert all(lit(img0, x, 50) for x in range(21, 60))      # composition: drawn solid
    assert not lit(img0, 35, 45) and lit(img1, 35, 45)       # the arrow drew (0.5 mm off-axis)


def test_ends_are_never_lod_dropped(qapp):
    def render(with_ends):
        ms = Model_Space(scene_role="block_editor")
        lid = hidden(ms)
        big = arrow(length=300.0, half=75.0, name="Big")       # 30 px at 0.1 px/mm
        ms.register_block_definition(big)
        ln = LineItem(QPointF(0.0, 0.0), QPointF(3600.0, 0.0))
        ln.style["linetype"] = lid
        if with_ends:
            set_ends(ln, finish=big.id)
        ms.addItem(ln)
        return _render(ms, QRectF(0.0, -200.0, 4000.0, 400.0), 400, 40)

    img0, img1 = render(False), render(True)
    row = [QColor(img0.pixel(x, 20)).lightness() > 128 for x in range(5, 355)]
    assert all(row)                                           # composition: LOD -> solid
    lit = lambda img, x, y: QColor(img.pixel(x, y)).lightness() > 128
    assert not lit(img0, 345, 23) and lit(img1, 345, 23)      # the end still draws


def _item_ink_bbox(img, bg):
    """``_ink_bbox`` over the pixels where *img* differs from *bg* (the same
    view without the item): the item's own ink, never the scene's origin
    marker, which a 6 px stroke + small ends would sit inside."""
    def arr(i):
        i = i.convertToFormat(QImage.Format.Format_RGB32)
        ptr = i.constBits()
        ptr.setsize(i.sizeInBytes())
        return np.frombuffer(bytes(ptr), np.uint32).reshape(
            i.height(), i.bytesPerLine() // 4)[:, : i.width()]
    ys, xs = np.nonzero(arr(img) != arr(bg))
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def _view_image(v):
    """The view's viewport rendered off-screen through its own transform
    (``QGraphicsView.render``: background + items, as painted on screen)."""
    vp = v.viewport().rect()
    img = QImage(vp.size(), QImage.Format.Format_RGB32)
    img.fill(QColor("black"))
    p = QPainter(img)
    v.render(p, QRectF(img.rect()), vp)
    p.end()
    return img


@pytest.mark.parametrize("zoom", [0.15, 0.06])
def test_bounds_cover_fixed_and_weight_relative_ends(qapp, zoom):
    a, r = arrow(), round_end()
    ms = _plan([a, r])
    ms.setBackgroundBrush(QColor("black"))
    ln = _add(ms, LineItem(QPointF(-1000.0, 0.0), QPointF(1000.0, 0.0)))
    ln.style["weight"] = "Thickest"
    ln.style["colour"] = "#ffffff"
    set_ends(ln, start=r.id, finish=a.id)
    v = QGraphicsView(ms)
    try:
        # Off-screen + non-interactive: no real cursor hover / window
        # exposure can change the ink (flake hardening); the images are
        # rendered through the view's own transform, not grabbed.
        v.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        v.setInteractive(False)
        v.resize(400, 400)
        v.setTransform(v.transform().fromScale(zoom, zoom))
        v.show()
        v.centerOn(0, 0)
        qapp.processEvents()
        img = _view_image(v)
        assert ln.pen().widthF() >= 4.0                        # a real heavy pen
        br = v.mapFromScene(ln.sceneTransform().mapRect(ln.boundingRect())).boundingRect()
        ms.removeItem(ln)                                      # the scene's own ink
        x0, y0, x1, y1 = _item_ink_bbox(img, _view_image(v))   # (origin marker) stays
        assert y1 - y0 >= ln.pen().widthF() + 4                # composition: the ends drew
        over = max(br.left() - x0, br.top() - y0, x1 - br.right(), y1 - br.bottom())
        assert over <= 1, (zoom, (x0, y0, x1, y1), br, over)
    finally:
        v.close()


@pytest.mark.parametrize("case", ["lts7_short", "lod"])
def test_plain_fallback_stroke_is_the_trimmed_path(qapp, case):
    """Seam (G2 review note 3): when ``paint_stroke(trims=)`` returns False
    (LTS-7 short line / LOD) the fallback plain stroke is the TRIMMED path:
    the axis between the trim point and the (short) arrow's base is dark."""
    def render(with_ends):
        ms = Model_Space(scene_role="block_editor")
        if case == "lts7_short":
            lt = make_linetype(screen="fixed")       # 5.4 mm at 10 px/mm > 4 mm line
            ms.register_block_definition(lt)
            lid, end, crop, size = lt.id, (4.0, 0.0), QRectF(-2.0, -5.0, 10.0, 10.0), (100, 100)
            a = arrow(length=1.0, half=0.5, trim=2.5)   # arrow 3..4, stroke stops at 1.5
        else:
            lid = hidden(ms)                         # 9 mm period at 0.1 px/mm: LOD
            end, crop, size = (3600.0, 0.0), QRectF(0.0, -200.0, 4000.0, 400.0), (400, 40)
            a = arrow(length=300.0, half=75.0, trim=1000.0)  # arrow 3300..3600, stop 2600
        ms.register_block_definition(a)
        ln = LineItem(QPointF(0.0, 0.0), QPointF(*end))
        ln.style["linetype"] = lid
        if with_ends:
            set_ends(ln, finish=a.id)
        ms.addItem(ln)
        return _render(ms, crop, *size)

    lit = lambda img, x, y: QColor(img.pixel(x, y)).lightness() > 128
    gap, y = ((range(37, 49), 50) if case == "lts7_short" else (range(265, 326), 20))
    img0, img1 = render(False), render(True)
    assert all(lit(img0, x, y) for x in gap)                 # composition: drawn solid there
    assert not any(lit(img1, x, y) for x in gap)             # trimmed: the gap is dark
    keep = 15 if case == "lts7_short" else 100
    assert lit(img1, keep, y)                                # the kept stroke still draws
