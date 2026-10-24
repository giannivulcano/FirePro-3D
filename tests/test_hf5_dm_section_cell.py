"""HF5 Task 7 -- DM section cell is a Fill Type selector."""
import json

from PyQt6.QtCore import QPointF, QSettings

from firepro3d import display_manager as dm
from firepro3d import fill_types as ft
from firepro3d.fill_layers import BackgroundLayer, FillLayers, PatternLayer
from firepro3d.ui_kit import Selector


def _dm(model_space):
    return dm.DisplayManager(model_space)


def _wall(ms):
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(0, 0), QPointF(2000, 0))
    ms._walls.append(w)
    ms.addItem(w)
    return w


def test_wall_and_floor_cells_are_selectors_roof_has_none(qapp, model_space):
    d = _dm(model_space)
    try:
        for key in ("Wall", "Floor"):
            w = d._cat_data[key]["widgets"]["section_sel"]
            assert isinstance(w, Selector)
            assert d._tree.itemWidget(d._cat_data[key]["tree_item"], dm._COL_SECTION) is w
            assert w.currentText() == f"{key} Section"
            assert set(t.name for t in ft.project_table().all()) <= {
                w.itemText(i) for i in range(w.count())}
        assert d._cat_data["Roof"]["widgets"].get("section_sel") is None
        assert d._tree.itemWidget(d._cat_data["Roof"]["tree_item"], dm._COL_SECTION) is None
        assert d._cat_data["Pipe"]["widgets"].get("section_sel") is None
        assert "section_btn" not in d._cat_data["Wall"]["widgets"]
        assert not hasattr(dm, "SectionPatternDialog")
        assert not hasattr(d, "_pick_section")
    finally:
        d.close()


def test_picking_a_type_applies_to_walls_and_persists_on_ok(qapp, model_space):
    t = ft.project_table().ensure_named("Concrete", ft.legacy_section_layers("#00ff00", "diagonal", 1.0))
    wall = _wall(model_space)
    d = _dm(model_space)
    try:
        w = d._cat_data["Wall"]["widgets"]["section_sel"]
        w.setCurrentText("Concrete")
        assert wall._display_section_type == t.id          # live preview
        d.accept()
    finally:
        d.close()
    vals = dm._read_category_from_settings("Wall")
    assert vals["section_type"] == "Concrete" and vals["section_look"]["background"]["color"] == "#00ff00"
    s = QSettings("GV", "FirePro3D")
    assert not s.contains("display/Wall/section") and not s.contains("display/Wall/section_pattern")
    assert wall._display_section_type == t.id


def test_instance_pick_stores_the_id_override_and_reset_returns_to_category(qapp, model_space):
    t = ft.project_table().ensure_named("Concrete", ft.legacy_section_layers("#00ff00", "diagonal", 1.0))
    wall = _wall(model_space)
    d = _dm(model_space)
    try:
        inst = d._inst_data[id(wall)]["widgets"]["section_sel"]
        assert inst.currentText() == "Wall Section"
        inst.setCurrentText("Concrete")
        assert wall._display_overrides["section_type"] == t.id     # R7: the id
        assert wall._display_section_type == t.id
        # a category change no longer reaches the overridden instance
        d._cat_data["Wall"]["widgets"]["section_sel"].setCurrentText("Solid Black")
        assert wall._display_section_type == t.id
        d._reset_instance(wall)
        assert "section_type" not in wall._display_overrides
        assert inst.currentText() == "Solid Black"
        assert wall._display_section_type == ft.project_table().by_name("Solid Black").id
    finally:
        d.close()


def test_category_pick_propagates_to_instances_without_an_override(qapp, model_space):
    ft.project_table().ensure_named("Concrete", ft.legacy_section_layers("#00ff00", "diagonal", 1.0))
    a, b = _wall(model_space), _wall(model_space)
    d = _dm(model_space)
    try:
        d._inst_data[id(b)]["widgets"]["section_sel"].setCurrentText("Solid Black")   # b overrides
        d._cat_data["Wall"]["widgets"]["section_sel"].setCurrentText("Concrete")
        assert d._inst_data[id(a)]["widgets"]["section_sel"].currentText() == "Concrete"
        assert d._inst_data[id(b)]["widgets"]["section_sel"].currentText() == "Solid Black"
    finally:
        d.close()


def test_a_missing_item_type_shows_a_question_entry_not_another_type(qapp, model_space):
    wall = _wall(model_space)
    wall._display_section_type = "gone-0123456789"
    d = _dm(model_space)
    try:
        sel = d._inst_data[id(wall)]["widgets"]["section_sel"]
        assert sel.currentText() == "? gone-012"
    finally:
        d.close()


def test_reset_all_selects_the_factory_type(qapp, model_space):
    ft.project_table().ensure_named("Concrete", ft.legacy_section_layers("#00ff00", "diagonal", 1.0))
    d = _dm(model_space)
    try:
        sel = d._cat_data["Floor"]["widgets"]["section_sel"]
        sel.setCurrentText("Concrete")
        d._reset_model_tab()
        assert sel.currentText() == "Floor Section"
    finally:
        d.close()


def test_selector_follows_the_table_after_refresh(qapp, model_space):
    d = _dm(model_space)
    try:
        sel = d._cat_data["Wall"]["widgets"]["section_sel"]
        assert "Late" not in [sel.itemText(i) for i in range(sel.count())]
        ft.project_table().add(ft.FillType("late", "Late", FillLayers(BackgroundLayer("#010203", 1.0))))
        d._refresh_section_selectors()
        assert "Late" in [sel.itemText(i) for i in range(sel.count())]
        assert sel.currentText() == "Wall Section"          # selection kept
    finally:
        d.close()


def test_token_and_no_fill_bodies_survive_the_conversion():
    """The old dialog offered Automatic / Accent and No Fill for the body colour;
    both convert (token kept, '' = no body)."""
    from firepro3d.constants import TOKEN_ACCENT
    lay = ft.legacy_section_layers(TOKEN_ACCENT, "diagonal", 1.0)
    assert lay.background == BackgroundLayer(TOKEN_ACCENT, 1.0)
    assert ft.legacy_section_layers("", "diagonal", 1.0).background is None


def test_set_as_default_writes_type_and_look_and_no_legacy_default_keys(qapp, model_space):
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Wall/default_section", "#123456")            # a stale legacy default
    d = _dm(model_space)
    try:
        d._set_model_as_default()
    finally:
        d.close()
    assert s.value("display/Wall/default_section_type") == "Wall Section"
    assert json.loads(s.value("display/Wall/default_section_look"))["pattern"]["ref"]
    assert not s.contains("display/Wall/default_section")
    assert not s.contains("display/Wall/section")


def _grab(widget, w=200):
    from PyQt6.QtGui import QImage
    widget.resize(w, widget.height())
    return widget.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)


def test_closed_section_cell_shows_the_swatch_left_of_the_name(qapp, model_space):
    ft.project_table().ensure_named("Swatchy", FillLayers(BackgroundLayer("#00ff00", 1.0)))
    d = _dm(model_space)
    try:
        sel = d._cat_data["Wall"]["widgets"]["section_sel"]
        sel.setCurrentText("Swatchy")
        img = _grab(sel)
        y = img.height() // 2
        assert img.pixelColor(14, y).name() == "#00ff00"        # inside the swatch
        assert img.pixelColor(img.width() - 40, y).name() != "#00ff00"
        assert sel.height() == Selector().height()             # row height unchanged
    finally:
        d.close()


def test_a_plain_selector_ignores_item_icons(qapp):
    """The swatch is opt-in: every other Selector paints identically with or
    without an item icon."""
    import hashlib
    from PyQt6.QtGui import QIcon, QPixmap, QColor

    def digest(with_icon):
        s = Selector()
        pm = QPixmap(40, 20)
        pm.fill(QColor("#00ff00"))
        s.addItem(QIcon(pm) if with_icon else QIcon(), "Same")
        img = _grab(s)
        return hashlib.sha256(bytes(img.constBits().asarray(img.sizeInBytes()))).hexdigest()
    assert digest(True) == digest(False)
