"""LT2-8 / H-g -- weight rename aliases (unit half; holder guards are Task 9)."""
import pytest

from firepro3d import paper_display as pd
from firepro3d.paper_display import LineWeightDef


@pytest.fixture(autouse=True)
def _table():
    pd.set_project_line_weights([*pd.FACTORY_LINE_WEIGHTS,
                                 LineWeightDef("A", 0.40)])
    pd.set_weight_aliases({})
    yield
    pd.set_weight_aliases({})
    pd.reset_project_line_weights()


def _rename(old, new):
    defs = [LineWeightDef(new if d.name == old else d.name, d.width_mm)
            for d in pd.project_line_weights()]
    pd.set_project_line_weights(defs)
    pd.record_weight_rename(old, new)


def test_old_name_resolves_to_renamed_width():
    _rename("A", "B")
    assert pd.canonical_weight_name("A") == "B"
    assert pd.resolve_line_weight_mm("A") == pytest.approx(0.40)


def test_chain_collapses_and_rename_back_drops_alias():
    _rename("A", "B")
    _rename("B", "C")
    assert pd.weight_aliases() == {"A": "C", "B": "C"}
    _rename("C", "A")
    assert pd.canonical_weight_name("A") == "A"
    assert pd.canonical_weight_name("B") == "A"
    assert "A" not in pd.weight_aliases()


def test_cycle_guard_terminates():
    pd.set_weight_aliases({"X": "Y", "Y": "X"})
    assert pd.canonical_weight_name("X") == "X"


def test_aliases_persist_and_reset():
    _rename("A", "B")
    data = pd.get_paper_display_for_save()
    assert data["line_weight_aliases"] == {"A": "B"}
    pd.set_weight_aliases({})
    pd.apply_paper_display_from_project(data)
    assert pd.weight_aliases() == {"A": "B"}
    pd.reset_project_line_weights()
    assert pd.weight_aliases() == {}


def test_merge_does_not_readd_an_alias_key():
    _rename("A", "B")
    assert pd.merge_project_line_weights({"A": 0.99}) == []
    assert "A" not in pd.weight_names()


def test_model_blocks_weight_default_light():
    pd.set_model_blocks_weight(None)
    assert pd.model_blocks_weight() == "Light"
    pd.set_model_blocks_weight("Heavy")
    assert pd.model_blocks_weight() == "Heavy"
    pd.set_model_blocks_weight(None)


def test_new_live_row_named_like_an_alias_key_wins():
    _rename("A", "B")
    pd.set_project_line_weights([*pd.project_line_weights(),
                                 LineWeightDef("A", 0.77)])
    assert pd.canonical_weight_name("A") == "A"
    assert pd.resolve_line_weight_mm("A") == pytest.approx(0.77)
    assert pd.resolve_line_weight_mm("B") == pytest.approx(0.40)


def test_apply_none_clears_aliases():
    _rename("A", "B")
    pd.apply_paper_display_from_project(None)
    assert pd.weight_aliases() == {}


# -- Holder guards (Task 9): every live holder follows a DM rename -----------

from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_editor import BlockEditorWidget
from firepro3d.display_manager import DisplayManager
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.text_item import TextAnnotationData, TextItem


def _scene():
    ms = Model_Space()
    ln = LineItem(QPointF(0, 0), QPointF(10, 0)); ln.style["weight"] = "A"
    txt = TextItem(TextAnnotationData(text="T", border=True,
                                      border_weight="A")).to_dict()
    defn = BlockDefinition.new(name="D", library="L", series="S",
                               primitives=[ln.to_dict(), txt], origin=(0, 0))
    ms.register_block_definition(defn)
    t = TextItem(TextAnnotationData(text="M", border=True, border_weight="A"))
    ms.addItem(t); ms._texts.append(t)
    return ms, defn, t


def _dm_rename(ms, old, new):
    d = DisplayManager(ms, active_context="paper")
    row = [x.name for x in d._lw_defs].index(old)
    d._lw_table.item(row, 0).setText(new)
    return d


def test_definition_style_and_text_follow_rename(qapp):
    ms, defn, _t = _scene()
    _dm_rename(ms, "A", "B").accept()
    prims = ms.block_registry.get(defn.id).primitives
    assert prims[0]["style"]["weight"] == "B"
    assert prims[1]["border_weight"] == "B"


def test_open_block_editor_follows_rename(qapp):
    ms, defn, _t = _scene()
    ed = BlockEditorWidget(ms, block_id=defn.id)
    ed.seed_from_dicts(defn.primitives)
    ms._editor_scenes_provider = lambda: [ed.editor_scene]
    _dm_rename(ms, "A", "B").accept()
    assert ed.editor_scene._draw_lines[0].style["weight"] == "B"
    assert ed.editor_scene._texts[0]._data.border_weight == "B"


def test_manager_registers_editor_provider(qapp):
    """BlockEditorManager wires the provider the rename walker reads."""
    from PyQt6.QtWidgets import QTabWidget
    from firepro3d.block_editor import BlockEditorManager
    ms, defn, _t = _scene()
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, ms)
    ed = mgr.edit_definition(defn.id)
    assert ms._editor_scenes_provider() == [ed.editor_scene]
    _dm_rename(ms, "A", "B").accept()
    assert ed.editor_scene._draw_lines[0].style["weight"] == "B"


def test_model_undo_across_rename_draws_and_saves_new(qapp):
    ms, _defn, t = _scene()
    ms.push_undo_state()
    _dm_rename(ms, "A", "B").accept()
    ms.push_undo_state(); ms.undo()
    nm = ms._texts[0]._data.border_weight
    assert pd.resolve_line_weight_mm(nm) == pytest.approx(0.40)
    assert ms._texts[0].to_dict()["border_weight"] == "B"


def test_paste_of_pre_rename_record(qapp):
    ln = LineItem(QPointF(0, 0), QPointF(10, 0)); ln.style["weight"] = "A"
    rec = ln.to_dict()
    _rename("A", "B")
    assert LineItem.from_dict(rec).style["weight"] == "B"


def test_cancel_restores_names_and_aliases(qapp):
    ms, defn, _t = _scene()
    d = _dm_rename(ms, "A", "B")
    assert pd.weight_aliases() == {"A": "B"}
    d.reject()
    assert pd.weight_aliases() == {}
    assert ms.block_registry.get(defn.id).primitives[0]["style"]["weight"] == "A"
    assert "A" in pd.weight_names()


def test_model_blocks_weight_follows_rename_and_cancel(qapp):
    pd.set_model_blocks_weight("A")
    try:
        ms, _defn, _t = _scene()
        d = _dm_rename(ms, "A", "B")
        assert pd.model_blocks_weight() == "B"
        d.reject()
        assert pd.model_blocks_weight() == "A"
    finally:
        pd.set_model_blocks_weight(None)


def test_new_weight_cannot_hijack_an_alias_key(qapp):
    ms, _defn, _t = _scene()
    d = _dm_rename(ms, "A", "B")
    row = [x.name for x in d._lw_defs].index("Heavy")
    d._lw_table.item(row, 0).setText("A")              # refused
    assert "Heavy" in [x.name for x in d._lw_defs]
    row = [x.name for x in d._lw_defs].index("B")
    d._lw_table.item(row, 0).setText("A")              # renaming back is fine
    assert "A" in [x.name for x in d._lw_defs]
    d.accept()


def test_add_skips_alias_key_names(qapp):
    ms, _defn, _t = _scene()
    d = DisplayManager(ms, active_context="paper")
    nxt = f"Custom {len(d._lw_defs) + 1}"
    pd.set_weight_aliases({nxt: "Heavy"})
    d._on_lw_add()
    assert nxt not in [x.name for x in d._lw_defs]
    d.reject()


def test_fpdb_bundles_canonical_names(qapp):
    from firepro3d.block_library import used_weight_names
    ln = LineItem(QPointF(0, 0), QPointF(10, 0)); ln.style["weight"] = "A"
    _rename("A", "B")
    assert used_weight_names([{"primitives": [ln.to_dict()]}]) == {"B"}
    raw = {"primitives": [{"type": "draw_line", "style": {"weight": "A"}}]}
    assert used_weight_names([raw]) == {"B"}


def test_in_use_counts_style_weights(qapp):
    """Only a definition stroke's style.weight references A -> in use."""
    ms = Model_Space()
    ln = LineItem(QPointF(0, 0), QPointF(10, 0)); ln.style["weight"] = "A"
    ms.register_block_definition(BlockDefinition.new(
        name="D", library="L", series="S", primitives=[ln.to_dict()],
        origin=(0, 0)))
    d = DisplayManager(ms, active_context="paper")
    assert d._line_weight_in_use("A")
    assert not d._line_weight_in_use("Very Heavy")
    d.reject()


def test_in_use_counts_model_blocks_weight(qapp):
    pd.set_model_blocks_weight("A")
    try:
        d = DisplayManager(Model_Space(), active_context="paper")
        assert d._line_weight_in_use("A")
        d.reject()
    finally:
        pd.set_model_blocks_weight(None)


def test_definition_text_alias_key_loads_canonical(qapp):
    """A stored text primitive whose border_weight is an alias key loads as
    the canonical name (BlockDefinition.from_dict, H-g)."""
    _ms, defn, _t = _scene()
    rec = defn.to_dict()
    _rename("A", "B")
    loaded = BlockDefinition.from_dict(rec)
    texts = [p for p in loaded.primitives if p.get("type") == "text"]
    assert texts and texts[0]["border_weight"] == "B"


def test_paper_format_undo_across_rename_resolves_new(qapp):
    """FormatTextCommand restores the old name; it still draws at B and saves as B."""
    from firepro3d.paper_commands import FormatTextCommand
    from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
    scene = PaperScene(Sheet.create_default(),
                       ViewResolver(None, None, None, None))
    data = TextAnnotationData(text="S", border=True, border_weight="A")
    scene._do_add_annotation(data)
    cmd = FormatTextCommand(scene, data, {"border_weight": "A"},
                            {"border_weight": "Medium"})
    cmd.redo()
    _rename("A", "B")
    cmd.undo()
    assert pd.resolve_line_weight_mm(data.border_weight) == pytest.approx(0.40)
    assert data.to_dict()["border_weight"] == "B"
