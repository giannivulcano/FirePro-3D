from firepro3d.text_item import TextAnnotationData, TextItem


def test_frame_fields_default_off():
    d = TextAnnotationData()
    assert d.border is False
    assert d.border_weight == "Light"
    assert d.border_line_type == "solid"
    assert d.border_corner == "square"


def test_frame_roundtrip_to_from_dict():
    d = TextAnnotationData(text="N", border=True, border_weight="Heavy",
                           border_line_type="dashed", border_corner="chamfer")
    d2 = TextAnnotationData.from_dict(d.to_dict())
    assert (d2.border, d2.border_weight, d2.border_line_type, d2.border_corner) \
        == (True, "Heavy", "dashed", "chamfer")


def test_frame_from_dict_legacy_defaults_off():
    legacy = {"type": "text", "text": "x", "height_mm": 4.0}
    d = TextAnnotationData.from_dict(legacy)
    assert d.border is False and d.border_corner == "square"


def test_set_property_frame_keys_model(qapp):
    item = TextItem(TextAnnotationData(text="A"))
    item.set_property("Border", True)
    item.set_property("Border Weight", "Heavy")
    item.set_property("Line Type", "dashed")
    item.set_property("Corner", "chamfer")
    d = item._data
    assert (d.border, d.border_weight, d.border_line_type, d.border_corner) \
        == (True, "Heavy", "dashed", "chamfer")


def test_model_get_properties_exposes_frame(qapp):
    item = TextItem(TextAnnotationData(text="A", border=True, border_corner="round"))
    props = item.get_properties()
    assert props["Border"]["value"] is True
    assert props["Corner"]["value"] == "round"
    assert set(props["Corner"]["options"]) == {"square", "round", "chamfer"}


def test_paper_panel_change_frame_keys():
    from firepro3d.paper_space import _text_panel_change, _text_panel_properties
    d = TextAnnotationData(text="A")
    assert _text_panel_change(d, "Border", True) == {"border": True}
    assert _text_panel_change(d, "Corner", "chamfer") == {"border_corner": "chamfer"}
    assert _text_panel_change(d, "Border", False) is None   # unchanged → no-op
    form = _text_panel_properties(TextAnnotationData(border=True))
    assert form["Border"]["value"] is True
