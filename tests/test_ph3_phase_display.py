"""PH3 DD1 / DD2 unit tests: PhaseDisplay, the pass context and the row merge.

Raw sources: factory graphics = constants.PHASE_EXISTING_COLOUR / PHASE_EXISTING_FILL
(D-PH10, phase_registry.factory_statuses); weight names = paper_display.DEFAULT_LINE_WEIGHTS.
"""
from types import SimpleNamespace

import pytest

from firepro3d import phase_display as phd
from firepro3d import phase_registry as pr
from firepro3d.constants import (PHASE_DEMOLITION, PHASE_EXISTING, PHASE_EXISTING_COLOUR,
                                 PHASE_EXISTING_FILL, PHASE_NEW)
from firepro3d.phase_display import FORCED, PhaseDisplay
from tests.test_underlay_display import _record

ROW = {"color": "token:auto", "fill": "token:bg", "section_color": "token:auto",
       "line_weight": "Fine", "opacity": 60, "visible": True, "as_authored": True}


def _data(kind="plan", phase_display=None):
    """The two SheetViewData fields begin_pass reads (the real dataclass gains
    ``phase_display`` in Task 4; Task 4's tests drive the real one)."""
    return SimpleNamespace(source_view_type=kind,
                           phase_display=phase_display or PhaseDisplay())


@pytest.fixture
def active():
    """``active(*hidden, kind="plan")`` opens a Phasing-on pass; closed at teardown."""
    def go(*hidden, kind="plan"):
        phd.begin_pass(_data(kind, phase_display=PhaseDisplay(True, frozenset(hidden))))
    yield go
    phd._STACK.clear()


def test_from_dict_missing_or_malformed_is_disabled():
    assert PhaseDisplay.from_dict(None) == PhaseDisplay()
    assert PhaseDisplay.from_dict("x") == PhaseDisplay()
    assert PhaseDisplay.from_dict({}) == PhaseDisplay()


def test_round_trip_and_unknown_ids_dropped():
    d = PhaseDisplay(True, frozenset({PHASE_DEMOLITION, PHASE_EXISTING}))
    assert d.to_dict() == {"enabled": True,
                           "hidden": sorted([PHASE_DEMOLITION, PHASE_EXISTING])}
    assert PhaseDisplay.from_dict(d.to_dict()) == d
    got = PhaseDisplay.from_dict({"enabled": True, "hidden": ["gone", PHASE_EXISTING, 3]})
    assert got.hidden == frozenset({PHASE_EXISTING})


def test_with_enabled_and_with_shown():
    d = PhaseDisplay().with_enabled(True).with_shown(PHASE_DEMOLITION, False)
    assert d == PhaseDisplay(True, frozenset({PHASE_DEMOLITION}))
    assert d.with_shown(PHASE_DEMOLITION, True).hidden == frozenset()


def test_no_pass_or_phasing_off_returns_the_row_itself():
    rec = _record(phase=PHASE_EXISTING)
    assert phd.merge(ROW, rec) is ROW
    phd.begin_pass(_data(phase_display=PhaseDisplay(False, frozenset({PHASE_EXISTING}))))
    try:
        assert phd.active() is None
        assert phd.merge(ROW, rec) is ROW
    finally:
        phd.end_pass()
    assert phd._STACK == []


def test_schematic_viewport_never_activates(active):
    active(PHASE_EXISTING, kind="schematic")
    assert phd.active() is None
    assert phd.merge(ROW, _record(phase=PHASE_EXISTING)) is ROW


def test_existing_takes_factory_colour_and_fill_dash_keeps_the_rest(active):
    active()
    out = phd.merge(ROW, _record(phase=PHASE_EXISTING))
    assert out["color"] == PHASE_EXISTING_COLOUR and out["fill"] == PHASE_EXISTING_FILL
    assert out["section_color"] == PHASE_EXISTING_FILL      # AC15: the Fill replaces the cut body
    assert out["line_weight"] == "Fine" and out["opacity"] == 60   # "--" keeps the row (R1, R2)
    assert out[FORCED] == frozenset({"color", "fill"})
    assert ROW["color"] == "token:auto" and FORCED not in ROW      # the row is never written


def test_status_weight_and_opacity_replace_the_row(active):
    pr.project_table().set_graphic(PHASE_EXISTING, "weight", "Extra Thick")
    pr.project_table().set_graphic(PHASE_EXISTING, "opacity", 50)
    active()
    out = phd.merge(ROW, _record(phase=PHASE_EXISTING))
    assert out["line_weight"] == "Extra Thick" and out["opacity"] == 50   # R2, R1: replace
    assert {"line_weight", "opacity"} <= out[FORCED]


def test_hidden_status_sets_visible_false(active):
    active(PHASE_DEMOLITION)
    assert phd.merge(ROW, _record(phase=PHASE_DEMOLITION))["visible"] is False
    assert phd.merge(ROW, _record(phase=PHASE_EXISTING))["visible"] is True


def test_new_has_no_override_but_can_hide(active):
    active(PHASE_NEW)                                   # D-PH9: New plots with no override
    out = phd.merge(ROW, _record(phase=PHASE_NEW))
    assert out["visible"] is False and out[FORCED] == frozenset()
    assert out["color"] == ROW["color"]


def test_unphased_item_plots_normally(qapp, active):
    """D-PH3: datum / annotation items carry no phase and always plot normally."""
    from PyQt6.QtWidgets import QGraphicsRectItem
    active(PHASE_NEW, PHASE_EXISTING, PHASE_DEMOLITION)
    assert phd.merge(ROW, QGraphicsRectItem()) is ROW


def test_keys_restrict_the_merge(active):
    active()
    out = phd.merge(ROW, _record(phase=PHASE_EXISTING), keys=phd.SYMBOL_KEYS)
    assert out["fill"] == ROW["fill"] and out["section_color"] == ROW["section_color"]
    assert out[FORCED] == frozenset({"color"})


@pytest.mark.parametrize("authored,forced,slot,want", [
    (False, frozenset(), "color", True),          # row OFF writes every colour slot
    (True, frozenset(), "color", False),          # row ON keeps authored
    (True, frozenset({"color"}), "color", True),  # DD2: the forced slot writes
    (True, frozenset({"color"}), "fill", False),  # DD2: an unforced slot keeps authored
])
def test_writes_rule(authored, forced, slot, want):
    assert phd.writes({FORCED: forced}, authored, slot) is want


def test_label_opacity_is_the_phase_opacity_else_one():
    assert phd.label_opacity({"opacity": 60, FORCED: frozenset()}) == 1.0
    assert phd.label_opacity({"opacity": 50, FORCED: frozenset({"opacity"})}) == 0.5
