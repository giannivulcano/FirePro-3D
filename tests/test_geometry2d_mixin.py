"""
test_geometry2d_mixin.py
========================
Tests for Geometry2DMixin adoption across the 5 draw-geometry classes:
LineItem, PolylineItem, RectangleItem, CircleItem, ArcItem.

Covers:
- z_range_mm with level + offset
- z_range_mm with no level manager
- level_offset_mm default + conditional serialization
- from_dict back-compat when level_offset_mm absent
- level + offset round-trip for all 4 serializable types (PolylineItem excluded: non-standard ctor)
- is_fillable() True/False
"""
import pytest
from PyQt6.QtCore import QPointF
from firepro3d.model_space import Model_Space
from firepro3d.level_manager import LevelManager
from firepro3d.construction_geometry import (
    LineItem, PolylineItem, RectangleItem, CircleItem, ArcItem,
)


def _scene(qapp):
    s = Model_Space()
    s._level_manager = LevelManager()
    return s


def _rect():
    return RectangleItem(QPointF(0, 0), QPointF(100, 100))


def test_z_range_zero_thickness_at_level_plus_offset(qapp):
    s = _scene(qapp)
    r = _rect()
    r.level = "Level 2"
    r._level_offset_mm = 200.0
    s.addItem(r)
    # Level 2 elevation = 3048 mm; offset = 200 → 3248
    assert r.z_range_mm() == (3248.0, 3248.0)


def test_z_range_none_without_level_manager(qapp):
    r = _rect()  # not in a scene
    assert r.z_range_mm() is None


def test_offset_default_zero_and_serialize_only_when_nonzero(qapp):
    r = _rect()
    assert r._level_offset_mm == 0.0
    assert "level_offset_mm" not in r.to_dict()
    r._level_offset_mm = 50.0
    assert r.to_dict()["level_offset_mm"] == 50.0


def test_from_dict_backcompat_missing_offset_is_zero(qapp):
    r = _rect()
    d = r.to_dict()
    r2 = RectangleItem.from_dict(d)
    assert r2._level_offset_mm == 0.0


def test_offset_and_level_roundtrip_all_types(qapp):
    for obj in (
        LineItem(QPointF(0, 0), QPointF(10, 0)),
        _rect(),
        CircleItem(QPointF(0, 0), 25.0),
        ArcItem(QPointF(0, 0), 25.0, 0.0, 90.0),
    ):
        obj.level = "Level 3"
        obj._level_offset_mm = 12.5
        clone = type(obj).from_dict(obj.to_dict())
        assert clone.level == "Level 3", f"{type(obj).__name__}: level not round-tripped"
        assert clone._level_offset_mm == 12.5, f"{type(obj).__name__}: offset not round-tripped"


def test_fillability(qapp):
    assert _rect().is_fillable() is True
    assert CircleItem(QPointF(0, 0), 25.0).is_fillable() is True
    assert LineItem(QPointF(0, 0), QPointF(10, 0)).is_fillable() is False
