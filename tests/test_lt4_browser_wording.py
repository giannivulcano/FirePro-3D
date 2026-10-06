"""LT4 A7 badges (LT4-10) + A8 delete wording (LT4-11e)."""
from PyQt6.QtCore import QPointF

from firepro3d import block_library
from firepro3d.block_definition import BlockDefinition
from firepro3d.blocks_browser import BlocksBrowser
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import make_linetype

_LT_TIP = "Linetype — apply it from a line's Linetype row"
_PAT_TIP = "Pattern block — used by hatch fills; it can't be placed"


def _leaf(tree, name):
    stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    while stack:
        it = stack.pop()
        if it.text(0) == name:
            return it
        stack.extend(it.child(j) for j in range(it.childCount()))
    return None


def _pattern(name):
    return BlockDefinition.new(
        name=name, library="L", series="Hatches", origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()],
        tile={"w": 5.0, "h": 5.0, "row_shift": 0.0, "size": "model"})


def test_a7_badges_project_and_library(qapp, tmp_path):
    ms = Model_Space()
    lt = make_linetype("Hidden")
    ms.register_block_definition(lt)
    lib_lt = make_linetype("Center")
    block_library.save_to_library(lib_lt, root=str(tmp_path))
    br = BlocksBrowser(ms, root=str(tmp_path))
    br.refresh()
    for name in ("Hidden", "Center"):
        leaf = _leaf(br._tree, name)
        assert leaf is not None and not leaf.icon(0).isNull(), name
        assert leaf.toolTip(0).startswith("Linetype — apply it from a line's "
                                          "Linetype row"), name


def test_a7_pattern_badge_on_project_and_library_rows(qapp, tmp_path):
    """LT4-10: patterns are badged on library rows too (index ``tile`` flag);
    a library leaf keeps its path data; a plain library block stays unbadged."""
    ms = Model_Space()
    ms.register_block_definition(_pattern("ProjZig"))
    block_library.save_to_library(_pattern("LibZig"), root=str(tmp_path))
    block_library.save_to_library(BlockDefinition.new(
        name="LibValve", library="L", series="Hatches", origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(0, 0), QPointF(10, 0)).to_dict()]),
        root=str(tmp_path))
    br = BlocksBrowser(ms, root=str(tmp_path))
    br.refresh()
    for name in ("ProjZig", "LibZig"):
        leaf = _leaf(br._tree, name)
        assert leaf is not None and not leaf.icon(0).isNull(), name
        assert leaf.toolTip(0) == _PAT_TIP, name
    lib = _leaf(br._tree, "LibZig")
    assert lib.font(0).italic()
    from firepro3d.blocks_browser import _ROLE_PATH
    assert lib.data(0, _ROLE_PATH)
    plain = _leaf(br._tree, "LibValve")
    assert plain.icon(0).isNull()
    assert plain.toolTip(0).startswith("In the library")


def test_a8_delete_wording_for_linetype_users(qapp):
    ms = Model_Space()
    lt = make_linetype("Hidden")
    ms.register_block_definition(lt)
    for name in ("Valve", "Riser"):
        ln = LineItem(QPointF(0, 0), QPointF(5, 0))
        ln.style["linetype"] = lt.id
        ms.register_block_definition(BlockDefinition.new(
            name=name, library="L", series="S", origin=(0, 0),
            primitives=[ln.to_dict()]))
    assert ms.block_users_message(lt.id) == (
        "“Hidden” is used by lines inside: Riser, Valve — change their "
        "linetype first.")


def test_a8_linetype_nested_by_a_block_keeps_nesting_wording(qapp):
    """LT4-11e: nesting users keep "explode or remove it there"."""
    ms = Model_Space()
    lt = make_linetype("Hidden")
    ms.register_block_definition(lt)
    ms.register_block_definition(BlockDefinition.new(
        name="Host", library="L", series="S", origin=(0, 0),
        primitives=[{"type": "block_instance", "block_id": lt.id,
                     "x": 0.0, "y": 0.0}]))
    assert ms.block_users_message(lt.id) == (
        "“Hidden” is used inside: Host — explode or remove it there first.")
