from PyQt6.QtCore import QRectF, QPointF, QEvent, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View

# Node markers use ItemIgnoresTransformations, giving them a fixed-pixel shape
# that inflates to ~356 scene units when no view transform is attached (unit
# tests have no view). Window rects are therefore sized to fully contain a
# node's inflated marker shape, and entities are spaced far apart so their
# inflated shapes do not overlap. The window(contained) vs crossing(intersect)
# semantics are what these tests assert.


def test_window_selects_fully_contained_only(qapp):
    sc = Model_Space()
    inside = sc.add_node(5000.0, 5000.0)
    edge = sc.add_pipe(sc.add_node(0.0, 0.0), sc.add_node(100.0, 100.0))
    # Straddler crosses the window's left edge: it intersects the window but is
    # not fully contained, so a window (contains) query must exclude it. This
    # also falsifies a contains/intersects swap in the implementation.
    straddler = sc.add_pipe(sc.add_node(4600.0, 5000.0),
                            sc.add_node(5000.0, 5000.0))
    # Window fully contains the node marker at (5000,5000); the far pipe and the
    # straddler are excluded, so a window (contains) query selects only the node.
    sc.commit_rubber_band(QRectF(4800, 4800, 600, 600), crossing=False, additive=False)
    assert inside.isSelected()
    assert not edge.isSelected()
    assert not straddler.isSelected()


def test_crossing_selects_intersecting(qapp):
    sc = Model_Space()
    edge = sc.add_pipe(sc.add_node(0.0, 0.0), sc.add_node(100.0, 100.0))
    # Small box straddles the pipe diagonal: it intersects but does not contain.
    sc.commit_rubber_band(QRectF(40, 40, 20, 20), crossing=True, additive=False)
    assert edge.isSelected()


def test_additive_preserves_existing(qapp):
    sc = Model_Space()
    a = sc.add_node(0.0, 0.0)
    b = sc.add_node(5000.0, 5000.0)
    a.setSelected(True)
    # Window contains only b; additive must keep a's pre-existing selection.
    sc.commit_rubber_band(QRectF(4800, 4800, 600, 600), crossing=False, additive=True)
    assert a.isSelected() and b.isSelected()


def test_excluded_flag_never_selected(qapp):
    sc = Model_Space()
    n = sc.add_node(50.0, 50.0)
    n._exclude_from_bulk_select = True
    sc.commit_rubber_band(QRectF(-200, -200, 500, 500), crossing=True, additive=False)
    assert not n.isSelected()


# ── Posted-drag integration tests (view + scene) ──────────────────────────
# These drive the full Model_View interaction envelope with real QMouseEvents
# posted to the viewport, exercising the scene-drawn window/crossing band that
# replaced Qt-native RubberBandDrag in select mode. A real 600x600 view is
# shown, so markers are hit against their ON-SCREEN (device-transformed) shape.


def _drag_vp(view, vp_start, vp_end, ctrl=False):
    """Post a press/move/release drag in VIEWPORT pixel coordinates.

    Driving in viewport px (not scene coords) is deliberate: markers use
    ItemIgnoresTransformations so their on-screen footprint does not track
    their scene position. Picking empty start pixels and a rect that encloses
    the on-screen marker cluster is far more robust than reasoning in scene
    units. The default fit puts the origin cluster near viewport centre and
    leaves the corners empty (verified empirically).
    """
    mods = (Qt.KeyboardModifier.ControlModifier if ctrl
            else Qt.KeyboardModifier.NoModifier)
    p1 = QPointF(*vp_start)
    p2 = QPointF(*vp_end)
    seq = [(QEvent.Type.MouseButtonPress, p1), (QEvent.Type.MouseMove, p2),
           (QEvent.Type.MouseButtonRelease, p2)]
    for t, p in seq:
        ev = QMouseEvent(t, p, Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton, mods)
        QApplication.sendEvent(view.viewport(), ev)


def _mk(qapp):
    sc = Model_Space()
    view = Model_View(sc)
    view.resize(600, 600)
    view.show()
    QApplication.processEvents()
    sc.set_mode(None)
    return sc, view


def test_ltr_drag_is_window(qapp):
    sc, view = _mk(qapp)
    inside = sc.add_node(0.0, 0.0)
    # Empty-start L->R window drag: press at the empty top-left corner and
    # drag to the bottom-right, enclosing the origin node's on-screen marker.
    _drag_vp(view, (50, 50), (550, 550))   # L->R window
    assert inside.isSelected()


def test_rtl_drag_is_crossing(qapp):
    sc, view = _mk(qapp)
    # Nodes spaced far apart so the pipe spans a large on-screen diagonal
    # (vp ~76,76 -> ~522,522). A small box straddling the middle of that
    # diagonal INTERSECTS the pipe but does NOT contain it — so this test
    # fails under a window(contains) query and passes only for crossing.
    edge = sc.add_pipe(sc.add_node(-15000.0, -15000.0),
                       sc.add_node(15000.0, 15000.0))
    # Empty-start R->L drag (end.x < start.x = crossing) across the pipe.
    _drag_vp(view, (330, 270), (270, 330))   # R->L crossing
    assert edge.isSelected()
