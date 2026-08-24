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

def test_move_dispatch_registered(scene):
    # Guards the exact wiring gap: mouse-move must dispatch to _move_polygon.
    assert scene._MOVE_DISPATCH.get("polygon") == "_move_polygon"

def test_move_creates_and_commit_clears_ghost(scene):
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    scene._move_polygon(None, QPointF(100, 0))
    assert scene._polygon_preview is not None
    scene._commit_polygon_at(QPointF(100, 0))
    assert scene._polygon_preview is None

def test_no_single_place_attribute(scene):
    assert not hasattr(scene, "single_place_mode")

def test_placement_continuous_after_commit(scene):
    from PyQt6.QtCore import QPointF
    scene.set_mode("draw_circle")
    scene._draw_circle_center = QPointF(0, 0)
    scene._commit_draw_circle_at(QPointF(100, 0))
    assert scene.mode == "draw_circle"   # stays continuous, never "select"


# ── P shortcut wires polygon mode (real entry-point: posted QKeyEvent on shown view) ──

def test_p_shortcut_sets_polygon_mode(view, scene):
    """Posting Key_P to a focused Model_View must switch scene.mode to 'polygon'.

    RED-VERIFY: before adding Qt.Key.Key_P to _TOOL_SHORTCUTS, this test
    would fail because the key press is not handled and mode stays unchanged.
    """
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QApplication

    # Start in a different mode so we can detect the change.
    scene.set_mode("select")
    assert scene.mode != "polygon", "pre-condition: mode must not be polygon before key press"

    view.setFocus()
    QApplication.processEvents()

    for event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(
            view,
            QKeyEvent(event_type, Qt.Key.Key_P, Qt.KeyboardModifier.NoModifier),
        )

    assert scene.mode == "polygon", (
        f"Expected mode 'polygon' after pressing P; got {scene.mode!r}"
    )
