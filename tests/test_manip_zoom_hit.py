"""Manipulator handle hit-testing at NON-identity view zoom (posted events).

Handles are ItemIgnoresTransformations, so ``hit_test``/``handles_at`` map the
press through the view's device transform; a plain ``mapFromScene`` only agrees
at m11 == 1 and a handle press at any other zoom fell through to selection and
cleared it (U1 live-smoke regression). The rotate-knob test that used to guard
this was retired with the knob (2026-09-23); this re-covers the mapping for the
handles that remain: (a) a RectangleItem's live corner grip and (b) a rigid
ResizeHandle (a box-native paper-sized TextItem — the only rigid-resize item
reachable in the model scene).
"""
import pytest
from PyQt6.QtCore import QPointF, Qt, QEvent
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.model_space import Model_Space
from firepro3d.level_manager import LevelManager
from firepro3d.scale_manager import ScaleManager
from firepro3d.model_view import Model_View
from firepro3d.selection_manipulator import SelectionManipulator

ZOOMS = [0.02, 0.5, 4.0]
_BOX_PX = 200.0        # item size on screen, independent of zoom
_DRAG_PX = 60.0        # outward drag on screen (x and y)


@pytest.fixture
def scene_and_view(qapp):
    scene = Model_Space()
    scene._level_manager = LevelManager()
    scene.scale_manager = ScaleManager()
    view = Model_View(scene)
    view.resize(800, 600)
    view.show()
    QTest.qWaitForWindowExposed(view)
    qapp.processEvents()
    yield scene, view
    view.close()


def _zoom_to(view, zoom, centre):
    view.resetTransform()
    view.scale(zoom, zoom)
    view.centerOn(centre)
    QApplication.instance().processEvents()
    assert view.transform().m11() == pytest.approx(zoom)


def _manip(scene) -> SelectionManipulator:
    return next(i for i in scene.items()
                if isinstance(i, SelectionManipulator))


def _post(view, etype, vp_pt: QPointF):
    app = QApplication.instance()
    vp = view.viewport()
    buttons = (Qt.MouseButton.NoButton if etype == QEvent.Type.MouseButtonRelease
               else Qt.MouseButton.LeftButton)
    ev = QMouseEvent(etype, vp_pt, vp.mapToGlobal(vp_pt.toPoint()).toPointF(),
                     Qt.MouseButton.LeftButton, buttons,
                     Qt.KeyboardModifier.NoModifier)
    app.sendEvent(vp, ev)
    app.processEvents()


_OUTER_PX = 5.0       # press offset: outside the frame's 3 px shape pad, but
                      # inside the handle (half 4.5 px + 3 px grab pad)


def _drag_from(view, manip, scene_pt: QPointF, handle):
    """Posted press on the OUTER half of *handle* (anchored at *scene_pt*) —
    outside the frame shape, so only the zoom-aware handle mapping can route
    it — then drag _DRAG_PX outward and release. Returns the mode seen right
    after the press."""
    start = (view.mapFromScene(scene_pt).toPointF()
             + QPointF(_OUTER_PX, _OUTER_PX))
    press_scene = view.mapToScene(start.toPoint())
    frame_local = manip.mapFromScene(press_scene)
    assert not manip.shape().contains(frame_local)    # truly outside the frame
    # zoom-aware handle hit (grip handle objects are rebuilt per query, so
    # match by kind + index rather than identity)
    key = (type(handle), getattr(handle, "index", None), handle.role)
    assert key in {(type(h), getattr(h, "index", None), h.role)
                   for h in manip.handles_at(press_scene)}
    assert manip.hit_test(press_scene) is True
    _post(view, QEvent.Type.MouseButtonPress, start)
    mode = manip._mode
    mid = start + QPointF(_DRAG_PX / 2, _DRAG_PX / 2)
    end = start + QPointF(_DRAG_PX, _DRAG_PX)
    _post(view, QEvent.Type.MouseMove, mid)
    _post(view, QEvent.Type.MouseMove, end)
    _post(view, QEvent.Type.MouseButtonRelease, end)
    return mode


@pytest.mark.parametrize("zoom", ZOOMS)
def test_rect_corner_grip_drag_at_zoom(qapp, scene_and_view, zoom):
    from firepro3d.geometry_2d import RectangleItem
    from firepro3d.manip_handle import RectGripHandle
    scene, view = scene_and_view
    size = _BOX_PX / zoom
    r = RectangleItem(QPointF(0, 0), QPointF(size, size / 2))
    scene.addItem(r)
    scene._draw_rects.append(r)
    _zoom_to(view, zoom, QPointF(size / 2, size / 4))
    r.setSelected(True)
    qapp.processEvents()
    manip = _manip(scene)
    w0, h0 = r.rect().width(), r.rect().height()
    br = r.mapToScene(r.rect().bottomRight())
    grip = next(h for h in manip._active_handles()
                if isinstance(h, RectGripHandle)
                and (h.scene_position(manip._rect) - br).manhattanLength() < 1e-6)

    mode = _drag_from(view, manip, grip.scene_position(manip._rect), grip)

    assert mode == "grip"                         # the grip gesture began
    assert r.isSelected()                         # selection survived
    # A live grip puts the corner AT the cursor (absolute), so the outer-half
    # press offset carries into the result.
    grow = (_DRAG_PX + _OUTER_PX) / zoom
    tol = 4.0 / zoom                              # a few px of rounding/snap
    assert r.rect().width() == pytest.approx(w0 + grow, abs=tol)
    assert r.rect().height() == pytest.approx(h0 + grow, abs=tol)
    assert abs(r.rect().left()) < tol and abs(r.rect().top()) < tol   # TL held


@pytest.mark.parametrize("zoom", ZOOMS)
def test_text_rigid_resize_handle_drag_at_zoom(qapp, scene_and_view, zoom):
    from firepro3d.text_item import TextItem, TextAnnotationData
    from firepro3d.manip_handle import ResizeHandle
    from firepro3d.manip_math import HandleRole
    scene, view = scene_and_view
    size = _BOX_PX / zoom
    t = TextItem(TextAnnotationData(text="Hi", x=0, y=0,
                                    wrap_width_mm=size, box_height_mm=size / 2))
    # Box-native (scale-capable) sizing → the manipulator shows its RIGID
    # resize handles (the paper-text path; model text uses parametric grips).
    t._force_device_independent = True
    t._apply_format()
    scene.addItem(t)
    b0 = t.manip_bounds()
    _zoom_to(view, zoom, b0.center())
    t.setSelected(True)
    qapp.processEvents()
    manip = _manip(scene)
    assert manip._is_box_native_single(t)
    host = manip._handles[HandleRole.BOTTOM_RIGHT]
    assert host.isVisible() and isinstance(host.handle, ResizeHandle)

    mode = _drag_from(view, manip, host.scenePos(), host.handle)

    assert mode == "resize"                       # rigid resize began
    assert t.isSelected()                         # selection survived
    b1 = t.manip_bounds()
    assert b1.width() > b0.width() + _DRAG_PX / zoom / 2
    assert b1.height() > b0.height() + _DRAG_PX / zoom / 2
    tol = 4.0 / zoom
    assert b1.left() == pytest.approx(b0.left(), abs=tol)     # TL anchor held
    assert b1.top() == pytest.approx(b0.top(), abs=tol)
