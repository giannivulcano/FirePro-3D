"""The SNAP aperture must be the SAME pixel radius at every zoom (contract A)."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsScene
from firepro3d import snap_engine
from firepro3d.snap_engine import SnapEngine
from firepro3d.construction_geometry import LineItem


@pytest.fixture
def scene_with_line(qapp):
    scene = QGraphicsScene()
    line = LineItem(QPointF(0.0, 0.0), QPointF(1000.0, 0.0))   # endpoint at (0,0) is the target
    scene.addItem(line)
    return scene


def _xform(scale: float) -> QTransform:
    t = QTransform()
    t.scale(scale, scale)
    return t


@pytest.mark.parametrize("scale", [0.02, 1.0, 10.0])
def test_endpoint_caught_within_aperture_at_every_zoom(scene_with_line, scale):
    eng = SnapEngine()
    aperture = snap_engine.SNAP_TOLERANCE_PX
    inside_px = aperture - 3
    # Place cursor off-axis (negative x) so nearest on [0,0]→[1000,0] is
    # clamped to the endpoint (0,0) — avoids competing perpendicular/nearest hits.
    cursor = QPointF(-inside_px / scale, 0.0)   # px → scene at this zoom
    res = eng.find(cursor, scene_with_line, _xform(scale))
    assert res is not None, f"endpoint missed at scale={scale}"
    assert res.snap_type == "endpoint"


@pytest.mark.parametrize("scale", [0.02, 1.0, 10.0])
def test_endpoint_missed_just_outside_aperture_at_every_zoom(scene_with_line, scale):
    eng = SnapEngine()
    aperture = snap_engine.SNAP_TOLERANCE_PX
    outside_px = aperture + 6
    # Place cursor off-axis (negative x) so there is no competing nearest hit
    # between cursor and endpoint — only the endpoint itself is a candidate.
    cursor = QPointF(-outside_px / scale, 0.0)
    res = eng.find(cursor, scene_with_line, _xform(scale))
    assert res is None, f"snap fired beyond aperture at scale={scale}"


def test_default_aperture_is_20():
    assert snap_engine.SNAP_TOLERANCE_PX == 20
