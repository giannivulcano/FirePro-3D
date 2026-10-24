"""SB2b Marks -- pure pattern / numbering / ordering core (spec element-parameters.md Marks)."""
import pytest

from firepro3d import marks


@pytest.mark.parametrize("pattern,n,level,expected", [
    ("D{n}", 3, None, "D3"),
    ("{level}{n:02}", 1, 4, "401"),
    ("{level}{n:02}", 123, 1, "1123"),     # padding never truncates
    ("DR-{n:02}", 7, None, "DR-07"),
    ("LOBBY", 9, None, "LOBBY"),           # no counter token -> literal
    ("", 5, 2, ""),                        # blank pattern -> blank Mark
    ("{level}-{n}", 2, None, "-2"),        # no level -> {level} prints empty
    ("{n:2}", 1, None, "{n:2}"),           # not a token -> literal
])
def test_format_mark(pattern, n, level, expected):
    assert marks.format_mark(pattern, n, level) == expected


def test_next_number_highest_matching_plus_one():
    existing = ["D1", "D7", "D3", "X9", "D", "d8", ""]
    assert marks.next_number("D{n}", None, existing) == 8


def test_next_number_resolves_level_first():
    existing = ["101", "102", "205", "1105"]
    assert marks.next_number("{level}{n:02}", 1, existing) == 106   # "1105" = level 1, n 105
    assert marks.next_number("{level}{n:02}", 2, existing) == 6
    assert marks.next_number("{level}{n:02}", 3, existing) == 1


def test_next_number_padded_requires_width():
    # {n:02} matches 2+ digits only; "D5" is not a DR-{n:02} Mark
    assert marks.next_number("DR-{n:02}", None, ["DR-5", "DR-09", "D5"]) == 10


def test_next_number_gaps_not_refilled():
    assert marks.next_number("W{n}", None, ["W1", "W5"]) == 6


def test_next_number_no_counter_or_blank_is_one():
    assert marks.next_number("LOBBY", None, ["LOBBY"]) == 1
    assert marks.next_number("", None, ["D1"]) == 1


def test_mark_number_parses_resolved_pattern():
    assert marks.mark_number("{level}{n:02}", 1, "107") == 7
    assert marks.mark_number("{level}{n:02}", 2, "107") is None
    assert marks.mark_number("D{n}", None, "D0012") == 12


def test_duplicate_groups_exact_and_nonblank():
    items = {"a": "D1", "b": "D1", "c": "d1", "d": "", "e": "", "f": "D2"}
    groups = marks.duplicate_groups(items)
    assert groups == {"D1": {"a", "b"}}


def test_reading_order_rows_then_left_to_right():
    # scene coords: y grows downward, so "top" = smallest y.
    pts = {
        "r1_right": (5000.0, 100.0),
        "r1_left": (0.0, 450.0),        # within 600 of the row's first element -> same row
        "r2_left": (0.0, 1200.0),
        "r2_right": (3000.0, 900.0),     # 900 - 100 > 600 -> starts row 2
    }
    assert marks.reading_order(pts, tol=600.0) == ["r1_left", "r1_right", "r2_left", "r2_right"]


def test_reading_order_row_anchor_is_first_element_not_chain():
    # 0 -> 500 -> 1000: 1000 is > 600 from the row's FIRST element (0) -> new row
    pts = {"a": (10.0, 0.0), "b": (0.0, 500.0), "c": (5.0, 1000.0)}
    assert marks.reading_order(pts, tol=600.0) == ["b", "a", "c"]


def _e(key, level_order, level_num, pt, mark, in_scope=True):
    return marks.RenumberEntry(key=key, level_order=level_order, level_number=level_num,
                               point=pt, mark=mark, in_scope=in_scope)


def test_renumber_whole_project_level_by_level_from_one():
    es = [_e("u1", 1, 2, (0, 0), "D9"), _e("g2", 0, 1, (500, 0), "D1"),
          _e("g1", 0, 1, (0, 0), "D4")]
    out = marks.renumber_entries(es, "D{n}", restart_per_level=False, keep_order=False)
    assert out == {"g1": "D1", "g2": "D2", "u1": "D3"}


def test_renumber_restart_per_level_with_level_token():
    es = [_e("g1", 0, 1, (0, 0), "105"), _e("g2", 0, 1, (900, 0), "101"),
          _e("u1", 1, 2, (0, 0), "209")]
    out = marks.renumber_entries(es, "{level}{n:02}", restart_per_level=True, keep_order=False)
    assert out == {"g1": "101", "g2": "102", "u1": "201"}


def test_renumber_keep_order_closes_gaps():
    es = [_e("a", 0, 1, (900, 0), "D2"), _e("b", 0, 1, (0, 0), "D7"),
          _e("c", 0, 1, (400, 0), "D4")]
    out = marks.renumber_entries(es, "D{n}", restart_per_level=False, keep_order=True)
    assert out == {"a": "D1", "c": "D2", "b": "D3"}


def test_renumber_out_of_scope_untouched_and_floor_above_them():
    es = [_e("keep", 0, 1, (0, 0), "D5", in_scope=False),
          _e("x", 0, 1, (100, 0), "D1"), _e("y", 0, 1, (900, 0), "D2")]
    out = marks.renumber_entries(es, "D{n}", restart_per_level=False, keep_order=False)
    assert out == {"x": "D6", "y": "D7"}
    assert "keep" not in out


def test_renumber_keep_order_unparsable_marks_after_parsed_in_reading_order():
    es = [_e("a", 0, 1, (900, 0), "D3"), _e("b", 0, 1, (0, 0), ""),
          _e("c", 0, 1, (400, 0), "custom")]
    out = marks.renumber_entries(es, "D{n}", restart_per_level=False, keep_order=True)
    assert out == {"a": "D1", "b": "D2", "c": "D3"}


def test_gridline_labels_orientation_rule():
    verticals = {"v_mid": 5000.0, "v_left": 0.0, "v_right": 9000.0}      # key -> x
    horizontals = {"h_top": 0.0, "h_bottom": 8000.0}                     # key -> scene y
    out = marks.gridline_labels(verticals, horizontals)
    assert out == {"v_left": "1", "v_mid": "2", "v_right": "3",
                   "h_bottom": "A", "h_top": "B"}


def test_letter_label_rolls_to_two_letters():
    assert marks.letter_label(0) == "A"
    assert marks.letter_label(25) == "Z"
    assert marks.letter_label(26) == "AA"
    assert marks.letter_label(27) == "AB"


def test_default_patterns_match_spec_m3():
    assert marks.DEFAULT_PATTERNS == {
        "Door": "D{n}", "Window": "W{n}", "Opening": "O{n}", "Wall": "WL{n}",
        "Pipe": "P{n}", "Sprinkler": "S{n}", "Room": "{level}{n:02}",
    }
    assert marks.RENUMBER_CATEGORIES == marks.MARK_CATEGORIES + ("Gridline",)
