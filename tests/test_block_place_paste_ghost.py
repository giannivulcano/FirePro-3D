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
