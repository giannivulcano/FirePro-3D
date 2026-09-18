"""tests/test_hatch_migration.py

Verifies that:
  1. HatchItem class is gone from firepro3d.annotations.
  2. Under containment C8, legacy "hatches" entries in .fpd files are
     read-but-discarded on load (they used to migrate into loose
     PolylineItems, which are now forbidden loose content).
"""

from __future__ import annotations

import json
import pytest

from PyQt6.QtCore import QPointF

from firepro3d.model_space import Model_Space
from firepro3d.level_manager import LevelManager
from firepro3d.scale_manager import ScaleManager
from firepro3d.geometry_2d import PolylineItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scene(qapp) -> Model_Space:
    s = Model_Space()
    s._level_manager = LevelManager()
    s.scale_manager = ScaleManager()
    return s


def _square_elements():
    """Return a HatchItem-format element list for a 100x100 square at origin.

    Element format: [el_type, x, y]
      0 = MoveToElement, 1 = LineToElement
    """
    return [
        [0, 0.0, 0.0],    # MoveTo  (0, 0)
        [1, 100.0, 0.0],  # LineTo  (100, 0)
        [1, 100.0, 100.0],# LineTo  (100, 100)
        [1, 0.0, 100.0],  # LineTo  (0, 100)
        [1, 0.0, 0.0],    # LineTo  (0, 0) — close
    ]


def _minimal_payload(hatches: list) -> dict:
    """Minimal valid .fpd payload containing the given hatches list."""
    return {
        "version": 12,
        "project_info": {},
        "scale": {"px_per_mm": 4.0, "unit": "mm"},
        "display_settings": {},
        "paper_display": {},
        "levels": [],
        "plan_views": [],
        "active_level": "Level 1",
        "nodes": [],
        "pipes": [],
        "annotations": [],
        "underlays": [],
        "water_supply": None,
        "design_areas": [],
        "polylines": [],
        "draw_lines": [],
        "draw_rectangles": [],
        "draw_circles": [],
        "draw_arcs": [],
        "gridlines": [],
        "walls": [],
        "floor_slabs": [],
        "roofs": [],
        "rooms": [],
        "hatches": hatches,
        "constraints": [],
        "detail_views": [],
        "sheets": [],
        "titleblock_template": None,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_hatch_item_class_gone():
    """HatchItem must not exist in firepro3d.annotations after retirement."""
    import firepro3d.annotations as ann
    assert not hasattr(ann, "HatchItem"), (
        "HatchItem class still present in firepro3d.annotations"
    )


def test_legacy_solid_hatch_dropped_on_load(qapp, tmp_path):
    """Containment C8: a legacy 'solid' hatch entry is discarded on load."""
    hatch_entry = {
        "type": "hatch",
        "path": _square_elements(),
        "pos": [10.0, 20.0],
        "pattern_type": "solid",
        "colour": "#123456",
        "level": "Level 2",
        "angle": 45.0,
        "spacing": 8.0,
    }
    payload = _minimal_payload([hatch_entry])

    fp = str(tmp_path / "legacy_solid.fpd")
    with open(fp, "w") as f:
        json.dump(payload, f)

    scene = _make_scene(qapp)
    scene.load_from_file(fp)

    assert scene._polylines == [], (
        f"Legacy hatch must clean-drop, got {len(scene._polylines)} polyline(s)"
    )


def test_legacy_diagonal_hatch_dropped_on_load(qapp, tmp_path):
    """Containment C8: a legacy 'diagonal' hatch entry is discarded on load."""
    hatch_entry = {
        "type": "hatch",
        "path": _square_elements(),
        "pos": [0.0, 0.0],
        "pattern_type": "diagonal",
        "colour": "#aabbcc",
        "level": "Level 1",
        "angle": 45.0,
        "spacing": 8.0,
    }
    payload = _minimal_payload([hatch_entry])

    fp = str(tmp_path / "legacy_diagonal.fpd")
    with open(fp, "w") as f:
        json.dump(payload, f)

    scene = _make_scene(qapp)
    scene.load_from_file(fp)

    assert scene._polylines == [], (
        f"Legacy hatch must clean-drop, got {len(scene._polylines)} polyline(s)"
    )
