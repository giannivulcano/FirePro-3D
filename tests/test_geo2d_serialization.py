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
"""

from __future__ import annotations

import json
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.model_space import Model_Space
from firepro3d.level_manager import LevelManager
from firepro3d.construction_geometry import RectangleItem
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

def test_file_roundtrip_offset_and_fill(qapp, tmp_path):
    """save_to_file / load_from_file preserves level, offset, fill, and color."""
    scene = _make_scene(qapp)
    r = _add_rect(scene, level="Level 2", offset=250.0,
                  fill="solid", color="#123456")

    fp = str(tmp_path / "test_project.fpd")
    ok = scene.save_to_file(fp)
    assert ok, "save_to_file returned False"

    # Load into a fresh scene
    scene2 = _make_scene(qapp)
    scene2.load_from_file(fp)

    assert len(scene2._draw_rects) == 1, (
        f"Expected 1 draw_rect after load, got {len(scene2._draw_rects)}"
    )
    loaded = scene2._draw_rects[0]

    assert loaded.level == "Level 2"
    assert loaded._level_offset_mm == pytest.approx(250.0)
    assert loaded.fill_type == "solid"
    assert loaded._display_fill_color == "#123456"


def test_file_roundtrip_zero_offset_not_stored(qapp, tmp_path):
    """A zero offset is omitted from the JSON (optimized dict path)."""
    scene = _make_scene(qapp)
    r = RectangleItem(QPointF(0, 0), QPointF(50, 50))
    # leave _level_offset_mm at default 0.0
    scene._draw_rects.append(r)
    scene.addItem(r)

    fp = str(tmp_path / "zero_offset.fpd")
    scene.save_to_file(fp)

    with open(fp) as f:
        payload = json.load(f)

    rects = payload.get("draw_rectangles", [])
    assert len(rects) == 1
    # _geom2d_to_dict omits level_offset_mm when it's 0.0
    assert "level_offset_mm" not in rects[0], (
        "Zero offset should be omitted from serialized dict"
    )


def test_file_roundtrip_fill_none_not_stored(qapp, tmp_path):
    """fill_type='none' is omitted from JSON."""
    scene = _make_scene(qapp)
    r = RectangleItem(QPointF(0, 0), QPointF(50, 50))
    # fill_type defaults to "none"
    scene._draw_rects.append(r)
    scene.addItem(r)

    fp = str(tmp_path / "fill_none.fpd")
    scene.save_to_file(fp)

    with open(fp) as f:
        payload = json.load(f)

    rects = payload.get("draw_rectangles", [])
    assert len(rects) == 1
    assert "fill" not in rects[0], "fill_type='none' should be omitted from dict"


def test_file_roundtrip_hatch_fill(qapp, tmp_path):
    """Hatch fill_type and pattern survive a file round-trip."""
    scene = _make_scene(qapp)
    r = RectangleItem(QPointF(0, 0), QPointF(80, 80))
    r.fill_type = "hatch"
    r.fill_pattern = "diagonal"
    r._display_fill_color = "#aabbcc"
    scene._draw_rects.append(r)
    scene.addItem(r)

    fp = str(tmp_path / "hatch.fpd")
    scene.save_to_file(fp)

    scene2 = _make_scene(qapp)
    scene2.load_from_file(fp)

    assert len(scene2._draw_rects) == 1
    loaded = scene2._draw_rects[0]
    assert loaded.fill_type == "hatch"
    assert loaded.fill_pattern == "diagonal"
    assert loaded._display_fill_color == "#aabbcc"


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
