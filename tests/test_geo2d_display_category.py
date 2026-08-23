"""
tests/test_geo2d_display_category.py
=====================================
Verify the "2D Geometry" Display-Manager category:

1. The category key exists in the DM registry (_CATEGORY_MAP).
2. Setting the category colour changes a construction item's effective stroke
   colour (the value `paint()` reads, i.e. `_display_color` after
   apply_display_to_item is called).
3. Toggling the category visibility hides items.
4. A per-instance `_display_color` still wins over the category (cascade).

Test harness: mirrors test_visibility_display.py — bare QGraphicsScene +
minimal sprinkler_system stub.
"""

from __future__ import annotations

import types

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.display_manager import (
    _CATEGORY_MAP,
    _apply_to_scene_items,
    _read_category_from_settings,
    apply_display_to_item,
)
from firepro3d.construction_geometry import (
    LineItem,
    PolylineItem,
    RectangleItem,
    CircleItem,
    ArcItem,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def scene(qapp):
    """Bare QGraphicsScene with minimal stubs required by the DM helpers."""
    s = QGraphicsScene()
    ss = types.SimpleNamespace(nodes=[], pipes=[])
    s.sprinkler_system = ss
    # Empty geometry lists (model_space initialises these)
    s._polylines = []
    s._draw_lines = []
    s._draw_rects = []
    s._draw_circles = []
    s._draw_arcs = []
    return s


def _add_line(scene):
    item = LineItem(QPointF(0, 0), QPointF(100, 100), color="#ffffff")
    scene.addItem(item)
    scene._draw_lines.append(item)
    return item


def _add_rect(scene):
    item = RectangleItem(QPointF(0, 0), QPointF(100, 100), color="#ffffff")
    scene.addItem(item)
    scene._draw_rects.append(item)
    return item


def _add_circle(scene):
    item = CircleItem(QPointF(50, 50), 50, color="#ffffff")
    scene.addItem(item)
    scene._draw_circles.append(item)
    return item


def _add_polyline(scene):
    item = PolylineItem(QPointF(0, 0), color="#ffffff")
    item.append_point(QPointF(100, 100))
    scene.addItem(item)
    scene._polylines.append(item)
    return item


def _add_arc(scene):
    item = ArcItem(QPointF(50, 50), 50, 0, 180, color="#ffffff")
    scene.addItem(item)
    scene._draw_arcs.append(item)
    return item


# ---------------------------------------------------------------------------
# Test 1: "2D Geometry" category exists in the registry
# ---------------------------------------------------------------------------

class TestCategoryExists:
    def test_category_key_in_map(self):
        """'2D Geometry' must be registered in _CATEGORY_MAP."""
        assert "2D Geometry" in _CATEGORY_MAP, (
            "'2D Geometry' not found in _CATEGORY_MAP. "
            f"Keys present: {list(_CATEGORY_MAP.keys())}"
        )

    def test_category_has_required_fields(self):
        """The category entry must have at minimum color and visible fields."""
        cat = _CATEGORY_MAP["2D Geometry"]
        assert "color" in cat
        assert "visible" in cat


# ---------------------------------------------------------------------------
# Test 2: Category colour change reaches item._display_color
# ---------------------------------------------------------------------------

class TestCategoryColourApply:
    def test_set_category_colour_updates_display_color(self, qapp, scene):
        """apply_display_to_item must write _display_color onto construction items."""
        item = _add_line(scene)
        target_color = "#ff0000"
        apply_display_to_item(item, target_color, scale=1.0, opacity=100,
                              visible=True)
        assert item._display_color == target_color, (
            f"Expected _display_color={target_color!r}, got {item._display_color!r}"
        )

    def test_display_color_used_in_paint(self, qapp, scene):
        """After the DM sets _display_color, paint() must render that colour.

        Render a RectangleItem into a 200x200 image.  The rect spans
        [10,10]-[190,190] in scene space, so the left border is at x=10 scene
        units → pixel 10 in a 200px image (1:1 mapping).  After apply_display_to_item
        sets _display_color='#ff0000', sampling pixels along the left border
        must find a red-dominant pixel.
        """
        # Use a fresh scene so there's no interference from other items added
        # in the fixture.
        s2 = type(scene)()
        s2.sprinkler_system = scene.sprinkler_system
        s2._polylines = []
        s2._draw_lines = []
        s2._draw_rects = []
        s2._draw_circles = []
        s2._draw_arcs = []

        item = RectangleItem(QPointF(10, 10), QPointF(190, 190), color="#ffffff")
        s2.addItem(item)

        apply_display_to_item(item, "#ff0000", scale=1.0, opacity=100,
                              visible=True)

        size = 200
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        # Render scene [0,0,200,200] into image [0,0,200,200] → 1:1
        s2.render(p, QRectF(0, 0, size, size), QRectF(0, 0, size, size))
        p.end()

        # The left border is at x=10; sample a 3-pixel band [9..11] at mid height
        # to account for sub-pixel cosmetic pen placement.
        found_red = False
        for x in range(9, 13):
            c = QColor(img.pixel(x, 100))
            if c.red() > 150 and c.green() < 100 and c.blue() < 100:
                found_red = True
                break
        assert found_red, (
            "Expected a red stroke pixel near the left border (x=9-12, y=100) "
            f"but none found; pixels: "
            + str([(x, QColor(img.pixel(x, 100)).name()) for x in range(9, 13)])
        )

    def test_apply_to_scene_items_reaches_all_geo2d_types(self, qapp, scene):
        """_apply_to_scene_items must find and update all 5 geo2d item types."""
        ln = _add_line(scene)
        pl = _add_polyline(scene)
        rc = _add_rect(scene)
        ci = _add_circle(scene)
        ar = _add_arc(scene)

        vals = {"color": "#00ff00", "fill": None, "scale": 1.0,
                "opacity": 100, "visible": True, "font": None,
                "section": None, "section_pattern": None, "section_scale": 1.0}
        _apply_to_scene_items(scene, "2D Geometry", vals, respect_overrides=False)

        for item in (ln, pl, rc, ci, ar):
            assert item._display_color == "#00ff00", (
                f"{type(item).__name__}._display_color expected '#00ff00', "
                f"got {item._display_color!r}"
            )


# ---------------------------------------------------------------------------
# Test 3: Category visibility toggle hides / shows items
# ---------------------------------------------------------------------------

class TestCategoryVisibilityToggle:
    def test_hide_category_hides_all_items(self, qapp, scene):
        """Setting visible=False via apply_display_to_item hides geo2d items."""
        items = [
            _add_line(scene),
            _add_polyline(scene),
            _add_rect(scene),
            _add_circle(scene),
            _add_arc(scene),
        ]
        vals = {"color": "#ffffff", "fill": None, "scale": 1.0,
                "opacity": 100, "visible": False, "font": None,
                "section": None, "section_pattern": None, "section_scale": 1.0}
        _apply_to_scene_items(scene, "2D Geometry", vals, respect_overrides=False)

        for item in items:
            assert not item.isVisible(), (
                f"{type(item).__name__} should be hidden but is still visible"
            )

    def test_show_category_restores_visibility(self, qapp, scene):
        """Setting visible=True via apply_display_to_item shows geo2d items."""
        item = _add_line(scene)
        item.setVisible(False)

        vals = {"color": "#ffffff", "fill": None, "scale": 1.0,
                "opacity": 100, "visible": True, "font": None,
                "section": None, "section_pattern": None, "section_scale": 1.0}
        _apply_to_scene_items(scene, "2D Geometry", vals, respect_overrides=False)

        assert item.isVisible()

    def test_visibility_override_respected(self, qapp, scene):
        """An instance _display_overrides['visible']=False must survive a
        category visible=True sweep (respect_overrides=True path)."""
        item = _add_line(scene)
        item._display_overrides["visible"] = False
        item.setVisible(False)

        vals = {"color": "#ffffff", "fill": None, "scale": 1.0,
                "opacity": 100, "visible": True, "font": None,
                "section": None, "section_pattern": None, "section_scale": 1.0}
        _apply_to_scene_items(scene, "2D Geometry", vals, respect_overrides=True)

        assert not item.isVisible(), (
            "Per-instance visible=False override should prevent category "
            "visible=True from re-showing the item"
        )


# ---------------------------------------------------------------------------
# Test 4: Per-instance _display_color overrides category (cascade)
# ---------------------------------------------------------------------------

class TestPerInstanceOverrideCascade:
    def test_instance_display_color_wins_over_category(self, qapp, scene):
        """An item with _display_overrides['color'] retains its own colour
        when a category sweep runs with respect_overrides=True."""
        item = _add_line(scene)
        item._display_color = "#0000ff"
        item._display_overrides["color"] = "#0000ff"

        vals = {"color": "#ff0000", "fill": None, "scale": 1.0,
                "opacity": 100, "visible": True, "font": None,
                "section": None, "section_pattern": None, "section_scale": 1.0}
        _apply_to_scene_items(scene, "2D Geometry", vals, respect_overrides=True)

        # The category says red but the instance override says blue
        assert item._display_color == "#0000ff", (
            f"Instance override should win: expected '#0000ff', "
            f"got {item._display_color!r}"
        )

    def test_no_instance_override_gets_category_color(self, qapp, scene):
        """An item without _display_overrides gets the category colour."""
        item = _add_line(scene)
        item._display_overrides.clear()

        vals = {"color": "#ff00ff", "fill": None, "scale": 1.0,
                "opacity": 100, "visible": True, "font": None,
                "section": None, "section_pattern": None, "section_scale": 1.0}
        _apply_to_scene_items(scene, "2D Geometry", vals, respect_overrides=True)

        assert item._display_color == "#ff00ff"
