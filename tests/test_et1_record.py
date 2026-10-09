"""ET1 G2 (record) + spec A: end record {"trim"[, "screen"]}, per-end
"scale" written only when != 1, ResolvedEnd.scale, parse_end_scale."""
import json

import pytest

from firepro3d import stroke_style as ss
from firepro3d.block_definition import BlockDefinition, _norm_end
from firepro3d.geometry_2d import LineItem
from tests.lt5_support import arrow


def test_norm_end_drops_size_and_keeps_screen_only_when_fixed():
    assert _norm_end({"size": "weight_relative", "trim": 1.5}) == {"trim": 1.5}
    assert _norm_end({"size": "fixed", "trim": 2.0, "screen": "fixed"}) == {
        "trim": 2.0, "screen": "fixed"}
    assert _norm_end({"trim": -1.0, "screen": "bogus"}) == {"trim": 0.0}
    assert _norm_end({"trim": "abc"}) == {"trim": 0.0}
    assert _norm_end("no") is None


def test_to_dict_has_no_size_key_and_round_trips_screen():
    a = arrow(screen="fixed")
    rec = json.loads(json.dumps(a.to_dict()))
    assert rec["end"] == {"trim": 3.0, "screen": "fixed"}
    assert "size" not in rec["end"]
    d2 = BlockDefinition.from_dict(rec)
    assert d2.end == {"trim": 3.0, "screen": "fixed"}
    legacy = BlockDefinition.from_dict({**rec, "end": {"size": "weight_relative", "trim": 1.5}})
    assert legacy.end == {"trim": 1.5}            # loads Fixed, trim as mm


def test_per_end_scale_written_only_when_not_one():
    assert ss._end({"end": "arrow", "scale": 2.0}) == {"end": "arrow", "visible": True, "scale": 2.0}
    assert ss._end({"end": "arrow", "scale": 1.0}) == {"end": "arrow", "visible": True}
    assert ss._end({"end": "arrow", "scale": "x"}) == {"end": "arrow", "visible": True}
    assert ss._end({"end": "arrow", "scale": 0}) == {"end": "arrow", "visible": True}
    assert ss._end({"end": "arrow", "scale": float("inf")}) == {"end": "arrow", "visible": True}
    st = ss.normalize_style({"start": {"end": "none", "mirrored": True, "scale": 0.5}})
    assert st["start"] == {"end": "none", "visible": True, "mirrored": True, "scale": 0.5}
    assert ss.default_style()["start"] == {"end": ss.BY_LINETYPE, "visible": True}   # LT2 golden


def test_resolved_end_carries_scale():
    a = arrow()
    reg = {a.id: a}
    s, f = ss.resolve_ends({"start": {"end": a.id, "scale": 2.0},
                            "finish": {"end": a.id, "visible": False, "scale": 3.0}}, None, reg)
    assert (s.defn, s.scale) == (a, 2.0)
    assert (f.defn, f.scale) == (None, 3.0)        # Visible off keeps the pick + scale
    assert ss.NO_ENDS[0].scale == 1.0
    assert ss.ResolvedEnd(a, None, False).scale == 1.0   # default for the LT5 call shape


@pytest.mark.parametrize("v, exp", [("2", 2.0), ("1.5 ×", 1.5), ("2×", 2.0), (0.25, 0.25),
                                    ("abc", None), ("0", None), ("-1", None), ("inf", None),
                                    ("12", None), (True, None)])
def test_parse_end_scale(v, exp):
    assert ss.parse_end_scale(v) == exp


def test_line_record_round_trips_scale_through_to_dict():
    ln = LineItem.__new__(LineItem)
    # to_dict/from_dict of a styled primitive carries the style record verbatim
    from PyQt6.QtCore import QPointF
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ln.style["finish"] = {"end": "arrow", "visible": True, "scale": 2.0}
    d = ln.to_dict()
    assert d["style"]["finish"]["scale"] == 2.0
