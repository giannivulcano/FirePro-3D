"""SB1b G8 -- Model_Space.retarget_block_refs re-points every holder (D12).

One undo step: after the retarget every holder reads the NEW id, one undo
restores OLD (and the baseline-registered NEW definition stays), redo re-applies.
Holder rows follow the plan's T1 table (H1-H5); H7 (the derived section cache)
is checked on its own. The Display category defaults (H6, app-wide QSettings)
are checked as NOT rewritten.
"""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.block_instance import BlockInstance
from firepro3d.fill_layers import FillLayers, PatternLayer
from firepro3d.floor_slab import FloorSlab
from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.hatch_patterns import LEGACY_ALIAS
from firepro3d.model_space import Model_Space
from firepro3d.wall import WallSegment

SQ = [QPointF(0, 0), QPointF(1000, 0), QPointF(1000, 1000), QPointF(0, 1000)]


def _symbol_pair(ms):
    """A symbol definition and its user duplicate (the D12 situation)."""
    old = ms.commit_block_definition(
        block_id=None, name="Sym", library="Lib", series="S",
        primitives=[LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict()],
        origin=(0.0, 0.0), place_instance=False)
    new = ms.duplicate_block_definition(old.id)
    return old.id, new.id


def _tile_pair(ms, shipped_hatches):
    """A shipped hatch tile and its user duplicate."""
    shipped_hatches(ms)
    old = LEGACY_ALIAS["diagonal"]
    assert old in ms._block_definitions
    new = ms.duplicate_block_definition(old)
    return old, new.id


def _ref_of_prim_fill(prim):
    from firepro3d.fill_layers import pattern_ref
    return pattern_ref(prim.get("fill"))


# Each holder builder returns (old_id, new_id, reader); the reader re-finds the
# live holder every call (undo rebuilds items from the snapshot).

def _holder_instance(ms, shipped_hatches):                      # H1
    old, new = _symbol_pair(ms)
    ms.place_block_instance(old, (0.0, 0.0))

    def read():
        inst = ms._block_instances[0]
        bid = inst.block_id
        # backrefs follow the id (edit-propagation)
        assert inst in ms._block_definitions[bid]._instances
        other = new if bid == old else old
        assert inst not in ms._block_definitions[other]._instances
        return bid
    return old, new, read


def _holder_nested(ms, shipped_hatches):                        # H2
    old, new = _symbol_pair(ms)
    inst = BlockInstance(block_id=old, resolver=ms.get_block_definition)
    host = ms.commit_block_definition(
        block_id=None, name="Host", library="Lib", series="S",
        primitives=[inst.to_nested_dict()], origin=(0.0, 0.0),
        place_instance=False)
    return old, new, lambda: ms._block_definitions[host.id].primitives[0]["block_id"]


def _holder_fill_item(ms, shipped_hatches):                     # H3
    old, new = _tile_pair(ms, shipped_hatches)
    r = RectangleItem(QPointF(0, 0), QPointF(200, 100))
    ms.addItem(r)
    ms._draw_rects.append(r)
    r.set_property("Fill Pattern", PatternLayer(old))
    return old, new, lambda: ms._draw_rects[0].fill_layers.pattern.ref


def _holder_fill_prim(ms, shipped_hatches):                     # H4
    old, new = _tile_pair(ms, shipped_hatches)
    r = RectangleItem(QPointF(0, 0), QPointF(200, 100))
    r.fill_layers = FillLayers(pattern=PatternLayer(old))
    host = ms.commit_block_definition(
        block_id=None, name="HostFill", library="Lib", series="S",
        primitives=[r.to_dict()], origin=(0.0, 0.0), place_instance=False)
    return old, new, lambda: _ref_of_prim_fill(
        ms._block_definitions[host.id].primitives[0])


def _holder_display_override(ms, shipped_hatches):              # H5 (floor)
    old, new = _tile_pair(ms, shipped_hatches)
    slab = FloorSlab(points=SQ)
    ms.addItem(slab)
    ms._floor_slabs.append(slab)
    slab._display_overrides["section_pattern"] = old
    return old, new, lambda: ms._floor_slabs[0]._display_overrides["section_pattern"]


_ROWS = [
    pytest.param(_holder_instance, True, id="H1"),
    pytest.param(_holder_nested, True, id="H2"),
    pytest.param(_holder_fill_item, True, id="H3"),
    pytest.param(_holder_fill_prim, True, id="H4"),
    pytest.param(_holder_display_override, True, id="H5"),
]


@pytest.mark.parametrize("make, undoable", _ROWS)
def test_g8_retarget_and_undo(qapp, shipped_hatches, make, undoable):
    ms = Model_Space()
    old, new, read = make(ms, shipped_hatches)
    ms.push_undo_state()                      # baseline: holders + both ids
    assert read() == old
    steps = len(ms._undo_stack)
    assert ms.retarget_block_refs(old, new) >= 1
    assert read() == new
    assert len(ms._undo_stack) == steps + 1   # exactly ONE undo step
    ms.undo()
    assert read() == old
    assert new in ms._block_definitions       # baseline-registered stays
    ms.redo()
    assert read() == new


def test_g8_wall_override_retargets_but_undo_gap_is_preexisting(qapp, shipped_hatches):
    """H5 for kinds whose override Model_Space undo never restored (P4 probe
    at 55dc0e26: walls, roofs, rooms and 2D geometry lose _display_overrides
    on undo; FloorSlab and network items keep them). The retarget itself
    still covers them."""
    ms = Model_Space()
    old, new = _tile_pair(ms, shipped_hatches)
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0))
    ms.addItem(w)
    ms._walls.append(w)
    w._display_overrides["section_pattern"] = old
    ms.push_undo_state()
    assert ms.retarget_block_refs(old, new) >= 1
    assert ms._walls[0]._display_overrides["section_pattern"] == new


def test_g8_every_holder_in_one_call_is_one_undo_step(qapp, shipped_hatches):
    ms = Model_Space()
    old, new = _tile_pair(ms, shipped_hatches)
    r = RectangleItem(QPointF(0, 0), QPointF(200, 100))
    ms.addItem(r)
    ms._draw_rects.append(r)
    r.fill_layers = FillLayers(pattern=PatternLayer(old))
    slab = FloorSlab(points=SQ)
    ms.addItem(slab)
    ms._floor_slabs.append(slab)
    slab._display_overrides["section_pattern"] = old
    host_prim = RectangleItem(QPointF(0, 0), QPointF(5, 5))
    host_prim.fill_layers = FillLayers(pattern=PatternLayer(old))
    host = ms.commit_block_definition(
        block_id=None, name="H", library="Lib", series="S",
        primitives=[host_prim.to_dict()], origin=(0.0, 0.0), place_instance=False)
    ms.push_undo_state()
    steps = len(ms._undo_stack)
    assert ms.retarget_block_refs(old, new) == 3
    assert len(ms._undo_stack) == steps + 1
    ms.undo()
    assert ms._draw_rects[0].fill_layers.pattern.ref == old
    assert ms._floor_slabs[0]._display_overrides["section_pattern"] == old
    assert _ref_of_prim_fill(ms._block_definitions[host.id].primitives[0]) == old


def test_g8_display_cache_follows_override(qapp, shipped_hatches):
    """H7: the derived item cache is re-derived from the retargeted override."""
    ms = Model_Space()
    old, new = _tile_pair(ms, shipped_hatches)
    slab = FloorSlab(points=SQ)
    ms.addItem(slab)
    ms._floor_slabs.append(slab)
    slab._display_overrides["section_pattern"] = old
    slab._display_section_pattern = old
    ms.push_undo_state()
    ms.retarget_block_refs(old, new)
    assert ms._floor_slabs[0]._display_section_pattern == new


def test_g8_category_defaults_are_not_rewritten(qapp, shipped_hatches):
    """H6: the app-wide Display category default is excluded."""
    from PyQt6.QtCore import QSettings
    ms = Model_Space()
    old, new = _tile_pair(ms, shipped_hatches)
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Floor/default_section_pattern", old)
    slab = FloorSlab(points=SQ)
    ms.addItem(slab)
    ms._floor_slabs.append(slab)
    slab._display_overrides["section_pattern"] = old
    ms.push_undo_state()
    ms.retarget_block_refs(old, new)
    assert s.value("display/Floor/default_section_pattern") == old


def test_g8_unknown_or_same_id_is_a_noop(qapp, shipped_hatches):
    ms = Model_Space()
    old, new = _tile_pair(ms, shipped_hatches)
    r = RectangleItem(QPointF(0, 0), QPointF(200, 100))
    ms.addItem(r)
    ms._draw_rects.append(r)
    r.fill_layers = FillLayers(pattern=PatternLayer(old))
    ms.push_undo_state()
    before = len(ms._undo_stack)
    assert ms.retarget_block_refs(old, old) == 0
    assert ms.retarget_block_refs("nope", new) == 0
    assert ms.retarget_block_refs(old, "nope") == 0
    assert len(ms._undo_stack) == before
    # nothing referenced it: no step either
    assert ms.retarget_block_refs(new, old) == 0
    assert len(ms._undo_stack) == before
    assert ms._draw_rects[0].fill_layers.pattern.ref == old
