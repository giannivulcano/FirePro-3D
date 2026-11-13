"""SB4g T11 -- D6 / R6 / AC3 / AC8: the per-element symbol id persists sparsely
(file, undo, paste, placement template, auto-populate) and a legacy Graphic
value loads as the default symbol. Raw sources: design D6 ("written only when
not None"; "a file's Graphic value is ignored"), R6 ("every head loads with the
default symbol"), fixture tests/fixtures/ph1_pre_phasing_v12.fpd (node 3's
sprinkler carries "Graphic": "Sprinkler0" -- the pre-SB4g writer)."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

from PyQt6.QtCore import QPointF

from firepro3d.network_codec import SYMBOL_KEY, serialize_node
from firepro3d.node import Node
from firepro3d.sprinkler import Sprinkler
from tests._sb4g_helpers import SPR_IDS, head, scene, water_supply

FIXTURE = Path(__file__).parent / "fixtures" / "ph1_pre_phasing_v12.fpd"


def _save(ms, tmp_path, name="t.fpd"):
    f = tmp_path / name
    assert ms.save_to_file(str(f), backup=False)
    return f, json.loads(f.read_text(encoding="utf-8"))


def test_g5_legacy_graphic_value_loads_the_default_symbol(qapp, tmp_path,
                                                          real_system_library):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    spr_rec = next(n["sprinkler"] for n in raw["nodes"] if n["sprinkler"])
    assert spr_rec["Graphic"]["value"] == "Sprinkler0"          # the pre-SB4g writer
    spr_rec["Graphic"]["value"] = "Sprinkler2"                  # a non-default legacy pick
    src = tmp_path / "old.fpd"
    src.write_text(json.dumps(raw), encoding="utf-8")
    ms = scene()
    assert ms.load_from_file(str(src))                           # no exception, no refusal
    (spr,) = ms.sprinkler_system.sprinklers
    assert spr.symbol_block is None                              # R6: dropped, not mapped
    assert spr.definition().id == SPR_IDS[0]                     # draws the System default
    _f, out = _save(ms, tmp_path, "resaved.fpd")
    rec = next(n["sprinkler"] for n in out["nodes"] if n["sprinkler"])
    assert "Graphic" not in rec and SYMBOL_KEY not in rec        # gone, and sparse


def test_ac3_symbol_block_round_trips_file_undo_and_paste(qapp, tmp_path,
                                                          real_system_library):
    ms = scene()
    n, spr = head(ms)
    assert SYMBOL_KEY not in serialize_node(n, {n: 0})["sprinkler"]   # None is sparse
    spr.set_symbol_block(SPR_IDS[2])
    f, raw = _save(ms, tmp_path)
    rec = next(e["sprinkler"] for e in raw["nodes"] if e["sprinkler"])
    assert rec[SYMBOL_KEY] == SPR_IDS[2]
    assert "Symbol" not in rec                                   # the row label is never stored
    ms2 = scene()
    assert ms2.load_from_file(str(f))
    (s2,) = ms2.sprinkler_system.sprinklers
    assert s2.symbol_block == SPR_IDS[2] and s2.definition().id == SPR_IDS[2]
    rec[SYMBOL_KEY] = 7                                          # non-str -> None
    f.write_text(json.dumps(raw), encoding="utf-8")
    ms3 = scene()
    assert ms3.load_from_file(str(f))
    assert ms3.sprinkler_system.sprinklers[0].symbol_block is None
    # undo rebuilds the network from serialize_node / deserialize_node
    ms.push_undo_state()
    ms.push_undo_state()
    ms.undo()
    (su,) = ms.sprinkler_system.sprinklers
    assert su.symbol_block == SPR_IDS[2] and su.definition().id == SPR_IDS[2]
    # paste (Ctrl+V / Array / Duplicate Level share paste_items)
    node = su.node
    new = ms.paste_items(QPointF(5000.0, 0.0), data=ms._clipboard_item_dicts([node]))
    pasted = [i for i in new if isinstance(i, Node) and i.has_sprinkler()]
    assert [p.sprinkler.symbol_block for p in pasted] == [SPR_IDS[2]]


def test_ac3_placement_template_and_auto_populate_carry_the_symbol(qapp,
                                                                   real_system_library):
    from tests.test_sb3b_room_tag_style import _add_room
    ms = scene()
    tmpl = Sprinkler(None)
    tmpl.symbol_block = SPR_IDS[1]
    n = ms.add_node(0.0, 0.0)
    spr = ms.add_sprinkler(n, tmpl)                               # the placement path (model_space add_sprinkler)
    assert spr.symbol_block == SPR_IDS[1] and spr.definition().id == SPR_IDS[1]
    room = _add_room(ms, "Office", x0=10000.0)
    rec = SimpleNamespace(manufacturer="Tyco", model="", type="Upright", k_factor=5.6,
                          coverage_area=130, min_pressure=7, temp_rating=155)
    ms.auto_populate_room(room, [QPointF(10500.0, 500.0)], rec, "Level 1", "Level 1",
                          -50.8, symbol_block=SPR_IDS[2])
    placed = [s for s in ms.sprinkler_system.sprinklers if s is not spr]
    assert [s.symbol_block for s in placed] == [SPR_IDS[2]]


def test_ac3_water_supply_symbol_round_trips_file_and_paste(qapp, tmp_path):
    ms = scene()
    ws = water_supply(ms)
    _f, raw = _save(ms, tmp_path, "a.fpd")
    assert SYMBOL_KEY not in raw["water_supply"]                  # sparse
    ws.symbol_block = "lib-ws-1"            # R8: an id is kept even when it does not resolve
    f, raw = _save(ms, tmp_path, "b.fpd")
    assert raw["water_supply"][SYMBOL_KEY] == "lib-ws-1"
    ms2 = scene()
    assert ms2.load_from_file(str(f))
    assert ms2.water_supply_node.symbol_block == "lib-ws-1"
    data = ms._clipboard_item_dicts([ws])
    assert data[0][SYMBOL_KEY] == "lib-ws-1"
