"""
test_geometry2d_mixin.py
========================
Tests for Geometry2DMixin across the draw-geometry classes.

Since containment C3 the primitives are **definition-local and level-less** —
level / offset / z_range machinery moved off the primitive (see
test_geometry_2d_levelless.py for the level-less contract and
test_block_instance_level.py for level-on-instance). What remains here:
- z_range_mm falls back to the DisplayableItemMixin base (always None).
- is_fillable() True/False.
"""
from PyQt6.QtCore import QPointF
from firepro3d.geometry_2d import LineItem, CircleItem, RectangleItem


def _rect():
    return RectangleItem(QPointF(0, 0), QPointF(100, 100))


def test_primitive_z_range_is_none(qapp):
    # Level-less primitive: no z_range override → base returns None.
    r = _rect()
    assert r.z_range_mm() is None


def test_fillability(qapp):
    assert _rect().is_fillable() is True
    assert CircleItem(QPointF(0, 0), 25.0).is_fillable() is True
    assert LineItem(QPointF(0, 0), QPointF(10, 0)).is_fillable() is False
