"""SB4d guard 9 (D7): Elevation / Section / Detail Marker rows act on the
LINE only -- Colour tints crop box / leader / cut line / arrow; Fill, Font
and Scale are gone and stale stored values are ignored; the Detail row
reads back the item's _tag_color (the divergence the probe found)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, QSettings

from tests._sb4d_helpers import HEAD_R, dispose, head_def, plan_scene

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
