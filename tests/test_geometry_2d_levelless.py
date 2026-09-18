"""
test_geometry_2d_levelless.py
=============================
Containment contract C3: the 8 non-text 2D primitives are definition-local and
**level-less** — they carry no level attribute, no Level/Level-Offset/Elevation
property rows, and no level in serialization. Level scope lives on the placed
BlockInstance instead (see test_block_instance_level.py). The reference-graphic
``layer`` tag is unaffected.
"""

from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import (
    LineItem, PolylineItem, RectangleItem, CircleItem, ArcItem,
    RegularPolygonItem, EllipseItem, SplineItem, GeometryTemplate,
)


def _all_primitives():
    return [
        LineItem(QPointF(0, 0), QPointF(100, 0)),
        PolylineItem(QPointF(0, 0)),
        RectangleItem(QPointF(0, 0), QPointF(100, 100)),
        CircleItem(QPointF(0, 0), 50.0),
        ArcItem(QPointF(0, 0), 50.0, 0.0, 90.0),
        RegularPolygonItem(QPointF(0, 0), 6, 50.0),
        EllipseItem(QPointF(0, 0), 50.0, 30.0),
        SplineItem([QPointF(0, 0), QPointF(50, 50), QPointF(100, 0)]),
    ]


def test_primitives_have_no_level_attribute(qapp):
    for item in _all_primitives():
        assert not hasattr(item, "level"), f"{type(item).__name__} still has .level"
        assert not hasattr(item, "_level_offset_mm"), \
            f"{type(item).__name__} still has _level_offset_mm"


def test_primitive_properties_have_no_level_rows(qapp):
    for item in _all_primitives():
        props = item.get_properties()
        for banned in ("Level", "Level Offset", "Elevation"):
            assert banned not in props, \
                f"{type(item).__name__} still exposes {banned!r}"


def test_primitive_to_dict_has_no_level_keys(qapp):
    for item in _all_primitives():
        d = item.to_dict()
        assert "level" not in d, f"{type(item).__name__} still serializes level"
        assert "level_offset_mm" not in d, \
            f"{type(item).__name__} still serializes level_offset_mm"


def test_geometry_template_is_level_less(qapp):
    t = GeometryTemplate()
    assert not hasattr(t, "level")
    assert not hasattr(t, "_level_offset_mm")
    assert "Level" not in t.get_properties()


def test_layer_tag_still_round_trips(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.layer = "WALLS"
    assert r.to_dict().get("layer") == "WALLS"
    r2 = RectangleItem.from_dict(r.to_dict())
    assert r2.layer == "WALLS"


def test_definition_ignores_stray_level_on_primitive_dict(qapp):
    from firepro3d.block_definition import BlockDefinition
    rect = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    prim = rect.to_dict()
    prim["level"] = "Level 1"          # pre-C3 dict carrying a stray level
    prim["level_offset_mm"] = 300.0
    d = BlockDefinition(id="b1", version=1, name="t", library="",
                        series="", scale_mode="default", origin=(0.0, 0.0),
                        attributes=[], primitives=[prim])
    ops = d.render_ops()
    assert any(not p.isEmpty() for *_h, p in ops)
