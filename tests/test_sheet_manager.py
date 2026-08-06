"""SheetManager invariants (spec paper-space.md §19.2) — pure unit tests."""
from __future__ import annotations

import pytest

from firepro3d.paper_space import Sheet, SheetManager


def _sheet(number, name="N"):
    s = Sheet.create_default()
    s.number, s.name = number, name
    return s


def test_empty_list_seeds_default_sheet_in_place():
    lst = []
    mgr = SheetManager(lst)
    assert len(lst) == 1, "manager must append the default INTO the caller's list"
    assert mgr.sheets is lst


def test_get_by_number():
    lst = [_sheet("FP-1.0"), _sheet("FP-2.0")]
    mgr = SheetManager(lst)
    assert mgr.get("FP-2.0") is lst[1]
    assert mgr.get("nope") is None


def test_validate_number_rules():
    mgr = SheetManager([_sheet("FP-1.0"), _sheet("FP-2.0")])
    assert not mgr.validate_number("")           # empty rejected
    assert not mgr.validate_number("   ")        # whitespace rejected
    assert not mgr.validate_number("FP-1.0")     # collision rejected
    assert mgr.validate_number("FP-3.0")
    # renumbering a sheet to its own number is valid (ignore=self)
    assert mgr.validate_number("FP-1.0", ignore=mgr.sheets[0])


def test_suggest_number_pattern_following():
    assert SheetManager([_sheet("FP-1.0")]).suggest_number() == "FP-2.0"
    assert SheetManager([_sheet("1")]).suggest_number() == "2"
    # collision → keeps bumping
    mgr = SheetManager([_sheet("FP-1.0"), _sheet("FP-2.0")])
    assert mgr.suggest_number() == "FP-3.0"


def test_suggest_number_no_digits_falls_back():
    mgr = SheetManager([_sheet("COVER")])
    assert mgr.suggest_number() == "FP-2.0"


def test_create_appends_active_ready_sheet():
    lst = [_sheet("FP-1.0")]
    lst[0].paper_size, lst[0].orientation = "ANSI B", "portrait"
    mgr = SheetManager(lst)
    s = mgr.create()
    assert s is lst[-1]
    assert s.number == "FP-2.0"
    assert s.name == SheetManager.DEFAULT_NAME
    # uniform-size rule (§19.1): new sheet inherits the project size
    assert s.paper_size == "ANSI B" and s.orientation == "portrait"
    assert s.sheet_views == [] and s.annotations == []


def test_delete_returns_neighbor_and_blocks_last():
    a, b, c = _sheet("1"), _sheet("2"), _sheet("3")
    mgr = SheetManager([a, b, c])
    assert mgr.delete(b) is c            # successor
    assert mgr.delete(c) is a            # was last → predecessor
    with pytest.raises(ValueError):
        mgr.delete(a)                    # ≥1 invariant


def test_reorder_permutation_only():
    a, b, c = _sheet("1"), _sheet("2"), _sheet("3")
    lst = [a, b, c]
    mgr = SheetManager(lst)
    assert mgr.reorder(["3", "1", "2"]) is True
    assert lst == [c, a, b]
    assert mgr.reorder(["3", "1", "2"]) is False      # no-op
    assert mgr.reorder(["3", "1"]) is False           # not a permutation
    assert mgr.reorder(["3", "1", "9"]) is False      # unknown number


def test_reorder_refuses_duplicate_numbers():
    mgr = SheetManager([_sheet("1"), _sheet("1"), _sheet("2")])
    assert mgr.reorder(["2", "1", "1"]) is False


def test_set_paper_all():
    a, b = _sheet("1"), _sheet("2")
    b.paper_size = "ANSI B"
    mgr = SheetManager([a, b])
    assert mgr.set_paper_all("ANSI D", "") is True
    assert a.paper_size == b.paper_size == "ANSI D"
    assert mgr.set_paper_all("ANSI D", "") is False   # no-op reports False
