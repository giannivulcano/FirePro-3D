"""Arrow-key flip through the REAL entry path (block mirror/scale G7).

Blocks-browser double-click -> <- -> first canvas click: the arrow must reach
the scene BEFORE any click on the canvas, via main.py's deferred focus
hand-off (``QTimer.singleShot(0, view.setFocus)`` in ``_on_block_activated``,
review I1) -- no explicit setFocus here. Modelled on
``tests/test_block_drag_drop.py::test_space_rotates_the_first_placement_after_a_browser_double_click``
and kept in its own file because that file segfaults when run whole.

RED-provability caveat (same as the sibling): in this harness keyboard focus
already lands on the visible plan tab without the hand-off, so the hand-off
itself is a regression guard, not RED-provable here. The flip branch IS
RED-provable: with the keyPressEvent branch removed, the first placement comes
out upright.
"""
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_view import Model_View
from tests.test_block_drag_drop import (  # noqa: F401 (fixtures by name)
    _click_place, _dclick_leaf, _drop_lib_instances, _forget_defs, _hover,
    _main_window_singleton, main_window)


def _L_def(name):
    """(0,0)->(100,0) and (0,0)->(0,-40): asymmetric, so a flip is visible."""
    return BlockDefinition.new(name=name, library="L", series="S", origin=(0.0, 0.0),
                               primitives=[LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict(),
                                           LineItem(QPointF(0, 0), QPointF(0, -40)).to_dict()])


def _ends(scene, inst):
    return {(round(p.x(), 3), round(p.y(), 3))
            for k, p, _n in scene._snap_engine._collect(inst) if k == "endpoint"}


def test_left_arrow_flips_the_first_placement_after_a_browser_double_click(qapp, main_window):
    proj = main_window.scene
    b = _L_def("L_FLIP")
    proj.register_block_definition(b)
    QApplication.processEvents()
    try:
        main_window._activate_plan_view(proj.active_level)  # the visible plan tab
        QApplication.processEvents()
        v = main_window.central_tabs.currentWidget()
        assert isinstance(v, Model_View) and v.isVisible() and v.scene() is proj
        _dclick_leaf(main_window, b.name)
        assert proj.mode == "place_block"
        QApplication.processEvents()          # main.py's deferred view.setFocus
        v.resetTransform()
        v.centerOn(0, 0)
        QApplication.processEvents()
        _hover(v, QPointF(20, 30))
        # The arrow goes wherever keyboard focus is -- exactly as the OS delivers it
        fw = QApplication.focusWidget()
        assert fw is not None
        for et in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(fw, QKeyEvent(et, Qt.Key.Key_Left,
                                                 Qt.KeyboardModifier.NoModifier))
        QApplication.processEvents()
        _click_place(v, QPointF(20, 30))      # the FIRST canvas click
        inst = [i for i in proj._block_instances if i.block_id == b.id][-1]
        assert inst.block_mirrored() is True
        # Mirrored left-right across the vertical line through the insertion point.
        assert _ends(proj, inst) == {(20, 30), (-80, 30), (20, -10)}
    finally:
        proj.set_mode("select")
        _drop_lib_instances(proj, b.id)
        _forget_defs(proj, b)
        QApplication.processEvents()
