"""G-LTS8 (zoom half) -- a 100 m Fixed line stays dashed when zoomed in,
and windowed expansion draws exactly what the full expansion draws."""
from PyQt6.QtCore import QRectF

from firepro3d import linetype_render as lr
from firepro3d import path_walk as pw
from firepro3d.constants import LINETYPE_MAX_PERIODS
from tests.lt3_support import make_linetype
from tests.test_lts_canvas import _editor, _line, _render, _row, runs


def test_g_lts8_100m_fixed_line_dashed_past_the_period_cap(qapp):
    # 400 px/mm: period 54 px = 0.135 mm -> 100 m / 0.135 mm ~ 740k periods,
    # past LINETYPE_MAX_PERIODS (which would draw it solid).
    ms, lid = _editor("fixed")
    _line(ms, lid, (-50000, 0), (50000, 0))
    assert 100000 / (54 / 400) > LINETYPE_MAX_PERIODS
    row = _row(_render(ms, QRectF(0, -0.05, 1, 0.1)), 20)       # 400 px/mm
    dashes = [n for v, n in runs(row)[1:-1] if v]
    assert dashes and all(abs(n - 36) <= 2 for n in dashes), runs(row)


def test_g_lts8_100m_fixed_line_in_a_placed_block_dashed_zoomed_in(qapp):
    from PyQt6.QtCore import QPointF
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.geometry_2d import LineItem
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    lt = make_linetype(screen="fixed")
    ms.register_block_definition(lt)
    ln = LineItem(QPointF(-50000, 0), QPointF(50000, 0))
    ln.style["linetype"] = lt.id
    d = BlockDefinition.new(name="B", library="L", series="S",
                            primitives=[ln.to_dict()], origin=(0.0, 0.0))
    ms.register_block_definition(d)
    ms.place_block_instance(d.id, (0.0, 1000.0), level=ms.active_level)
    row = _row(_render(ms, QRectF(10, 999.95, 1, 0.1)), 20)     # 400 px/mm
    dashes = [n for v, n in runs(row)[1:-1] if v]
    assert dashes and all(abs(n - 36) <= 2 for n in dashes), runs(row)


def _dash_starts(path, lo, hi):
    """Sorted x of every dash subpath start inside [lo, hi] (open line
    subpaths have no area, so compare geometry, not QPainterPath.intersects)."""
    xs = []
    for i in range(path.elementCount()):
        e = path.elementAt(i)
        if e.isMoveTo() and lo <= e.x <= hi:
            xs.append(round(e.x, 6))
    return sorted(xs)


def test_windowed_expansion_matches_full_inside_the_window(qapp):
    lt = lr.LinetypeDef.from_block(make_linetype())
    piece = pw.Seg(-5000.0, 0.0, 5000.0, 0.0)           # ~1,111 periods > 512
    win = (0.0, -10.0, 64.0, 10.0)
    full, _ = lr.expand((piece,), lt, 1.0, (0.0, 0.0))
    part, _ = lr.expand((piece,), lt, 1.0, (0.0, 0.0), window=win)
    starts = _dash_starts(full, 0.0, 64.0)
    assert starts and _dash_starts(part, 0.0, 64.0) == starts   # same dashes
    assert part.elementCount() < full.elementCount() / 10      # really windowed


def test_visible_spans_seg_and_arc(qapp):
    win = (0.0, -1.0, 10.0, 1.0)
    s = lr.visible_spans(pw.Seg(-10.0, 0.0, 30.0, 0.0), win, 10.0)
    assert s == [(10.0, 20.0)]
    assert lr.visible_spans(pw.Seg(0.0, 5.0, 10.0, 5.0), win, 10.0) == []
    arc = pw.Arc(0.0, 0.0, 1000.0, 0.0, 180.0)          # passes (1000, 0)
    spans = lr.visible_spans(arc, (990.0, -10.0, 1010.0, 10.0), 20.0)
    assert spans and spans[0][0] <= 1e-6 and spans[-1][1] < 200.0


def test_scale_lines_keep_one_cache_key_across_pans(qapp):
    lt = lr.LinetypeDef.from_block(make_linetype())
    piece = pw.Seg(0.0, 0.0, 100.0, 0.0)               # 11 periods: never windowed
    a = lr.expand((piece,), lt, 1.0, (0.0, 0.0), window=(0.0, -1.0, 8.0, 1.0))
    b = lr.expand((piece,), lt, 1.0, (0.0, 0.0), window=(64.0, -1.0, 72.0, 1.0))
    assert a is b                                      # short pieces ignore the window
