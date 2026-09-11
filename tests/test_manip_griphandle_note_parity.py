"""U3 box-native migration guards for NoteAnnotation.

Mirrors tests/test_manip_griphandle_rect_parity.py. Each guard constructs a real
NoteAnnotation, drives observable behaviour, and asserts ground truth. Rotation
uses the bake-at-rest model ported from RectangleItem (data _angle, NO Qt
setRotation).
"""
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform

from firepro3d.annotations import NoteAnnotation


# ── Task 1: data-model fields ────────────────────────────────────────────────

def test_new_fields_default_to_identity(qapp):
    """A fresh note has angle 0 and auto-fit box height (0) — identity vs today."""
    note = NoteAnnotation("Hello", x=10, y=20)
    assert note._angle == 0.0
    assert note._box_height == 0.0
    assert note._pivot is None
