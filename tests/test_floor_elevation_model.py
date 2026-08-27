import math
import pytest
from PyQt6.QtCore import QPointF
from firepro3d.floor_slab import FloorSlab, _resolve_boundary_z
from firepro3d.constants import MIN_FLOOR_THICKNESS_MM

class _FakeLevel:
    def __init__(self, elevation): self.elevation = elevation
class _FakeLM:
    def __init__(self, elevs): self._e = {k: _FakeLevel(v) for k, v in elevs.items()}
    def get(self, name): return self._e.get(name)
class _FakeScene:
    def __init__(self, lm): self._level_manager = lm
def _square():
    return [QPointF(0,0), QPointF(1000,0), QPointF(1000,1000), QPointF(0,1000)]
LM = _FakeLM({"Level 1": 0.0, "Level 2": 3048.0})

def _slab(**kw):
    s = FloorSlab(points=_square())
    for k, v in kw.items(): setattr(s, k, v)
    return s

def test_resolver_absolute_returns_z():
    assert _resolve_boundary_z("absolute", "Level 1", 0.0, 1234.5, LM) == 1234.5
def test_resolver_level_adds_offset():
    assert _resolve_boundary_z("level", "Level 2", -100.0, 0.0, LM) == 2948.0
def test_resolver_missing_level_returns_none():
    assert _resolve_boundary_z("level", "Nope", 0.0, 0.0, LM) is None

def test_default_recipe_zrange():
    s = _slab(_top_mode="level", _top_level="Level 1", _top_offset_mm=0.0,
              _bottom_mode="thickness", _thickness_mm=152.4)
    s._scene = _FakeScene(LM)
    assert s.z_range_mm() == (-152.4, 0.0)
def test_cross_level_span_zrange():
    s = _slab(_top_mode="level", _top_level="Level 2", _top_offset_mm=0.0,
              _bottom_mode="level", _bottom_level="Level 1", _bottom_offset_mm=0.0)
    s._scene = _FakeScene(LM)
    assert s.z_range_mm() == (0.0, 3048.0)
def test_absolute_top_and_bottom_zrange():
    s = _slab(_top_mode="absolute", _top_abs_z_mm=500.0,
              _bottom_mode="absolute", _bottom_abs_z_mm=100.0)
    s._scene = _FakeScene(LM)
    assert s.z_range_mm() == (100.0, 500.0)
def test_inversion_returns_ordered_tuple():
    s = _slab(_top_mode="absolute", _top_abs_z_mm=0.0,
              _bottom_mode="absolute", _bottom_abs_z_mm=200.0)
    s._scene = _FakeScene(LM)
    assert s.z_range_mm() == (0.0, 200.0)
def test_zero_height_get_3d_mesh_none():
    s = _slab(_top_mode="absolute", _top_abs_z_mm=0.0,
              _bottom_mode="absolute", _bottom_abs_z_mm=0.0)
    s._scene = _FakeScene(LM)
    assert s.get_3d_mesh(LM) is None
def test_missing_level_zrange_none():
    s = _slab(_top_mode="level", _top_level="Ghost", _top_offset_mm=0.0,
              _bottom_mode="thickness", _thickness_mm=152.4)
    s._scene = _FakeScene(LM)
    assert s.z_range_mm() is None
