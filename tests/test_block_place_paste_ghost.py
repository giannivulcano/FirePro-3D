"""Block placement uses the Paste ghost (2026-10-10 placement batch).

G1 no self-snap (L164) · G2 trace ghost, no scene ghost item · G3 click places,
stays armed · G4 Space / Shift+Space rotate 90° CW / CCW on screen · G5 Paste of
a block instance has a ghost (L204).
"""
import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_instance import BlockInstance
from firepro3d.geometry_2d import LineItem
from firepro3d.halo import halo_scene_path
from firepro3d.model_space import Model_Space


def _def(ms):
    d = BlockDefinition.new(name="A", library="L", series="S",
                            primitives=[LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict()],
                            origin=(0.0, 0.0))
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
    v.setFocus()
    QApplication.processEvents()
    return v


def _hover(view, scene_pt):
    ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(view.mapFromScene(scene_pt)),
                     Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()


def _click(view, scene_pt):
    _hover(view, scene_pt)
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, QPoint(view.mapFromScene(scene_pt)))
    QApplication.processEvents()


def _ghost_rect(sc):
    r = None
    for p in sc._move_ghost:
        r = p.boundingRect() if r is None else r.united(p.boundingRect())
    return r


def _close(v, sc):
    sc.set_mode(None)
    v.close()
    v.deleteLater()
    QApplication.processEvents()


def test_g5_pasting_a_block_instance_shows_its_ghost(qapp):
    sc = Model_Space()
    d = _def(sc)
    inst = sc.place_block_instance(d.id, (10.0, 20.0))
    paths = sc._modify_ctl._clipboard_ghost_paths([inst.to_dict()])
    assert len(paths) == 1
    r = paths[0].boundingRect()
    assert (round(r.left()), round(r.right()), round(r.top())) == (10, 110, 20)


def _scene_with_target():
    sc = Model_Space()
    d = _def(sc)
    target = LineItem(QPointF(-300, 0), QPointF(-100, 0))
    sc.addItem(target)
    sc._draw_lines.append(target)
    return sc, d, target


def test_g1_the_ghost_is_never_a_snap_target(qapp):
    sc, d, target = _scene_with_target()
    v = _shown(sc)
    try:
        sc.set_mode("place_block", template=d.id)
        for pt in (QPointF(200, 150), QPointF(203, 152), QPointF(240, 149)):
            _hover(v, pt)
            sc.get_effective_position(QPointF(pt.x() + 1, pt.y() + 1))
            assert sc._snap_result is None              # empty space: no glyph
        _hover(v, QPointF(-103, 2))
        sc.get_effective_position(QPointF(-103, 2))
        assert sc._snap_result is not None and sc._snap_result.source_item is target
    finally:
        _close(v, sc)


def test_g2_trace_ghost_with_the_origin_on_the_cursor_no_scene_item(qapp):
    sc, d, _t = _scene_with_target()
    v = _shown(sc)
    try:
        sc.set_mode("place_block", template=d.id)
        _hover(v, QPointF(200, 150))
        assert not [i for i in sc.items() if isinstance(i, BlockInstance)]
        r = _ghost_rect(sc)
        assert (round(r.left()), round(r.right()), round(r.top())) == (200, 300, 150)
    finally:
        _close(v, sc)


def test_g3_each_click_places_and_the_mode_stays_armed(qapp):
    sc, d, _t = _scene_with_target()
    v = _shown(sc)
    try:
        sc.push_undo_state()
        depth0 = sc._undo_pos
        sc.set_mode("place_block", template=d.id)
        _click(v, QPointF(200, 150))
        _click(v, QPointF(400, 150))
        assert [i.block_pos() for i in sc._block_instances] == [(200.0, 150.0), (400.0, 150.0)]
        assert sc._undo_pos == depth0 + 2 and sc.mode == "place_block"
        assert _ghost_rect(sc) is not None                       # re-armed ghost
    finally:
        _close(v, sc)
