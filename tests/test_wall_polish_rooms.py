"""G6 (wall polish AC5): room boundary detection yields identical polygons
after the outline/junction changes.  _EXPECTED captured at base c9a5bddd."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.wall import WallSegment, ALIGN_LEFT, ALIGN_RIGHT

_POLY = [(0.0, 4000.0), (3000.0, 0.0), (3000.0, 4000.0), (0.0, 0.0)]
# Detection reads endpoints only, so Left and Right goldens coincide at base.
_EXPECTED = {ALIGN_LEFT: _POLY, ALIGN_RIGHT: _POLY}   # from the base SHA run


def _add(s, p1, p2, align):
    w = WallSegment(QPointF(*p1), QPointF(*p2), thickness_mm=200.0)
    w._alignment = align
    s.addItem(w)
    s._walls.append(w)
    return w


@pytest.mark.parametrize("align", [ALIGN_LEFT, ALIGN_RIGHT])
def test_room_polygon_with_tee_unchanged(qapp, align):
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    for p1, p2 in (((0, 0), (6000, 0)), ((6000, 0), (6000, 4000)),
                   ((6000, 4000), (0, 4000)), ((0, 4000), (0, 0))):
        _add(s, p1, p2, align)
    _add(s, (3000, 0), (3000, 4000), align)          # T partition, both ends
    poly = s._detect_room_boundary(QPointF(1500, 2000))
    assert poly, "scenario must detect a real room"
    got = [(round(p.x(), 3), round(p.y(), 3)) for p in poly]
    assert got == _EXPECTED[align]
