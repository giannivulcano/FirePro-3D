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


# ── review G5: the frame never joins a multi-selection panel (I1) ─────────

def _frame_and_off_axis_line():
    w, sc = _lt()
    off = LineItem(QPointF(0, 5), QPointF(20, 5))        # not an axis mark
    w._add_primitive(off)
    return w, sc, sc.capability_frame_item(), off


def _dash_weights(sc):
    from firepro3d.linetype_authoring import axis_items
    return [l.style["weight"] for l, r in axis_items(sc) if r[0] == "dash"]


def test_frame_alone_still_shows_its_rows(qapp):
    _, sc, f, _ = _frame_and_off_axis_line()
    pm = PropertyManager()
    pm.show_properties([f])
    assert len(pm.findChildren(PatternList)) == 1


def test_frame_primary_multiselect_weight_reaches_only_the_line(qapp):
    _, sc, f, off = _frame_and_off_axis_line()
    dashes0, rep0 = _dash_weights(sc), sc.block_repeat
    pm = PropertyManager()
    pm.show_properties([f, off])
    qapp.processEvents()
    assert not pm.findChildren(PatternList)               # the Line's form
    combo = pm._prop_widgets["Weight"]
    named = [combo.itemText(i) for i in range(combo.count())
             if not combo.itemText(i).startswith(("By ", "<"))][1]
    pm._apply_property("Weight", named)
    assert off.style["weight"] == named
    assert _dash_weights(sc) == dashes0 and sc.block_repeat == rep0


def test_line_primary_multiselect_by_linetype_leaves_the_dashes(qapp):
    _, sc, f, off = _frame_and_off_axis_line()
    dashes0 = _dash_weights(sc)
    pm = PropertyManager()
    pm.show_properties([off, f])
    qapp.processEvents()
    combo = pm._prop_widgets["Weight"]
    by_lt = [combo.itemText(i) for i in range(combo.count())
             if combo.itemText(i).startswith(ss.BY_LINETYPE_LABEL)][0]
    pm._apply_property("Weight", by_lt)
    assert _dash_weights(sc) == dashes0
    assert off.style["weight"] == ss.BY_LINETYPE


def test_line_primary_multiselect_length_leaves_the_repeat(qapp):
    _, sc, f, off = _frame_and_off_axis_line()
    pm = PropertyManager()
    pm.show_properties([off, f])
    qapp.processEvents()
    assert "Length" in pm._prop_widgets
    pm._apply_property("Length", 30.0)
    assert sc.block_repeat["length"] == 9.0
    assert abs(off._pt1.x() - off._pt2.x()) == 30.0


def test_tile_frame_and_rectangle_multiselect_width_reaches_only_the_rect(qapp):
    from firepro3d.geometry_2d import RectangleItem
    w = BlockEditorWidget(Model_Space())
    w._add_primitive(LineItem(QPointF(0, 0), QPointF(20, -8)))
    assert w.toggle_capability("tile")
    sc = w.editor_scene
    rect = RectangleItem(QPointF(0, 0), QPointF(10, -4))
    w._add_primitive(rect)
    tile0 = sc.block_tile
    pm = PropertyManager()
    pm.show_properties([sc.capability_frame_item(), rect])
    pm._apply_property("Width", 50.0)
    assert sc.block_tile == tile0
    assert rect.rect().width() == 50.0


# ── review G5 minors (M1, M3, M4, M5) ─────────────────────────────────────

def test_same_rows_twice_is_one_undo_step(qapp):
    from firepro3d.linetype_authoring import apply_pattern_rows
    _, sc = _lt()
    n = len(sc._undo_stack)
    assert apply_pattern_rows(sc, [("dash", 8.0), ("gap", 3.0)]) is True
    assert apply_pattern_rows(sc, [("dash", 8.0), ("gap", 3.0)]) is False
    assert len(sc._undo_stack) == n + 1


def test_length_field_rejects_below_content_end_immediately(qapp):
    from firepro3d.dimension_edit import DimensionEdit
    w, sc = _lt()
    pm = PropertyManager()
    pm.show_properties(BlockPropertiesInfo(sc, "Hidden", w))
    field = pm._prop_widgets["Length"]
    assert isinstance(field, DimensionEdit)
    field.setText("4")
    field.editingFinished.emit()
    assert field.value_mm() == 9.0                         # reverted, no refresh
    field.setText("6")                                     # == content end
    field.editingFinished.emit()
    assert field.value_mm() == 6.0


def test_dots_only_weight_row_is_by_category_not_mixed(qapp):
    from firepro3d.linetype_authoring import apply_pattern_rows
    _, sc = _lt()
    assert apply_pattern_rows(sc, [("dot", 0.0), ("gap", 3.0)])
    v = capability_rows(sc)["Weight"]["value"]
    assert v.startswith("By Category") and "< mixed >" not in \
        capability_rows(sc)["Weight"]["options"]


def test_unknown_dash_weight_is_shown_as_its_own_option(qapp):
    from firepro3d.linetype_authoring import axis_items
    _, sc = _lt()
    for l, r in axis_items(sc):
        if r[0] == "dash":
            l.style["weight"] = "Retired Weight"
    row = capability_rows(sc)["Weight"]
    assert row["value"] == "Retired Weight"
    assert row["options"][0] == "Retired Weight"


# ── seam review I1: the pre-placement template inside a linetype editor ──

def _hidden_project():
    from firepro3d.block_definition import BlockDefinition
    proj = Model_Space()
    hid = BlockDefinition.new(
        name="Hidden", library="L", series="S", origin=(0, 0),
        primitives=[LineItem(QPointF(0, 0), QPointF(5, 0)).to_dict()],
        repeat={"length": 8.0, "size": "drafting"})
    proj.register_block_definition(hid)
    return proj, hid


def _draw_next_line(sc):
    """Commit a Line through the real draw-tool path (apply_current)."""
    sc.set_mode("draw_line")
    sc._make_line_like(QPointF(0, 4), QPointF(7, 4))
    return sc._draw_lines[-1]


def _row_a_selected_line_shows(sc, line):
    from firepro3d.geometry_2d import stroke_rows
    return stroke_rows(line.style, sc.block_registry)


def _assert_template_matches_draw(sc, expect_weight_value):
    cur0 = dict(ss.current_style())
    props = sc._get_geometry_template().get_properties()
    assert props["Linetype"]["value"] == "Continuous"
    assert props["Linetype"]["disabled"] is True
    assert props["Linetype"]["tooltip"] ==         "Lines inside a linetype are always Continuous"
    assert props["Weight"]["value"] == expect_weight_value
    assert props["Weight"]["disabled"] is True
    assert props["Weight"]["tooltip"] ==         "New lines take the linetype's Weight (set it in the Repeat section)"
    assert ss.current_style() == cur0                       # WM-10 / LT4-4
    drawn = _draw_next_line(sc)
    assert drawn.style["linetype"] == ss.CONTINUOUS
    shown = _row_a_selected_line_shows(sc, drawn)
    assert shown["Linetype"]["value"] == props["Linetype"]["value"]
    assert shown["Weight"]["value"] == props["Weight"]["value"]
    assert ss.current_style() == cur0


def test_template_in_a_linetype_shows_continuous_and_the_dash_weight(qapp):
    from firepro3d import linetype_authoring as la
    proj, hid = _hidden_project()
    w = BlockEditorWidget(proj)
    assert w.toggle_capability("repeat")
    sc = w.editor_scene
    la.set_pattern_weight(sc, "Heavy")
    ss.set_current(linetype=hid.id, weight="Light")
    _assert_template_matches_draw(sc, "Heavy")


def test_template_in_a_dots_only_linetype_shows_the_weight_a_draw_gets(qapp):
    from firepro3d import linetype_authoring as la
    proj, hid = _hidden_project()
    w = BlockEditorWidget(proj)
    assert w.toggle_capability("repeat")
    sc = w.editor_scene
    assert la.apply_pattern_rows(sc, [("dot", 0.0), ("gap", 3.0)])
    ss.set_current(linetype=hid.id, weight="Light")
    _assert_template_matches_draw(sc, "Light")


def test_template_outside_a_linetype_is_unaffected(qapp):
    proj, hid = _hidden_project()
    ss.set_current(linetype=hid.id, weight="Light")
    props = proj._get_geometry_template().get_properties()
    assert props["Linetype"]["value"] == "Hidden"
    assert not props["Linetype"].get("disabled")
    assert not props["Weight"].get("disabled")
    assert props["Weight"]["value"] == "Light"
    plain = BlockEditorWidget(proj).editor_scene        # editor, no repeat
    props = plain._get_geometry_template().get_properties()
    assert not props["Linetype"].get("disabled")
    assert not props["Weight"].get("disabled")
    assert ss.current_style() == {"linetype": hid.id, "weight": "Light"}


# ── review G5 R-N1: a dots-only pattern's Weight row is disabled ─────────

def test_dots_only_weight_row_is_disabled_with_why_tooltip(qapp):
    from firepro3d.linetype_authoring import apply_pattern_rows
    w, sc = _lt()
    pm = PropertyManager()
    pm.show_properties(BlockPropertiesInfo(sc, "Hidden", w))
    combo = pm._prop_widgets["Weight"]
    assert combo.isEnabled()                               # seed has a dash
    assert apply_pattern_rows(sc, [("dot", 0.0), ("gap", 3.0)])
    pm.show_properties(BlockPropertiesInfo(sc, "Hidden", w))
    combo = pm._prop_widgets["Weight"]
    assert not combo.isEnabled()
    assert combo.toolTip() == "Add a dash to set the linetype's Weight"
