"""LT1-6 -- every weight picker lists the live project table by width (guard T8)."""
from PyQt6.QtCore import QModelIndex, QPoint
from PyQt6.QtWidgets import QMenu

from firepro3d import paper_display as pd
from firepro3d.paper_display import LineWeightDef
from firepro3d.text_item import TextAnnotationData, TextItem


def _table():
    pd.set_project_line_weights([*pd.FACTORY_LINE_WEIGHTS,
                                 LineWeightDef("Site", 0.40)])


def _check_options(opts):
    assert opts == pd.weight_names()
    assert opts.index("Site") == opts.index("Heavy") + 1  # 0.35 < 0.40 < 0.50


def test_text_item_property_options_include_custom(qapp):
    _table()
    item = TextItem(TextAnnotationData(text="A", border=True))
    _check_options(list(item.get_properties()["Border Weight"]["options"]))


def test_paper_text_panel_options_include_custom(qapp):
    _table()
    from firepro3d.paper_space import _text_panel_properties
    d = TextAnnotationData(text="A", border=True)
    _check_options(list(_text_panel_properties(d)["Border Weight"]["options"]))


def test_frame_group_combo_lists_custom(qapp):
    _table()
    from firepro3d.frame_group import FrameGroupController
    item = TextItem(TextAnnotationData(text="A", border=True))
    fg = FrameGroupController(lambda: [item])
    fg.sync()
    combo = fg.weight_combo
    assert [combo.itemText(i) for i in range(combo.count())] == pd.weight_names()
    assert combo.currentText() == item.data.border_weight


def test_frame_group_selects_custom_weight(qapp):
    _table()
    from firepro3d.frame_group import FrameGroupController
    item = TextItem(TextAnnotationData(text="A", border=True,
                                       border_weight="Site"))
    fg = FrameGroupController(lambda: [item])
    fg.sync()
    assert fg.weight_combo.currentText() == "Site"


def test_underlay_weight_menu_lists_project_table(qapp, monkeypatch):
    _table()
    from tests.test_underlay_manager_delegates import (
        _dxf_model, _option, _release_event)
    from firepro3d.theme import DARK
    from firepro3d.underlay_manager_model import Col
    from firepro3d.underlay_manager_delegates import WeightDelegate
    seen = []

    def fake_exec(self, *a, **k):
        seen.append([x.text() for x in self.actions()])
        return None

    monkeypatch.setattr(QMenu, "exec", fake_exec)
    monkeypatch.setattr(WeightDelegate, "_menu_pos", lambda self, opt: QPoint(0, 0))
    _rec, _scene, model = _dxf_model()
    idx = model.index(0, int(Col.WEIGHT), QModelIndex())
    opt = _option()
    assert WeightDelegate(DARK).editorEvent(
        _release_event(opt), model, opt, idx) is True
    assert seen == [["Default", *pd.weight_names()]]
    assert "Site" in seen[0]
