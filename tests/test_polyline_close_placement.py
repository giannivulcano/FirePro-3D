from PyQt6.QtCore import QPointF, Qt
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.construction_geometry import PolylineItem
import pytest
from PyQt6.QtTest import QTest

@pytest.fixture
def scene(qapp):
    return Model_Space()

@pytest.fixture
def view(scene):
    v = Model_View(scene); v.resize(800, 600); v.resetTransform(); v.show()
    QTest.qWaitForWindowExposed(v); yield v; v.close()

def _start(scene, *pts):
    scene.set_mode("polyline")
    pl = PolylineItem(QPointF(*pts[0]))
    scene.addItem(pl); scene._polylines.append(pl); scene._polyline_active = pl
    for p in pts[1:]:
        pl.append_point(QPointF(*p))
    return pl

def test_click_start_closes_with_3_points(scene):
    pl = _start(scene, (0, 0), (100, 0), (50, 100))
    scene._press_polyline(None, None, QPointF(0.5, 0.5), None, None, None)
    assert pl.is_closed() is True
    assert scene._polyline_active is None
    assert scene.mode == "polyline"
    assert len(pl._points) == 3

def test_click_start_ignored_with_2_points(scene):
    pl = _start(scene, (0, 0), (100, 0))
    scene._press_polyline(None, None, QPointF(0.5, 0.5), None, None, None)
    assert pl.is_closed() is False
    assert scene._polyline_active is pl

def test_click_interior_vertex_does_not_close(scene):
    pl = _start(scene, (0, 0), (100, 0), (50, 100))
    scene._press_polyline(None, None, QPointF(100, 0), None, None, None)  # near pts[1]
    assert pl.is_closed() is False

def test_delete_pops_last_vertex(scene):
    pl = _start(scene, (0, 0), (100, 0), (50, 100))
    scene._delete_or_pop_polyline_vertex()
    assert len(pl._points) == 2
    assert scene._polyline_active is pl and scene.mode == "polyline"

def test_delete_at_one_vertex_cancels(scene):
    pl = _start(scene, (0, 0))
    scene._delete_or_pop_polyline_vertex()
    assert scene._polyline_active is None
    assert pl not in scene._polylines
    assert scene.mode == "polyline"

def test_close_via_real_clicks(view, scene):
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication
    scene.set_mode("polyline")
    def click(sp):
        vp = view.viewport(); v = view.mapFromScene(QPointF(*sp)); g = vp.mapToGlobal(v)
        for et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            QApplication.sendEvent(vp, QMouseEvent(et, QPointF(v), QPointF(g),
                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier))
    for sp in [(0, 0), (100, 0), (50, 100)]:
        click(sp)
    click((0, 0))
    assert scene._polylines and scene._polylines[-1].is_closed()
    assert scene.mode == "polyline"
