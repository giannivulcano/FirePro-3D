"""Notes on schematics, Part 3: new-schematic defaults, the Text sizing and
Drawing scale rows, and the printed Height row (N10-N13)."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QFont, QFontMetricsF
from PyQt6.QtWidgets import QLabel

from firepro3d.annotative import editor_text_printed, editor_text_scale
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_editor import BlockEditorWidget
from firepro3d.block_properties_info import BlockPropertiesInfo
from firepro3d.constants import DEFAULT_TEXT_HEIGHT_MM
from firepro3d.dimension_edit import DimensionEdit
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.property_manager import PropertyManager
from firepro3d.text_item import TextAnnotationData, TextItem


def _project(ds=48.0):
    proj = Model_Space()
    proj.scale_manager.drawing_scale = ds
    return proj


def _line_item():
    return LineItem(QPointF(0, 0), QPointF(100, 0))


def _old(proj):
    d = BlockDefinition.new(name="Old", library="", series="", origin=(0.0, 0.0),
                            primitives=[_line_item().to_dict()], kind="schematic")
    proj.register_block_definition(d)
    w = BlockEditorWidget(proj, block_id=d.id, kind="schematic")
    w.seed_from_definition(d)
    return w


def _info(w):
    return BlockPropertiesInfo(w.editor_scene, "X", editor=w)


def _place_text(sc):
    sc.set_mode("text")
    sc._press_text(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    sc._press_text(None, QPointF(500, 200), QPointF(500, 200), None, None, None)
    return sc._texts[-1]


def test_a_new_schematic_starts_printed_at_the_project_scale(qapp):
    w = BlockEditorWidget(_project(48.0), kind="schematic")
    sc = w.editor_scene
    assert editor_text_printed(sc) and editor_text_scale(sc) == 48.0
    assert not w.is_dirty()


def test_a_new_schematic_stays_printed_past_an_undo_to_the_baseline(qapp):
    """The meta joins the undo baseline: Ctrl+Z of the first edit is not a
    silent switch to Real size."""
    w = BlockEditorWidget(_project(48.0), kind="schematic")
    sc = w.editor_scene
    w._add_primitive(_line_item())
    sc.push_undo_state()
    sc.undo()
    assert editor_text_printed(sc) and editor_text_scale(sc) == 48.0


def test_a_new_block_stays_real_size(qapp):
    w = BlockEditorWidget(_project(48.0), kind="block")
    assert not editor_text_printed(w.editor_scene)
    assert "Text sizing" not in _info(w).get_properties()


def test_a_saved_new_schematic_carries_both_keys(qapp):
    proj = _project(48.0)
    w = BlockEditorWidget(proj, kind="schematic")
    w._add_primitive(_line_item())
    d = w.commit_block("New", "", "")
    rec = d.to_dict()
    assert rec["text_sizing"] == "printed" and rec["text_scale"] == 48.0


def test_a_new_text_defaults_to_the_printed_height(qapp):
    w = BlockEditorWidget(_project(20.0), kind="schematic")
    t = _place_text(w.editor_scene)
    assert t._data.height_mm == pytest.approx(DEFAULT_TEXT_HEIGHT_MM * 20.0)


def test_a_new_text_in_an_old_schematic_keeps_the_model_default(qapp):
    from firepro3d.constants import DEFAULT_MODEL_TEXT_HEIGHT_MM
    t = _place_text(_old(_project(20.0)).editor_scene)
    assert t._data.height_mm == DEFAULT_MODEL_TEXT_HEIGHT_MM


def test_rows_on_a_printed_schematic(qapp):
    w = BlockEditorWidget(_project(20.0), kind="schematic")
    props = _info(w).get_properties()
    assert props["Text sizing"]["options"] == ["Real size", "Printed"]
    assert props["Text sizing"]["value"] == "Printed"
    assert props["Drawing scale"]["value"] == "1:20"
    assert "1:20" in props["Drawing scale"]["options"]


def test_a_non_preset_scale_is_offered_as_its_own_option(qapp):
    props = _info(BlockEditorWidget(_project(37.0), kind="schematic")).get_properties()
    assert props["Drawing scale"]["value"] == "1:37"
    assert "1:37" in props["Drawing scale"]["options"]


def test_rows_on_an_old_schematic_hide_drawing_scale(qapp):
    props = _info(_old(_project())).get_properties()
    assert props["Text sizing"]["value"] == "Real size"
    assert "Drawing scale" not in props


def test_switching_an_old_schematic_keeps_the_editor_look(qapp):
    """N13: the row writes the meta; every primitive keeps its size."""
    w = _old(_project(20.0))
    sc = w.editor_scene
    t = TextItem(TextAnnotationData(text="HELLO", height_mm=60.0))
    w._add_primitive(t)
    sc.push_undo_state()
    h, box = t._data.height_mm, t.manip_bounds()
    w._mark_clean()
    _info(w).set_property("Text sizing", "Printed")
    assert editor_text_printed(sc) and editor_text_scale(sc) == 20.0
    assert t._data.height_mm == h and t.manip_bounds() == box
    assert w.is_dirty()
    sc.undo()
    assert not editor_text_printed(sc)


def test_switching_back_writes_neither_key(qapp):
    w = BlockEditorWidget(_project(20.0), kind="schematic")
    _info(w).set_property("Text sizing", "Real size")
    meta = w.editor_scene.block_meta
    assert "text_sizing" not in meta and "text_scale" not in meta


def _height_widget(pm):
    form = pm._form
    for i in range(form.rowCount()):
        lbl = form.itemAt(i, form.ItemRole.LabelRole)
        fld = form.itemAt(i, form.ItemRole.FieldRole)
        if lbl and isinstance(lbl.widget(), QLabel) \
                and lbl.widget().text() == "Height" and fld:
            return fld.widget()
    return None


def _arial_cap_ratio() -> float:
    f = QFont("Arial")
    f.setPixelSize(1000)
    return QFontMetricsF(f).capHeight() / 1000.0


def test_height_row_shows_and_parses_printed_size(qapp):
    """N10, through the real panel: on a 1:20 schematic a 60 mm text is 3
    printed mm. The row shows that as a Word-style pt size and a typed size
    commits scene mm. Expected pt from Arial's raw metric and 25.4 / 72 mm."""
    w = BlockEditorWidget(_project(20.0), kind="schematic")
    t = TextItem(TextAnnotationData(text="H", height_mm=60.0, font_family="Arial"))
    w._add_primitive(t)
    pm = PropertyManager()
    pm.show_properties(t)
    edit = _height_widget(pm)
    assert isinstance(edit, DimensionEdit)
    pt = 3.0 / (25.4 / 72.0 * _arial_cap_ratio())
    assert edit.text() == f"{round(pt, 1):g} pt"
    edit.setText("4mm")
    edit.editingFinished.emit()
    assert t.data.height_mm == pytest.approx(80.0)
    edit.setText(f"{pt}")
    edit.editingFinished.emit()
    assert t.data.height_mm == pytest.approx(60.0, abs=1e-6)


def test_height_row_on_an_old_schematic_stays_real_mm(qapp):
    w = _old(_project(20.0))
    t = TextItem(TextAnnotationData(text="H", height_mm=60.0))
    w._add_primitive(t)
    pm = PropertyManager()
    pm.show_properties(t)
    edit = _height_widget(pm)
    assert edit.text() == "60.00 mm"
    edit.setText("3mm")
    edit.editingFinished.emit()
    assert t.data.height_mm == pytest.approx(3.0)
