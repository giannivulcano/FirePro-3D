"""
test_block_editor_levelless_authoring.py
========================================
Containment C3 block-editor smoke: the Block-Editor scene
(Model_Space(scene_role="block_editor")) must still author, undo-restore, and
copy/paste the level-less 2D primitives — the geometry-drawing / paste paths
that used to copy a template level must work without one.
"""

import json
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from firepro3d.model_space import Model_Space
from firepro3d.geometry_2d import RectangleItem, CircleItem


def _editor_scene():
    s = Model_Space(scene_role="block_editor")
    return s


def test_block_editor_authors_levelless_primitive(qapp):
    s = _editor_scene()
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    s.addItem(r)
    s._draw_rects.append(r)
    assert not hasattr(r, "level")


def test_block_editor_undo_capture_restore_primitive(qapp):
    s = _editor_scene()
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    s.addItem(r)
    s._draw_rects.append(r)
    snap = s._capture_network()
    s._restore_network(snap)
    assert len(s._draw_rects) == 1
    assert not hasattr(s._draw_rects[0], "level")


def test_block_editor_paste_primitive(qapp):
    s = _editor_scene()
    c = CircleItem(QPointF(0, 0), 50.0)
    payload = json.dumps([c.to_dict()])
    QApplication.clipboard().setText(payload)
    before = len(s._draw_circles)
    s.paste_items(QPointF(10, 10))
    assert len(s._draw_circles) == before + 1
    assert not hasattr(s._draw_circles[-1], "level")
