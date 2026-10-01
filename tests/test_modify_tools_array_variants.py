"""P1 DD5: Array variants (Linear / 2D / Polar), angle lock, session memory.

Governing: docs/superpowers/specs/2026-10-01-scene-tools-p1-batch-design.md
DD5 + acceptance M1 (folded into scene-tools.md D10 at Account). Every guard
drives the real path: a shown Model_View over a real block_editor
Model_Space, real mouse events, the real HUD (begin_dynamic_input / editor
text / Tab / Esc / _accept), and asserts scene coordinates of the copies.
The views ignore the real OS mouse (``ignore_os_mouse``) so a user's cursor
over the test window cannot inject moves.
"""
import math

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

from tests._modify_tools_helpers import add_primitive, ignore_os_mouse
from tests._snap_polish_helpers import click, close_view, make_view, move

COS30 = math.cos(math.radians(30.0))
SIN30 = math.sin(math.radians(30.0))


def _view(**kw):
    """A shown Model_View (``make_view``) deaf to the real OS mouse."""
    view, scene = make_view(**kw)
    ignore_os_mouse(view)
    return view, scene


def _type(scene, **fields):
    """Engage the HUD, type *fields* by name, press the HUD's Enter path."""
    assert scene.begin_dynamic_input() is True
    for name, text in fields.items():
        scene.dynamic_input.editor(name).setText(text)
    scene.dynamic_input._accept()


def _centres(circles):
    return sorted((round(c._center.x(), 2), round(c._center.y(), 2))
                  for c in circles)


def test_typed_count_prefills_the_next_array(qapp):
    """DD5 memory: a typed Count is remembered for the next Array on the same
    canvas (it used to fall back to the fixed default 3)."""
    view, scene = _view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")          # centre (0,0) r=50
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(200, 0))
        _type(scene, Spacing="200", Count="4")
        assert len(getattr(scene, attr)) == 4
        p0 = scene._undo_pos
        # Run 2: click-commit at the cursor spacing — Count is the remembered 4.
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(0, -300))
        click(view, QPointF(0, -300))
        lst = getattr(scene, attr)
        assert len(lst) == 4 + 3                                       # [RED]
        assert _centres(lst[4:]) == [(0.0, -900.0), (0.0, -600.0), (0.0, -300.0)]
        assert scene._undo_pos == p0 + 1
        assert item.isSelected()
    finally:
        close_view(view, scene)
