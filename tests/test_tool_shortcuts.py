"""tests/test_tool_shortcuts.py — single-key drawing-tool shortcuts (#9).

L/R/C/A/G activate Line/Rectangle/Circle/Arc/Gridline via ``Model_View.keyPressEvent``,
which is scene-focus-gated by construction (only fires when the canvas holds focus,
never while a HUD field or another widget does).  Bare keys only — Ctrl/Shift combos
fall through to their own bindings.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent

from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View


@pytest.fixture
def scene(qapp):
    return Model_Space()


@pytest.fixture
def view(scene):
    v = Model_View(scene)
    v.resize(400, 300)
    yield v
    v.close()


def _press(view, key, mods=Qt.KeyboardModifier.NoModifier):
    ev = QKeyEvent(QEvent.Type.KeyPress, key, mods)
    view.keyPressEvent(ev)
    return ev


@pytest.mark.parametrize("key,mode", [
    (Qt.Key.Key_L, "draw_line"),
    (Qt.Key.Key_R, "draw_rectangle"),
    (Qt.Key.Key_C, "draw_circle"),
    (Qt.Key.Key_A, "draw_arc"),
    (Qt.Key.Key_G, "draw_gridline"),
    (Qt.Key.Key_K, "polyline"),      # placeholder until Line+Polyline merge
])
def test_bare_key_activates_tool(view, scene, key, mode):
    ev = _press(view, key)
    assert scene.mode == mode
    assert ev.isAccepted()


def test_ctrl_letter_is_not_a_tool_shortcut(view, scene):
    # Ctrl+A must NOT enter draw_arc (it's Select All); the tool map is bare-key
    # only.  Mode-unchanged is the real check (a fresh QKeyEvent defaults to
    # accepted, so isAccepted() is not a reliable fall-through signal here).
    scene.set_mode("select")
    _press(view, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert scene.mode == "select"


def test_shift_letter_is_not_a_tool_shortcut(view, scene):
    scene.set_mode("select")
    _press(view, Qt.Key.Key_R, Qt.KeyboardModifier.ShiftModifier)
    assert scene.mode == "select"
