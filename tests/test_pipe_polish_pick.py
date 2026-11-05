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


_NO, _LEFT, _NOMOD = (Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier)


def _send(view, kind, scene_pt):
    # sendEvent, not QTest: the shown-view fixture drops spontaneous QTest mouse events.
    vp = QPointF(view.mapFromScene(scene_pt))
    btn, btns = {QEvent.Type.MouseMove: (_NO, _NO),
                 QEvent.Type.MouseButtonPress: (_LEFT, _LEFT),
                 QEvent.Type.MouseButtonDblClick: (_LEFT, _LEFT),
                 QEvent.Type.MouseButtonRelease: (_LEFT, _NO)}[kind]
    QApplication.sendEvent(view.viewport(), QMouseEvent(kind, vp, btn, btns, _NOMOD))
    QApplication.processEvents()


def _move(view, scene_pt):
    _send(view, QEvent.Type.MouseMove, scene_pt)


def _click(view, scene_pt):
    _move(view, scene_pt)
    _send(view, QEvent.Type.MouseButtonPress, scene_pt)
    _send(view, QEvent.Type.MouseButtonRelease, scene_pt)


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
def test_pickup_is_max_of_aperture_and_snap_radius(shown_model_view, zoom):
    """R1: pickup radius = max(15 px in scene units, SNAP_RADIUS = 10 units)."""
    view, scene = shown_model_view
    n = _node(scene, 0, 0)       # lone node: no pipe hit shape to muddy the probe
    _zoom(view, zoom)
    ctl = _pipe_mode(scene)
    r = max(15.0 / zoom, 10.0)   # 30 units at 0.5, 10 units (the floor) at 2.0
    inside, outside = QPointF(r - 1, 0), QPointF(r + 1, 0)
    assert ctl.resolve_pipe_target(inside, inside) == ("node", n)
    assert ctl.resolve_pipe_target(outside, outside) == ("none", None)


def _nodes(scene):
    return list(scene.sprinkler_system.nodes)


def _marker(scene):
    m = scene.pipe_target_marker
    return (m.kind if m.isVisible() else "none"), m.pos()


def _cross_pipe(scene):
    """A horizontal pipe through the origin (its ends are far from the probes)."""
    a, b = _node(scene, -300, 0), _node(scene, 300, 0)
    return a, b, scene.add_pipe(a, b, None, _propagate_ceiling=False)


@pytest.mark.parametrize("second", [False, True])
def test_zoom3_node_8_away_marker_says_node_and_click_connects(shown_model_view, second):
    view, scene = shown_model_view
    m_node = _node(scene, 8, 0)
    start = _node(scene, 0, -60)
    _zoom(view, 3.0)
    _pipe_mode(scene)
    if second:
        _click(view, QPointF(0, -60))
        assert scene.pipe_start_node is start
    n_nodes, n_pipes = len(_nodes(scene)), len(scene.sprinkler_system.pipes)
    _move(view, QPointF(0, 0))
    assert _marker(scene) == ("node", QPointF(8, 0))
    _send(view, QEvent.Type.MouseButtonPress, QPointF(0, 0))
    _send(view, QEvent.Type.MouseButtonRelease, QPointF(0, 0))
    assert len(_nodes(scene)) == n_nodes                    # no loose node
    if second:
        assert len(scene.sprinkler_system.pipes) == n_pipes + 1
        assert {m_node.other_end(p) for p in m_node.pipes} == {start}
    else:
        assert scene.pipe_start_node is m_node
        assert scene._pipe_node_was_new is False
        scene.cancel_pipe_placement()
        assert m_node in _nodes(scene)                      # Esc must not delete it


@pytest.mark.parametrize("second", [False, True])
def test_zoom3_node_8_off_a_pipe_still_connects_not_splits(shown_model_view, second):
    view, scene = shown_model_view
    _cross_pipe(scene)
    m_node = _node(scene, 0, 8)
    start = _node(scene, 0, -60)
    _zoom(view, 3.0)
    _pipe_mode(scene)
    if second:
        _click(view, QPointF(0, -60))
    n_nodes, n_pipes = len(_nodes(scene)), len(scene.sprinkler_system.pipes)
    _move(view, QPointF(0, 0))
    assert _marker(scene) == ("node", QPointF(0, 8))
    _send(view, QEvent.Type.MouseButtonPress, QPointF(0, 0))
    assert len(_nodes(scene)) == n_nodes
    assert len(scene.sprinkler_system.pipes) == n_pipes + (1 if second else 0)   # no split
    if not second:
        assert scene.pipe_start_node is m_node
        assert scene._pipe_node_was_new is False


@pytest.mark.parametrize("second", [False, True])
def test_zoom3_node_12_away_on_pipe_marker_says_split_and_click_splits(shown_model_view, second):
    view, scene = shown_model_view
    _cross_pipe(scene)
    far = _node(scene, 0, 12)
    start = _node(scene, 0, -60)
    _zoom(view, 3.0)
    _pipe_mode(scene)
    if second:
        _click(view, QPointF(0, -60))
    n_nodes, n_pipes = len(_nodes(scene)), len(scene.sprinkler_system.pipes)
    _move(view, QPointF(0, 0))
    assert _marker(scene) == ("pipe", QPointF(0, 0))
    _send(view, QEvent.Type.MouseButtonPress, QPointF(0, 0))
    assert len(_nodes(scene)) == n_nodes + 1
    assert far.pipes == []
    made = next(n for n in _nodes(scene) if n.scenePos() == QPointF(0, 0))
    assert len(made.pipes) == (3 if second else 2)
    assert len(scene.sprinkler_system.pipes) == n_pipes + (2 if second else 1)


@pytest.mark.parametrize("second", [False, True])
def test_zoom3_node_12_away_no_pipe_no_marker_and_a_new_node(shown_model_view, second):
    view, scene = shown_model_view
    far = _node(scene, 12, 0)
    start = _node(scene, 0, -60)
    _zoom(view, 3.0)
    _pipe_mode(scene)
    if second:
        _click(view, QPointF(0, -60))
    n_nodes = len(_nodes(scene))
    _move(view, QPointF(0, 0))
    assert _marker(scene)[0] == "none"
    _send(view, QEvent.Type.MouseButtonPress, QPointF(0, 0))
    assert len(_nodes(scene)) == n_nodes + 1
    assert far.pipes == []
    if not second:
        assert scene._pipe_node_was_new is True
        assert scene.pipe_start_node.scenePos() == QPointF(0, 0)


def test_riser_hit_press_connects_to_the_nearest_z_node(shown_model_view):
    view, scene = shown_model_view
    low, high = _node(scene, 0, 0, 0.0), _node(scene, 0, 0, 3000.0)
    scene.add_pipe(low, high, None, _propagate_ceiling=False).update_geometry()
    _zoom(view, 1.0)
    _pipe_mode(scene)
    n_nodes = len(_nodes(scene))
    p = QPointF(0, 0)
    _move(view, p)
    kind, _pos = _marker(scene)
    _send(view, QEvent.Type.MouseButtonPress, p)
    assert kind == "node"
    assert len(_nodes(scene)) == n_nodes
    assert scene.pipe_start_node in (low, high)
    assert scene._pipe_node_was_new is False


@pytest.mark.parametrize("zoom", [0.5, 2.0])
def test_pipe_hit_width_matches_the_pipe_shape(shown_model_view, zoom):
    """Just inside / just outside Pipe.shape()'s half width (16 px wide)."""
    view, scene = shown_model_view
    _a, _b, pipe = _cross_pipe(scene)
    _zoom(view, zoom)
    ctl = _pipe_mode(scene)
    half = max(pipe.pen().widthF(), 16.0 / zoom) / 2.0
    for dy, want in ((half - 0.5, "pipe"), (half + 0.5, "none")):
        p = QPointF(0, dy)
        assert pipe.shape().contains(p) is (want == "pipe")       # today's rule
        assert ctl.resolve_pipe_target(p, p)[0] == want
    # the stroke's square cap reaches one half width past each end, no further
    for dx, want in ((half - 0.5, "pipe"), (half + 0.5, "none")):
        past = QPointF(300 + dx, 0)
        assert pipe.shape().contains(past) is (want == "pipe")
        assert ctl.resolve_pipe_target(past, past)[0] == want


def test_hidden_pipe_is_not_hit(shown_model_view):
    view, scene = shown_model_view
    _a, _b, pipe = _cross_pipe(scene)
    _zoom(view, 1.0)
    ctl = _pipe_mode(scene)
    p = QPointF(0, 0)
    assert pipe in scene.items(p)                 # visible: today's query sees it
    assert ctl.resolve_pipe_target(p, p) == ("pipe", pipe)
    pipe.setVisible(False)
    assert pipe not in scene.items(p)             # hidden: today's query skips it
    assert ctl.resolve_pipe_target(p, p) == ("none", None)


def test_esc_and_double_click_hide_the_marker(shown_model_view):
    view, scene = shown_model_view
    _cross_pipe(scene)
    start = _node(scene, 0, -60)
    _zoom(view, 1.0)
    _pipe_mode(scene)
    _click(view, QPointF(0, -60))
    _move(view, QPointF(100, 0))
    assert _marker(scene)[0] == "pipe"
    assert scene.cancel_pipe_placement() is True
    assert _marker(scene)[0] == "none"
    _click(view, QPointF(0, -60))
    _move(view, QPointF(100, 0))
    assert _marker(scene)[0] == "pipe"
    _send(view, QEvent.Type.MouseButtonDblClick, QPointF(100, 0))
    assert scene.pipe_start_node is None
    assert _marker(scene)[0] == "none"
    _move(view, QPointF(100, 0))                  # returns on the next move
    assert _marker(scene)[0] == "pipe"


def test_chain_split_marker_sits_where_the_split_lands(shown_model_view):
    """45-snapped end: the marker is the projection of the snapped end."""
    view, scene = shown_model_view
    a, b = _node(scene, -500, 0), _node(scene, 500, 0)
    scene.add_pipe(a, b, None, _propagate_ceiling=False)
    start = _node(scene, 0, -400)
    _zoom(view, 1.0)
    _pipe_mode(scene)
    _click(view, QPointF(0, -400))
    # 40 units right of the 90-degree line: the cursor (OSNAP-snapped onto the
    # pipe at x=40) hits the pipe, but the 45 snap pulls the end to x=0, where
    # the split lands.
    cursor = QPointF(40, -5)
    _move(view, cursor)
    kind, pos = _marker(scene)
    assert kind == "pipe"
    assert abs(pos.x()) < 1.0                      # not at the cursor's x=40
    _send(view, QEvent.Type.MouseButtonPress, cursor)
    made = [n for n in _nodes(scene) if n not in (a, b, start)]
    assert len(made) == 1
    assert pos == made[0].scenePos()


def test_marker_honours_the_tab_selected_candidate(shown_model_view):
    view, scene = shown_model_view
    plain = _node(scene, 0, 0)
    spr = _node(scene, 5, 0)
    spr.add_sprinkler()
    _zoom(view, 1.0)
    ctl = _pipe_mode(scene)
    p = QPointF(1, 0)
    ctl.move_pipe(None, p)
    assert len(ctl._tab_candidates) == 2
    chosen = ctl._tab_candidates[ctl._tab_index]
    kind, pos = _marker(scene)
    assert kind == "node" and pos == chosen.scenePos()
    ctl.cycle_tab()
    chosen2 = ctl._tab_candidates[ctl._tab_index]
    assert chosen2 is not chosen
    assert _marker(scene)[1] == chosen2.scenePos()      # the cycle moves the marker too
    _send(view, QEvent.Type.MouseButtonPress, p)
    assert scene.pipe_start_node is chosen2             # what the marker showed


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
    p = QPointF(60, 0)        # inside the 75 mm riser disk, past the 15 px pickup
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


def test_equal_z_crossing_picks_the_later_added_pipe(shown_model_view):
    """scene.items stacked a tie with the later-added pipe on top; so does _pipe_at."""
    view, scene = shown_model_view
    _a, _b, first = _cross_pipe(scene)
    c, d = _node(scene, 0, -300), _node(scene, 0, 300)
    second = scene.add_pipe(c, d, None, _propagate_ceiling=False)
    second.update_geometry()
    _zoom(view, 1.0)
    ctl = _pipe_mode(scene)
    assert first.zValue() == second.zValue()
    p = QPointF(0, 0)
    top = [i for i in scene.items(p) if i in (first, second)][0]
    assert top is second                      # today's query: later-added on top
    assert ctl.resolve_pipe_target(p, p) == ("pipe", second)


def test_fully_transparent_pipe_is_not_hit(shown_model_view):
    """Display Manager can set a pipe's opacity to 0; scene.items skipped it."""
    view, scene = shown_model_view
    _a, _b, pipe = _cross_pipe(scene)
    _zoom(view, 1.0)
    ctl = _pipe_mode(scene)
    p = QPointF(0, 0)
    assert ctl.resolve_pipe_target(p, p) == ("pipe", pipe)
    pipe.setOpacity(0.0)
    assert pipe not in scene.items(p)
    assert ctl.resolve_pipe_target(p, p) == ("none", None)


@pytest.mark.parametrize("zoom", [0.5, 2.0])
def test_sloped_pipe_hit_width_matches_the_shape(shown_model_view, zoom):
    """A 45 degree run: just inside / outside the half width, and past the cap."""
    view, scene = shown_model_view
    a, b = _node(scene, 0, 0), _node(scene, 1000, 1000)
    pipe = scene.add_pipe(a, b, None, _propagate_ceiling=False)
    pipe.update_geometry()
    _zoom(view, zoom)
    ctl = _pipe_mode(scene)
    half = max(pipe.pen().widthF(), 16.0 / zoom) / 2.0
    s = 2 ** -0.5
    mid = QPointF(500, 500)
    for off, want in ((half - 0.5, "pipe"), (half + 0.5, "none")):
        p = mid + QPointF(-s, s) * off                       # across the run
        assert pipe.shape().contains(p) is (want == "pipe")
        assert ctl.resolve_pipe_target(p, p)[0] == want
        q = QPointF(0, 0) - QPointF(s, s) * off              # past the near end
        assert pipe.shape().contains(q) is (want == "pipe")
        assert ctl.resolve_pipe_target(q, q)[0] == want


def test_display_scale_widens_the_hit_beyond_the_reject_margin(shown_model_view):
    """A Display Manager scale above 1 widens the stroke; the bbox reject follows."""
    view, scene = shown_model_view
    a, b = _node(scene, 0, 0), _node(scene, 1000, 1000)
    pipe = scene.add_pipe(a, b, None, _propagate_ceiling=False)
    pipe.update_geometry()
    pipe._display_scale = 8.0
    pipe.set_pipe_display()
    _zoom(view, 1.0)
    ctl = _pipe_mode(scene)
    half = pipe.pen().widthF() / 2.0
    assert half > 150.0
    s = 2 ** -0.5
    q = QPointF(0, 0) - QPointF(s, s) * (half - 0.5)         # inside the square cap
    assert pipe.shape().contains(q)
    assert ctl.resolve_pipe_target(q, q) == ("pipe", pipe)


# ---- VC9 I1, I2, M2, M3: seams with the wider pickup -------------------------

def test_typed_length_ignores_a_node_under_the_cursor(shown_model_view):
    """I1: the Tab list follows the mouse; a typed end is exact."""
    view, scene = shown_model_view
    far = _node(scene, 3000, 0)
    _zoom(view, 0.1)
    ctl = _pipe_mode(scene)
    ctl.press_pipe(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    ctl.move_pipe(None, QPointF(2900, 0))
    assert far in ctl._tab_candidates                   # the cursor rests near it
    assert scene._commit_pipe_typed({"Length": 1000.0, "Angle": 0.0}) is True
    end = scene.pipe_start_node
    assert end is not far
    assert end.scenePos() == QPointF(1000, 0)
    assert far.pipes == []


def test_pickup_takes_the_nearest_node_not_the_first_added(shown_model_view):
    """I2: at fit zoom the radius holds real neighbours."""
    view, scene = shown_model_view
    a, b = _node(scene, 0, 0), _node(scene, 100, 0)
    _zoom(view, 0.1)
    ctl = _pipe_mode(scene)
    assert ctl.resolve_pipe_target(QPointF(100, 0), QPointF(100, 0)) == ("node", b)
    ctl.move_pipe(None, QPointF(100, 0))
    assert ctl._tab_candidates == [b, a]
    ctl.press_pipe(None, QPointF(100, 0), QPointF(100, 0), None, None, None)
    assert scene.pipe_start_node is b


def test_second_click_near_the_start_still_reaches_a_neighbour(shown_model_view):
    """I2: the chain start is no target, so a nearby click is not refused."""
    view, scene = shown_model_view
    a, b = _node(scene, 0, 0), _node(scene, 100, 0)
    _zoom(view, 0.1)
    ctl = _pipe_mode(scene)
    ctl.move_pipe(None, QPointF(0, 0))
    ctl.press_pipe(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    assert scene.pipe_start_node is a
    p = QPointF(40, 0)                                  # nearer to a
    ctl.move_pipe(None, p)
    assert scene.pipe_target_marker.pos() == QPointF(100, 0)
    assert ctl.press_pipe(None, p, p, None, None, None) is True
    assert len(scene.sprinkler_system.pipes) == 1
    assert {a.other_end(q) for q in a.pipes} == {b}


def test_stacked_nodes_still_pick_by_template_elevation(shown_model_view):
    """I2: XY first, but a riser stack at one spot still goes by z_hint."""
    view, scene = shown_model_view
    low, high = _node(scene, 0, 0, 0.0), _node(scene, 3, 0, 3000.0)
    _zoom(view, 0.1)
    ctl = _pipe_mode(scene)
    p = QPointF(0, 0)                                   # low is the nearer one
    assert ctl.resolve_pipe_target(p, p, z_hint=2800.0) == ("node", high)
    ctl._update_pipe_tab_candidates(p, z_hint=2800.0)
    assert ctl._tab_candidates == [high, low]


def test_sprinkler_tool_near_a_node_lands_where_clicked(shown_model_view):
    """M2, ratified: the head goes on the pipe unless the click is inside 12 px."""
    from firepro3d.pipe import Pipe
    view, scene = shown_model_view
    a, _b, pipe = _run(scene)
    _zoom(view, 1.0)
    scene.set_mode("sprinkler")
    picks = {}
    for x in (8, 100):
        under = [i for i in scene.items(QPointF(x, 0)) if isinstance(i, (Node, Pipe))]
        picks[x] = under[0] if under else None
    assert picks == {8: a, 100: pipe}
    nodes, pipes = len(scene.sprinkler_system.nodes), len(scene.sprinkler_system.pipes)
    p = QPointF(100, 0)
    scene._press_sprinkler(None, p, p, pipe, None, pipe)
    assert a.has_sprinkler() is False
    assert len(scene.sprinkler_system.nodes) == nodes + 1
    assert len(scene.sprinkler_system.pipes) == pipes + 1


def test_scene_escape_ends_the_chain_like_the_shortcut(shown_model_view):
    """M3: both Esc paths hide the marker and drop an unused new start node."""
    from PyQt6.QtGui import QKeyEvent
    view, scene = shown_model_view
    _run(scene)
    ctl = _pipe_mode(scene)
    nodes = len(scene.sprinkler_system.nodes)
    far = QPointF(0, 900)
    ctl.move_pipe(None, far)
    ctl.press_pipe(None, far, far, None, None, None)
    ctl.move_pipe(None, QPointF(5, 0))
    assert scene.pipe_target_marker.isVisible() is True
    scene.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                  Qt.KeyboardModifier.NoModifier))
    assert scene.pipe_start_node is None
    assert scene.mode == "pipe"
    assert scene.pipe_target_marker.isVisible() is False
    assert len(scene.sprinkler_system.nodes) == nodes
