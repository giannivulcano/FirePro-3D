"""
tests/test_geo2d_polygon_seams.py
==================================
Behavior tests for the parallel-list seam fixes that wire RegularPolygonItem
into the same collectors its sibling geo2d types participate in:

1. Level-visibility (Fix 1): a polygon on Level 1 is hidden when Level 2 is
   active with no overlapping view range.  Mirrors test_geo2d_level_manager.py.

2. "2D Geometry" display-category (Fix 2): toggling the category visibility
   off hides a polygon, and a category colour sweep reaches the polygon's
   _display_color.  Mirrors test_geo2d_display_category.py.

These tests were written to be RED before Fix 1 / Fix 2 and GREEN after.
"""

from __future__ import annotations

import types

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.model_space import Model_Space
from firepro3d.level_manager import LevelManager
from firepro3d.display_manager import _apply_to_scene_items
from firepro3d.construction_geometry import RegularPolygonItem
from PyQt6.QtWidgets import QGraphicsScene


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_scene(qapp) -> Model_Space:
    """Model_Space with a seeded LevelManager (Level 1 at 0 mm, Level 2 at 3048 mm)."""
    s = Model_Space()
    s._level_manager = LevelManager()
    return s


def _add_polygon(scene, level: str = "Level 1", offset: float = 0.0,
                 color: str = "#ffffff") -> RegularPolygonItem:
    """Add a hexagonal RegularPolygonItem to the scene on the given level."""
    p = RegularPolygonItem(center=QPointF(100, 100), sides=6, radius_mm=50.0,
                            color=color)
    p.level = level
    p._level_offset_mm = offset
    scene._draw_polygons.append(p)
    scene.addItem(p)
    return p


def _bare_scene(qapp) -> QGraphicsScene:
    """Bare QGraphicsScene with all geo2d list stubs, mirroring the DM test fixture."""
    s = QGraphicsScene()
    s.sprinkler_system = types.SimpleNamespace(nodes=[], pipes=[])
    s._polylines = []
    s._draw_lines = []
    s._draw_rects = []
    s._draw_circles = []
    s._draw_arcs = []
    s._draw_polygons = []
    return s


# ---------------------------------------------------------------------------
# Fix 1: Level-visibility via LevelManager.apply_to_scene
# ---------------------------------------------------------------------------

class TestPolygonLevelVisibility:

    def test_polygon_visible_on_its_own_level(self, qapp):
        """A polygon on Level 1 is visible when Level 1 is active."""
        s = _make_scene(qapp)
        pg = _add_polygon(s, level="Level 1")
        s._level_manager.apply_to_scene(
            s, active_level="Level 1", view_height=2896.0, view_depth=-1000.0
        )
        assert pg.isVisible() is True

    def test_polygon_hidden_when_different_level_active(self, qapp):
        """A polygon on Level 1 must be hidden when Level 2 is active and the
        view range does not extend down to Level 1's elevation (0 mm).

        This is the canonical RED test for Fix 1: without the
        ``for item in getattr(scene, "_draw_polygons", [])`` loop in
        level_manager.py, apply_to_scene never visits the polygon and it stays
        visible at its initial Qt-default visibility state.
        """
        s = _make_scene(qapp)
        pg = _add_polygon(s, level="Level 1", offset=0.0)
        # Level 2 is at 3048 mm.  view_depth=200 means the visible window is
        # [3048+200, 3048+2896] = [3248, 5944], which does NOT include Level 1
        # at elevation 0 mm, so the polygon should be hidden.
        s._level_manager.apply_to_scene(
            s, active_level="Level 2", view_height=2896.0, view_depth=200.0
        )
        assert pg.isVisible() is False, (
            "Polygon on Level 1 should be hidden when Level 2 is active with "
            "a view range that does not include elevation 0."
        )

    def test_polygon_visible_when_z_range_overlaps(self, qapp):
        """A polygon on Level 1 is visible when the Level 2 view range includes 0."""
        s = _make_scene(qapp)
        pg = _add_polygon(s, level="Level 1", offset=0.0)
        # view_depth=-500 from Level 2 (3048 mm) → window is [2548, 5944],
        # which includes Level 1 at 0 mm (within [-1000, 2548] overlap? No.
        # Actually: view_depth is the bottom offset from the level elevation.
        # Level 2 elev = 3048; bottom = 3048 + (-500) = 2548; top = 3048+2896=5944.
        # Level 1 elev = 0, which is NOT in [2548, 5944].
        # Use a very large view depth to go below Level 1.
        s._level_manager.apply_to_scene(
            s, active_level="Level 2", view_height=3000.0, view_depth=-4000.0
        )
        assert pg.isVisible() is True, (
            "Polygon on Level 1 (elev 0) should be visible when the Level 2 "
            "view range extends down to include elevation 0."
        )


# ---------------------------------------------------------------------------
# Fix 2: "2D Geometry" display-category via _apply_to_scene_items
# ---------------------------------------------------------------------------

class TestPolygonDisplayCategory:

    def test_hide_category_hides_polygon(self, qapp):
        """Setting the '2D Geometry' category visibility to False must hide a
        RegularPolygonItem.

        This is the canonical RED test for Fix 2: without
        ``items.extend(getattr(scene, "_draw_polygons", []))`` in
        display_manager.py, the polygon is never visited and stays visible.
        """
        s = _bare_scene(qapp)
        pg = RegularPolygonItem(center=QPointF(50, 50), sides=6, radius_mm=30.0,
                                color="#ffffff")
        s.addItem(pg)
        s._draw_polygons.append(pg)

        vals = {
            "color": "#ffffff", "fill": None, "scale": 1.0,
            "opacity": 100, "visible": False, "font": None,
            "section": None, "section_pattern": None, "section_scale": 1.0,
        }
        _apply_to_scene_items(s, "2D Geometry", vals, respect_overrides=False)

        assert not pg.isVisible(), (
            "RegularPolygonItem should be hidden after '2D Geometry' "
            "category visible=False sweep, but it is still visible."
        )

    def test_category_colour_reaches_polygon_display_color(self, qapp):
        """A colour sweep on '2D Geometry' must write _display_color on a polygon."""
        s = _bare_scene(qapp)
        pg = RegularPolygonItem(center=QPointF(50, 50), sides=6, radius_mm=30.0,
                                color="#ffffff")
        s.addItem(pg)
        s._draw_polygons.append(pg)

        vals = {
            "color": "#ff0000", "fill": None, "scale": 1.0,
            "opacity": 100, "visible": True, "font": None,
            "section": None, "section_pattern": None, "section_scale": 1.0,
        }
        _apply_to_scene_items(s, "2D Geometry", vals, respect_overrides=False)

        assert pg._display_color == "#ff0000", (
            f"Expected polygon._display_color='#ff0000', got {pg._display_color!r}"
        )

    def test_show_category_shows_polygon(self, qapp):
        """Setting visible=True on '2D Geometry' must restore polygon visibility."""
        s = _bare_scene(qapp)
        pg = RegularPolygonItem(center=QPointF(50, 50), sides=6, radius_mm=30.0,
                                color="#ffffff")
        pg.setVisible(False)
        s.addItem(pg)
        s._draw_polygons.append(pg)

        vals = {
            "color": "#ffffff", "fill": None, "scale": 1.0,
            "opacity": 100, "visible": True, "font": None,
            "section": None, "section_pattern": None, "section_scale": 1.0,
        }
        _apply_to_scene_items(s, "2D Geometry", vals, respect_overrides=False)

        assert pg.isVisible(), (
            "RegularPolygonItem should be visible after '2D Geometry' "
            "category visible=True sweep."
        )
