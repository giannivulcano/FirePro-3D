"""SB1a: pure attribute schema / resolver (design S1, S3; A7, A8)."""
import pytest

from firepro3d.block_attributes import (
    normalise_attr, format_value, resolve_values, resolve_fields, has_fields,
    rename_key_in_texts, references_of, unknown_tokens)


def _rec(**kw):
    base = {"key": "Mark", "label": "Mark", "type": "text", "source": "instance",
            "host_key": "", "default": "A1", "prefix": "", "suffix": "",
            "precision": 0, "placeholder": "?"}
    base.update(kw)
    return base


def test_normalise_fills_every_field_and_keeps_key():
    r = normalise_attr({"key": "Mark"})
    assert r == {"key": "Mark", "label": "Mark", "type": "text", "source": "instance",
                 "host_key": "", "default": "", "prefix": "", "suffix": "",
                 "precision": 0, "placeholder": "?"}
    with pytest.raises(ValueError):
        normalise_attr({"key": ""})
    with pytest.raises(ValueError):
        normalise_attr({"key": "x", "type": "date"})


def test_format_value_number_precision_prefix_suffix():
    r = _rec(type="number", precision=2, prefix="L=", suffix=" mm")
    assert format_value(r, 3.14159) == "L=3.14 mm"
    assert format_value(r, "2") == "L=2.00 mm"
    assert format_value(r, "abc") == "?"          # non-numeric -> placeholder
    assert format_value(_rec(type="number", precision=0), 7) == "7"
    assert format_value(_rec(), "") == "?"        # empty text -> placeholder
    assert format_value(_rec(), None) == "?"
    assert format_value(_rec(prefix="(", suffix=")"), "B") == "(B)"


def test_resolve_values_instance_override_host_sources():
    attrs = [_rec(),
             _rec(key="Area", type="number", precision=1, source="host",
                  host_key="Room.Area", default="", placeholder="--")]
    # instance source: typed value else default
    assert resolve_values(attrs, {}, None) == {"Mark": "A1", "Area": "--"}
    assert resolve_values(attrs, {"Mark": "B2"}, None)["Mark"] == "B2"
    # host source: provider value
    v = resolve_values(attrs, {}, {"Room.Area": 12.345})
    assert v["Area"] == "12.3"
    # host source: presence in instance values is the override (A4 / D4)
    v = resolve_values(attrs, {"Area": "99"}, {"Room.Area": 12.345})
    assert v["Area"] == "99.0"
    # provider lacks the key -> placeholder
    assert resolve_values(attrs, {}, {"Other": 1})["Area"] == "--"


def test_resolve_fields_and_has_fields_and_unknown_tokens():
    assert has_fields("Tag @[Mark]") is True
    assert has_fields("plain") is False
    text, unknown = resolve_fields("@[Mark]/@[Nope]", {"Mark": "A1"})
    assert text == "A1/@[Nope]" and unknown == ["Nope"]
    prims = [{"type": "text", "text": "@[Mark] @[Zed]"},
             {"type": "line", "x1": 0},
             {"type": "text", "text": "@[Zed]"}]
    assert unknown_tokens(prims, [_rec()]) == ["Zed"]


def test_rename_and_references():
    prims = [{"type": "text", "text": "@[Mark]-@[Mark]"},
             {"type": "text", "text": "x"},
             {"type": "line"}]
    assert references_of(prims, "Mark") == [0]
    n = rename_key_in_texts(prims, "Mark", "Tag")
    assert n == 1
    assert prims[0]["text"] == "@[Tag]-@[Tag]"
    assert references_of(prims, "Mark") == []


def test_rename_keys_single_pass_swap_and_chain():
    from firepro3d.block_attributes import rename_keys_in_texts
    prims = [{"type": "text", "text": "@[A]-@[B]-@[C]"}, {"type": "line", "text": "@[A]"}]
    assert rename_keys_in_texts(prims, {"A": "B", "B": "A"}) == 1
    assert prims[0]["text"] == "@[B]-@[A]-@[C]"          # swap, not collapsed
    assert prims[1]["text"] == "@[A]"                    # non-text untouched
    prims = [{"type": "text", "text": "@[A]@[B]"}]
    rename_keys_in_texts(prims, {"A": "B", "B": "C"})
    assert prims[0]["text"] == "@[B]@[C]"                # chain, not A->C
