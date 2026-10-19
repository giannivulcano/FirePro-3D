"""UP1 fill_layers: the one reader / writer of the shape ``fill`` record (design D1)."""
import math

import pytest

from firepro3d.fill_layers import (BackgroundLayer, EMPTY, FillLayers, NO_LAYER,
                                   PatternLayer, alpha, from_record, pattern_ref,
                                   to_record)


def test_empty_writes_no_record():
    assert EMPTY.is_empty and to_record(EMPTY) is None and to_record(None) is None


def test_new_shape_round_trips_both_layers():
    fl = FillLayers(BackgroundLayer("#3366cc", 0.5),
                    PatternLayer("builtin-hatch-diagonal", "token:auto", 0.8, 2.0))
    rec = to_record(fl)
    assert rec == {"background": {"color": "#3366cc", "opacity": 0.5},
                   "pattern": {"ref": "builtin-hatch-diagonal", "color": "token:auto",
                               "opacity": 0.8, "scale": 2.0}}
    assert from_record(rec) == fl


def test_absent_layer_key_omitted():
    rec = to_record(FillLayers(pattern=PatternLayer("builtin-hatch-diagonal")))
    assert set(rec) == {"pattern"}
    assert from_record(rec).background is None


@pytest.mark.parametrize("rec, want", [
    ({"type": "solid", "color": "#00ff00", "opacity": 0.5},
     FillLayers(background=BackgroundLayer("#00ff00", 0.5))),
    ({"type": "hatch", "pattern": "diagonal", "color": "#ff0000", "opacity": 0.45},
     FillLayers(pattern=PatternLayer("builtin-hatch-diagonal", "#ff0000", 0.45, 1.0))),
    ({"type": "solid"},                                    # legacy defaults
     FillLayers(background=BackgroundLayer("#888888", 0.45))),
    ({"type": "solid", "color": None, "opacity": 0.45},
     FillLayers(background=BackgroundLayer("#888888", 0.45))),
    ({"type": "solid", "color": "", "opacity": 0.45}, EMPTY),     # HF1 No Fill
    ({"type": "none", "color": "#123456"}, EMPTY),
    ({"type": "hatch", "color": "token:accent", "opacity": 1.0},  # pattern missing
     FillLayers(pattern=PatternLayer("builtin-hatch-diagonal", "token:accent", 1.0, 1.0))),
])
def test_legacy_records_read_same_look(rec, want):
    assert from_record(rec) == want


@pytest.mark.parametrize("rec", [None, "solid", 3, [], {"background": "x"},
                                 {"pattern": {"ref": ""}}, {"type": "solid", "opacity": "x"},
                                 {"background": {"color": 5}}])
def test_malformed_records_read_empty_or_partial_never_raise(rec):
    fl = from_record(rec)
    assert isinstance(fl, FillLayers)
    assert fl.pattern is None


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf"), "x"])
def test_bad_stored_scale_loads_as_one(bad):
    fl = from_record({"pattern": {"ref": "r", "scale": bad}})
    assert fl.pattern.scale == 1.0


def test_opacity_clamped_and_alpha_matches_legacy_rounding():
    fl = from_record({"background": {"color": "#000000", "opacity": 7}})
    assert fl.background.opacity == 1.0
    assert alpha(0.45) == int(round(0.45 * 255)) == 115


def test_pattern_ref_reads_both_shapes():
    assert pattern_ref({"type": "hatch", "pattern": "diagonal"}) == "builtin-hatch-diagonal"
    assert pattern_ref({"pattern": {"ref": "abc"}}) == "abc"
    assert pattern_ref({"type": "solid"}) is None
    assert pattern_ref(None) is None


def test_no_layer_is_a_singleton_sentinel():
    assert repr(NO_LAYER) == "NO_LAYER"
    assert NO_LAYER is not None and not isinstance(NO_LAYER, (BackgroundLayer, PatternLayer))
