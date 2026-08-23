"""Tests for GeometryTemplate level-offset default and copy-to-item contract."""

import pytest
from firepro3d.construction_geometry import GeometryTemplate


def test_template_has_offset_default_zero():
    t = GeometryTemplate()
    assert t._level_offset_mm == 0.0


def test_template_offset_and_level_copy_to_new_item(qapp):
    # Simulate the create-site copy contract used by model_space.
    from PyQt6.QtCore import QPointF
    from firepro3d.construction_geometry import RectangleItem

    tmpl = GeometryTemplate()
    tmpl.level = "Level 2"
    tmpl._level_offset_mm = 300.0
    r = RectangleItem(QPointF(0, 0), QPointF(10, 10))
    # contract that model_space create-sites must satisfy:
    r.level = tmpl.level
    r._level_offset_mm = getattr(tmpl, "_level_offset_mm", 0.0)
    assert r.level == "Level 2"
    assert r._level_offset_mm == 300.0
