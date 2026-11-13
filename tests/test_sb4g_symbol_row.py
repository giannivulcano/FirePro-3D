"""SB4g T12 -- D7 / AC3 / G2: the Symbol row on sprinkler and water supply,
driven through the shown PropertyManager (the real enum Selector). Raw
sources: design D7 ("System symbols of that category, then user-library blocks
passing eligible_symbol"), R10 (only flagged real-size blocks), R3 (a new head
takes the template's choice), sprinkler0.svg fill #2e2e2e vs sprinkler2.svg
circle fill:none, water_supply.svg fill #2b2b2e."""
import json

from PyQt6.QtCore import QRectF

from firepro3d.app_data import block_library_dir
from firepro3d.network_codec import SYMBOL_KEY
from firepro3d.property_manager import PropertyManager
from firepro3d.sprinkler import Sprinkler
from tests._sb4g_helpers import (SPR0_FILL, SPR_IDS, WS_FILL, head, lib_symbol,
                                   names, render, scene, water_supply)

RECT = QRectF(-400.0, -400.0, 800.0, 800.0)
SPR_SYSTEM = ["Sprinkler0 (System)", "Sprinkler1 (System)", "Sprinkler2 (System)"]


def _pick(pm, label, key="Symbol"):
    """The test_sb3b_room_tag_style._pick idiom: drive the panel's enum
    Selector by text through its shipped currentTextChanged connect."""
    combo = pm._prop_widgets[key]
    fired = []
    combo.currentTextChanged.connect(lambda t: fired.append(t))
    combo.setCurrentText(label)
    assert fired == [label], "Selector.setCurrentText did not emit currentTextChanged"
    pm._refresh_timer.stop()
    return combo


def _library(root):
    lib_symbol(root, "LibHead", "lib-head-1", "Sprinkler")
    lib_symbol(root, "LibPlain", "lib-plain-1", "")                      # real size, unflagged
    lib_symbol(root, "LibAnnot", "lib-annot-1", "Sprinkler", annotative=True)
    lib_symbol(root, "LibWS", "lib-ws-1", "Water Supply")


def test_g2_sprinkler_row_lists_flagged_symbols_and_a_pick_redraws_in_one_step(
        qapp, real_system_library):
    _library(block_library_dir())
    ms = scene()
    node, spr = head(ms)
    ms.push_undo_state()                                    # the seed a new / opened file has
    props = spr.get_properties()
    keys = list(props)
    assert keys.index("Symbol") == keys.index("Design Density") + 1     # the old Graphic slot
    row = props["Symbol"]
    assert row["type"] == "enum"
    assert row["options"] == SPR_SYSTEM + ["LibHead (Library)"]       # no LibPlain / LibAnnot / LibWS
    assert row["value"] == "Sprinkler0 (System)"            # None shows the System default
    before = names(render(ms, RECT))
    assert SPR0_FILL in before
    pm = PropertyManager()
    pm.show_properties([node])                              # a node resolves to its head
    combo = pm._prop_widgets["Symbol"]
    assert [combo.itemText(i) for i in range(combo.count())] == row["options"]
    n = len(ms._undo_stack)
    _pick(pm, "Sprinkler2 (System)")
    assert len(ms._undo_stack) == n + 1                     # ONE undo step
    assert spr.symbol_block == SPR_IDS[2] and spr.definition().id == SPR_IDS[2]
    picked = names(render(ms, RECT))
    assert SPR0_FILL not in picked                          # sprinkler2: no #2e2e2e disc
    ms.undo()
    (su,) = ms.sprinkler_system.sprinklers
    assert su.symbol_block is None and su.definition().id == SPR_IDS[0]
    ms.redo()
    (sr,) = ms.sprinkler_system.sprinklers
    assert sr.symbol_block == SPR_IDS[2] and sr.definition().id == SPR_IDS[2]
    # Library pick: embed + assignment = ONE step; the default pick stores None
    pm.show_properties([sr.node])
    m = len(ms._undo_stack)
    _pick(pm, "LibHead (Library)")
    assert "lib-head-1" in ms._block_definitions and sr.symbol_block == "lib-head-1"
    assert len(ms._undo_stack) == m + 1
    pm.show_properties([sr.node])
    _pick(pm, "Sprinkler0 (System)")
    assert sr.symbol_block is None                          # sparse: the default is None
    pm.show_properties([])
    pm._refresh_timer.stop()


def test_g2_water_supply_row_lists_only_water_supply_symbols(qapp, real_system_library):
    _library(block_library_dir())
    ms = scene()
    ws = water_supply(ms)
    ms.push_undo_state()
    row = ws.get_properties()["Symbol"]
    assert row["options"] == ["Water Supply (System)", "LibWS (Library)"]
    assert row["value"] == "Water Supply (System)"
    assert WS_FILL in names(render(ms, RECT))
    pm = PropertyManager()
    pm.show_properties([ws])
    n = len(ms._undo_stack)
    _pick(pm, "LibWS (Library)")
    assert len(ms._undo_stack) == n + 1
    assert ws.symbol_block == "lib-ws-1" and ws.definition().id == "lib-ws-1"
    assert WS_FILL not in names(render(ms, RECT))           # a line-only user symbol
    ms.undo()
    assert ms.water_supply_node.symbol_block is None
    pm.show_properties([])
    pm._refresh_timer.stop()


def test_template_row_pick_reaches_the_next_head(qapp, real_system_library):
    ms = scene()
    tmpl = Sprinkler(None)
    tmpl._scene_ref = ms                                    # what the placement controller sets
    pm = PropertyManager()
    pm.show_properties([tmpl])
    _pick(pm, "Sprinkler1 (System)")
    assert tmpl.symbol_block == SPR_IDS[1]
    n = ms.add_node(0.0, 0.0)
    assert ms.add_sprinkler(n, tmpl).symbol_block == SPR_IDS[1]
    pm.show_properties([])
    pm._refresh_timer.stop()


def test_row_keeps_a_missing_id_and_mixed_select_is_a_no_op(qapp, real_system_library):
    ms = scene()
    _na, a = head(ms)
    _nb, b = head(ms, 3000.0, 0.0)
    a.symbol_block = "gone-1"
    row = a.get_properties()["Symbol"]
    assert row["value"] == "gone-1 (missing)" and "gone-1 (missing)" in row["options"]
    pm = PropertyManager()
    pm.show_properties([a.node, b.node])
    combo = pm._prop_widgets["Symbol"]
    assert combo.currentText() == "< mixed >"
    pm._apply_property("Symbol", "< mixed >")              # a stale / mixed label: no-op
    pm._refresh_timer.stop()
    assert a.symbol_block == "gone-1" and b.symbol_block is None
    pm.show_properties([])


def test_symbol_row_is_never_saved_as_a_property_and_a_template_copy_carries_the_id(
        qapp, tmp_path, real_system_library):
    """T11's SYMBOL_ROW_KEY filters (network_codec.sprinkler_props and
    Sprinkler.set_properties) were unproven until the row existed."""
    ms = scene()
    _n, spr = head(ms)
    spr.set_symbol_block(SPR_IDS[2])
    f = tmp_path / "t.fpd"
    assert ms.save_to_file(str(f), backup=False)
    rec = next(n["sprinkler"] for n in json.loads(f.read_text(encoding="utf-8"))["nodes"]
               if n["sprinkler"])
    assert "Symbol" not in rec                              # the view label is not stored
    assert rec[SYMBOL_KEY] == SPR_IDS[2]                    # the id is, sparsely
    # template copy: the row's label must not be replayed, the id must travel
    tmpl = Sprinkler(None)
    tmpl._scene_ref = ms
    tmpl.symbol_block = SPR_IDS[1]
    _n2, other = head(ms, 3000.0, 0.0)
    ms.push_undo_state()
    steps = len(ms._undo_stack)
    other.set_properties(tmpl)
    assert other.symbol_block == SPR_IDS[1]
    assert len(ms._undo_stack) == steps          # a copy replays no Symbol pick (no undo step)
