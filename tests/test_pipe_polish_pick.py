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


def _pipe_mode(scene):
    scene.set_mode("pipe")
    return scene._pipe_ctl


def _click(view, scene_pt):
    # sendEvent, not QTest: the shown-view fixture drops spontaneous QTest mouse events.
    vp = QPointF(view.mapFromScene(scene_pt))
    NO, LEFT, NOMOD = (Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)
    for t, btn, btns in ((QEvent.Type.MouseMove, NO, NO),
                         (QEvent.Type.MouseButtonPress, LEFT, LEFT),
                         (QEvent.Type.MouseButtonRelease, LEFT, NO)):
        QApplication.sendEvent(view.viewport(), QMouseEvent(t, vp, btn, btns, NOMOD))
    QApplication.processEvents()


def test_press_near_node_splits_and_connects(shown_model_view):
    view, scene = shown_model_view
    a, b, _pipe = _run(scene)
    _zoom(view, 1.0)
    _pipe_mode(scene)
    pipes, nodes = len(scene.sprinkler_system.pipes), len(scene.sprinkler_system.nodes)
    _click(view, QPointF(100, 0))
    new = scene.pipe_start_node
    assert len(scene.sprinkler_system.pipes) == pipes + 1
    assert len(scene.sprinkler_system.nodes) == nodes + 1
    assert len(new.pipes) == 2
    assert {new.other_end(p) for p in new.pipes} == {a, b}


def test_second_click_near_node_splits_and_connects(shown_model_view):
    view, scene = shown_model_view
    a, b, _pipe = _run(scene)
    start = _node(scene, 100, 500)
    _zoom(view, 1.0)
    _pipe_mode(scene)
    _click(view, QPointF(100, 500))
    assert scene.pipe_start_node is start
    pipes, nodes = len(scene.sprinkler_system.pipes), len(scene.sprinkler_system.nodes)
    _click(view, QPointF(100, 0))
    assert len(scene.sprinkler_system.pipes) == pipes + 2      # split + new pipe
    assert len(scene.sprinkler_system.nodes) == nodes + 1      # one split node, no loose node
    mid = next(n for n in scene.sprinkler_system.nodes
               if abs(n.scenePos().x() - 100) < 1 and abs(n.scenePos().y()) < 1)
    assert len(mid.pipes) == 3
    assert {mid.other_end(p) for p in mid.pipes} == {a, b, start}


def test_second_click_inside_aperture_connects_to_node(shown_model_view):
    """Zoom 0.5: the aperture is 30 units, the fixed radius 10; a click 25 units
    short of a node still joins it and leaves no loose node."""
    view, scene = shown_model_view
    start, target = _node(scene, 0, 500), _node(scene, 1000, 500)
    _zoom(view, 0.5)
    ctl = _pipe_mode(scene)
    scene.pipe_start_node = start
    nodes = len(scene.sprinkler_system.nodes)
    p = QPointF(975, 500)
    ctl.press_pipe(None, p, p, None, None, None)
    assert len(scene.sprinkler_system.nodes) == nodes
    assert target.other_end(target.pipes[0]) is start


@pytest.mark.parametrize("zoom", [0.5, 2.0])
def test_pickup_is_screen_sized(shown_model_view, zoom):
    view, scene = shown_model_view
    n = _node(scene, 0, 0)       # lone node: no pipe hit shape to muddy the 16 px probe
    _zoom(view, zoom)
    ctl = _pipe_mode(scene)
    assert ctl.resolve_pipe_target(QPointF(14 / zoom, 0), QPointF(14 / zoom, 0)) == ("node", n)
    assert ctl.resolve_pipe_target(QPointF(16 / zoom, 0), QPointF(16 / zoom, 0)) == ("none", None)


def test_fixed_radius_callers_stay_fixed(shown_model_view):
    view, scene = shown_model_view
    _node(scene, 0, 0)
    _zoom(view, 0.1)
    assert scene.find_nearby_node(50, 0) is None        # paste, add_node: 10 units


def test_riser_hit_resolves_to_nearest_z_node(shown_model_view):
    view, scene = shown_model_view
    low, high = _node(scene, 0, 0, 0.0), _node(scene, 0, 0, 3000.0)
    pipe = scene.add_pipe(low, high, None, _propagate_ceiling=False)
    pipe.update_geometry()
    _zoom(view, 1.0)
    ctl = _pipe_mode(scene)
    p = QPointF(100, 0)
    assert ctl.resolve_pipe_target(p, p, z_hint=2900.0) == ("node", high)


def test_marker_follows_target(shown_model_view):
    view, scene = shown_model_view
    a, _b, pipe = _run(scene)
    _zoom(view, 1.0)
    ctl = _pipe_mode(scene)
    m = scene.pipe_target_marker
    ctl.move_pipe(None, QPointF(5, 0))
    assert (m.kind, m.isVisible(), m.pos()) == ("node", True, QPointF(0, 0))
    ctl.move_pipe(None, QPointF(500, 3))
    assert (m.kind, m.isVisible(), m.pos()) == ("pipe", True, QPointF(500, 0))
    ctl.move_pipe(None, QPointF(500, 900))
    assert m.isVisible() is False


def test_marker_kinds_paint_differently(qapp):
    from PyQt6.QtGui import QColor, QImage, QPainter
    from firepro3d.pipe_target_marker import PipeTargetMarker

    def img(kind):
        out = QImage(40, 40, QImage.Format.Format_ARGB32)
        out.fill(QColor("white"))
        p = QPainter(out)
        p.translate(20, 20)
        m = PipeTargetMarker()
        m.kind = kind
        m.paint(p, None, None)
        p.end()
        return out

    assert img("node") != img("pipe")


def test_marker_hides_on_mode_exit(shown_model_view):
    view, scene = shown_model_view
    _run(scene)
    ctl = _pipe_mode(scene)
    ctl.move_pipe(None, QPointF(5, 0))
    scene.set_mode("select")
    assert scene.pipe_target_marker.isVisible() is False


def test_marker_survives_project_reset(shown_model_view):
    view, scene = shown_model_view
    scene.clear()
    scene.init_preview_node()
    assert scene.pipe_target_marker.scene() is scene
