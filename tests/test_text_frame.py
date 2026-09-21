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
