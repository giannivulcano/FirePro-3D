"""Panel-protocol tests for TextAnnotationItem (get_properties/set_property)."""
from firepro3d.paper_space import (
    PaperScene, Sheet, TextAnnotationData, TextAnnotationItem, ViewResolver,
)


def _stub_resolver():
    """Return a ViewResolver with all-None managers (safe for sheets with no views)."""
    return ViewResolver(None, None, None, None)


def _scene() -> PaperScene:
    return PaperScene(Sheet.create_default(), _stub_resolver())


def test_get_properties_shape(qapp):
    data = TextAnnotationData(text="X", height_mm=4.7625, bold=True,
                              align="C", color="#ff0000")
    item = TextAnnotationItem(data)
    props = item.get_properties()
    assert props["Font"]["type"] == "font"
    assert props["Height"]["type"] == "dimension"
    assert props["Height"]["value_mm"] == 4.7625
    assert props["Height"]["minimum"] == 0.0
    assert callable(props["Height"]["parser"])
    assert props["Bold"] == {"type": "bool", "value": True}
    assert props["Italic"] == {"type": "bool", "value": False}
    assert props["Color"]["type"] == "color"
    assert props["Alignment"]["value"] == "Center"
    assert props["Alignment"]["options"] == ["Left", "Center", "Right"]
    assert props["Opaque Background"] == {"type": "bool", "value": False}
    assert props["Leader"]["type"] == "label"     # placeholder for leader follow-up


def test_set_property_pushes_single_undo_command(qapp):
    scene = _scene()
    item = scene.add_annotation(TextAnnotationData(text="X"))
    before = scene.undo_stack.count()
    item.set_property("Bold", True)
    assert item.data.bold is True
    assert scene.undo_stack.count() == before + 1
    scene.undo_stack.undo()
    assert item.data.bold is False
    scene.undo_stack.redo()
    assert item.data.bold is True


def test_set_property_noop_pushes_nothing(qapp):
    scene = _scene()
    item = scene.add_annotation(TextAnnotationData(text="X", bold=True))
    before = scene.undo_stack.count()
    item.set_property("Bold", True)
    assert scene.undo_stack.count() == before


def test_set_property_alignment_maps_display_to_code(qapp):
    scene = _scene()
    item = scene.add_annotation(TextAnnotationData(text="X"))
    item.set_property("Alignment", "Center")
    assert item.data.align == "C"


def test_set_property_height_rejects_nonpositive(qapp):
    scene = _scene()
    item = scene.add_annotation(TextAnnotationData(text="X", height_mm=4.0))
    before = scene.undo_stack.count()
    item.set_property("Height", 0.0)
    item.set_property("Height", -1.0)
    assert item.data.height_mm == 4.0
    assert scene.undo_stack.count() == before


def test_set_property_offscene_applies_directly(qapp):
    # Template pattern: an item with no scene writes straight to its data.
    item = TextAnnotationItem(TextAnnotationData(text=""))
    item.set_property("Italic", True)
    item.set_property("Font", "Courier New")
    assert item.data.italic is True
    assert item.data.font_family == "Courier New"


def test_undo_after_format_updates_live_item(qapp):
    scene = _scene()
    item = scene.add_annotation(TextAnnotationData(text="X", height_mm=4.0))
    item.set_property("Height", 8.0)
    assert item.data.height_mm == 8.0
    old_scale = item.scale()
    scene.undo_stack.undo()
    assert item.data.height_mm == 4.0
    assert item.scale() != old_scale      # _apply_format re-ran


def test_set_property_font_arial_over_empty_is_noop(qapp):
    # font_family "" renders as Arial; re-committing "Arial" must not push.
    scene = _scene()
    item = scene.add_annotation(TextAnnotationData(text="X"))  # font_family ""
    before = scene.undo_stack.count()
    item.set_property("Font", "Arial")
    assert item.data.font_family == ""
    assert scene.undo_stack.count() == before


def test_set_property_alignment_rejects_mixed_placeholder(qapp):
    scene = _scene()
    item = scene.add_annotation(TextAnnotationData(text="X", align="C"))
    before = scene.undo_stack.count()
    item.set_property("Alignment", "< mixed >")
    assert item.data.align == "C"
    assert scene.undo_stack.count() == before


def test_paper_scene_exposes_scale_manager(qapp):
    from firepro3d.scale_manager import ScaleManager
    scene = _scene()
    assert isinstance(scene.scale_manager, ScaleManager)


def test_begin_place_text_copies_template_formatting(qapp):
    from PyQt6.QtCore import QPointF
    scene = _scene()
    scene.text_template = TextAnnotationData(
        height_mm=6.35, font_family="Courier New", bold=True, italic=True,
        color="#00ff00", align="R", opaque_bg=True,
    )
    item = scene.begin_place_text(QPointF(100, 100))
    d = item.data
    assert d.height_mm == 6.35
    assert d.font_family == "Courier New"
    assert d.bold and d.italic and d.opaque_bg
    assert d.color == "#00ff00"
    assert d.align == "R"
    assert d.text == "" and d.wrap_width_mm == 0.0   # content/wrap NOT templated
    item.cancel_edit()                                # clean up transient


def test_begin_place_text_without_template_uses_defaults(qapp):
    from PyQt6.QtCore import QPointF
    from firepro3d.constants import DEFAULT_TEXT_HEIGHT_MM
    scene = _scene()
    item = scene.begin_place_text(QPointF(100, 100))
    assert item.data.height_mm == DEFAULT_TEXT_HEIGHT_MM
    assert item.data.bold is False
    item.cancel_edit()


def test_widget_emits_add_text_mode_toggled(qapp):
    from firepro3d.paper_space import PaperSpaceWidget
    w = PaperSpaceWidget(Sheet.create_default(), _stub_resolver())
    got = []
    w.add_text_mode_toggled.connect(got.append)
    w._add_text_btn.setChecked(True)
    w._add_text_btn.setChecked(False)
    assert got == [True, False]


def _panel_widget_for(pm, label_text):
    """Return the field widget in the row whose label is *label_text*."""
    from PyQt6.QtWidgets import QLabel
    form = pm._form
    for i in range(form.rowCount()):
        lbl = form.itemAt(i, form.ItemRole.LabelRole)
        fld = form.itemAt(i, form.ItemRole.FieldRole)
        if lbl and isinstance(lbl.widget(), QLabel) \
                and lbl.widget().text() == label_text and fld:
            return fld.widget()
    return None


def test_panel_renders_text_item_rows(qapp):
    from PyQt6.QtWidgets import QCheckBox, QFontComboBox
    from firepro3d.dimension_edit import DimensionEdit
    from firepro3d.property_manager import PropertyManager
    scene = _scene()
    item = scene.add_annotation(TextAnnotationData(text="X", bold=True))
    pm = PropertyManager()
    pm.show_properties(item)
    assert isinstance(_panel_widget_for(pm, "Font"), QFontComboBox)
    assert isinstance(_panel_widget_for(pm, "Height"), DimensionEdit)
    bold = _panel_widget_for(pm, "Bold")
    assert isinstance(bold, QCheckBox) and bold.isChecked()


def test_panel_checkbox_commit_routes_to_set_property(qapp):
    from firepro3d.property_manager import PropertyManager
    scene = _scene()
    item = scene.add_annotation(TextAnnotationData(text="X"))
    pm = PropertyManager()
    pm.show_properties(item)
    before = scene.undo_stack.count()
    _panel_widget_for(pm, "Bold").setChecked(True)   # user toggle
    assert item.data.bold is True
    assert scene.undo_stack.count() == before + 1


def test_panel_height_field_gets_parser_and_minimum(qapp):
    from firepro3d.property_manager import PropertyManager
    scene = _scene()
    item = scene.add_annotation(TextAnnotationData(text="X", height_mm=4.7625))
    pm = PropertyManager()
    pm.show_properties(item)
    h = _panel_widget_for(pm, "Height")
    assert h._parser is not None
    assert h._minimum == 0.0
    h.setText('1/8"')
    # Emit the SIGNAL (not the private slot): DimensionEdit's own handler was
    # connected first (updates value_mm), then the panel's commit lambda.
    h.editingFinished.emit()
    assert item.data.height_mm == 3.175


def test_multiselect_commit_is_single_undo_step(qapp):
    from firepro3d.property_manager import PropertyManager
    scene = _scene()
    a = scene.add_annotation(TextAnnotationData(text="A"))
    b = scene.add_annotation(TextAnnotationData(text="B"))
    pm = PropertyManager()
    pm.show_properties([a, b])
    before = scene.undo_stack.count()
    pm._apply_property("Bold", True)
    assert a.data.bold and b.data.bold
    assert scene.undo_stack.count() == before + 1     # ONE macro, not two commands
    scene.undo_stack.undo()
    assert not a.data.bold and not b.data.bold
    scene.undo_stack.redo()
    assert a.data.bold and b.data.bold
