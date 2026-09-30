"""place_block mode: one click places at the snapped point, 0 deg (smoke 2).

The rotation step was removed (user: "just place at 0, I can rotate later with
scene tools"): a click commits the instance at the snapped cursor, upright, as
one undo step, and the mode stays live (ghost re-armed) until Esc.
"""
import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _def(ms, name="A"):
    d = BlockDefinition.new(name=name, library="L", series="S",
                            primitives=[{"type": "draw_line", "pt1": [0, 0],
                                         "pt2": [100, 0], "color": "#ffffff",
                                         "lineweight": 1.0}], origin=(0.0, 0.0))
    ms.register_block_definition(d)
    return d


def _shown(scene):
    from firepro3d.model_view import Model_View
    from firepro3d.scale_manager import ScaleManager
    scene.scale_manager = ScaleManager()
    v = Model_View(scene)
    v.resize(900, 700)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.resetTransform()
    v.centerOn(0, 0)
    QApplication.processEvents()
    return v


def _hover(view, scene_pt):
    """A bare (no-button) MouseMove delivered synchronously to the viewport
    (QTest.mouseMove moves the OS cursor and delivers asynchronously)."""
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QMouseEvent
    ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(view.mapFromScene(scene_pt)),
                     Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()


def _click(view, scene_pt):
    """One real left click at *scene_pt* (hover first so the ghost tracks)."""
    vp_pt = QPoint(view.mapFromScene(scene_pt))
    _hover(view, scene_pt)
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, vp_pt)
    QApplication.processEvents()


def _scene_with_snap_target():
    sc = Model_Space()
    d = _def(sc)
    target = LineItem(QPointF(-300, 0), QPointF(-100, 0))   # endpoint to snap onto
    sc.addItem(target)
    sc._draw_lines.append(target)
    return sc, d


def test_one_click_places_at_snapped_point_0deg_one_undo_and_rearms(qapp):
    sc, d = _scene_with_snap_target()
    v = _shown(sc)
    try:
        sc.push_undo_state()                                 # baseline
        depth0 = sc._undo_pos
        sc.set_mode("place_block", template=d.id)
        _click(v, QPointF(-103, 2))                          # within the aperture
        assert [(i.block_id, i.block_pos(), i.block_rotation())
                for i in sc._block_instances] == [(d.id, (-100.0, 0.0), 0.0)]
        assert sc._undo_pos == depth0 + 1                    # exactly one undo step
        # the mode stays live with a fresh ghost that is NOT a placed instance
        assert sc.mode == "place_block"
        g = sc._place_block_ghost
        assert g is not None and g.scene() is sc
        assert g not in sc._block_instances
        assert g.block_rotation() == 0.0
        # a second click places a second instance (still 0 deg) exactly where
        # the ghost showed the snapped cursor (grid/other snaps may apply here)
        _hover(v, QPointF(200, 150))
        shown_at = sc._place_block_ghost.block_pos()
        assert shown_at == pytest.approx((200.0, 150.0), abs=10.0)
        _click(v, QPointF(200, 150))
        assert len(sc._block_instances) == 2
        assert sc._block_instances[1].block_pos() == shown_at
        assert sc._block_instances[1].block_rotation() == 0.0
        assert sc._undo_pos == depth0 + 2
        # Esc exits and removes the ghost
        g = sc._place_block_ghost
        assert g is not None
        QTest.keyClick(v.viewport(), Qt.Key.Key_Escape)
        QApplication.processEvents()
        assert sc.mode != "place_block"
        assert sc._place_block_ghost is None
        assert g.scene() is None
        sc.undo()                                            # one Ctrl+Z = one placement
        assert len(sc._block_instances) == 1
    finally:
        sc.cleanup(); v.close(); v.deleteLater(); QApplication.processEvents()


def test_place_block_offers_no_hud_and_draws_no_guides(qapp):
    """No rotate step: no rotation HUD, no protractor guides after a click,
    and Enter with nothing typed is a no-op."""
    from PyQt6.QtWidgets import QGraphicsLineItem
    sc, d = _scene_with_snap_target()
    v = _shown(sc)
    try:
        lines_before = {id(i) for i in sc.items() if isinstance(i, QGraphicsLineItem)}
        sc.set_mode("place_block", template=d.id)
        assert sc.active_schema() is None
        _click(v, QPointF(50, 50))
        _hover(v, QPointF(150, 90))
        assert sc.active_schema() is None
        assert sc.dynamic_input is None
        new_lines = [i for i in sc.items() if isinstance(i, QGraphicsLineItem)
                     and id(i) not in lines_before and i.isVisible()]
        assert new_lines == []
        n = len(sc._block_instances)
        assert n == 1
        QTest.keyClick(v.viewport(), Qt.Key.Key_Return)
        QApplication.processEvents()
        assert len(sc._block_instances) == n and sc.mode == "place_block"
    finally:
        sc.set_mode(None)
        sc.cleanup(); v.close(); v.deleteLater(); QApplication.processEvents()


def test_place_block_exit_clears_ghost(model_space):
    d = _def(model_space)
    model_space.set_mode("place_block", template=d.id)
    model_space._move_place_block(None, QPointF(0.0, 0.0))
    assert model_space._place_block_ghost is not None
    model_space.set_mode(None)
    assert model_space._place_block_ghost is None
    assert model_space._place_block_id is None


def test_place_block_reentry_clears_stale_ghost(model_space):
    # Seam-review blocker: activating a DIFFERENT block mid-placement must drop
    # the previous block's ghost (else it previews the wrong block).
    a = _def(model_space, "A")
    b = _def(model_space, "B")
    model_space.set_mode("place_block", template=a.id)
    model_space._move_place_block(None, QPointF(0.0, 0.0))
    old_ghost = model_space._place_block_ghost
    assert old_ghost is not None
    model_space.set_mode("place_block", template=b.id)   # re-enter for block B
    assert model_space._place_block_id == b.id
    assert model_space._place_block_ghost is None         # stale ghost cleared
    assert old_ghost.scene() is None                      # removed from the scene


def test_make_block_from_selection_consumes_and_places(model_space):
    from firepro3d.geometry_2d import LineItem
    from PyQt6.QtCore import QPointF
    li = LineItem.from_dict({"type": "draw_line", "pt1": [0, 0], "pt2": [100, 0],
                             "color": "#ffffff", "lineweight": 1.0})
    model_space.addItem(li)
    model_space._draw_lines.append(li)
    inst = model_space.make_block_from_selection(
        [li], origin=QPointF(0.0, 0.0), name="Corner", library="Detail", series="Joints")
    assert li not in model_space._draw_lines
    assert li.scene() is None
    assert inst.block_id in model_space._block_definitions
    assert inst in model_space._block_instances
    d = model_space.get_block_definition(inst.block_id)
    assert d.name == "Corner" and d.library == "Detail" and d.series == "Joints"


def test_make_block_refuses_empty(model_space):
    from PyQt6.QtCore import QPointF
    assert model_space.make_block_from_selection(
        [], origin=QPointF(0, 0), name="x", library="l", series="s") is None
