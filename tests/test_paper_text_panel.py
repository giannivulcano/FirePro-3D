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
    assert props["Underline"] == {"type": "bool", "value": False}
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
        underline=True, color="#00ff00", align="R", opaque_bg=True,
    )
    item = scene.begin_place_text(QPointF(100, 100))
    d = item.data
    assert d.height_mm == 6.35
    assert d.font_family == "Courier New"
    assert d.bold and d.italic and d.underline and d.opaque_bg
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
    w.set_add_text_mode(True)
    w.set_add_text_mode(False)
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
    _panel_widget_for(pm, "Bold").click()           # real user click
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


def test_template_settings_round_trip(qapp):
    from firepro3d.paper_space import (
        text_template_to_settings, apply_template_settings,
    )
    src = TextAnnotationData(height_mm=6.35, font_family="Courier New",
                             bold=True, italic=False, underline=True,
                             color="#00ff00", align="R", opaque_bg=True)
    raw = text_template_to_settings(src)
    # QSettings on Windows may stringify values — simulate the worst case.
    raw = {k: str(v) for k, v in raw.items()}
    dst = TextAnnotationData()
    apply_template_settings(dst, raw)
    assert dst.height_mm == 6.35
    assert dst.font_family == "Courier New"
    assert dst.bold is True and dst.italic is False
    assert dst.underline is True
    assert dst.color == "#00ff00" and dst.align == "R"
    assert dst.opaque_bg is True


def test_apply_template_settings_rejects_bad_height(qapp):
    from firepro3d.paper_space import apply_template_settings
    from firepro3d.constants import DEFAULT_TEXT_HEIGHT_MM
    dst = TextAnnotationData()
    apply_template_settings(dst, {"height_mm": "0"})
    assert dst.height_mm == DEFAULT_TEXT_HEIGHT_MM
    apply_template_settings(dst, {"height_mm": "garbage"})
    assert dst.height_mm == DEFAULT_TEXT_HEIGHT_MM


# ── Word-style pt height display (2026-07-09 smoke-test feedback) ─────────


def test_font_pt_round_trip(qapp):
    from firepro3d.paper_space import _font_pt_from_mm, _mm_from_font_pt
    data = TextAnnotationData()          # Arial default
    mm = _mm_from_font_pt(data, 12.0)
    assert 2.5 < mm < 3.6                # ~3.0 mm cap for 12 pt Arial
    assert abs(_font_pt_from_mm(data, mm) - 12.0) < 1e-6


def test_parse_height_pt_variants(qapp):
    from firepro3d.paper_space import _parse_height_pt, _mm_from_font_pt
    data = TextAnnotationData()
    expected = _mm_from_font_pt(data, 12.0)
    assert _parse_height_pt(data, "12") == expected
    assert _parse_height_pt(data, "12 pt") == expected
    assert _parse_height_pt(data, "12pt") == expected
    # Explicit dimension strings still parse as literal cap heights
    assert abs(_parse_height_pt(data, '1/8"') - 3.175) < 1e-6
    assert abs(_parse_height_pt(data, "3mm") - 3.0) < 1e-6
    assert _parse_height_pt(data, "garbage") is None


def test_format_height_pt(qapp):
    from firepro3d.paper_space import _format_height_pt, _mm_from_font_pt
    data = TextAnnotationData()
    assert _format_height_pt(data, _mm_from_font_pt(data, 12.0)) == "12 pt"


def test_panel_height_field_displays_and_parses_pt(qapp):
    from firepro3d.property_manager import PropertyManager
    from firepro3d.paper_space import _mm_from_font_pt
    scene = _scene()
    item = scene.add_annotation(TextAnnotationData(text="X"))
    pm = PropertyManager()
    pm.show_properties(item)
    h = _panel_widget_for(pm, "Height")
    assert h.text().endswith("pt")       # displays Word-style pt
    h.setText("12")
    h.editingFinished.emit()
    assert item.data.height_mm == _mm_from_font_pt(item.data, 12.0)


def test_scrollbars_hidden(qapp):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QScrollArea
    from firepro3d.paper_space import PaperSpaceWidget
    from firepro3d.property_manager import PropertyManager
    w = PaperSpaceWidget(Sheet.create_default(), _stub_resolver())
    off = Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert w.view.horizontalScrollBarPolicy() == off
    assert w.view.verticalScrollBarPolicy() == off
    pm = PropertyManager()
    scroll = pm.findChild(QScrollArea)
    assert scroll.horizontalScrollBarPolicy() == off
    assert scroll.verticalScrollBarPolicy() == off


# ── Mixed-state checkbox click behavior (2026-07-09 smoke-test bug) ───────


def test_mixed_bold_shows_partial_and_first_click_applies(qapp):
    from PyQt6.QtCore import Qt
    from firepro3d.property_manager import PropertyManager
    scene = _scene()
    a = scene.add_annotation(TextAnnotationData(text="A", bold=True))
    b = scene.add_annotation(TextAnnotationData(text="B", bold=False))
    pm = PropertyManager()
    pm.show_properties([a, b])
    chk = _panel_widget_for(pm, "Bold")
    assert chk.checkState() == Qt.CheckState.PartiallyChecked  # partial shown
    before = scene.undo_stack.count()
    chk.click()                              # REAL user path (not _apply_property)
    assert a.data.bold is True and b.data.bold is True   # first click applies
    assert scene.undo_stack.count() == before + 1        # one macro step
    assert chk.checkState() == Qt.CheckState.Checked


def test_checkbox_click_never_cycles_into_partial(qapp):
    from PyQt6.QtCore import Qt
    from firepro3d.property_manager import PropertyManager
    scene = _scene()
    a = scene.add_annotation(TextAnnotationData(text="A", bold=True))
    b = scene.add_annotation(TextAnnotationData(text="B", bold=False))
    pm = PropertyManager()
    pm.show_properties([a, b])
    chk = _panel_widget_for(pm, "Bold")
    chk.click()                              # partial -> checked (both bold)
    chk.click()                              # checked -> unchecked (both unbold)
    assert chk.checkState() == Qt.CheckState.Unchecked
    assert a.data.bold is False and b.data.bold is False
    chk.click()                              # unchecked -> CHECKED, never partial
    assert chk.checkState() == Qt.CheckState.Checked
    assert a.data.bold is True and b.data.bold is True


# ── Underline field (2026-07-16) ──────────────────────────────────────────────


def test_underline_field_defaults_false():
    from firepro3d.paper_space import TextAnnotationData
    assert TextAnnotationData().underline is False


def test_underline_round_trips_serialization():
    from firepro3d.paper_space import TextAnnotationData
    d = TextAnnotationData(text="hi", underline=True)
    d2 = TextAnnotationData.from_dict(d.to_dict())
    assert d2.underline is True
    legacy = d.to_dict()
    del legacy["underline"]
    assert TextAnnotationData.from_dict(legacy).underline is False


def test_underline_renders_on_font(qapp):
    item = TextAnnotationItem(TextAnnotationData(text="X"))
    item.data.underline = True
    item._apply_format()
    assert item.font().underline() is True


def test_underline_panel_row_and_commit(qapp):
    scene = _scene()
    item = scene.add_annotation(TextAnnotationData(text="X"))
    props = item.get_properties()
    assert props["Underline"]["type"] == "bool"
    assert props["Underline"]["value"] is False
    before = scene.undo_stack.count()
    item.set_property("Underline", True)
    assert item.data.underline is True
    assert scene.undo_stack.count() == before + 1
    scene.undo_stack.undo()
    assert item.data.underline is False


# ── Template underline (2026-07-16 spec gap fix) ──────────────────────────────


def test_template_underline_seeds_placement(qapp):
    from PyQt6.QtCore import QPointF
    scene = _scene()
    scene.text_template = TextAnnotationData(underline=True)
    item = scene.begin_place_text(QPointF(100, 100))
    assert item.data.underline is True
    item.cancel_edit()


def test_template_underline_survives_settings_round_trip(qapp):
    from firepro3d.paper_space import (
        text_template_to_settings, apply_template_settings,
    )
    d = TextAnnotationData(underline=True)
    raw = text_template_to_settings(d)
    # QSettings on Windows may stringify values — simulate the worst case.
    raw = {k: str(v) for k, v in raw.items()}
    d2 = TextAnnotationData()
    apply_template_settings(d2, raw)
    assert d2.underline is True
