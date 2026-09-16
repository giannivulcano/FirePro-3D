"""tests/test_block_editor_preview_node.py — no blue placement dot in the block editor.

Bug (user, 2026-09-16): a blue preview-node dot rode every placement in the Block
Editor.  The plan scene suppresses that dot while the crosshair owns the cursor
(main._apply_crosshair sets scene._suppress_preview_node), but the Block Editor's
isolated scene never got it.  The editor authors only 2D geometry (own ghost), so
it suppresses the dot at construction.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QTabWidget

from firepro3d.model_space import Model_Space
from firepro3d.block_editor import BlockEditorManager


def _open_editor(qapp):
    project = Model_Space()
    mgr = BlockEditorManager(QTabWidget(), project)
    return mgr.open_new()


def test_editor_scene_suppresses_preview_node(qapp):
    w = _open_editor(qapp)
    assert w.editor_scene._suppress_preview_node is True


def test_update_preview_node_keeps_dot_hidden_in_editor(qapp):
    w = _open_editor(qapp)
    sc = w.editor_scene
    # Driving the real preview-node update (as placement moves do) must NOT show
    # the blue dot while suppression is on.
    sc.update_preview_node(QPointF(123, 45))
    assert sc.preview_node.isVisible() is False
