from firepro3d.paper_space import TextAnnotationData, Sheet


def test_text_annotation_data_round_trip():
    d = TextAnnotationData(
        text="GENERAL NOTES\n1. Comply with NFPA 13.",
        x=12.5, y=30.0, height_mm=3.175, wrap_width_mm=120.0,
        font_family="Arial", bold=True, italic=False,
        color="#ff0000", align="C", opaque_bg=True,
    )
    out = TextAnnotationData.from_dict(d.to_dict())
    assert out == d
    assert d.to_dict()["type"] == "text"


def test_text_annotation_data_partial_dict_defaults():
    out = TextAnnotationData.from_dict({"text": "X"})
    assert out.text == "X"
    assert out.height_mm == 3.175
    assert out.color == "#000000"
    assert out.align == "L"
    assert out.wrap_width_mm == 0.0


def test_sheet_without_annotations_key_loads_empty():
    base = Sheet.create_default().to_dict()
    base.pop("annotations", None)
    s = Sheet.from_dict(base)
    assert s.annotations == []


def test_sheet_round_trips_annotations():
    s = Sheet.create_default()
    s.annotations.append(TextAnnotationData(text="Note", x=5, y=5))
    s2 = Sheet.from_dict(s.to_dict())
    assert len(s2.annotations) == 1
    assert s2.annotations[0].text == "Note"
