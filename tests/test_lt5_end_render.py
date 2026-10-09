"""LT5 C1 -- end_render: printed_factor (one Drafting rule, two callers),
EndDef reading + cache, end_scales / end_trims (ET1: (screen | printed) x
per-end Scale), trimmed_path, paint_ends pixels (Fixed length, pen width
under the end scale, mirror, colour, canvas-only badge)."""
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
from tests.lt5_support import arrow, half_arrow, tick

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


def _paint(ends, pen, *, ff=1.0, sf=None, pieces=_LINE):
    img = _blank()
    p = QPainter(img)
    try:
        er.paint_ends(p, pieces, ends, pen, printed=ff, screen=sf)
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
    assert (ed.block_id, ed.screen, ed.trim) == (a.id, "scale", 3.0)
    assert [op.kind for op in ed.ops] == ["fill", "stroke"]
    assert er.EndDef.from_block(a) is ed                         # cached
    assert ed.bounds == pytest.approx((-3.0, -0.75, 0.0, 0.75))
    assert ed.reach == pytest.approx(math.hypot(3.0, 0.75))
    a.set_end({"trim": 1.0, "screen": "fixed"})                  # version bump
    ed2 = er.EndDef.from_block(a)
    assert ed2 is not ed and (ed2.screen, ed2.trim) == ("fixed", 1.0)
    plain = BlockDefinition.new(name="P", library="L", series="S",
                                primitives=[], origin=(0.0, 0.0))
    assert er.EndDef.from_block(plain) is None


def test_end_scales_and_trims(qapp):
    a, f = arrow(), arrow(screen="fixed", name="F")
    ea, ef = er.EndDef.from_block(a), er.EndDef.from_block(f)
    one = ResolvedEnd(a, None, False)
    two = ResolvedEnd(a, None, False, 2.0)
    assert er.end_scales(ea, one, printed=10.0, screen=4.0) == 10.0     # Scale with zoom: printed
    assert er.end_scales(ef, one, printed=10.0, screen=4.0) == 4.0      # Fixed size: screen
    assert er.end_scales(ef, one, printed=10.0, screen=None) == 10.0    # off a model canvas
    assert er.end_scales(ea, two, printed=10.0, screen=None) == 20.0    # x per-end Scale
    ends = (two, ResolvedEnd(f, None, False))
    assert er.end_trims(ends, printed=10.0, screen=4.0) == (60.0, 12.0)
    assert er.end_trims((_OFF, ResolvedEnd(None, "gone", False)), printed=10.0) == (0.0, 0.0)


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
    img = _paint((_OFF, ResolvedEnd(arrow(), None, False)), _pen(), ff=ff)
    row = _row(img, 50)
    assert row and max(row) <= 101                       # tip at the attach point
    assert abs((max(row) - min(row)) - 3.0 * ff) <= 1.5  # base at -3 mm x ff


def test_start_end_points_outward(qapp):
    img = _paint((ResolvedEnd(arrow(), None, False), _OFF), _pen(), ff=10.0)
    row = _row(img, 50)
    assert row and min(row) >= 19 and abs(max(row) - 50) <= 1.5


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


def test_item_ends_fast_path_is_only_ever_a_shortcut(qapp):
    """``_item_ends`` returns NO_ENDS (both the paint gate and the
    boundingRect gate) only where the resolver draws nothing; otherwise it
    IS the resolver's answer -- over every slot shape x linetype."""
    from PyQt6.QtCore import QPointF
    from firepro3d.geometry_2d import LineItem
    from firepro3d.model_space import Model_Space
    from firepro3d.stroke_style import NO_ENDS, has_ends, resolve_ends, resolve_stroke
    a = arrow()
    plain_lt = make_linetype()
    lt = make_linetype(name="WithEnd")
    lt.set_repeat({**lt.repeat, "ends": {"start": a.id, "finish": a.id}})
    ms = Model_Space(scene_role="block_editor")
    for d in (a, plain_lt, lt):
        ms.register_block_definition(d)
    reg = ms.block_registry
    recs = [None, "junk", {}, {"end": None}, {"end": ""}, {"end": "by_linetype"},
            {"end": "by_block"}, {"end": "none"}, {"end": a.id},
            {"end": "deadbeef"}, {"end": a.id, "visible": False},
            {"end": "by_linetype", "visible": False}, {"end": 7}]
    n_short = n_draw = 0
    for ref in ("continuous", plain_lt.id, lt.id, "gone-lt"):
        for r0 in recs:
            for r1 in (None, {"end": "none"}, {"end": a.id}, {"end": "by_linetype"}):
                ln = LineItem(QPointF(0.0, 0.0), QPointF(10.0, 0.0))
                ms.addItem(ln)
                ln.style["linetype"] = ref
                ln.style["start"], ln.style["finish"] = r0, r1
                truth = resolve_ends(ln.style, resolve_stroke(ln.style, reg).lt, reg)
                for got in (ln._item_ends(ln._resolved_stroke()), ln._item_ends()):
                    if got is NO_ENDS:
                        n_short += 1
                        assert not has_ends(truth), (ref, r0, r1, truth)
                    else:
                        n_draw += 1
                        assert got == truth, (ref, r0, r1)
                ms.removeItem(ln)
    assert n_short > 50 and n_draw > 50                  # both branches exercised


def test_has_default_ends_gate_without_copies(qapp):
    a = arrow()
    plain_lt = make_linetype()
    lt = make_linetype(name="WithEnd")
    lt.set_repeat({**lt.repeat, "ends": {"finish": a.id}})
    reg = {d.id: d for d in (a, plain_lt, lt)}
    assert (plain_lt.has_default_ends, lt.has_default_ends, a.has_default_ends) == (
        False, True, False)
    assert er.linetype_has_default_end(lt.id, reg)
    assert not er.linetype_has_default_end(plain_lt.id, reg)
    assert not er.linetype_has_default_end(a.id, reg)        # not a linetype
    assert not er.linetype_has_default_end("deadbeef", reg)
    assert not er.linetype_has_default_end(lt.id, None)


def test_item_ends_paint_and_bounds_gates_agree(qapp):
    """The paint gate (rs.lt defaults) and the boundingRect gate (registry)
    return the same ends for every slot / linetype combination."""
    from firepro3d.geometry_2d import LineItem
    from firepro3d.model_space import Model_Space
    from firepro3d.stroke_style import NO_ENDS
    from PyQt6.QtCore import QPointF
    from tests.lt5_support import set_ends
    a = arrow()
    plain_lt = make_linetype()
    lt = make_linetype(name="WithEnd")
    lt.set_repeat({**lt.repeat, "ends": {"start": a.id}})
    ms = Model_Space(scene_role="block_editor")
    for d in (a, plain_lt, lt):
        ms.register_block_definition(d)
    for ref in ("continuous", plain_lt.id, lt.id, "deadbeef"):
        for start, finish in ((None, None), ("none", "none"), (a.id, None),
                              (None, "gone"), ("by_linetype", "none")):
            ln = LineItem(QPointF(0.0, 0.0), QPointF(10.0, 0.0))
            ln.style["linetype"] = ref
            set_ends(ln, start=start, finish=finish)
            ms.addItem(ln)
            via_rs = ln._item_ends(ln._resolved_stroke())
            via_reg = ln._item_ends()
            assert via_rs == via_reg, (ref, start, finish)
            if ref == lt.id and start in (None, "by_linetype"):
                assert via_rs[0].defn is a                   # the default drew
            if start in (None, "none", "by_linetype") and finish in (None, "none")                     and ref != lt.id:
                assert via_rs is NO_ENDS
