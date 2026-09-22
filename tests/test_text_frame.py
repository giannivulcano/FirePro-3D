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
    assert {o[0] for o in props["Corner"]["options"]} == {"square", "round", "chamfer"}


def test_paper_panel_change_frame_keys():
    from firepro3d.paper_space import _text_panel_change, _text_panel_properties
    d = TextAnnotationData(text="A")
    assert _text_panel_change(d, "Border", True) == {"border": True}
    assert _text_panel_change(d, "Corner", "chamfer") == {"border_corner": "chamfer"}
    assert _text_panel_change(d, "Border", False) is None   # unchanged → no-op
    form = _text_panel_properties(TextAnnotationData(border=True))
    assert form["Border"]["value"] is True


# ── Render tests (frame pixels) ─────────────────────────────────────────────

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage, QPainter, QColor
from PyQt6.QtWidgets import QGraphicsScene


def _render_nonwhite_count(item):
    """Render the item's scene region to a white image; count non-white pixels."""
    scene = QGraphicsScene()
    scene.addItem(item)
    src = item.sceneBoundingRect().adjusted(-6, -6, 6, 6)
    img = QImage(260, 180, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, 260, 180), src)
    p.end()
    white = QColor("white").rgb()
    n = 0
    for y in range(img.height()):
        for x in range(img.width()):
            if img.pixel(x, y) != white:
                n += 1
    scene.removeItem(item)
    return n


def test_frame_adds_pixels_when_border_on_model(qapp):
    item = TextItem(TextAnnotationData(text="ABC", height_mm=4.0))
    off = _render_nonwhite_count(item)
    item.set_property("Border", True)
    on = _render_nonwhite_count(item)
    assert on > off + 20   # the stroked border adds a clear pixel delta


def test_frame_path_corner_variants_nonempty(qapp):
    item = TextItem(TextAnnotationData(text="ABC", border=True))
    for corner in ("square", "round", "chamfer"):
        item._data.border_corner = corner
        assert not item._frame_path().isEmpty()


def test_frame_pen_uses_named_weight_and_color(qapp):
    item = TextItem(TextAnnotationData(text="A", border=True, color="#123456",
                                       border_weight="Heavy", border_line_type="dashed"))
    pen = item._frame_pen()
    assert pen.color().name() == "#123456"
    assert pen.style() == __import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.PenStyle.DashLine
    assert pen.widthF() > 0


# ── Fill colour tests ────────────────────────────────────────────────────────

def test_fill_fields_default_none():
    d = TextAnnotationData()
    assert d.fill_color == "" and d.fill_opacity == 100.0
    assert not hasattr(d, "opaque_bg")


def test_fill_roundtrip():
    d = TextAnnotationData(fill_color="#d19a26", fill_opacity=35.0)
    dd = d.to_dict()
    d2 = TextAnnotationData.from_dict(dd)
    assert d2.fill_color == "#d19a26" and d2.fill_opacity == 35.0
    assert "opaque_bg" not in dd


def test_opaque_bg_migration():
    on = TextAnnotationData.from_dict({"type": "text", "opaque_bg": True})
    off = TextAnnotationData.from_dict({"type": "text", "opaque_bg": False})
    assert on.fill_color == "#ffffff" and on.fill_opacity == 100.0
    assert off.fill_color == ""


def test_fill_renders_pixels(qapp):
    # _render_nonwhite_count already exists earlier in this test file (Phase 1)
    item = TextItem(TextAnnotationData(text="AB", height_mm=4.0))
    off = _render_nonwhite_count(item)
    item.set_property("Fill Color", "#c0392b")
    on = _render_nonwhite_count(item)
    assert on > off + 50


# ── Grouped annotation-text panel form (T10) ────────────────────────────────

def test_annotation_panel_grouped_form(qapp):
    item = TextItem(TextAnnotationData(text="A", border=True, fill_color="#d19a26"))
    p = item.get_properties()
    keys = list(p.keys())
    assert keys.index("Text") < keys.index("Format") < keys.index("Frame") < keys.index("Fill")
    assert p["Text"]["type"] == "header" and p["Format"]["type"] == "header"
    assert keys.index("Font") > keys.index("Format") and keys.index("Height") > keys.index("Format")
    assert p["Height"]["type"] == "number"
    assert p["Corner"]["type"] == "icon_enum"
    assert [o[0] for o in p["Corner"]["options"]] == ["square", "round", "chamfer"]
    assert p["Style"]["type"] == "bool_group"
    assert p["Font Color"]["type"] == "color"
    assert p["Fill Color"]["type"] == "color" and p["Fill Opacity"]["type"] == "percent"


def test_annotation_panel_commits(qapp):
    item = TextItem(TextAnnotationData(text="A"))
    item.set_property("Content", "hello")
    item.set_property("Font Color", "#223344")
    item.set_property("Height", 60)
    assert item._data.text == "hello"
    assert item._data.color == "#223344"
    assert abs(item._data.height_mm - 60) < 1e-6


def test_panel_renders_textitem_end_to_end(qapp):
    from firepro3d.property_manager import PropertyManager
    item = TextItem(TextAnnotationData(text="A"))
    pm = PropertyManager()
    pm.show_properties(item)           # builds the grouped form without error
    from PyQt6.QtWidgets import QAbstractButton
    # Corner + Alignment both render as icon_enum; filter to the corner values.
    corner_btns = [b for b in pm.findChildren(QAbstractButton)
                   if b.property("icon_enum_val") in ("square", "round", "chamfer")]
    assert len(corner_btns) == 3       # icon_enum Corner rendered in the real panel
    next(b for b in corner_btns if b.property("icon_enum_val") == "chamfer").click()
    assert item._data.border_corner == "chamfer"
