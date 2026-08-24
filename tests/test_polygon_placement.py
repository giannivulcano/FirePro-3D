import math
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.construction_geometry import RegularPolygonItem

@pytest.fixture
def scene(qapp):
    return Model_Space()

@pytest.fixture
def view(scene):
    v = Model_View(scene); v.resize(800, 600); v.resetTransform(); v.show()
    QTest.qWaitForWindowExposed(v); yield v; v.close()

def test_two_click_places_polygon(scene):
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    assert scene._polygon_center == QPointF(0, 0)
    scene._press_polygon(None, None, QPointF(100, 0), None, None, None)
    assert len(scene._draw_polygons) == 1
    poly = scene._draw_polygons[-1]
    assert isinstance(poly, RegularPolygonItem)
    assert poly._sides == 6
    assert math.isclose(poly._radius_mm, 100.0, abs_tol=1e-6)
    assert scene._polygon_center is None
    assert scene.mode == "polygon"

def test_default_sides_six(scene):
    scene.set_mode("polygon")
    assert scene._polygon_sides == 6

def test_radius_too_small_rejected(scene):
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(0.1, 0), None, None, None)
    assert len(scene._draw_polygons) == 0
    assert scene._polygon_center == QPointF(0, 0)

def test_up_down_change_sides_live(view, scene):
    scene.set_mode("polygon")
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QApplication
    def key(k):
        for et in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(view, QKeyEvent(et, k, Qt.KeyboardModifier.NoModifier))
    key(Qt.Key.Key_Up)
    assert scene._polygon_sides == 7
    key(Qt.Key.Key_Down); key(Qt.Key.Key_Down)
    assert scene._polygon_sides == 5

def test_left_right_toggle_inscribed(view, scene):
    scene.set_mode("polygon")
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QApplication
    start = scene._polygon_inscribed
    for et in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(view, QKeyEvent(et, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier))
    assert scene._polygon_inscribed is (not start)

def test_sides_clamped_3_to_120(scene):
    scene.set_mode("polygon")
    scene._polygon_sides = 3
    scene._cycle_polygon_sides(-1)
    assert scene._polygon_sides == 3
    scene._polygon_sides = 120
    scene._cycle_polygon_sides(+1)
    assert scene._polygon_sides == 120

def test_hud_radius_matches_mouse(scene):
    from firepro3d.dynamic_input import SCHEMAS
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    rim = SCHEMAS["polygon"].resolve(QPointF(0, 0), {"Radius": 150.0})
    scene._commit_polygon_at(rim)
    assert math.isclose(scene._draw_polygons[-1]._radius_mm, 150.0, abs_tol=1e-6)
