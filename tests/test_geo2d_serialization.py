"""tests/test_geo2d_serialization.py

Serialization round-trip for Geometry2DMixin fields on both paths:

Path A — file I/O:
    scene.save_to_file(path) → scene.load_from_file(path)
    Uses SceneIOMixin.save_to_file / load_from_file which call
    RectangleItem.to_dict() / RectangleItem.from_dict() internally.

Path B — undo snapshot:
    scene._capture_network() / scene._restore_network(state)
    Rebuilds draw geometry items from their to_dict / from_dict in place.

Both paths verify that level, _level_offset_mm, fill_type, and
_display_fill_color survive a round-trip without any information loss.

Additionally (Task 5):
- RegularPolygonItem round-trips through both paths.
- Closed PolylineItem flag round-trips through the file path.
- paste_items() dispatches "polygon" type correctly.
"""

from __future__ import annotations

import json
import math
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from firepro3d.model_space import Model_Space
from firepro3d.level_manager import LevelManager
from firepro3d.geometry_2d import RectangleItem, RegularPolygonItem, PolylineItem
from firepro3d.scale_manager import ScaleManager


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_scene(qapp):
    """Minimal Model_Space with a LevelManager and ScaleManager."""
    s = Model_Space()
    lm = LevelManager()
    s._level_manager = lm
    s.scale_manager = ScaleManager()
    return s


def _add_rect(scene, level="Level 2", offset=250.0, fill="solid",
              color="#123456") -> RectangleItem:
    """Create and register a RectangleItem with mixin fields set."""
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.level = level
    r._level_offset_mm = offset
    r.fill_type = fill
    r._display_fill_color = color
    scene._draw_rects.append(r)
    scene.addItem(r)
    return r


# ── Path A: file round-trip ───────────────────────────────────────────────────
# Containment C8: loose construction geometry is forbidden model content. It is
# no longer written on save and read-but-discarded on load, so the FILE path
# clean-drops it (the undo-snapshot Path B below still round-trips it).

def test_file_save_omits_loose_geometry(qapp, tmp_path):
    """save_to_file no longer writes loose draw geometry (containment C8)."""
    scene = _make_scene(qapp)
    _add_rect(scene, level="Level 2", offset=250.0,
              fill="solid", color="#123456")

    fp = str(tmp_path / "test_project.fpd")
    ok = scene.save_to_file(fp)
    assert ok, "save_to_file returned False"

    with open(fp) as f:
        payload = json.load(f)
    assert payload.get("draw_rectangles", []) == []
    assert "polylines" not in payload or payload["polylines"] == []


def test_file_load_drops_loose_rect(qapp, tmp_path):
    """A saved rect is clean-dropped on load (containment C8)."""
    scene = _make_scene(qapp)
    _add_rect(scene, level="Level 2", offset=250.0,
              fill="solid", color="#123456")

    fp = str(tmp_path / "test_project.fpd")
    scene.save_to_file(fp)

    scene2 = _make_scene(qapp)
    scene2.load_from_file(fp)
    assert scene2._draw_rects == []


def test_legacy_loose_rect_dropped_on_load(qapp, tmp_path):
    """A legacy .fpd with a draw_rectangles entry clean-drops on load."""
    payload = {
        "version": 12,
        "draw_rectangles": [{
            "type": "rectangle", "p1": [0, 0], "p2": [80, 80],
            "level": "Level 1", "fill": "hatch", "fill_pattern": "diagonal",
            "fill_color": "#aabbcc",
        }],
        "walls": [],
    }
    fp = str(tmp_path / "legacy_rect.fpd")
    with open(fp, "w") as f:
        json.dump(payload, f)

    scene2 = _make_scene(qapp)
    scene2.load_from_file(fp)  # must not raise
    assert scene2._draw_rects == []


# ── Path B: undo snapshot round-trip ─────────────────────────────────────────

def test_undo_roundtrip_offset_and_fill(qapp):
    """_capture_network / _restore_network preserves level, offset, and fill."""
    scene = _make_scene(qapp)
    r = _add_rect(scene, level="Level 3", offset=99.0,
                  fill="hatch", color="#ffcc00")

    # Capture state
    state = scene._capture_network()

    # Mutate in-place
    r._level_offset_mm = 0.0
    r.fill_type = "none"
    r._display_fill_color = None

    # Restore
    scene._restore_network(state)

    assert len(scene._draw_rects) == 1, (
        f"Expected 1 draw_rect after _restore_network, "
        f"got {len(scene._draw_rects)}"
    )
    restored = scene._draw_rects[0]

    assert restored.level == "Level 3"
    assert restored._level_offset_mm == pytest.approx(99.0)
    assert restored.fill_type == "hatch"
    assert restored._display_fill_color == "#ffcc00"


def test_undo_roundtrip_multiple_rects(qapp):
    """Multiple rects with different offsets all survive the undo round-trip."""
    scene = _make_scene(qapp)
    _add_rect(scene, level="Level 1", offset=0.0, fill="none", color="#ffffff")
    _add_rect(scene, level="Level 2", offset=150.0, fill="solid", color="#336699")

    state = scene._capture_network()

    # Wipe both rects' mixin fields
    for r in scene._draw_rects:
        r._level_offset_mm = 999.0
        r.fill_type = "solid"

    scene._restore_network(state)

    assert len(scene._draw_rects) == 2

    offsets = sorted(r._level_offset_mm for r in scene._draw_rects)
    assert offsets[0] == pytest.approx(0.0)
    assert offsets[1] == pytest.approx(150.0)

    fill_types = {r.fill_type for r in scene._draw_rects}
    assert "none" in fill_types
    assert "solid" in fill_types


def test_to_dict_from_dict_direct(qapp):
    """Unit-level check: to_dict / from_dict alone round-trip all mixin fields."""
    r = RectangleItem(QPointF(10, 20), QPointF(110, 120))
    r.level = "Level 2"
    r._level_offset_mm = 777.5
    r.fill_type = "solid"
    r.fill_pattern = "grid"
    r._display_fill_color = "#deadbe"

    d = r.to_dict()

    assert d["level"] == "Level 2"
    assert d["level_offset_mm"] == pytest.approx(777.5)
    assert d["fill"]["type"] == "solid"
    assert d["fill"]["color"] == "#deadbe"

    r2 = RectangleItem.from_dict(d)
    assert r2.level == "Level 2"
    assert r2._level_offset_mm == pytest.approx(777.5)
    assert r2.fill_type == "solid"
    assert r2._display_fill_color == "#deadbe"


# ── Task 5: RegularPolygonItem + closed PolylineItem dual serialization ───────

def test_polygon_survives_undo_capture(qapp):
    """_capture_network / _restore_network round-trips RegularPolygonItem."""
    scene = _make_scene(qapp)
    p = RegularPolygonItem(QPointF(10, 20), sides=5, radius_mm=80.0)
    scene.addItem(p)
    scene._draw_polygons.append(p)

    snap = scene._capture_network()
    assert "polygons" in snap
    assert len(snap["polygons"]) == 1

    scene._draw_polygons.clear()
    scene.removeItem(p)

    scene._restore_network(snap)
    assert len(scene._draw_polygons) == 1
    assert scene._draw_polygons[0]._sides == 5


def test_restore_network_clears_existing_polygons(qapp):
    """_restore_network must not duplicate polygons on a second restore."""
    scene = _make_scene(qapp)
    p = RegularPolygonItem(QPointF(0, 0), sides=6, radius_mm=50.0)
    scene.addItem(p)
    scene._draw_polygons.append(p)

    snap = scene._capture_network()

    # Restore twice — polygon count must remain 1.
    scene._restore_network(snap)
    scene._restore_network(snap)
    assert len(scene._draw_polygons) == 1


def test_polygon_file_dropped_on_load(qapp, tmp_path):
    """Containment C8: a loose RegularPolygonItem clean-drops through the file path."""
    scene = _make_scene(qapp)
    p = RegularPolygonItem(QPointF(0, 0), sides=8, radius_mm=60.0,
                           rotation_deg=30.0, inscribed=False)
    scene.addItem(p)
    scene._draw_polygons.append(p)

    f = tmp_path / "poly.fpd"
    scene.save_to_file(str(f))

    scene2 = _make_scene(qapp)
    scene2.load_from_file(str(f))

    assert scene2._draw_polygons == []


def test_closed_polyline_file_dropped_on_load(qapp, tmp_path):
    """Containment C8: a loose PolylineItem clean-drops through the file path."""
    scene = _make_scene(qapp)
    pl = PolylineItem(QPointF(0, 0))
    pl.append_point(QPointF(100, 0))
    pl.append_point(QPointF(0, 100))
    pl.close()

    scene.addItem(pl)
    scene._polylines.append(pl)

    f = tmp_path / "pl.fpd"
    scene.save_to_file(str(f))

    scene2 = _make_scene(qapp)
    scene2.load_from_file(str(f))

    assert scene2._polylines == []


def test_polygon_paste(qapp):
    """paste_items dispatches 'polygon' type and appends to _draw_polygons."""
    scene = _make_scene(qapp)
    p = RegularPolygonItem(QPointF(0, 0), sides=6, radius_mm=50.0)
    d = p.to_dict()

    QApplication.clipboard().setText(json.dumps([d]))

    before = len(scene._draw_polygons)
    scene.paste_items(QPointF(0, 0))
    assert len(scene._draw_polygons) == before + 1
    assert scene._draw_polygons[-1]._sides == 6


def test_polygon_included_in_items_on_level(qapp):
    """_items_on_level must include RegularPolygonItem entries."""
    scene = _make_scene(qapp)
    from firepro3d.geometry_2d import RegularPolygonItem
    p = RegularPolygonItem(QPointF(0, 0), sides=5, radius_mm=40.0)
    p.level = "Level 1"
    scene.addItem(p)
    scene._draw_polygons.append(p)
    items = scene._items_on_level("Level 1")
    assert p in items
