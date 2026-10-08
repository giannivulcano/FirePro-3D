"""LT5 C1 -- end_render: printed_factor (one Drafting rule, two callers),
EndDef reading + cache, end_scales / end_trims, trimmed_path, paint_ends
pixels (Fixed length, weight-relative radius, pen width under the end
scale, mirror, colour, canvas-only badge)."""
import math

import pytest
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QTransform

from firepro3d import end_render as er
from firepro3d import linetype_render as lr
from firepro3d import paper_display as pdm
from firepro3d import path_walk as pw
from firepro3d import theme
from firepro3d.block_definition import BlockDefinition
from firepro3d.stroke_style import ResolvedEnd
from tests.lt3_support import make_linetype
from tests.lt5_support import arrow, half_arrow, round_end, tick

_OFF = ResolvedEnd(None, None, False)
_LINE = (pw.Seg(20.0, 50.0, 100.0, 50.0),)     # finish attach (100, 50), outward +X


def _pen(width=1.0, cosmetic=True, colour="#ffffff"):
    p = QPen(QColor(colour))
    p.setWidthF(width)
    p.setCosmetic(cosmetic)
    return p


def _blank():
    img = QImage(200, 100, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    return img


def _paint(ends, pen, *, ff=1.0, wf=1.0, pieces=_LINE):
    img = _blank()
    p = QPainter(img)
    try:
        er.paint_ends(p, pieces, ends, pen, fixed_factor=ff, weight_factor=wf)
        assert p.worldTransform() == QTransform()        # painter state restored
    finally:
        p.end()
    return img


def _lit(img, x, y):
    return QColor(img.pixel(x, y)).lightness() > 128


def _row(img, y):
    return [x for x in range(img.width()) if _lit(img, x, y)]


def _col(img, x):
    return [y for y in range(img.height()) if _lit(img, x, y)]


@pytest.mark.parametrize("args,want", [
    (dict(paper_scale=0.02, role="plan", drawing_scale=100.0), 50.0),
    (dict(paper_scale=None, role="plan", drawing_scale=100.0), 100.0),
    (dict(paper_scale=None, role="plan", drawing_scale=None), 1.0),
    (dict(paper_scale=None, role="block_editor", drawing_scale=100.0), 1.0),
    (dict(paper_scale=None, role=None, drawing_scale=None), 1.0),
])
def test_printed_factor_is_the_drafting_branch_of_length_factor(qapp, args, want):
    assert lr.printed_factor(**args) == pytest.approx(want)
    drafting = lr.LinetypeDef.from_block(make_linetype())
    assert lr.length_factor(drafting, **args) == lr.printed_factor(**args)
    model = lr.LinetypeDef.from_block(make_linetype(size="model"))
    assert lr.length_factor(model, **args) == 1.0


def test_end_def_reads_the_capability_and_caches_on_version(qapp):
    a = arrow()
    ed = er.EndDef.from_block(a)
    assert (ed.block_id, ed.size, ed.trim) == (a.id, "fixed", 3.0)
    assert [op.kind for op in ed.ops] == ["fill", "stroke"]
    assert er.EndDef.from_block(a) is ed                         # cached
    assert ed.bounds == pytest.approx((-3.0, -0.75, 0.0, 0.75))
    assert ed.reach == pytest.approx(math.hypot(3.0, 0.75))
    a.set_end({"size": "weight_relative", "trim": 1.0})          # version bump
    ed2 = er.EndDef.from_block(a)
    assert ed2 is not ed and (ed2.size, ed2.trim) == ("weight_relative", 1.0)
    plain = BlockDefinition.new(name="P", library="L", series="S",
                                primitives=[], origin=(0.0, 0.0))
    assert er.EndDef.from_block(plain) is None


def test_end_scales_and_trims(qapp):
    a, r = arrow(), round_end()
    ea, eround = er.EndDef.from_block(a), er.EndDef.from_block(r)
    assert er.end_scales(ea, fixed_factor=10.0, weight_factor=4.0) == 10.0
    assert er.end_scales(eround, fixed_factor=10.0, weight_factor=4.0) == 4.0
    ends = (ResolvedEnd(a, None, False), ResolvedEnd(r, None, False))
    assert er.end_trims(ends, fixed_factor=10.0, weight_factor=4.0) == (30.0, 0.0)
    assert er.end_trims((_OFF, ResolvedEnd(None, "gone", False)),
                        fixed_factor=10.0, weight_factor=4.0) == (0.0, 0.0)


def test_trimmed_path_keeps_joins_and_an_overtrim_is_empty(qapp):
    pcs = (pw.Seg(0.0, 0.0, 10.0, 0.0), pw.Seg(10.0, 0.0, 10.0, 10.0))
    path = er.trimmed_path(pcs, 2.0, 3.0)
    kinds = [path.elementAt(i).type for i in range(path.elementCount())]
    assert kinds.count(QPainterPath.ElementType.MoveToElement) == 1   # one subpath: join kept
    first, last = path.elementAt(0), path.elementAt(path.elementCount() - 1)
    assert (first.x, first.y) == pytest.approx((2.0, 0.0))
    assert (last.x, last.y) == pytest.approx((10.0, 7.0))
    assert er.trimmed_path(pcs, 12.0, 8.0).isEmpty()


@pytest.mark.parametrize("ff", [5.0, 10.0])
def test_fixed_arrow_length_is_three_times_the_fixed_factor(qapp, ff):
    img = _paint((_OFF, ResolvedEnd(arrow(), None, False)), _pen(), ff=ff, wf=99.0)
    row = _row(img, 50)
    assert row and max(row) <= 101                       # tip at the attach point
    assert abs((max(row) - min(row)) - 3.0 * ff) <= 1.5  # base at -3 mm x ff


def test_start_end_points_outward(qapp):
    img = _paint((ResolvedEnd(arrow(), None, False), _OFF), _pen(), ff=10.0)
    row = _row(img, 50)
    assert row and min(row) >= 19 and abs(max(row) - 50) <= 1.5


@pytest.mark.parametrize("w", [8.0, 16.0])
def test_weight_relative_round_radius_is_half_the_pen_width(qapp, w):
    end = (_OFF, ResolvedEnd(round_end(), None, False))
    # Non-cosmetic pen w: fill radius w/2 + the w-wide outline centred on it
    # (NOT scaled by k) -> lit diameter 2w.
    run = _col(_paint(end, _pen(w, cosmetic=False), ff=99.0, wf=w), 100)
    assert abs(len(run) - 2.0 * w) <= 2
    # Cosmetic 1 px pen: lit diameter = 2 x (w/2) + 1.
    run = _col(_paint(end, _pen(1.0), ff=99.0, wf=w), 100)
    assert abs(len(run) - (w + 1.0)) <= 2


@pytest.mark.parametrize("cosmetic", [True, False])
def test_end_stroke_keeps_the_line_pen_width_under_the_end_scale(qapp, cosmetic):
    """P4: a cosmetic pen stays px under scale(k); a non-cosmetic one is
    divided by k -- the tick draws at the line's own width either way."""
    img = _paint((_OFF, ResolvedEnd(tick(), None, False)), _pen(3.0, cosmetic), ff=10.0)
    assert len(_row(img, 50)) == 3                       # not 30
    assert abs(len(_col(img, 100)) - 20) <= 3            # +-1 mm x 10 (+ square cap)


@pytest.mark.parametrize("mirrored", [False, True])
def test_mirrored_flips_an_asymmetric_end(qapp, mirrored):
    img = _paint((_OFF, ResolvedEnd(half_arrow(), None, mirrored)), _pen(), ff=10.0)
    above = sum(_lit(img, x, y) for x in range(70, 101) for y in range(30, 48))
    below = sum(_lit(img, x, y) for x in range(70, 101) for y in range(53, 70))
    if mirrored:
        assert below > 50 and above == 0
    else:
        assert above > 50 and below == 0


def test_end_content_draws_in_the_pen_colour(qapp):
    img = _paint((_OFF, ResolvedEnd(arrow(), None, False)), _pen(colour="#ff0000"), ff=10.0)
    c = QColor(img.pixel(90, 50))                        # inside the fill
    assert (c.red(), c.green(), c.blue()) == (255, 0, 0)


def test_missing_end_badge_is_canvas_only(qapp, monkeypatch):
    ends = (_OFF, ResolvedEnd(None, "deadbeef", False))
    warn = QColor(theme.detect().warn)
    img = _paint(ends, _pen())
    amber = sum(1 for x in range(90, 111) for y in range(40, 61)
                if all(abs(a - b) < 30 for a, b in zip(
                    QColor(img.pixel(x, y)).getRgb()[:3], warn.getRgb()[:3])))
    assert amber > 10
    monkeypatch.setattr(pdm, "_THIN_SUSPEND", 1)        # a live paper pass
    assert _paint(ends, _pen()) == _blank()
