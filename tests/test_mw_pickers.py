"""MW-6 in the weight pickers: a stored factory name the project table lacks
shows as the row it actually draws as (its nearest row by mm); displaying it
never rewrites the stored value. Real widgets / property rows (VC3)."""
from PyQt6.QtCore import QPointF

from firepro3d import paper_display as pd
from firepro3d.paper_display import LineWeightDef

_NEW = [("Thinnest", 0.18), ("Thinner", 0.25), ("Thin", 0.35),
        ("Thick", 0.50), ("Thickest", 0.70)]


def _new_table():
    pd.set_project_line_weights([LineWeightDef(n, mm) for n, mm in _NEW])


def test_paper_tab_combo_shows_resolved_row(qapp):
    from firepro3d.display_manager import DisplayManager
    from firepro3d.model_space import Model_Space
    _new_table()
    cats = pd.factory_paper_categories()
    cats["Wall"]["line_weight"] = "Heavy"           # pre-MW stored global name
    pd.save_paper_categories(cats)
    d = DisplayManager(Model_Space(), active_context="paper")
    try:
        combo = d._paper_cat_data["Wall"]["lw_combo"]
        assert combo.currentText() == "Thin"        # what paper prints (0.35)
        d._refresh_lw_combos()                      # table-edit refill path
        assert combo.currentText() == "Thin"
        assert pd.load_paper_categories()["Wall"]["line_weight"] == "Heavy"
    finally:
        d.close()


def test_model_blocks_combo_shows_resolved_row(qapp):
    from firepro3d.display_manager import DisplayManager
    from firepro3d.model_space import Model_Space
    _new_table()
    pd.set_model_blocks_weight("Heavy")
    try:
        d = DisplayManager(Model_Space())
        try:
            assert d._model_blocks_combo.currentText() == "Thin"
            d._refresh_model_blocks_combo()
            assert d._model_blocks_combo.currentText() == "Thin"
            assert pd.model_blocks_weight() == "Heavy"
        finally:
            d.close()
    finally:
        pd.set_model_blocks_weight(None)


def test_text_border_weight_row_shows_resolved_row(qapp):
    from firepro3d.text_item import TextAnnotationData, TextItem
    _new_table()
    item = TextItem(TextAnnotationData(text="A", border=True,
                                       border_weight="Medium"))
    row = item.get_properties()["Border Weight"]
    assert row["value"] == "Thinner" and row["value"] in row["options"]
    assert item.data.border_weight == "Medium"


def test_paper_text_panel_border_weight_shows_resolved_row(qapp):
    from firepro3d.paper_space import _text_panel_properties
    from firepro3d.text_item import TextAnnotationData
    _new_table()
    d = TextAnnotationData(text="A", border=True, border_weight="Medium")
    assert _text_panel_properties(d)["Border Weight"]["value"] == "Thinner"


def test_frame_group_combo_shows_resolved_row(qapp):
    from firepro3d.frame_group import FrameGroupController
    from firepro3d.text_item import TextAnnotationData, TextItem
    _new_table()
    item = TextItem(TextAnnotationData(text="A", border=True,
                                       border_weight="Medium"))
    ctl = FrameGroupController(get_targets=lambda: [item])
    ctl.sync()
    assert ctl.weight_combo.currentText() == "Thinner"
    assert item.data.border_weight == "Medium"


def test_geometry_weight_row_shows_resolved_row(qapp):
    from firepro3d.geometry_2d import LineItem
    from firepro3d.model_space import Model_Space
    _new_table()
    ms = Model_Space()
    ln = LineItem(QPointF(0, 0), QPointF(100, 0))
    ms.addItem(ln)
    ln.style["weight"] = "Heavy"
    row = ln.get_properties()["Weight"]
    assert row["value"] == "Thin" and row["value"] in row["options"]
    assert ln.style["weight"] == "Heavy"


def test_unknown_name_keeps_todays_display(qapp):
    from firepro3d.text_item import TextAnnotationData, TextItem
    _new_table()
    item = TextItem(TextAnnotationData(text="A", border=True,
                                       border_weight="Foo"))
    assert item.get_properties()["Border Weight"]["value"] == "Foo"
