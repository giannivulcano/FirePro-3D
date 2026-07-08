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
