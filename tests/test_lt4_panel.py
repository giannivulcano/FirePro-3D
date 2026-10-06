"""LT4 panel: capability rows, Pattern list + preview row types, locked row."""
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QWidget

from firepro3d import stroke_style as ss
from firepro3d.block_editor import BlockEditorWidget
from firepro3d.block_properties_info import BlockPropertiesInfo
from firepro3d.capability_panel import capability_rows, set_capability_property
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.property_manager import PropertyManager
from firepro3d.ui_kit import PaintSwatch, PatternList


def _lt():
    w = BlockEditorWidget(Model_Space())
    w.toggle_capability("repeat")
    return w, w.editor_scene


def test_rows_for_a_linetype(qapp):
    _, sc = _lt()
    r = capability_rows(sc)
    for k in ("Repeat", "Pattern tile", "Linetype", "Length", "Size", "Weight",
              "Pattern", "Pattern rows", "Preview", "Preview swatch"):
        assert k in r, k
    assert r["Linetype"]["value"] is True and r["Size"]["value"] == "Drafting"
    assert r["Pattern rows"]["value"] == [("dash", 6.0), ("gap", 3.0)]
    for k, m in r.items():
        if m["type"] != "header":
            assert m.get("tooltip"), k


def test_overlap_rows_are_read_only_with_note(qapp):
    w, sc = _lt()
    w._add_primitive(LineItem(QPointF(4, 0), QPointF(8, 0)))
    r = capability_rows(sc)
    assert r["Pattern rows"]["value"] is None
    assert r["Pattern rows"]["note"] == "Dashes overlap — edit on the canvas"
    assert r["Weight"].get("disabled") is True


def test_length_below_content_end_reverts(qapp):
    w, sc = _lt()
    set_capability_property(sc, w, "Length", 4.0)
    assert sc.block_repeat["length"] == 9.0
    set_capability_property(sc, w, "Length", 12.0)
    assert sc.block_repeat["length"] == 12.0


def test_panel_renders_real_widgets_and_commits_through_dimension_edit(qapp):
    w, sc = _lt()
    pm = PropertyManager()
    pm.show_properties(BlockPropertiesInfo(sc, "Hidden", w))
    qapp.processEvents()
    pl = pm.findChildren(PatternList)
    assert len(pl) == 1 and pm.findChildren(PaintSwatch)
    from firepro3d.dimension_edit import DimensionEdit
    field = [f for f in pl[0].findChildren(DimensionEdit)][0]
    field.setText("8")
    field.editingFinished.emit()
    qapp.processEvents()
    assert sorted((l._pt1.x(), l._pt2.x()) for l in sc._draw_lines) == [(0.0, 8.0)]
    assert sc.block_repeat["length"] == 11.0


def test_primitive_linetype_row_locked_in_a_linetype(qapp):
    _, sc = _lt()
    props = sc._draw_lines[0].get_properties()
    assert props["Linetype"].get("disabled") is True
    assert props["Linetype"]["tooltip"] == "Lines inside a linetype are always Continuous"


def test_primitive_linetype_row_unlocked_outside_a_linetype(qapp):
    w = BlockEditorWidget(Model_Space())
    w._add_primitive(LineItem(QPointF(0, 0), QPointF(5, 0)))
    props = w.editor_scene._draw_lines[0].get_properties()
    assert not props["Linetype"].get("disabled")
    assert props["Linetype"]["tooltip"] != "Lines inside a linetype are always Continuous"


def test_selected_repeat_frame_shows_and_edits_the_same_rows(qapp):
    w, sc = _lt()
    f = sc.capability_frame_item()
    assert f is not None
    assert list(f.get_properties()) == list(capability_rows(sc))
    f.set_property("Length", 15.0)
    assert sc.block_repeat["length"] == 15.0


def test_preview_swatch_paints_through_the_real_renderer(qapp):
    from PyQt6.QtGui import QColor, QImage, QPainter
    from PyQt6.QtCore import QRectF
    _, sc = _lt()
    paint = capability_rows(sc)["Preview swatch"]["paint"]
    img = QImage(240, 64, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    paint(p, QRectF(0, 0, 240, 64))
    p.end()
    # The top straight sample at y = 8 px: inked dashes AND gaps along it.
    inked = [img.pixelColor(x, 8).alpha() > 0 for x in range(8, 232)]
    assert any(inked) and not all(inked)


def test_nothing_selected_panel_follows_imperial_display_units(qapp):
    """Display units are project-scoped: the nothing-selected Block Editor
    panel formats and parses its dimension fields through the editor
    scene's ScaleManager (format_length / parse_dimension), never bare mm."""
    import pytest
    from firepro3d.dimension_edit import DimensionEdit
    from firepro3d.scale_manager import DisplayUnit
    w, sc = _lt()
    sm = sc.scale_manager
    sm.display_unit = DisplayUnit.IMPERIAL
    pm = PropertyManager()
    pm.show_properties(BlockPropertiesInfo(sc, "Hidden", w))
    qapp.processEvents()
    pl = pm.findChildren(PatternList)
    field = pl[0].findChildren(DimensionEdit)[0]
    assert field.text() == sm.format_length(6.0)
    assert pm._prop_widgets["Length"].text() == sm.format_length(9.0)
    field.setText('1"')
    field.editingFinished.emit()
    qapp.processEvents()
    (line,) = sc._draw_lines
    assert line._pt1.x() == pytest.approx(0.0)
    assert line._pt2.x() == pytest.approx(25.4)
