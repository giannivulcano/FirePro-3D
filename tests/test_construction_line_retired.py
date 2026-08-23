"""tests/test_construction_line_retired.py

Verify that ConstructionLine has been fully retired:
- class no longer exists in construction_geometry
- not exported from the package
- legacy .fpd payloads with construction_lines are silently dropped on load
"""

from __future__ import annotations

import json
import os
import tempfile


def test_construction_line_class_gone():
    import firepro3d.construction_geometry as cg
    assert not hasattr(cg, "ConstructionLine")


def test_construction_line_not_exported():
    import firepro3d
    assert not hasattr(firepro3d, "ConstructionLine")


def test_legacy_construction_line_entry_dropped_on_load(qapp):
    """A saved project with construction_lines loads without error and drops them."""
    from firepro3d.model_space import Model_Space
    from firepro3d.level_manager import LevelManager
    from firepro3d.scale_manager import ScaleManager

    scene = Model_Space()
    scene._level_manager = LevelManager()
    scene.scale_manager = ScaleManager()

    # Build a minimal project payload that mirrors what scene_io.save_to_file writes,
    # plus a construction_lines key with one legacy entry.
    payload = {
        "version": 3,
        "project_info": {"name": "Legacy Test"},
        "scale": {"pixels_per_mm": 1.0, "is_calibrated": False},
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
        # Legacy key — must be silently ignored
        "construction_lines": [
            {"type": "construction_line", "pt1": [0, 0], "pt2": [100, 0], "level": "Level 1"}
        ],
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
        "hatches": [],
        "constraints": [],
        "detail_views": [],
        "sheets": [],
        "titleblock_template": None,
    }

    with tempfile.NamedTemporaryFile(suffix=".fpd", delete=False, mode="w",
                                     encoding="utf-8") as f:
        json.dump(payload, f)
        tmp_path = f.name

    try:
        # Should not raise
        scene.load_from_file(tmp_path)

        # No construction-line items remain on the scene
        clines = getattr(scene, "_construction_lines", [])
        assert clines == [], f"Expected no construction lines, got {clines}"
    finally:
        os.unlink(tmp_path)
