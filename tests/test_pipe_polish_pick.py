"""Pipe polish D3-D6: picking and placement targets."""
import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent, QTransform
from PyQt6.QtWidgets import QApplication

from firepro3d import halo_selection as hs
from firepro3d.node import Node


def _node(scene, x, y, z=0.0):
    n = Node(x, y, z)
    scene.addItem(n)
    scene.sprinkler_system.add_node(n)
    return n


def _run(scene, x0=0, x1=2000):
    a, b = _node(scene, x0, 0), _node(scene, x1, 0)
    return a, b, scene.add_pipe(a, b, None, _propagate_ceiling=False)


def _zoom(view, z):
    view.setTransform(QTransform.fromScale(z, z))
    view.centerOn(QPointF(0, 0))
    QApplication.processEvents()


def _top(scene, view, p):
    got = scene.halo_candidates_at(p, hs.HALO_APERTURE_PX / abs(view.transform().m11()),
                                   view.viewportTransform())
    return got[0] if got else None


@pytest.mark.parametrize("zoom", [0.5, 1.0, 3.0])
def test_node_vs_pipe_by_screen_distance(shown_model_view, zoom):
    view, scene = shown_model_view
    a, _b, pipe = _run(scene)
    _zoom(view, zoom)
    assert _top(scene, view, QPointF(0, 0)) is a
    assert _top(scene, view, QPointF(8 / zoom, 0)) is a
    assert _top(scene, view, QPointF(20 / zoom, 0)) is pipe


def test_real_click_selects_node_then_pipe(shown_model_view):
    view, scene = shown_model_view
    a, _b, pipe = _run(scene)
    scene.set_mode(None)
    _zoom(view, 1.0)
    for target, sp in ((a, QPointF(0, 0)), (pipe, QPointF(60, 0))):
        vp = QPointF(view.mapFromScene(sp))
        # HALO select: a sent hover builds the candidate list, then press/release
        # (a bare QTest.mouseClick with no hover selects nothing).
        QApplication.sendEvent(view.viewport(), QMouseEvent(
            QEvent.Type.MouseMove, vp, Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
        assert scene.halo_item() is target
        for t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            QApplication.sendEvent(view.viewport(), QMouseEvent(
                t, vp, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier))
        QApplication.processEvents()
        assert scene.selectedItems() == [target]
        scene.clearSelection()


def test_short_pipe_stays_reachable(shown_model_view):
    view, scene = shown_model_view
    # 20 mm run: the 12 px disks (12 mm) would cover all of it; the cap at a
    # third of the run (6.7 mm) leaves the middle to the pipe.
    _a, _b, pipe = _run(scene, 0, 20)
    _zoom(view, 1.0)
    assert _top(scene, view, QPointF(10, 0)) is pipe


@pytest.mark.parametrize("zoom", [0.5, 1.0, 3.0])
def test_plain_node_shape_is_the_pick_disk(shown_model_view, zoom):
    """``shape()`` (scene.items / itemAt) agrees with the HALO pick disk."""
    view, scene = shown_model_view
    a, _b, _pipe = _run(scene)
    _zoom(view, zoom)
    assert a.shape().boundingRect().width() / 2.0 == pytest.approx(12.0 / zoom)


def test_sprinkler_node_picks_by_symbol(shown_model_view):
    view, scene = shown_model_view
    a, _b, _pipe = _run(scene)
    a.add_sprinkler()
    _zoom(view, 3.0)
    r = a.sprinkler.TARGET_MM / 2.0 * a.sprinkler._display_scale
    assert _top(scene, view, QPointF(r * 0.8, r * 0.5)) is a
