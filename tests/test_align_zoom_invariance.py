import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsScene
from firepro3d.align_engine import Ray
from firepro3d.snap_engine import SnapEngine, SNAP_TOLERANCE_PX


@pytest.mark.parametrize("m11", [0.02, 1.0, 10.0])
def test_align_path_snap_is_pixel_invariant(qapp, m11):
    scene = QGraphicsScene()
    eng = SnapEngine()
    ray = Ray((0.0, 0.0), (1.0, 0.0), "hv", 1)
    xf = QTransform().scale(m11, m11)
    inside_scene = (SNAP_TOLERANCE_PX * 0.5) / m11    # 0.5·aperture in px → scene
    outside_scene = (SNAP_TOLERANCE_PX * 2.0) / m11   # 2·aperture in px → scene
    hit = eng.find(QPointF(50.0, inside_scene), scene, xf, align_paths=[ray])
    miss = eng.find(QPointF(50.0, outside_scene), scene, xf, align_paths=[ray])
    assert hit is not None and abs(hit.point.y()) < 1e-6
    assert miss is None or miss.snap_type != "nearest"   # not snapped to the path
