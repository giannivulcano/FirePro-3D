"""SV2 Task 6 -- G5 delete refusals (schematics.md D-S11a / D-S11b)."""
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.paper_space import Sheet, SheetViewData


def _setup():
    ms = Model_Space()
    sym = BlockDefinition.new(
        name="Sym", library="L", series="S",
        primitives=[LineItem(QPointF(0, 0), QPointF(0, 40)).to_dict()],
        origin=(0.0, 0.0))
    ms.register_block_definition(sym)
    sch = BlockDefinition.new(
        name="Riser", library="", series="",
        primitives=[{"type": "block_instance", "block_id": sym.id,
                     "pos": [0.0, 0.0], "rotation": 0.0}],
        origin=(0.0, 0.0), kind="schematic")
    ms.register_block_definition(sch)
    sheets = []
    for num in ("FP-1.0", "FP-2.0", "FP-5.0"):
        s = Sheet.create_default()
        s.number = num
        sheets.append(s)
    ms._sheets = sheets
    return ms, sym, sch, sheets


def _vp(block_id):
    return SheetViewData("schematic", block_id, "", 0.0, 10, 10, 50, 50)


def test_placed_schematic_delete_refused_naming_sheets(qapp):
    ms, sym, sch, sheets = _setup()
    sheets[1].sheet_views = [_vp(sch.id)]
    sheets[2].sheet_views = [_vp(sch.id), _vp(sch.id)]
    assert ms.schematic_sheet_users(sch.id) == ["FP-2.0", "FP-5.0"]
    assert ms.delete_block_definition(sch.id) is False
    assert ms.get_block_definition(sch.id) is not None
    msg = ms.block_users_message(sch.id)
    assert msg == ("“Riser” is used on sheets FP-2.0, FP-5.0"
                   " — remove its viewports first.")


def test_unplaced_schematic_deletes(qapp):
    ms, sym, sch, sheets = _setup()
    sheets[0].sheet_views = [SheetViewData("plan", sch.id, "", 0.0, 0, 0, 9, 9)]
    assert ms.schematic_sheet_users(sch.id) == []     # a plan named the same: no
    assert ms.delete_block_definition(sch.id) is True


def test_block_nested_in_schematic_refused_naming_it(qapp):
    ms, sym, sch, sheets = _setup()
    assert ms.delete_block_definition(sym.id) is False
    assert "Riser" in ms.block_users_message(sym.id)
