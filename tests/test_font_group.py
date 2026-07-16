"""Tests for the ribbon Font group controller (firepro3d/font_group.py)."""
import pytest
from firepro3d.font_group import next_ladder_pt, prev_ladder_pt
from firepro3d.constants import FONT_SIZE_LADDER_PT


def test_ladder_is_word_standard():
    assert FONT_SIZE_LADDER_PT == (
        8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 36, 48, 72)


@pytest.mark.parametrize("cur,expected", [
    (12, 14),      # on-ladder steps up
    (13, 14),      # off-ladder snaps to next step above
    (72, 72),      # top clamps
    (100, 100),    # above ladder stays put
    (5, 8),        # below ladder snaps to first step
])
def test_grow(cur, expected):
    assert next_ladder_pt(cur) == expected


@pytest.mark.parametrize("cur,expected", [
    (14, 12),      # on-ladder steps down
    (13, 12),      # off-ladder snaps to next step below
    (8, 8),        # bottom clamps
    (5, 5),        # below ladder stays put
    (100, 72),     # above ladder snaps to top step
])
def test_shrink(cur, expected):
    assert prev_ladder_pt(cur) == expected
