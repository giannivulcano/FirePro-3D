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


# -- Review round: project-scene geometry, refusal message, more holders ----

def _plan_line_scene():
    """A weight referenced ONLY by a styled LineItem in the project scene."""
    ms = Model_Space()
    ln = LineItem(QPointF(0, 0), QPointF(10, 0)); ln.style["weight"] = "A"
    ms.addItem(ln); ms._draw_lines.append(ln)
    return ms, ln


def test_plan_geometry_weight_is_in_use(qapp):
    ms, _ln = _plan_line_scene()
    d = DisplayManager(ms, active_context="paper")
    assert d._line_weight_in_use("A")
    row = [x.name for x in d._lw_defs].index("A")
    d._lw_table.setCurrentCell(row, 0)
    n = len(d._lw_defs)
    d._on_lw_remove()                                  # refused
    assert len(d._lw_defs) == n and "A" in [x.name for x in d._lw_defs]
    d.reject()


def test_plan_geometry_follows_rename(qapp):
    ms, ln = _plan_line_scene()
    _dm_rename(ms, "A", "B").accept()
    assert ln.style["weight"] == "B"


def _spy_tooltip(monkeypatch):
    from PyQt6.QtWidgets import QToolTip
    calls = []
    monkeypatch.setattr(QToolTip, "showText",
                        staticmethod(lambda *a, **k: calls.append(a)))
    return calls


def test_hijack_refusal_shows_message(qapp, monkeypatch):
    calls = _spy_tooltip(monkeypatch)
    ms, _defn, _t = _scene()
    d = _dm_rename(ms, "A", "B")
    assert calls == []
    row = [x.name for x in d._lw_defs].index("Heavy")
    d._lw_table.item(row, 0).setText("A")              # hijack -> refused
    assert len(calls) == 1
    assert calls[0][1] == ("“A” was renamed to “B” in this "
                           "project — choose another name")
    calls.clear()
    row = [x.name for x in d._lw_defs].index("B")
    d._lw_table.item(row, 0).setText("A")              # rename-back: no message
    assert calls == []
    d.reject()


def test_block_editor_undo_across_rename(qapp):
    ms, defn, _t = _scene()
    ed = BlockEditorWidget(ms, block_id=defn.id)
    ed.seed_from_dicts(defn.primitives)               # baseline snapshot (A)
    es = ed.editor_scene
    ms._editor_scenes_provider = lambda: [es]
    _dm_rename(ms, "A", "B").accept()
    es.push_undo_state(); es.undo()
    ln, tx = es._draw_lines[0], es._texts[0]
    assert pd.resolve_line_weight_mm(ln.style["weight"]) == pytest.approx(0.40)
    assert pd.resolve_line_weight_mm(tx._data.border_weight) == pytest.approx(0.40)
    assert ln.to_dict()["style"]["weight"] == "B"
    assert tx.to_dict()["border_weight"] == "B"


def test_paper_delete_undo_across_rename(qapp):
    from firepro3d.paper_commands import (DeleteTextAnnotationCommand,
                                          _find_text_item)
    from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
    scene = PaperScene(Sheet.create_default(),
                       ViewResolver(None, None, None, None))
    data = TextAnnotationData(text="S", border=True, border_weight="A")
    scene._do_add_annotation(data)
    cmd = DeleteTextAnnotationCommand(scene, data)
    cmd.redo()
    _dm_rename(Model_Space(), "A", "B").accept()
    cmd.undo()
    assert _find_text_item(scene, data) is not None
    assert pd.resolve_line_weight_mm(data.border_weight) == pytest.approx(0.40)
    assert data.to_dict()["border_weight"] == "B"


def _json_weights(node, out):
    """Collect every ``border_weight`` and ``style.weight`` value in a JSON tree."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "border_weight":
                out.append(v)
            elif k == "style" and isinstance(v, dict) and "weight" in v:
                out.append(v["weight"])
            _json_weights(v, out)
    elif isinstance(node, list):
        for v in node:
            _json_weights(v, out)
    return out


def test_fpd_save_writes_new_names(qapp, tmp_path):
    """.fpd save after a DM rename: the definition's text + line style save
    as B and the alias map is persisted. (Standalone model texts are not
    written to .fpd under containment C8, so they are not a .fpd holder.)"""
    import json
    ms, defn, _t = _scene()
    _dm_rename(ms, "A", "B").accept()
    path = tmp_path / "p.fpd"
    ms.save_to_file(str(path))
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["paper_display"]["line_weight_aliases"] == {"A": "B"}
    prims = doc["block_definitions"][defn.id]["primitives"]
    assert prims[0]["style"]["weight"] == "B"
    assert prims[1]["border_weight"] == "B"
    assert "A" not in _json_weights(doc, [])


def test_text_paste_of_pre_rename_copy(qapp):
    """Copy (the Ctrl+C write) before the rename, paste after."""
    ms = Model_Space()
    t = TextItem(TextAnnotationData(text="P", border=True, border_weight="A"))
    ms.addItem(t); ms._texts.append(t)
    assert ms._modify_ctl.write_clipboard([t], QPointF(0, 0)) == 1
    _dm_rename(ms, "A", "B").accept()
    new = ms.paste_items(QPointF(0, 50))
    pasted = [i for i in new if isinstance(i, TextItem)]
    assert pasted and pasted[0]._data.border_weight == "B"


def test_library_replace_after_rename(qapp):
    from firepro3d import block_library
    _ms, defn, _t = _scene()
    path = block_library.save_to_library(defn)
    _dm_rename(Model_Space(), "A", "B").accept()
    sc = Model_Space()
    sc.load_blocks_from_files([path])
    assert "A" not in pd.weight_names()
    prims = sc.block_registry.get(defn.id).primitives
    assert prims[0]["style"]["weight"] == "B"
    assert prims[1]["border_weight"] == "B"


# -- VC9 seam fix round ------------------------------------------------------

def _project_b_file(tmp_path):
    """Save project B: live "Heavy", no aliases, a definition whose line
    style and text primitive both name "Heavy"."""
    pd.set_project_line_weights(list(pd.FACTORY_LINE_WEIGHTS))
    pd.set_weight_aliases({})
    ms = Model_Space()
    ln = LineItem(QPointF(0, 0), QPointF(10, 0)); ln.style["weight"] = "Heavy"
    txt = TextItem(TextAnnotationData(text="T", border=True,
                                      border_weight="Heavy")).to_dict()
    defn = BlockDefinition.new(name="D", library="L", series="S",
                               primitives=[ln.to_dict(), txt], origin=(0, 0))
    ms.register_block_definition(defn)
    path = tmp_path / "b.fpd"
    ms.save_to_file(str(path))
    return path, defn.id


def test_open_ignores_previous_project_aliases(qapp, tmp_path):
    """C1: after renaming Heavy -> Bold in project A, opening project B
    (live Heavy) keeps B's names -- they resolve to Heavy's mm and re-save as
    Heavy (main._apply_loaded_file order: load_from_file, then paper apply)."""
    import json
    path, did = _project_b_file(tmp_path)
    _rename("Heavy", "Bold")                           # session = project A
    assert pd.weight_aliases() == {"Heavy": "Bold"}
    ms2 = Model_Space()
    ms2.load_from_file(str(path))
    pd.apply_paper_display_from_project(ms2._loaded_paper_display)
    prims = ms2.block_registry.get(did).primitives
    assert prims[0]["style"]["weight"] == "Heavy"
    assert prims[1]["border_weight"] == "Heavy"
    heavy_mm = dict((d.name, d.width_mm) for d in pd.FACTORY_LINE_WEIGHTS)["Heavy"]
    assert pd.resolve_line_weight_mm(prims[0]["style"]["weight"]) == pytest.approx(heavy_mm)
    out = tmp_path / "b2.fpd"
    ms2.save_to_file(str(out))
    saved = json.loads(out.read_text(encoding="utf-8"))["block_definitions"][did]
    assert saved["primitives"][0]["style"]["weight"] == "Heavy"
    assert saved["primitives"][1]["border_weight"] == "Heavy"


def test_open_installs_file_aliases_whose_key_is_live_in_previous_table(qapp, tmp_path):
    """M3 order (load path): the file's alias key may be a live row of the
    PREVIOUS project's table -- it must survive (pruned against the file's
    table, which is installed first)."""
    _rename("Heavy", "Bold")                           # project C: Heavy -> Bold
    ms = Model_Space()
    path = tmp_path / "c.fpd"
    ms.save_to_file(str(path))
    pd.set_project_line_weights(list(pd.FACTORY_LINE_WEIGHTS))   # session: live Heavy
    pd.set_weight_aliases({})
    Model_Space().load_from_file(str(path))
    assert pd.weight_aliases() == {"Heavy": "Bold"}
    assert pd.canonical_weight_name("Heavy") == "Bold"


def test_set_weight_aliases_drops_live_name_keys(qapp):
    """M3 order (paper apply / Cancel): table first, then aliases -- a
    corrupt alias whose key is a live row never redirects that row."""
    data = {"line_weights": [{"name": d.name, "width_mm": d.width_mm}
                             for d in pd.FACTORY_LINE_WEIGHTS],
            "line_weight_aliases": {"Heavy": "Light", "Gone": "Light"}}
    pd.apply_paper_display_from_project(data)
    assert pd.weight_aliases() == {"Gone": "Light"}
    assert pd.canonical_weight_name("Heavy") == "Heavy"
    # Other order: aliases then table -- set_project_line_weights prunes.
    pd.set_project_line_weights([LineWeightDef("Only", 0.3)])
    pd.set_weight_aliases({"X": "Only"})
    pd.set_project_line_weights([LineWeightDef("Only", 0.3),
                                 LineWeightDef("X", 0.5)])
    assert pd.weight_aliases() == {}


def test_model_blocks_weight_stored_canonical(qapp):
    """I3: an alias-key Blocks weight is stored as its target, so the in-use
    guard protects the target row."""
    _rename("Heavy", "Bold")
    try:
        pd.set_model_blocks_weight("Heavy")
        assert pd.model_blocks_weight() == "Bold"
        d = DisplayManager(Model_Space(), active_context="paper")
        assert d._line_weight_in_use("Bold")
        d.reject()
        # Real Open path: the project display_settings name an alias key.
        from PyQt6.QtCore import QSettings
        from firepro3d.display_manager import apply_project_display_settings
        pd.set_model_blocks_weight(None)
        QSettings("GV", "FirePro3D").remove("display/Blocks/default_line_weight")
        apply_project_display_settings(Model_Space(),
                                       {"Blocks": {"line_weight": "Heavy"}})
        assert pd.model_blocks_weight() == "Bold"
    finally:
        pd.set_model_blocks_weight(None)


@pytest.mark.parametrize("name", ["by_block", "BY_LINETYPE", "By Block",
                                  "by linetype", "Continuous", " continuous "])
def test_reserved_keyword_names_refused(qapp, name):
    """M2: keyword spellings can never become a weight row."""
    assert not pd.validate_line_weight_name(name, pd.project_line_weights())
    ms, _defn, _t = _scene()
    d = _dm_rename(ms, "A", name)                      # real DM edit path
    assert "A" in [x.name for x in d._lw_defs]
    assert name.strip() not in [x.name for x in d._lw_defs]
    d.reject()


def test_ordinary_names_still_valid(qapp):
    assert pd.validate_line_weight_name("Blocky", pd.project_line_weights())
