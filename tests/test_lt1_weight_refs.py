"""LT1-5 -- weights used by sheet / block-definition texts can't be removed;
renames follow them (guard T5)."""
from firepro3d import paper_display as pd
from firepro3d.block_definition import BlockDefinition
from firepro3d.display_manager import DisplayManager
from firepro3d.level_manager import LevelManager, PlanViewManager
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import LineWeightDef
from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
from firepro3d.text_item import TextAnnotationData, TextItem
from tests._paper_iso_helpers import _DetailMgrStub


def _scene_with_refs():
    pd.set_project_line_weights([*pd.FACTORY_LINE_WEIGHTS,
                                 LineWeightDef("SheetW", 0.41),
                                 LineWeightDef("DefW", 0.42)])
    ms = Model_Space()
    sheet = Sheet.create_default()
    sheet.annotations.append(TextAnnotationData(text="S", border=True,
                                                border_weight="SheetW"))
    ms._sheets = [sheet]
    prim = TextItem(TextAnnotationData(text="D", border=True,
                                       border_weight="DefW")).to_dict()
    defn = BlockDefinition.new(name="T", library="L", series="S",
                               primitives=[prim], origin=(0.0, 0.0))
    ms.register_block_definition(defn)
    return ms, sheet, defn


def _row(d, name):
    return [x.name for x in d._lw_defs].index(name)


def _rename(d, old, new):
    d._lw_table.item(_row(d, old), 0).setText(new)


def test_remove_refused_for_sheet_and_definition_text(qapp):
    ms, _sheet, _defn = _scene_with_refs()
    d = DisplayManager(ms, active_context="paper")
    for name in ("SheetW", "DefW"):
        d._lw_table.setCurrentCell(_row(d, name), 0)
        d._on_lw_remove()
        assert name in pd.weight_names()


def test_rename_follows_sheet_and_definition_text(qapp):
    ms, sheet, defn = _scene_with_refs()
    d = DisplayManager(ms, active_context="paper")
    _rename(d, "SheetW", "SheetW2")
    _rename(d, "DefW", "DefW2")
    assert sheet.annotations[0].border_weight == "SheetW2"
    assert ms.block_registry.get(defn.id).primitives[0]["border_weight"] == "DefW2"


def test_cancel_restores_text_references(qapp):
    ms, sheet, defn = _scene_with_refs()
    d = DisplayManager(ms, active_context="paper")
    _rename(d, "SheetW", "SheetW2")
    _rename(d, "DefW", "DefW2")
    d.reject()
    assert sheet.annotations[0].border_weight == "SheetW"
    assert ms.block_registry.get(defn.id).primitives[0]["border_weight"] == "DefW"


def test_live_paper_text_border_keeps_width_after_rename(qapp):
    ms, sheet, _defn = _scene_with_refs()
    lm = LevelManager()
    pvm = PlanViewManager()
    pvm.create("Level 1", lm)
    resolver = ViewResolver(ms, pvm, _DetailMgrStub(), None, level_manager=lm)
    paper = PaperScene(sheet, resolver)
    item = paper._annotations[0]
    assert item._data is sheet.annotations[0]
    assert abs(item._frame_pen().widthF() * (item.scale() or 1.0) - 0.41) < 1e-6
    d = DisplayManager(ms, active_context="paper")
    _rename(d, "SheetW", "SheetW2")
    pen_mm = item._frame_pen().widthF() * (item.scale() or 1.0)
    assert abs(pen_mm - 0.41) < 1e-6      # not the 0.25 mm fallback
