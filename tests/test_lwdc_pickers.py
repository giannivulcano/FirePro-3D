"""LW-DC-7 -- every Weight dropdown lists Defaults, a separator, then Custom.
Real Properties panel / DisplayManager Paper tab (VC3)."""
from PyQt6.QtCore import QPointF

from firepro3d import paper_display as pd
from firepro3d.paper_display import LineWeightDef


def _texts(combo):
    return [combo.itemText(i) for i in range(combo.count())]


def _table(custom=True):
    rows = list(pd.DEFAULT_LINE_WEIGHTS)
    if custom:
        rows.append(LineWeightDef("Pen X", 0.40))
    pd.set_project_line_weights(rows)


def _defaults():
    return [d.name for d in sorted(pd.DEFAULT_LINE_WEIGHTS,
                                   key=lambda d: d.width_mm)]


def _line_panel():
    from firepro3d.geometry_2d import LineItem
    from firepro3d.model_space import Model_Space
    from firepro3d.property_manager import PropertyManager
    ms = Model_Space()
    ln = LineItem(QPointF(0, 0), QPointF(100, 0))
    ms.addItem(ln)
    pm = PropertyManager()
    pm.show_properties([ln])
    return ms, ln, pm


def test_line_weight_row_sectioned_and_commits_custom(qapp):
    _table()
    _ms, ln, pm = _line_panel()
    combo = pm._prop_widgets["Weight"]
    texts = _texts(combo)
    assert texts[1:] == [*_defaults(), "", "Pen X"] and len(texts) == 10
    assert texts[0] not in _defaults()               # By Linetype head
    combo.setCurrentText("Pen X")
    assert ln.style["weight"] == "Pen X"


def test_line_weight_row_no_custom_no_separator(qapp):
    _table(custom=False)
    _ms, _ln, pm = _line_panel()
    assert "" not in _texts(pm._prop_widgets["Weight"])


def test_paper_tab_wall_combo_sectioned_and_survives_refresh(qapp):
    from firepro3d.display_manager import DisplayManager
    from firepro3d.model_space import Model_Space
    _table()
    d = DisplayManager(Model_Space(), active_context="paper")
    try:
        combo = d._paper_cat_data["Wall"]["lw_combo"]
        assert _texts(combo) == [*_defaults(), "", "Pen X"]
        combo.setCurrentText("Pen X")
        d._refresh_lw_combos()
        assert _texts(combo) == [*_defaults(), "", "Pen X"]
        assert combo.currentText() == "Pen X"
    finally:
        d.close()


def test_paper_tab_no_custom_no_separator(qapp):
    from firepro3d.display_manager import DisplayManager
    from firepro3d.model_space import Model_Space
    _table(custom=False)
    d = DisplayManager(Model_Space(), active_context="paper")
    try:
        assert _texts(d._paper_cat_data["Wall"]["lw_combo"]) == _defaults()
    finally:
        d.close()


def test_frame_group_combo_sectioned(qapp):
    from firepro3d.frame_group import FrameGroupController
    from firepro3d.text_item import TextAnnotationData, TextItem
    _table()
    item = TextItem(TextAnnotationData(text="A", border=True,
                                       border_weight="Pen X"))
    fg = FrameGroupController(lambda: [item])
    fg.sync()
    assert _texts(fg.weight_combo) == [*_defaults(), "", "Pen X"]
    assert fg.weight_combo.currentText() == "Pen X"
