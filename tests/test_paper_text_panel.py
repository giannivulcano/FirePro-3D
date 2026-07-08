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
