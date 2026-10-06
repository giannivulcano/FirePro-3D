"""LT4 pure rows ⇄ reading (linetypes.md LT4-1/LT4-2/LT4-9)."""
import pytest

from firepro3d.linetype_pattern import (SEED_ROWS, content_end, rows_from_reading,
                                        spans, validate_rows)
from firepro3d.linetype_render import axis_role


def test_axis_role_matches_lt3_3():
    assert axis_role((0, 0), (6, 0), 9) == ("dash", 0.0, 6.0)
    assert axis_role((8, 0), (12, 0), 9) == ("dash", 8.0, 1.0)      # clamped
    assert axis_role((4, 0), (4, 0), 9) == ("dot", 4.0)
    assert axis_role((10, 0), (10, 0), 9) is None                    # dot outside
    assert axis_role((0, 1), (6, 1), 9) is None                      # off axis
    assert axis_role((9, 0), (12, 0), 9) is None                     # wholly outside


def test_rows_from_reading_sequential():
    rows = rows_from_reading(((0.0, 6.0), (8.0, 1.0)), (11.0,), 12.0)
    assert rows == [("dash", 6.0), ("gap", 2.0), ("dash", 1.0), ("gap", 2.0),
                    ("dot", 0.0), ("gap", 1.0)]


def test_leading_gap_and_touching_dashes():
    assert rows_from_reading(((2.0, 3.0), (5.0, 1.0)), (), 6.0) == [
        ("gap", 2.0), ("dash", 3.0), ("dash", 1.0)]


def test_unrepresentable_overlap_and_dot_inside():
    assert rows_from_reading(((0.0, 6.0), (4.0, 4.0)), (), 9.0) is None
    assert rows_from_reading(((0.0, 6.0),), (3.0,), 9.0) is None
    # a dot exactly at a dash end is representable
    assert rows_from_reading(((0.0, 6.0),), (6.0,), 9.0) == [
        ("dash", 6.0), ("dot", 0.0), ("gap", 3.0)]


def test_spans_and_period_round_trip():
    rows = [("dash", 6.0), ("gap", 2.0), ("dot", 0.0), ("gap", 2.0)]
    sp, period = spans(rows)
    assert sp == [("dash", 0.0, 6.0), ("dot", 8.0, 8.0)] and period == 10.0
    dashes = tuple((a, b - a) for k, a, b in sp if k == "dash")
    dots = tuple(a for k, a, b in sp if k == "dot")
    assert rows_from_reading(dashes, dots, period) == rows


def test_content_end_unclamped_axis_only():
    prims = [{"type": "draw_line", "pt1": [7, 0], "pt2": [12, 0]},
             {"type": "draw_line", "pt1": [0, 5], "pt2": [40, 5]},      # off axis
             {"type": "draw_circle"}]
    assert content_end(prims) == 12.0
    assert content_end([]) == 0.0


@pytest.mark.parametrize("rows,ok", [
    ([("dash", 6.0), ("gap", 3.0)], True),
    ([("gap", 3.0)], False),                 # no dash or dot
    ([("dash", 0.0)], False),                # zero length
    ([("dash", -1.0)], False),
    ([("dot", 0.0)], True),
])
def test_validate_rows(rows, ok):
    assert validate_rows(rows) is ok


def test_seed():
    assert SEED_ROWS == (("dash", 6.0), ("gap", 3.0))
