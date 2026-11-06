"""Paper polish AC1 / AC2 / D8: the preset table, the parser and how saved
scales read. Denominators below are hand-written, never read from the table."""
import pytest
from PyQt6.QtCore import QRectF

from firepro3d import stroke_style as ss
from firepro3d.paper_space import (SCALE_PRESETS, SheetViewData, ViewportProperties,
                                   float_to_scale_str, scale_to_float)
from tests._sb4d_helpers import add_sheet, dispose, paper_view, plan_scene

FT = "'-0\""
EXPECTED = {
    "1:1000": 1000, "1:500": 500, "1:250": 250, "1:200": 200, "1:150": 150,
    "1:100": 100, "1:75": 75, "1:50": 50, "1:30": 30, "1:25": 25, "1:20": 20,
    "1:10": 10, "1:5": 5, "1:1": 1,
    f'1/32"=1{FT}': 384, f'1/16"=1{FT}': 192, f'3/32"=1{FT}': 128,
    f'1/8"=1{FT}': 96, f'3/16"=1{FT}': 64, f'1/4"=1{FT}': 48, f'3/8"=1{FT}': 32,
    f'1/2"=1{FT}': 24, f'3/4"=1{FT}': 16, f'1"=1{FT}': 12, f'1-1/2"=1{FT}': 8,
    f'3"=1{FT}': 4,
    '1"=10\'': 120, '1"=20\'': 240, '1"=30\'': 360, '1"=40\'': 480,
    '1"=50\'': 600, '1"=60\'': 720, '1"=100\'': 1200,
}


def test_the_table_is_exactly_the_ratified_list():
    assert {label for label, _ in SCALE_PRESETS} == set(EXPECTED)


@pytest.mark.parametrize("label,denom", EXPECTED.items())
def test_every_preset_round_trips_at_its_true_ratio(label, denom):
    assert scale_to_float(label) == pytest.approx(1.0 / denom)
    assert float_to_scale_str(1.0 / denom) == label


def test_no_two_presets_share_a_ratio():
    assert len({round(1.0 / r) for _, r in SCALE_PRESETS}) == len(SCALE_PRESETS)


@pytest.mark.parametrize("text,denom,reads", [
    ('1"=15\'', 180, "1:180"),
    ("1:125", 125, "1:125"),
    ("1:12.5", 12.5, "1:12.5"),
    (f'3/4"=1{FT}', 16, f'3/4"=1{FT}'),
    ('  1 " = 10 \' ', 120, '1"=10\''),
    ("1:0.001", 0.001, "1:0.001"),               # ratio 1000: the largest a viewport may take
])
def test_typed_scales_parse_and_read_back(text, denom, reads):
    r = scale_to_float(text)
    assert r == pytest.approx(1.0 / denom)
    assert float_to_scale_str(r) == reads


@pytest.mark.parametrize("bad", [
    "", "abc", "1:0", "1:00", '1"=0\'', f'0"=1{FT}', f'1/0"=1{FT}', "1:-5",
    "1:0.0001",                                   # ratio 10000: reads back as 1:0
    '99999999999999999999"=1\'-0"',               # inf
    f'{"9" * 400}/{"9" * 400}"=1\'-0"',           # nan
])
def test_bad_text_raises_value_error_only(bad):
    with pytest.raises(ValueError):
        scale_to_float(bad)


def test_model_scale_list_shares_the_table():
    """D8: the Model scale row reads the same list and every label survives its
    store-as-denominator round trip."""
    opts = ss.model_scale_options()
    assert set(opts) == set(EXPECTED)
    for label in opts:
        assert ss.model_scale_label(ss.model_scale_from_label(label)) == label


def test_a_viewport_saved_at_1_12_keeps_its_size_and_reads_one_inch(qapp, real_system_library):
    """D7: 3/36 is the literal the old 3/4" preset stored."""
    ms, sec, det, tabs = plan_scene()
    try:
        sheet = add_sheet(ms, "FP-1.0")
        view, ps = paper_view(ms, sec, det, sheet)
        rec = SheetViewData("plan", "Plan: Level 1", "T", 3 / 36, 30.0, 30.0, 100.0, 80.0,
                            crop_rect=QRectF(0.0, 0.0, 1200.0, 960.0)).to_dict()
        vp = ps.add_viewport(SheetViewData.from_dict(rec))
        assert vp._placeholder is False
        assert (vp.data.w, vp.data.h) == pytest.approx((100.0, 80.0))
        assert vp.data.scale == pytest.approx(1 / 12)
        row = ViewportProperties(ps, vp).get_properties()["Scale"]
        assert row["value"] == f'1"=1{FT}'
        assert row["value"] in row["options"]
    finally:
        dispose(ms, sec, tabs)
