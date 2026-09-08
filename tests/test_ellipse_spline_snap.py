import math
import pytest
from PyQt6.QtCore import QPointF
from firepro3d.snap_engine import SnapEngine
from firepro3d.construction_geometry import EllipseItem


@pytest.fixture
def eng(qapp):
    return SnapEngine()


def test_ellipse_emits_center_and_rotated_quadrants(eng):
    # Major axis rotated to Y-up 90 deg (points straight "up" = -y in Qt).
    e = EllipseItem(QPointF(0, 0), 100, 40, 90.0)
    triples = eng._collect(e)
    kinds = [(t[0], round(t[1].x(), 3), round(t[1].y(), 3)) for t in triples]
    # centre present
    assert ("center", 0.0, 0.0) in kinds
    # rotated major+ quadrant at Y-up 90 => (0, -100) in Qt scene coords
    assert ("quadrant", 0.0, -100.0) in kinds
    assert ("quadrant", 0.0, 100.0) in kinds          # major-
    # minor quadrants at +-40 along x
    assert ("quadrant", 40.0, 0.0) in kinds or ("quadrant", -40.0, 0.0) in kinds
    # It must NOT emit the axis-aligned boundingRect quadrant (100,0) that the
    # generic QGraphicsEllipseItem branch would wrongly produce for a rotated
    # ellipse (major axis is vertical here, so (100,0) would be wrong).
    assert ("quadrant", 100.0, 0.0) not in kinds


def test_ellipse_center_only_when_flag_off(eng):
    eng.snap_quadrant = False
    e = EllipseItem(QPointF(10, 20), 50, 30, 0.0)
    triples = eng._collect(e)
    assert any(t[0] == "center" for t in triples)
    assert not any(t[0] == "quadrant" for t in triples)
