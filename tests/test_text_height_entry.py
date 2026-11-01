"""text-sizing-wrap D2 / D3 (AC2, AC3): model-surface text Height entry and the
annotative Block Editor placement defaults.

T-height-row drives the real Property panel: the Height row's own widget shows
the value and a typed entry commits through its parser to the stored cap mm.
Expected pt values come from Arial's raw metric (capHeight at 1000 px) and the
typographic point (25.4 / 72 mm), never from the module's own converters.
T-be-default drives the real two-click text placement on a Block Editor scene.
"""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QFont, QFontMetricsF
from PyQt6.QtWidgets import QLabel

from firepro3d.dimension_edit import DimensionEdit
from firepro3d.model_space import Model_Space
from firepro3d.property_manager import PropertyManager
from firepro3d.text_item import TextAnnotationData, TextItem

_MM_PER_PT = 25.4 / 72.0


def _arial_cap_ratio() -> float:
    f = QFont("Arial")
    f.setPixelSize(1000)
    return QFontMetricsF(f).capHeight() / 1000.0


def _scene(role: str, scale_mode: str = "real_size") -> Model_Space:
    s = Model_Space(scene_role=role)
    if role == "block_editor":
        s.set_block_meta({**s.block_meta, "scale_mode": scale_mode}, push_undo=False)
    return s


def _height_widget(pm):
    form = pm._form
    for i in range(form.rowCount()):
        lbl = form.itemAt(i, form.ItemRole.LabelRole)
        fld = form.itemAt(i, form.ItemRole.FieldRole)
        if lbl and isinstance(lbl.widget(), QLabel) \
                and lbl.widget().text() == "Height" and fld:
            return fld.widget()
    return None


def _panel_for(scene, h_mm):
    it = TextItem(TextAnnotationData(text="X", height_mm=h_mm, font_family="Arial"))
    scene.addItem(it)
    pm = PropertyManager()
    pm.show_properties(it)
    w = _height_widget(pm)
    assert isinstance(w, DimensionEdit)
    return it, pm, w

_HELPERS = ("_parse_text_height_mm", "_text_cap_ratio", "_font_pt_from_mm",
            "_mm_from_font_pt", "_format_height_pt", "_parse_height_pt")


def test_height_helpers_have_one_home(qapp):
    """D2: the pt / mm height helpers live in text_item; paper_space and
    font_group use that one definition (network_codec imports it lazily)."""
    import firepro3d.font_group as fg
    import firepro3d.paper_space as ps
    import firepro3d.text_item as ti
    for name in _HELPERS:
        assert getattr(ti, name).__module__ == "firepro3d.text_item", name
        assert getattr(ps, name) is getattr(ti, name), name
    assert ps.MM_PER_PT == ti.MM_PER_PT == 25.4 / 72.0
    for name in ("_font_pt_from_mm", "_mm_from_font_pt", "_parse_height_pt"):
        assert getattr(fg, name) is getattr(ti, name), name


def test_annotative_block_height_row_shows_and_parses_pt(qapp):
    s = _scene("block_editor", "annotative")
    it, _pm, w = _panel_for(s, 3.0)
    shown_pt = round(3.0 / (_MM_PER_PT * _arial_cap_ratio()), 1)    # 11.9 for Arial
    assert w.text() == f"{shown_pt:g} pt"
    w.setText("10.5")
    w.editingFinished.emit()
    assert it.data.height_mm == pytest.approx(10.5 * _MM_PER_PT * _arial_cap_ratio(), rel=1e-9)


@pytest.mark.parametrize("role", ["plan", "block_editor"])
def test_real_size_height_row_takes_decimal_mm(qapp, role):
    s = _scene(role)
    it, _pm, w = _panel_for(s, 100.0)
    assert w.text() == "100.00 mm"           # mm, 2 decimals (TEXT_HEIGHT_MM_PRECISION)
    w.setText("2.5")
    w.editingFinished.emit()
    assert it.data.height_mm == 2.5
