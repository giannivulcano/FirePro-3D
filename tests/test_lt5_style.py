"""LT5 A1 -- end records, the None keyword and the end cascade (design A).

Unit level: ``resolve_ends`` takes any registry with ``.get`` and any
linetype reading with ``start_end`` / ``finish_end`` (the real
``BlockDefinition`` / ``LinetypeDef`` versions are covered by
tests/test_lt5_capability_data.py once A2 lands).
"""
from types import SimpleNamespace

import pytest

from firepro3d import stroke_style as ss

_END = SimpleNamespace(end={"size": "fixed", "trim": 0.0})   # an end block
_LTYPE = SimpleNamespace(end=None, repeat={"length": 9.0})   # not an end
_REG = {"arrow": _END, "dot": _END, "hidden": _LTYPE}


def _style(start=None, finish=None):
    st = ss.default_style()
    if start is not None:
        st["start"] = start
    if finish is not None:
        st["finish"] = finish
    return st


def test_keywords():
    assert ss.NONE == "none"
    assert ss.END_KEYWORDS == (ss.BY_LINETYPE, ss.NONE)
    assert ss.NONE not in ss._KEYWORDS          # weight/linetype list untouched


def test_mirrored_written_only_when_true():
    assert ss._end({"end": "arrow", "mirrored": True}) == {
        "end": "arrow", "visible": True, "mirrored": True}
    assert ss._end({"end": "arrow", "mirrored": False}) == {
        "end": "arrow", "visible": True}
    assert ss._end({"end": "arrow", "mirrored": 0}) == {
        "end": "arrow", "visible": True}
    st = ss.normalize_style({"start": {"end": "none", "visible": False,
                                       "mirrored": True}})
    assert st["start"] == {"end": "none", "visible": False, "mirrored": True}
    assert st["finish"] == {"end": "by_linetype", "visible": True}


def test_default_record_unchanged():
    assert ss.default_style()["start"] == {"end": "by_linetype", "visible": True}
    assert ss.normalize_style(None) == ss.default_style("#ffffff")


@pytest.mark.parametrize("v, exp", [
    ("arrow", True), ("", False), (None, False), (3, False),
    (ss.BY_LINETYPE, False), (ss.NONE, False), (ss.BY_BLOCK, False)])
def test_is_end_ref(v, exp):
    assert ss.is_end_ref(v) is exp


def test_end_block_requires_the_end_capability():
    assert ss.end_block("arrow", _REG) is _END
    assert ss.end_block("hidden", _REG) is None        # a linetype
    assert ss.end_block("gone", _REG) is None
    assert ss.end_block(ss.NONE, _REG) is None
    assert ss.end_block("arrow", None) is None


def test_by_linetype_without_default_is_no_end():
    assert ss.resolve_ends(_style(), None, _REG) == ss.NO_ENDS
    lt = SimpleNamespace(start_end=None, finish_end=None)
    assert ss.resolve_ends(_style(), lt, _REG) == ss.NO_ENDS
    assert not ss.has_ends(ss.NO_ENDS)


def test_by_linetype_takes_the_linetype_defaults():
    lt = SimpleNamespace(start_end="arrow", finish_end="gone")
    s, f = ss.resolve_ends(_style(), lt, _REG)
    assert s == ss.ResolvedEnd(_END, None, False)
    assert f == ss.ResolvedEnd(None, "gone", False)      # missing default
    assert ss.has_ends((s, f))


def test_explicit_none_id_missing_and_non_end():
    lt = SimpleNamespace(start_end="arrow", finish_end="arrow")
    s, f = ss.resolve_ends(
        _style({"end": "none", "visible": True},
               {"end": "dot", "visible": True, "mirrored": True}), lt, _REG)
    assert s == ss.ResolvedEnd(None, None, False)        # None beats default
    assert f == ss.ResolvedEnd(_END, None, True)
    s, f = ss.resolve_ends(
        _style({"end": "hidden", "visible": True},
               {"end": "gone", "visible": True}), None, _REG)
    assert s == ss.ResolvedEnd(None, "hidden", False)    # linetype id: missing
    assert f == ss.ResolvedEnd(None, "gone", False)


def test_visible_off_is_none_but_keeps_mirrored():
    s, _ = ss.resolve_ends(
        _style({"end": "arrow", "visible": False, "mirrored": True}), None, _REG)
    assert s == ss.ResolvedEnd(None, None, True)
    assert not ss.has_ends((s, s))
