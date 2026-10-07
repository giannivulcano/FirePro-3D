"""WM2 G10 -- overrides are full references (Q8)."""
import json

from firepro3d import block_library
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_library import used_weight_names
from firepro3d.block_registry import linetype_users_in, prim_refs
from tests.lt3_support import make_linetype
from tests.wm2_support import nested_record, scene_with, sprinkler_def


def test_record_linetype_override_is_a_dependency(qapp):
    lt = make_linetype()
    s = sprinkler_def()
    rec = nested_record(s.id, {"linetype": lt.id, "weight": "Thick"})
    assert prim_refs([rec]) == {s.id, lt.id}
    assert used_weight_names([{"primitives": [rec]}]) == {"Thick"}


def test_fpdb_bundles_record_override_linetype(qapp, tmp_path):
    lt = make_linetype()
    s = sprinkler_def()
    h = BlockDefinition.new(name="H", library="L", series="S",
                            primitives=[nested_record(s.id, {"linetype": lt.id})],
                            origin=(0.0, 0.0))
    ms, _inst = scene_with([lt, s, h], h.id)
    path = block_library.save_to_library(
        h, root=str(tmp_path), bundled=ms.block_registry.bundle_for(h.id))
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    assert set(data["bundled"]) == {s.id, lt.id}


def test_placement_override_blocks_linetype_delete(qapp):
    lt = make_linetype()
    s = sprinkler_def()
    ms, inst = scene_with([lt, s], s.id, {"linetype": lt.id})
    assert inst in linetype_users_in(ms, lt.id)
    assert ms.block_users_message(lt.id) is not None


def test_weight_rename_follows_placement_and_record(qapp):
    from firepro3d.display_manager import DisplayManager
    s = sprinkler_def()
    h = BlockDefinition.new(name="H", library="L", series="S",
                            primitives=[nested_record(s.id, {"weight": "Thick"})],
                            origin=(0.0, 0.0))
    ms, inst = scene_with([s, h], h.id, {"weight": "Thick"})
    dm = DisplayManager(ms)
    assert dm._line_weight_in_use("Thick")
    dm._propagate_lw_rename("Thick", "Bold")
    assert inst.overrides["weight"] == "Bold"
    rec = ms.get_block_definition(h.id).primitives[0]
    assert rec["overrides"]["weight"] == "Bold"
