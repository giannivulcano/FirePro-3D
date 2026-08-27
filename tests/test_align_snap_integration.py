from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsScene
from firepro3d.align_engine import Ray
from firepro3d.snap_engine import SnapEngine


def test_single_path_snap_projects_cursor_onto_ray(qapp):
    scene = QGraphicsScene()
    eng = SnapEngine()
    h = Ray(origin=(0.0, 0.0), direction=(1.0, 0.0), kind="hv", source_id=1)
    # cursor just above the horizontal ray → should snap onto it (y→0)
    res = eng.find(QPointF(50.0, 1.0), scene, QTransform(), align_paths=[h])
    assert res is not None and abs(res.point.y()) < 1e-6


def test_path_x_path_beats_single_path(qapp):
    scene = QGraphicsScene()
    eng = SnapEngine()
    h = Ray((0.0, 10.0), (1.0, 0.0), "hv", 1)
    v = Ray((20.0, 0.0), (0.0, 1.0), "hv", 2)
    res = eng.find(QPointF(20.5, 10.5), scene, QTransform(), align_paths=[h, v])
    assert res is not None
    assert abs(res.point.x() - 20.0) < 1e-6 and abs(res.point.y() - 10.0) < 1e-6


def test_real_snap_outranks_align_path(qapp):
    from PyQt6.QtWidgets import QGraphicsLineItem
    scene = QGraphicsScene()
    scene.addItem(QGraphicsLineItem(0.0, 0.0, 0.0, 100.0))  # endpoint at (0,0)
    eng = SnapEngine()
    stray = Ray((0.0, 3.0), (1.0, 0.0), "hv", 1)            # align path near (0,0)
    res = eng.find(QPointF(1.0, 1.0), scene, QTransform(), align_paths=[stray])
    assert res is not None and res.snap_type == "endpoint"  # real snap wins
