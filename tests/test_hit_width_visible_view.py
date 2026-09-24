"""Item hit shapes read the VISIBLE view's zoom, never views()[0], with no mm
floor (selection-mode §4.1; snapping-engine §14.4 invariant)."""
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.view_scale import scene_hit_width, scene_view_scale


def test_line_hit_width_tracks_active_view_not_views0(qapp):
    sc = Model_Space()
    ln = LineItem(QPointF(0, 0), QPointF(100, 0))
    sc.addItem(ln)
    vestigial = QGraphicsView(sc)            # views()[0], m11 == 1.0 (MainWindow.view)
    active = QGraphicsView(sc)
    active.setTransform(QTransform.fromScale(20.0, 20.0))
    # 10 px at 20 px/mm = 0.5 mm; the views()[0] read gave 10 mm.
    assert abs(ln.shape().boundingRect().height() - 0.5) < 0.05
    assert vestigial is not None


def test_hit_width_has_no_mm_floor_when_zoomed_in(qapp):
    sc = QGraphicsScene()
    ln = LineItem(QPointF(0, 0), QPointF(100, 0))
    sc.addItem(ln)
    v = QGraphicsView(sc)
    v.setTransform(QTransform.fromScale(100.0, 100.0))
    # 10 px / 100 = 0.1 mm (the old 2 mm floor made it 200 px on screen).
    assert ln.shape().boundingRect().height() < 0.2


def test_helper_defaults_without_view(qapp):
    ln = LineItem(QPointF(0, 0), QPointF(1, 0))
    assert scene_hit_width(ln, 12.0, 6.0) == 6.0
    assert scene_view_scale(None) == 1.0
