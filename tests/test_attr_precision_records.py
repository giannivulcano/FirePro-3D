"""Attribute record Unit + Precision override: schema and formatting
(text-sizing-wrap design D8; AC5, AC6, AC8)."""
import json
import os

import firepro3d
from firepro3d import block_library
from firepro3d.block_attributes import format_value, normalise_attr
from firepro3d.element_params import HostValue
from firepro3d.scale_manager import DisplayUnit, ScaleManager

_TAGS = os.path.join(os.path.dirname(firepro3d.__file__), "system_blocks", "Tags")


def _raw(name):
    with open(os.path.join(_TAGS, f"{name}.fpdb"), encoding="utf-8") as fh:
        return json.load(fh)


def _host(**kw):
    return normalise_attr({"key": "W", "source": "host", "host_key": "Width", **kw})


def _sm(unit, precision):
    sm = ScaleManager()
    sm.display_unit, sm.precision = unit, precision
    return sm


def test_malformed_precision_is_dropped_not_raised():
    for bad in ("abc", "2.5", 2.5, None, "", [1], True, "\u00b2"):
        assert normalise_attr({"key": "A", "precision": bad})["precision"] == 0
    assert normalise_attr({"key": "A", "precision": -3})["precision"] == 0
    assert normalise_attr({"key": "A", "precision": "3"})["precision"] == 3
    assert normalise_attr({"key": "A", "precision": 2.0})["precision"] == 2


def test_override_keys_are_sparse_and_validated():
    base = normalise_attr({"key": "A"})
    assert "unit" not in base and "display_precision" not in base
    r = normalise_attr({"key": "A", "unit": "m", "display_precision": "2"})
    assert (r["unit"], r["display_precision"]) == ("m", 2)
    for unit in ("imperial", "m", "mm"):
        assert normalise_attr({"key": "A", "unit": unit})["unit"] == unit
    for bad in ("furlong", "", None, "M", 3):
        assert "unit" not in normalise_attr({"key": "A", "unit": bad})
    for bad in ("abc", "2.5", "", None, True):
        assert "display_precision" not in normalise_attr({"key": "A", "display_precision": bad})
    assert normalise_attr({"key": "A", "display_precision": 9})["display_precision"] == 5
    assert normalise_attr({"key": "A", "display_precision": -1})["display_precision"] == 0
    assert normalise_attr(r) == r                     # every load re-normalises


def test_shipped_tag_records_normalise_unchanged():
    """Nothing moves: the shipped PipeLabel / RoomTag records gain no key."""
    for name in ("PipeLabel", "RoomTag"):
        raw = _raw(name)["attributes"]
        assert [normalise_attr(a) for a in raw] == raw


def test_corrupt_precision_record_no_longer_aborts_a_block_load(qapp, tmp_path):
    """AC8 (closes the bad-precision ValueError line): a .fpdb whose records
    carry malformed precisions loads, each reading its default."""
    data = _raw("PipeLabel")
    data["attributes"][0]["precision"] = "abc"
    data["attributes"][1]["precision"] = "2.5"
    data["attributes"][2]["display_precision"] = "x"
    path = tmp_path / "Corrupt.fpdb"
    path.write_text(json.dumps(data), encoding="utf-8")
    d = block_library.load_block_file(str(path))
    assert d is not None
    assert [a["precision"] for a in d.attributes] == [0, 0, 0, 0]
    assert all("display_precision" not in a for a in d.attributes)
