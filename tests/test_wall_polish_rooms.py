"""G6 (wall polish AC5), re-baselined by the room-detection rework (2026-11-12): the tee
scene now detects the exact interior face. The old golden ((0,4000),(3000,0),(3000,4000),(0,0))
was the R1 bow-tie (.todo/room-detect-1b.md §2). Expected faces are hand-computed:
  Left : rect bodies inward (inner 200..5800 x 200..3800), partition body 2800..3000
         -> left bay x 200..2800, y 200..3800 (1b truth 9.36e6)
  Right: rect bodies outward (inner 0..6000 x 0..4000), partition body 3000..3200
         -> left bay x 0..3000, y 0..4000 (1b truth 12.0e6)"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.wall import WallSegment, ALIGN_LEFT, ALIGN_RIGHT

_EXPECTED = {ALIGN_LEFT: ((200.0, 200.0, 2800.0, 3800.0), 9.36e6),
             ALIGN_RIGHT: ((0.0, 0.0, 3000.0, 4000.0), 12.0e6)}


def _add(s, p1, p2, align):
    w = WallSegment(QPointF(*p1), QPointF(*p2), thickness_mm=200.0)
    w._alignment = align
    s.addItem(w)
    s._walls.append(w)
    return w


@pytest.mark.parametrize("align", [ALIGN_LEFT, ALIGN_RIGHT])
def test_room_polygon_with_tee_unchanged(qapp, align):
    from firepro3d import room_detection
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    for p1, p2 in (((0, 0), (6000, 0)), ((6000, 0), (6000, 4000)),
                   ((6000, 4000), (0, 4000)), ((0, 4000), (0, 0))):
        _add(s, p1, p2, align)
    _add(s, (3000, 0), (3000, 4000), align)          # T partition, both ends
    for w in s._walls:
        w.invalidate_geometry()                      # joins see every neighbour
    face = room_detection.detect(s._room_walls(s.active_level), QPointF(1500, 2000))
    assert isinstance(face, room_detection.RoomFace), "scenario must detect a real room"
    xs = [p.x() for p in face.outer]
    ys = [p.y() for p in face.outer]
    (x0, y0, x1, y1), want = _EXPECTED[align]
    assert (min(xs), min(ys), max(xs), max(ys)) == pytest.approx((x0, y0, x1, y1), abs=1e-6)
    assert room_detection.ring_area(face.outer) == pytest.approx(want, abs=1.0)
