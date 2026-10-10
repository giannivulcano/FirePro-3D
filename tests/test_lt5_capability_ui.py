"""LT5 D1 -- the capability table: an end-type block is never a symbol
(set_mode, armed click, drag gate, paste), the Blocks browser badges it,
the library listing + capability folder flag it, and commit / symbol-refusal
wording reads "end type" (linetypes.md D-L12, LT5 Q12 / Q13)."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d import block_library, capability_folder
from firepro3d.block_definition import BlockDefinition
from firepro3d.capabilities import (CAP_INFO, CAPABILITY_KINDS,
                                    capability_place_reason,
                                    exclusive_message, kind_of)
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import make_linetype
from tests.lt5_support import v_end
from tests.test_lt4_browser_wording import _leaf

_END_TIP = ("End type — apply it from a line's Start End / Finish End rows; "
            "it can't be placed")


def _plain(ms, name="Plain"):
    d = BlockDefinition.new(
        name=name, library="L", series="S", origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(0, 0), QPointF(10, 0)).to_dict()])
    ms.register_block_definition(d)
    return d


def _sink(ms):
    shown = []
    ms._show_status = lambda msg, timeout=5000: shown.append(msg)
    return shown


def test_table_rows_and_kind_of(qapp):
    assert CAPABILITY_KINDS == ("tile", "repeat", "end")
    assert {k: CAP_INFO[k].noun for k in CAPABILITY_KINDS} == {
        "tile": "pattern", "repeat": "linetype", "end": "end type"}
    assert CAP_INFO["tile"].place_reason == block_library.PATTERN_REASON
    assert CAP_INFO["repeat"].place_reason == block_library.LINETYPE_REASON
    assert CAP_INFO["end"].place_reason == block_library.END_REASON
    ms = Model_Space()
    assert kind_of(v_end()) == "end"
    assert kind_of(make_linetype()) == "repeat"
    assert kind_of(_plain(ms)) is None and kind_of(None) is None
    # library index entries (dicts) read the same flags
    assert kind_of({"tile": False, "repeat": False, "end": True}) == "end"
    assert kind_of({"tile": True}) == "tile"
    assert capability_place_reason(v_end()) == block_library.END_REASON
    assert capability_place_reason(_plain(ms, "P2")) is None


def test_exclusive_message_keeps_lt4_wording_and_adds_end(qapp):
    assert exclusive_message("tile", "repeat") == (
        "Turn Pattern tile off first — a block is a pattern or a linetype, "
        "not both")
    assert exclusive_message("repeat", "tile") == (
        "Turn Linetype off first — a block is a pattern or a linetype, "
        "not both")
    assert exclusive_message("end", "repeat") == (
        "Turn End type off first — a block is a linetype or an end type, "
        "not both")
    assert exclusive_message("tile", "end") == (
        "Turn Pattern tile off first — a block is a pattern or an end type, "
        "not both")


def test_end_block_cannot_enter_place_mode(qapp):
    ms = Model_Space()
    e = v_end()
    ms.register_block_definition(e)
    shown = _sink(ms)
    ms.set_mode("place_block", template=e.id)
    assert ms.mode != "place_block"
    assert ms.instance_count(e.id) == 0
    assert shown == [block_library.END_REASON]


def test_armed_click_refuses_block_that_became_an_end(qapp):
    ms = Model_Space()
    d = _plain(ms)
    ms.set_mode("place_block", template=d.id)
    assert ms.mode == "place_block"
    shown = _sink(ms)
    d.set_end({"size": "fixed", "trim": 0.0})
    ms._press_place_block(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    assert ms.instance_count(d.id) == 0
    assert ms.mode != "place_block"
    assert shown[0] == block_library.END_REASON


def test_drag_gate_refuses_project_and_library_only_end(qapp, tmp_path):
    from firepro3d.model_view import Model_View
    ms = Model_Space()
    e = v_end()
    ms.register_block_definition(e)
    _d, _pool, reason = Model_View._resolve_block_drag(ms, {"id": e.id})
    assert reason == block_library.END_REASON
    lib = v_end(name="Tick")
    path = block_library.save_to_library(lib, root=str(tmp_path))
    assert ms.get_block_definition(lib.id) is None
    _d, _pool, reason = Model_View._resolve_block_drag(
        ms, {"id": lib.id, "path": str(path)})
    assert reason == block_library.END_REASON


def test_paste_skips_end_instances(qapp):
    ms = Model_Space()
    e = v_end()
    ms.register_block_definition(e)
    plain = _plain(ms)
    shown = _sink(ms)
    rec = {"type": "block_instance", "pos": [0, 0], "rotation": 0.0,
           "level": ms.active_level}
    new = ms.paste_items(QPointF(0, 0), data=[{**rec, "block_id": e.id},
                                              {**rec, "block_id": plain.id}])
    assert [i.block_id for i in new] == [plain.id]
    assert ms.instance_count(e.id) == 0
    assert shown == [block_library.END_REASON]


def test_browser_badges_end_blocks_on_project_and_library_rows(qapp, tmp_path):
    from firepro3d.blocks_browser import _ROLE_PATH, BlocksBrowser
    ms = Model_Space()
    ms.register_block_definition(v_end("Arrow"))
    block_library.save_to_library(v_end("Tick"), root=str(tmp_path))
    block_library.save_to_library(make_linetype("Center"), root=str(tmp_path))
    br = BlocksBrowser(ms, root=str(tmp_path))
    br.refresh()
    arrow, tick, center = (_leaf(br._tree, n) for n in ("Arrow", "Tick", "Center"))
    for leaf in (arrow, tick):
        assert leaf is not None and not leaf.icon(0).isNull()
        assert leaf.toolTip(0) == _END_TIP
    assert tick.font(0).italic() and tick.data(0, _ROLE_PATH)
    # The end glyph is its own picture, not the linetype dash-dot badge.
    a = arrow.icon(0).pixmap(14, 14).toImage()
    c = center.icon(0).pixmap(14, 14).toImage()
    assert a != c


def test_library_listing_flags_end_and_folder_scan_finds_it(qapp, tmp_path):
    # The index is retired (2026-10-10): the flag is read from the files.
    e = v_end("Arrow")
    block_library.save_to_library(e, root=str(tmp_path))
    block_library.save_to_library(make_linetype("Hidden"), root=str(tmp_path))
    end = {x["name"]: x["end"] for x in block_library.list_library(str(tmp_path))}
    assert end == {"Arrow": True, "Hidden": False}
    assert "end" in capability_folder.FLAGS
    assert [(n, b) for n, b, _ in capability_folder.scan(str(tmp_path), "end")] \
        == [("Arrow", e.id)]


def test_new_end_type_is_registered_not_placed(qapp):
    ms = Model_Space()
    shown = _sink(ms)
    prims = list(v_end().primitives)
    d = ms.commit_block_definition(
        block_id=None, name="Arrow", library="L", series="End Types",
        primitives=prims, origin=(0.0, 0.0), place_instance=True,
        capability=("end", {"trim": 1.5, "screen": "fixed"}))
    assert d is not None
    assert d.end == {"trim": 1.5, "screen": "fixed"}
    assert ms.instance_count(d.id) == 0
    assert shown[-1] == ("Saved end type ‘Arrow’ — end types aren't placed; "
                         "your original geometry is unchanged.")
    d2 = ms.commit_block_definition(
        block_id=d.id, name="Arrow", library="L", series="End Types",
        primitives=prims, origin=(0.0, 0.0), place_instance=False,
        capability=("end", {"trim": 0.0}))
    assert d2 is d and d.end == {"trim": 0.0}


def test_symbol_refusal_names_end_type(qapp):
    ms = Model_Space()
    d = _plain(ms)
    ms.place_block_instance(d.id, (0.0, 0.0))
    assert ms.symbol_use_refusal(d.id, "end") == (
        "Used as a symbol (1 placed) — remove those before making it an "
        "end type")
    assert ms.symbol_use_refusal(d.id, "repeat").endswith("making it a linetype")
    assert ms.symbol_use_refusal(d.id, "tile").endswith("making it a pattern")
