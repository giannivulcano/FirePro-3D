"""SB4d guard 9 (D7): Elevation / Section / Detail Marker rows act on the
LINE only -- Colour tints crop box / leader / cut line / arrow; Fill, Font
and Scale are gone and stale stored values are ignored; the Detail row
reads back the item's _tag_color (the divergence the probe found)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, QSettings

from tests._sb4d_helpers import HEAD_R, dispose, head_def, pixel_at, plan_scene

KEYS = ("Elevation Marker", "Section Marker", "Detail Marker")


def test_rows_are_line_only(qapp):
    from firepro3d.display_manager import (_CATEGORY_MAP, _category_has_font,
                                           _category_has_scale, category_label)
    for k in KEYS:
        assert _CATEGORY_MAP[k]["fill"] is None and _CATEGORY_MAP[k]["font"] is None
        assert not _category_has_scale(k) and not _category_has_font(k)
        assert category_label(k) == k


def test_stale_fill_font_scale_are_ignored_and_colour_applies(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Detail")
        s = QSettings("GV", "FirePro3D")
        for prop, val in (("color", "#00ff00"), ("fill", "#ff00ff"), ("scale", 3.0), ("font", 30)):
            s.setValue(f"display/Detail Marker/{prop}", val)
        m = det.create_detail("Detail 1", QRectF(0.0, 0.0, 4000.0, 3000.0))   # apply_category_defaults
        assert m._tag_color.name() == "#00ff00" and m.pen().color().name() == "#00ff00"
        assert m.scale() == 1.0
        assert m.bubble.enclosing_radius() == pytest.approx(HEAD_R * ms.scale_manager.drawing_scale, rel=1e-3)
        from firepro3d.display_manager import DisplayManager
        st = DisplayManager(ms)._read_item_display_state(m, "Detail Marker")
        assert (st["color"], st["fill"], st["font"], st["scale"]) == ("#00ff00", None, None, 1.0)
    finally:
        dispose(ms, sec, tabs)


def test_colour_tints_a_placed_section_and_a_cardinal_and_stale_values_are_ignored(qapp):
    """T18 review I1: Colour reaches the marker (_marker_color) AND the pixels
    -- the section's cut line, the cardinal's wedge; stale fill / font /
    scale stored under both rows change nothing."""
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Section")
        head_def(ms, "Elevation")
        s = QSettings("GV", "FirePro3D")
        for key, col in (("Section Marker", "#00ff00"), ("Elevation Marker", "#0000ff")):
            for prop, val in (("color", col), ("fill", "#ff00ff"), ("scale", 3.0), ("font", 30)):
                s.setValue(f"display/{key}/{prop}", val)
        sec.seed_cardinals()                                   # the shipped creation paths
        placed = sec.place_section(QPointF(0.0, 0.0), QPointF(6000.0, 0.0))
        north = sec.marker("north")
        placed.refresh_heads()
        north.refresh_heads()
        assert placed._marker_color.name() == "#00ff00"
        assert north._marker_color.name() == "#0000ff"
        # cut line: A (0, 0) -> B (6000, 0), trimmed 500 mm at each head
        assert pixel_at(ms, QPointF(3000.0, 0.0)) == "#00ff00"
        # wedge: on the axis from the head centre toward the tip, 1.3 R out
        nx, ny = north.normal_scene()
        c, r = north._cardinal_centre(), north._rk()
        tip_side = QPointF(c.x() + nx * 1.3 * r, c.y() + ny * 1.3 * r)
        assert pixel_at(ms, tip_side) == "#0000ff"
        for m in (placed, north):
            assert m.scale() == 1.0
            assert not hasattr(m, "_fill_color") and not hasattr(m, "_display_scale")
        assert placed.head_a.enclosing_radius() == pytest.approx(HEAD_R * ms.scale_manager.drawing_scale, rel=1e-3)
        assert north.head.enclosing_radius() == pytest.approx(HEAD_R * ms.scale_manager.drawing_scale, rel=1e-3)
    finally:
        dispose(ms, sec, tabs)


def test_marker_items_split_into_three_rows(qapp):
    from firepro3d.display_manager import _items_for_category_static
    from firepro3d.paper_display import _category_for_item
    ms, sec, det, tabs = plan_scene()
    try:
        sec.seed_cardinals()
        placed = sec.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
        d = det.create_detail("Detail 1", QRectF(0.0, 0.0, 2000.0, 2000.0))
        assert len(_items_for_category_static(ms, "Elevation Marker")) == 4
        assert _items_for_category_static(ms, "Section Marker") == [placed]
        assert _items_for_category_static(ms, "Detail Marker") == [d]
        assert _category_for_item(placed) == "Section Marker"
        assert _category_for_item(sec.marker("north")) == "Elevation Marker"
        assert _category_for_item(d) == "Detail Marker"
    finally:
        dispose(ms, sec, tabs)


def test_section_row_is_seeded_from_the_pre_split_row(qapp):
    from firepro3d.display_manager import _migrate_display_keys, _project_entry
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Elevation Marker/color", "#123456")
    _migrate_display_keys(s)
    assert s.value("display/Section Marker/color") == "#123456"
    assert _project_entry({"Elevation Marker": {"color": "#654321"}}, "Section Marker") == {"color": "#654321"}


def test_section_split_migration_runs_once(qapp):
    """T18 review: the one-shot marker -- a Section Marker key the user removes
    after the first pass is not re-seeded from the Elevation Marker row."""
    from firepro3d.display_manager import _migrate_display_keys
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Elevation Marker/color", "#123456")
    _migrate_display_keys(s)
    assert s.value("display/Section Marker/color") == "#123456"
    s.remove("display/Section Marker/color")
    s.setValue("display/Elevation Marker/color", "#abcdef")
    _migrate_display_keys(s)
    assert s.value("display/Section Marker/color") is None


def test_dm_tree_carries_three_line_only_marker_rows_model_and_paper(qapp):
    """T18 review: each marker row sits in the Grids & Levels group of both the
    model tab and the paper tab, with no live Fill / Section editor (Scale
    and Font columns no longer exist)."""
    from firepro3d.display_manager import DisplayManager
    ms, sec, det, tabs = plan_scene()
    dlg = DisplayManager(ms)
    try:
        for k in KEYS:
            data = dlg._cat_data[k]
            assert data["tree_item"].parent().text(0).startswith("Grids & Levels")
            w = data["widgets"]
            assert not w["fill_btn"].isEnabled() and w["section_sel"] is None
            assert w["color_btn"].isEnabled() and w["opacity"].isEnabled()
            pdata = dlg._paper_cat_data[k]
            assert pdata["tree_item"].parent().text(0) == "Grids & Levels"
            assert not pdata["fill_btn"].isEnabled() and not pdata["section_btn"].isEnabled()
    finally:
        dlg.reject()
        dlg.deleteLater()
        dispose(ms, sec, tabs)


def test_cancel_reverts_a_previewed_section_marker_colour(qapp):
    """T18 review: the preview tints the live markers and writes the row's
    QSettings (the elevation scenes read them); Cancel puts the stored value back.
    (The live item's colour is not restored by Cancel -- markers are outside
    the dialog's item snapshot, as before SB4d; filed, not asserted here.)"""
    from firepro3d.display_manager import DisplayManager
    ms, sec, det, tabs = plan_scene()
    s = QSettings("GV", "FirePro3D")
    try:
        placed = sec.place_section(QPointF(0.0, 0.0), QPointF(6000.0, 0.0))
        s.setValue("display/Section Marker/color", "#112233")
        dlg = DisplayManager(ms)
        try:
            dlg._cat_data["Section Marker"]["widgets"]["color_btn"].setProperty("_color", "#00ff00")
            dlg._on_category_changed("Section Marker", "color", "#00ff00")
            assert placed._marker_color.name() == "#00ff00"
            assert s.value("display/Section Marker/color") == "#00ff00"
        finally:
            dlg.reject()
            dlg.deleteLater()
        assert s.value("display/Section Marker/color") == "#112233"
    finally:
        dispose(ms, sec, tabs)
