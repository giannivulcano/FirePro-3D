"""Tests for firepro3d.text_item — the shared TextAnnotationData dataclass (C5)."""
from firepro3d.text_item import TextAnnotationData


def test_data_defaults_and_rotation_roundtrip():
    d = TextAnnotationData(text="Hi", x=1.0, y=2.0, height_mm=2.5)
    assert d.angle == 0.0
    d.angle = 30.0
    d2 = TextAnnotationData.from_dict(d.to_dict())
    assert d2.angle == 30.0
    assert d2.text == "Hi"
    assert d2.height_mm == 2.5
    for f in ("font_family", "bold", "italic", "underline",
              "opaque_bg", "align", "wrap_width_mm", "box_height_mm", "color"):
        assert hasattr(d2, f)
