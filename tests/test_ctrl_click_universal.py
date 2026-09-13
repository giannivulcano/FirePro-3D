"""C3: Ctrl+click is a universal selection toggle for ALL selectable types.

The gridline-only special case in ``Model_Space.mousePressEvent`` is folded
away; gridlines now flow through the same HALO-driven ``_press_select_item``
path as everything else. These tests drive the WIDGET (posted events on a
shown view) to prove a gridline (the folded case) and a node select via the
same generic path, and drive ``_press_select_item`` directly to prove the
universal Ctrl toggle-off works for a gridline target.

Note on scope: once ANY item is selected a SelectionManipulator becomes
visible and its interior-press guard (mousePressEvent, "select-manipulator
interior press") swallows subsequent left-clicks over its frame BEFORE
per-mode dispatch runs. That envelope is orthogonal to this task (C3 must not
touch manipulator press routing), so the toggle-OFF assertion exercises the
generic ``_press_select_item`` path directly rather than a second posted click
that the manip would eat.
"""
from types import SimpleNamespace

from PyQt6.QtCore import QPointF, QEvent, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.gridline import GridlineItem
from firepro3d.node import Node


def _hover(view, scene_pt):
    """Post a bare MouseMove so HALO rebuilds its candidate list at scene_pt."""
    ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(view.mapFromScene(scene_pt)),
                     Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view.viewport(), ev)


def _click(view, scene_pt, ctrl=False):
    mods = Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier
    for t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        ev = QMouseEvent(t, QPointF(view.mapFromScene(scene_pt)),
                         Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, mods)
        QApplication.sendEvent(view.viewport(), ev)


def _mk(qapp):
    sc = Model_Space()
    v = Model_View(sc)
    v.resize(500, 500)
    v.show()
    QApplication.processEvents()
    sc.set_mode(None)
    return sc, v


def test_ctrl_click_selects_gridline_via_generic_path(qapp):
    """The folded case: a posted Ctrl+click on a gridline body selects it.

    On the retired path the dedicated gridline branch handled this WITHOUT
    HALO. After the fold, selection REQUIRES HALO to have resolved the
    gridline (bubble/body -> parent GridlineItem) so ``_press_select_item``
    has a ``halo_item()`` target. Asserting HALO picks it first, then the
    click selects it, discriminates the HALO-driven path.
    """
    sc, v = _mk(qapp)
    g = GridlineItem(QPointF(0, 0), QPointF(0, 400), label="A")
    sc.addItem(g)
    sc._gridlines.append(g)
    pt = QPointF(0, 200)                 # on the gridline body

    _hover(v, pt)
    assert sc.halo_item() is g, "HALO must resolve the gridline body on hover"

    _click(v, pt, ctrl=True)
    assert g.isSelected()                # universal ctrl toggle: OFF -> ON


def test_ctrl_click_selects_node_via_generic_path(qapp):
    """Parity: a posted Ctrl+click on a node selects it through the same path."""
    sc, v = _mk(qapp)
    n = Node(0.0, 0.0)
    sc.addItem(n)
    pt = QPointF(0.0, 0.0)

    _hover(v, pt)
    assert sc.halo_item() is n, "HALO must resolve the node on hover"

    _click(v, pt, ctrl=True)
    assert n.isSelected()                # OFF -> ON


def test_ctrl_toggle_off_gridline_through_generic_path(qapp):
    """The universal Ctrl toggle-OFF: an already-selected gridline flips off.

    Driven through ``_press_select_item`` directly (see module docstring: the
    manipulator envelope swallows a second posted click, out of C3 scope). A
    gridline target must obey the same ``not isSelected()`` toggle as any
    other item — proving the gridline is no longer a special case.
    """
    sc, v = _mk(qapp)
    g = GridlineItem(QPointF(0, 0), QPointF(0, 400), label="A")
    sc.addItem(g)
    sc._gridlines.append(g)
    g.setSelected(True)

    pt = QPointF(0, 200)
    ev = SimpleNamespace(modifiers=lambda: Qt.KeyboardModifier.ControlModifier,
                         scenePos=lambda: pt)
    sc._halo_candidates = [g]
    sc._halo_index = 0
    sc._press_select_item(ev, pt, pt, g, None, None)
    assert not g.isSelected()            # ON -> OFF via the generic toggle
