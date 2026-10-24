"""HF5 Task 9 -- a pattern block a Fill Type tiles cannot be deleted (AC8, D-A15)."""
from dataclasses import replace

from PyQt6.QtCore import QPointF

from firepro3d import fill_types as ft
from firepro3d.block_definition import BlockDefinition
from firepro3d.fill_layers import BackgroundLayer, FillLayers, PatternLayer
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space

_DASH = "\u2014"


def _tile(name="Zig"):
    return BlockDefinition.new(
        name=name, library="L", series="S", origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()],
        tile={"w": 5.0, "h": 5.0, "row_shift": 0.0, "size": "model"})


def _typed(ms, ref, name="Concrete"):
    t = ft.FillType(ft.new_id(), name, FillLayers(None, PatternLayer(ref, "#000000", 1.0, 1.0)))
    ft.project_table().add(t)
    return t


def test_pattern_users_sorted_names(qapp):
    ms = Model_Space()
    d = _tile()
    ms.register_block_definition(d)
    _typed(ms, d.id, "b type")
    _typed(ms, d.id, "A type")
    _typed(ms, "other-block", "Elsewhere")
    assert ft.pattern_users(d.id) == ["A type", "b type"]
    assert ft.pattern_users("nobody") == []


def test_delete_refused_while_a_fill_type_uses_the_pattern(qapp):
    ms = Model_Space()
    d = _tile()
    ms.register_block_definition(d)
    t = _typed(ms, d.id)
    assert ms.delete_block_definition(d.id) is False
    assert d.id in ms._block_definitions
    assert ms.block_users_message(d.id) == (
        f"\u201cZig\u201d is used by Fill Types: Concrete {_DASH} change their pattern first.")
    # the pattern switched off in the type: the delete goes through
    ft.project_table().replace(replace(t, layers=FillLayers(BackgroundLayer("#000000", 1.0))))
    assert ms.block_users_message(d.id) is None
    assert ms.delete_block_definition(d.id) is True
    assert d.id not in ms._block_definitions


def test_message_joins_the_nesting_clause(qapp):
    ms = Model_Space()
    d = _tile()
    host = BlockDefinition.new(
        name="Host", library="L", series="S", origin=(0.0, 0.0),
        primitives=[{"type": "block_instance", "block_id": d.id, "pos": [0, 0], "rotation": 0.0}])
    ms.register_block_definition(d)
    ms.register_block_definition(host)
    _typed(ms, d.id)
    assert ms.block_users_message(d.id) == (
        f"\u201cZig\u201d is used inside: Host, and by Fill Types: Concrete"
        f" {_DASH} explode or remove it there, and change their pattern first.")


def test_block_manager_delete_shows_the_fill_type_message(qapp, monkeypatch):
    import firepro3d.themed_message as tm
    from firepro3d.block_manager import BlockManagerDialog
    ms = Model_Space()
    d = _tile()
    ms.register_block_definition(d)
    _typed(ms, d.id)
    shown = []
    monkeypatch.setattr(tm, "themed_info", lambda *args, **k: shown.append(args))

    class _MW:
        settings = None
    dlg = BlockManagerDialog(ms, _MW(), apply_stylesheet=False)
    try:
        row = dlg.model.row_for_id(d.id)
        dlg.view.setCurrentIndex(dlg.proxy.mapFromSource(dlg.model.index(row, 0)))
        dlg._delete()
        assert d.id in ms._block_definitions
        assert shown and "Fill Types: Concrete" in shown[-1][2]
        assert shown[-1][2] == ms.block_users_message(d.id)
    finally:
        dlg.close()


def test_legacy_name_ref_counts_through_the_canonical_alias(qapp):
    """A type whose pattern is stored as a legacy name still counts for the
    shipped block's frozen id (alias-aware, Group B carry-in)."""
    from firepro3d.hatch_patterns import LEGACY_ALIAS
    ms = Model_Space()
    _typed(ms, "diagonal")
    assert ft.pattern_users(LEGACY_ALIAS["diagonal"]) == ["Concrete"]
