"""curve_chain.close_loops — chain closure over shape objects (HF3 R3/R4/R5)."""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.constants import CHAIN_WELD_MM
from firepro3d.curve_chain import ChainResult, close_loops
from firepro3d.geometry_2d import ArcItem, CircleItem, LineItem, RectangleItem


def _square(gap: float = 0.0, size: float = 100.0):
    """Four lines; the last one stops *gap* mm short of closing."""
    a, b, c, d = QPointF(0, 0), QPointF(size, 0), QPointF(size, size), QPointF(0, size)
    return [LineItem(a, b), LineItem(b, c), LineItem(c, d),
            LineItem(d, QPointF(0, gap))]


def test_weld_constant_is_one_mm():
    assert CHAIN_WELD_MM == 1.0


def test_four_lines_half_mm_gap_make_one_loop(qapp):
    r = close_loops(_square(gap=0.5))
    assert isinstance(r, ChainResult) and r.reason is None
    assert len(r.loops) == 1 and len(r.loops[0]) == 4


def test_four_lines_with_1_5mm_gap_report_the_gap(qapp):
    r = close_loops(_square(gap=1.5))
    assert r.loops == []
    assert r.reason.startswith("Not enclosed -- gap of 1.5 mm at (0, 0)")


def test_reversed_piece_still_chains(qapp):
    pieces = _square()
    pieces[2] = LineItem(QPointF(0, 100), QPointF(100, 100))   # drawn backwards
    r = close_loops(pieces)
    assert r.reason is None and len(r.loops) == 1


def test_circle_plus_square_two_loops_outer_first(qapp):
    pieces = [CircleItem(QPointF(50, 50), 10)] + _square()
    r = close_loops(pieces)
    assert r.reason is None and len(r.loops) == 2
    assert isinstance(r.loops[0][0], LineItem)         # the 100x100 square (largest area)
    assert isinstance(r.loops[1][0], CircleItem)       # the island


def test_closed_shapes_are_single_piece_loops(qapp):
    r = close_loops([RectangleItem(QPointF(0, 0), QPointF(10, 10))])
    assert r.reason is None and len(r.loops) == 1 and len(r.loops[0]) == 1


def test_crossing_x_fails_with_open_end_reason(qapp):
    r = close_loops([LineItem(QPointF(0, 0), QPointF(100, 100)),
                     LineItem(QPointF(0, 100), QPointF(100, 0))])
    assert r.loops == []
    assert r.reason == "Not enclosed -- 2 curve(s) have an open end"


def test_closed_shape_plus_open_leftover_fails_whole(qapp):
    r = close_loops([CircleItem(QPointF(0, 0), 5), LineItem(QPointF(50, 0), QPointF(80, 0))])
    assert r.loops == [] and r.reason == "Not enclosed -- 1 curve(s) have an open end"


def test_empty_input_reports_no_candidates(qapp):
    r = close_loops([])
    assert r.loops == [] and r.reason == "Select closed shapes or curves that form a closed outline"


def test_two_arcs_make_a_loop(qapp):
    r = close_loops([ArcItem(QPointF(0, 0), 50, 0.0, 180.0),
                     ArcItem(QPointF(0, 0), 50, 180.0, 180.0)])
    assert r.reason is None and len(r.loops) == 1 and len(r.loops[0]) == 2


def test_loop_area_helper_is_positive_for_square(qapp):
    from firepro3d.curve_chain import loop_area, loop_path
    r = close_loops(_square())
    assert math.isclose(loop_area(loop_path(r.loops[0])), 100.0 * 100.0, rel_tol=0.02)
