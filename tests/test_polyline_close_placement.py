from PyQt6.QtCore import QPointF, Qt, QEvent
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication
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


# ── ShortcutOverride routing tests (real entry point) ────────────────────────

def _make_delete_shortcut_override():
    """Build a Delete ShortcutOverride QKeyEvent."""
    return QKeyEvent(
        QEvent.Type.ShortcutOverride,
        Qt.Key.Key_Delete,
        Qt.KeyboardModifier.NoModifier,
    )


def test_view_accepts_delete_shortcut_override_during_polyline(view, scene):
    """Model_View must accept the Delete ShortcutOverride when a polyline is active.

    This is the integration test for the ShortcutOverride fix: without the
    ``event()`` override in Model_View the window-level QShortcut(Delete)
    fires ``delete_selected_items`` and the vertex-pop is never reached.

    Also asserts the inverse: without an active polyline (mode "select") the
    same ShortcutOverride is NOT accepted, so normal Delete-selected still
    fires everywhere else.
    """
    # With an active polyline — override must be accepted
    _start(scene, (0, 0), (100, 0), (50, 100))
    assert scene.mode == "polyline"
    assert scene._polyline_active is not None

    ev_with = _make_delete_shortcut_override()
    QApplication.sendEvent(view, ev_with)
    assert ev_with.isAccepted(), (
        "Model_View did not accept Delete ShortcutOverride during polyline "
        "placement — the window shortcut will steal Delete before the scene "
        "sees it."
    )

    # Without an active polyline (select mode) — must NOT be accepted
    scene.set_mode("select")
    assert scene._polyline_active is None

    ev_without = _make_delete_shortcut_override()
    QApplication.sendEvent(view, ev_without)
    assert not ev_without.isAccepted(), (
        "Model_View incorrectly accepted Delete ShortcutOverride in select "
        "mode — normal Delete-selected would stop working."
    )


def test_delete_keypress_pops_vertex_via_scene(view, scene):
    """A KeyPress(Delete) forwarded through the view pops the last polyline vertex.

    Drives the real view → scene key-forwarding path (QGraphicsView.keyPressEvent
    forwards to the scene by default).  Asserts the polyline still has one fewer
    vertex and _polyline_active is still set (placement continues).
    """
    pl = _start(scene, (0, 0), (100, 0), (50, 100))
    assert len(pl._points) == 3

    ev = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_Delete,
        Qt.KeyboardModifier.NoModifier,
    )
    # Drive the real view keyPressEvent which forwards to the scene
    view.keyPressEvent(ev)

    assert len(pl._points) == 2, (
        f"Expected 2 vertices after Delete, got {len(pl._points)}"
    )
    assert scene._polyline_active is pl, (
        "Polyline should still be active (mode continues) after vertex pop"
    )
    assert scene.mode == "polyline"
