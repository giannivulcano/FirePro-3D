"""G-LTS5 + delta 2 -- a Fixed stroke under one on-screen period draws solid."""
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import make_linetype
from tests.test_lts_canvas import _editor, _line, _render, _row, runs


def test_g_lts5_short_raw_line_inside_a_gap_paints_solid(qapp):
    # 10 px/mm: Fixed period 54 px = 5.4 mm; dash 0-3.6 mm, gap 3.6-5.4 mm.
    # A 3.8..5.2 mm line lies wholly in the gap: without LTS-7 it is invisible.
    ms, lid = _editor("fixed")
    _line(ms, lid, (3.8, 0), (5.2, 0))
    row = _row(_render(ms, QRectF(0, -2, 40, 4)), 20)
    # The line spans x = 38..52 px (the origin marker lights x < ~12 on y = 0).
    assert all(row[40:50]) and not any(row[56:80]), runs(row)


def test_long_raw_line_stays_dashed(qapp):
    ms, lid = _editor("fixed")
    _line(ms, lid, (0, 0), (40, 0))
    row = _row(_render(ms, QRectF(0, -2, 40, 4)), 20)
    assert sum(1 for v, _ in runs(row) if not v) >= 3


def test_d2_short_line_in_block_solid_long_edge_dashed(qapp):
    # Plan 0.1 px/mm: period 54 px = 540 mm; dash 0-360 mm, gap 360-540 mm.
    ms = Model_Space()
    lt = make_linetype(screen="fixed")
    ms.register_block_definition(lt)
    long_ln = LineItem(QPointF(-1500, 0), QPointF(1500, 0))
    short_ln = LineItem(QPointF(380, 300), QPointF(520, 300))   # in a gap
    for ln in (long_ln, short_ln):
        ln.style["linetype"] = lt.id
    d = BlockDefinition.new(name="B", library="L", series="S",
                            primitives=[long_ln.to_dict(), short_ln.to_dict()],
                            origin=(0.0, 0.0))
    ms.register_block_definition(d)
    ms.place_block_instance(d.id, (0.0, 1000.0), level=ms.active_level)
    img = _render(ms, QRectF(-2000, -1000, 4000, 4000), 400, 400)
    long_row, short_row = _row(img, 200), _row(img, 230)
    assert sum(1 for v, _ in runs(long_row) if not v) >= 4      # dashed
    lit = [n for v, n in runs(short_row) if v]
    assert lit and abs(lit[0] - 14) <= 2, runs(short_row)        # solid 140 mm
