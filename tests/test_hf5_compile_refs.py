"""HF5 Task 4 -- compile / refs resolve a region record's type."""
from PyQt6.QtCore import QPointF

from firepro3d import fill_types as ft
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_registry import fill_type_refs, prim_refs
from firepro3d.constants import TOKEN_ELEMENT
from firepro3d.fill_layers import BackgroundLayer, FillLayers, PatternLayer
from firepro3d.filled_region import FilledRegionItem
from firepro3d.geometry_2d import LineItem
from firepro3d.hatch_patterns import LEGACY_ALIAS, project_pattern_refs
from firepro3d.model_space import Model_Space
from firepro3d.render_op import FILL, PATTERN

PAT = FillLayers(BackgroundLayer("#ff0000", 1.0), PatternLayer("pat-block", TOKEN_ELEMENT, 1.0, 1.0))


def _region_rec(type_id, color=None):
    a, b, c, d = QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)
    r = FilledRegionItem.from_pieces([[LineItem(a, b), LineItem(b, c), LineItem(c, d), LineItem(d, a)]])
    r.set_fill_type(type_id)
    rec = r.to_dict()
    if color is not None:
        rec["style"]["colour"] = color     # a styled record keeps its colour in style (no "color" key)
    return rec


def _defn(prims):      # tests/test_render_op_compile.py:10
    return BlockDefinition.new(name="T", library="L", series="S",
                               primitives=prims, origin=(0.0, 0.0))


def test_prim_refs_follow_type_to_pattern(qapp):
    ft.set_project_table(ft.FillTypeTable([ft.FillType("t", "T", PAT)]))
    rec = _region_rec("t")
    assert "pat-block" in prim_refs([rec])
    assert fill_type_refs([rec]) == {"t"}


def test_compile_emits_type_layers_with_element_colour(qapp):
    ft.set_project_table(ft.FillTypeTable([ft.FillType("t", "T", PAT)]))
    ops = _defn([_region_rec("t", color="#00ff00")]).render_ops()
    kinds = {o.kind: o for o in ops}
    assert kinds[FILL].colour == "#ff0000"
    assert kinds[PATTERN].tile_ref == "pat-block" and kinds[PATTERN].colour == "#00ff00"


def test_compile_follows_a_type_restyle(qapp):
    t = ft.FillTypeTable([ft.FillType("t", "T", PAT)])
    ft.set_project_table(t)
    defn = _defn([_region_rec("t")])
    assert {o.kind: o for o in defn.render_ops()}[FILL].colour == "#ff0000"
    t.replace(ft.FillType("t", "T", FillLayers(BackgroundLayer("#0000ff", 1.0))))
    ft.notify_changed()
    defn.invalidate_cache()                 # the restyle hook (a later task) calls this
    assert {o.kind: o for o in defn.render_ops()}[FILL].colour == "#0000ff"


def test_project_pattern_refs_include_table_patterns(qapp, model_space):
    ft.set_project_table(ft.FillTypeTable([ft.FillType("t", "T", PAT)]))
    assert "pat-block" in project_pattern_refs(model_space)


def _tile_pair(ms, shipped_hatches):
    """A shipped hatch tile and its user duplicate (tests/test_system_library_retarget.py)."""
    shipped_hatches(ms)
    old = LEGACY_ALIAS["diagonal"]
    assert old in ms._block_definitions
    new = ms.duplicate_block_definition(old)
    return old, new.id


def test_retarget_repoints_table_types_and_typed_overrides(qapp, shipped_hatches):
    ms = Model_Space()
    old, new = _tile_pair(ms, shipped_hatches)
    typed = FillLayers(None, PatternLayer(old, "#000000", 1.0, 1.0))
    ft.set_project_table(ft.FillTypeTable([ft.FillType("t", "T", typed)]))
    # a block definition whose typed region overrides the pattern ref itself
    rec = _region_rec("t")
    rec["fill"] = {"pattern": {"ref": old}}
    d = ms.commit_block_definition(block_id=None, name="Host", library="L", series="S",
                                   primitives=[rec], origin=(0.0, 0.0), place_instance=False)
    assert ms.retarget_block_refs(old, new) >= 1
    assert ft.project_table().get("t").layers.pattern.ref == new
    prim = ms._block_definitions[d.id].primitives[0]
    assert prim["fill_type"] == "t" and prim["fill"] == {"pattern": {"ref": new}}   # stays sparse


def test_project_pattern_refs_follow_a_typed_definition_record(qapp):
    """A typed record's own pattern override is a use the definition walk must find."""
    ms = Model_Space()
    ft.set_project_table(ft.FillTypeTable([ft.FillType("t", "T", FillLayers(BackgroundLayer("#ff0000", 1.0)))]))
    rec = _region_rec("t")
    rec["fill"] = {"pattern": {"ref": "ovr-pat"}}
    ms.commit_block_definition(block_id=None, name="Host", library="L", series="S",
                               primitives=[rec], origin=(0.0, 0.0), place_instance=False)
    assert "ovr-pat" in project_pattern_refs(ms)
