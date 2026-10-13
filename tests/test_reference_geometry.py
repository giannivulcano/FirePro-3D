"""Reference geometry on every 2D primitive (design RG1-RG14)."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import (ArcItem, CircleItem, EllipseItem, LineItem,
                                   PolylineItem, RectangleItem,
                                   RegularPolygonItem, SplineItem)
from firepro3d.block_definition import is_scaffold, is_scaffold_item


def _polyline():
    p = PolylineItem(QPointF(0, 0))
    p.append_point(QPointF(100, 0))
    p.append_point(QPointF(100, 50))
    return p


def _shapes():
    return [
        LineItem(QPointF(0, 0), QPointF(100, 0)),
        _polyline(),
        RectangleItem(QPointF(0, 0), QPointF(100, 50)),
        CircleItem(QPointF(0, 0), 50.0),
        ArcItem(QPointF(0, 0), 50.0, 0.0, 90.0),
        RegularPolygonItem(QPointF(0, 0), 6, 50.0),
        EllipseItem(QPointF(0, 0), 60.0, 30.0, 0.0),
        SplineItem([QPointF(0, 0), QPointF(50, 50), QPointF(100, 0)], 2),
    ]


_SHAPE_IDS = ["LineItem", "PolylineItem", "RectangleItem", "CircleItem",
              "ArcItem", "RegularPolygonItem", "EllipseItem", "SplineItem"]


@pytest.mark.parametrize("idx", range(8), ids=_SHAPE_IDS)
def test_flags_default_off_and_round_trip(qapp, idx):
    item = _shapes()[idx]
    assert item.reference is False and item.printed is False
    assert "reference" not in item.to_dict()          # RG2: normal records unchanged
    item.reference, item.printed = True, True
    d = item.to_dict()
    assert d["reference"] is True and d["printed"] is True
    assert d["type"] != "reference_line"
    back = type(item).from_dict(d)
    assert back.reference is True and back.printed is True
    assert back.style is not None                      # style kept (RG4)


def test_legacy_reference_line_record_loads_as_flagged_line(qapp):
    legacy = {"type": "reference_line", "pt1": [0, 0], "pt2": [10, 0],
              "color": "#abcdef", "lineweight": 1.0, "printed": True, "uid": "u1"}
    li = LineItem.from_dict(legacy)
    assert type(li) is LineItem
    assert li.reference is True and li.printed is True and li._uid == "u1"
    out = li.to_dict()
    assert out["type"] == "draw_line" and out["reference"] is True


def test_scaffold_predicate_is_flag_keyed(qapp):
    li = LineItem(QPointF(0, 0), QPointF(10, 0))
    c = CircleItem(QPointF(0, 0), 5.0)
    assert not is_scaffold(c.to_dict()) and not is_scaffold_item(c)
    c.reference = True
    assert is_scaffold(c.to_dict()) and is_scaffold_item(c)
    c.printed = True
    assert not is_scaffold(c.to_dict()) and not is_scaffold_item(c)
    assert is_scaffold({"type": "reference_line", "pt1": [0, 0], "pt2": [1, 0]})
    assert not is_scaffold(li.to_dict())


def test_text_has_no_reference_capability(qapp):
    from firepro3d.text_item import TextItem
    assert TextItem._REFERENCE_CAPABLE is False
    assert LineItem._REFERENCE_CAPABLE is True


# ── Task 2: paint hook, fill gate, compile op (RG4, RG5) ─────────────────────

from PyQt6.QtCore import QRectF, Qt  # noqa: E402
from PyQt6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PyQt6.QtWidgets import QGraphicsScene  # noqa: E402


def _render_item(item, size=160):
    sc = QGraphicsScene()
    sc.addItem(item)
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    sc.render(p, QRectF(0, 0, size, size), QRectF(-80, -80, 160, 160))
    p.end()
    sc.removeItem(item)
    return img


def _lit(img):
    return sum(1 for x in range(img.width()) for y in range(img.height())
               if img.pixelColor(x, y).value() > 40)


def test_reference_circle_paints_hairline_dashed_without_fill(qapp):
    c = CircleItem(QPointF(0, 0), 50.0)
    c.style["weight"] = "Thick"            # paper_display LineWeightDef("Thick", 0.50)
    c.fill_type = "solid"
    normal = _lit(_render_item(c))
    c2 = CircleItem.from_dict(c.to_dict())
    c2.reference = True
    ref = _lit(_render_item(c2))
    # Solid fill + weight lit thousands of px; a dashed hairline ring lights
    # fewer than the ring's circumference (2*pi*50 ~ 314 px).
    assert normal > 2000
    assert 0 < ref < 314
    assert c2.style == c.style                        # record untouched (RG4)
    pen = c2._reference_pen()
    assert pen.style() == Qt.PenStyle.DashLine and pen.isCosmetic() and pen.widthF() == 1.0


def test_paint_never_writes_display_colour_into_saved_data(qapp):
    c = CircleItem(QPointF(0, 0), 50.0, "#123456")
    c.reference = True
    c._display_color = "#888888"
    _render_item(c)
    assert c.to_dict()["style"]["colour"] == "#123456"   # RG5


def test_printed_reference_compiles_unstyled_dashed_op_and_no_fill(qapp):
    from firepro3d.block_definition import BlockDefinition
    c = CircleItem(QPointF(0, 0), 50.0)
    c.fill_type = "solid"
    c.reference, c.printed = True, True
    d = BlockDefinition.new(name="n", library="", series="",
                            primitives=[c.to_dict()], origin=(0.0, 0.0))
    ops = d.render_ops()
    assert len(ops) == 1                                   # no FILL op
    op = ops[0]
    assert op.weight is None and op.linetype is None and op.ends is None
    assert op.pen.style() == Qt.PenStyle.DashLine


# ── Task 3: Display Manager "Reference Geometry", migration, paper (RG12, RG13)

from PyQt6.QtCore import QSettings  # noqa: E402  (conftest-isolated store)


def _bare_scene_with(*items):
    from firepro3d.model_space import Model_Space
    s = Model_Space(scene_role="block_editor")
    for it in items:
        s.addItem(it)
        (s._draw_circles if isinstance(it, CircleItem) else s._draw_lines).append(it)
    return s


@pytest.fixture
def _scratch_display_keys():
    """Remove the display keys these tests write (isolated store, but shared
    across the session)."""
    keys = ("display/_reference_geometry_v1", "display/Reference Lines/color",
            "display/Reference Geometry/color", "display/2D Geometry/color")
    st = QSettings("GV", "FirePro3D")
    before = {k: st.value(k) for k in keys if st.contains(k)}
    yield
    st = QSettings("GV", "FirePro3D")
    for k in keys:
        st.remove(k)
    for k, v in before.items():
        st.setValue(k, v)
    st.sync()


def test_reference_geometry_category_collects_flagged_items_only(qapp):
    from firepro3d import display_manager as dm
    a, b = CircleItem(QPointF(0, 0), 5.0), CircleItem(QPointF(0, 0), 9.0)
    b.reference = True
    s = _bare_scene_with(a, b)
    assert "Reference Geometry" in dm._CATEGORY_MAP and "Reference Lines" not in dm._CATEGORY_MAP
    assert dm._items_for_category_static(s, "Reference Geometry") == [b]
    assert b not in dm._items_for_category_static(s, "2D Geometry")
    assert a in dm._items_for_category_static(s, "2D Geometry")


def test_legacy_reference_lines_settings_migrate(qapp, _scratch_display_keys):
    from firepro3d import display_manager as dm
    st = QSettings("GV", "FirePro3D")
    st.remove("display/_reference_geometry_v1")
    st.setValue("display/Reference Lines/color", "#ff00ff")
    st.remove("display/Reference Geometry/color")
    vals = dm._read_category_from_settings("Reference Geometry", st)
    assert vals["color"] == "#ff00ff"
    assert dm._project_entry({"Reference Lines": {"color": "#00ff00"}},
                             "Reference Geometry") == {"color": "#00ff00"}


def test_refresh_category_display_follows_the_flag(qapp, _scratch_display_keys):
    from firepro3d import display_manager as dm
    st = QSettings("GV", "FirePro3D")
    st.setValue("display/Reference Geometry/color", "#777777")
    st.setValue("display/2D Geometry/color", "#eeeeee")
    c = CircleItem(QPointF(0, 0), 5.0)
    c.reference = True
    dm.refresh_category_display(c)
    assert c._display_color == "#777777"
    c.reference = False
    dm.refresh_category_display(c)
    assert c._display_color == "#eeeeee"


def test_paper_category_for_reference_shape(qapp):
    from firepro3d.paper_display import _category_for_item
    c = CircleItem(QPointF(0, 0), 5.0)
    assert _category_for_item(c) == "Construction"
    c.reference = True
    assert _category_for_item(c) == "Reference Geometry"
