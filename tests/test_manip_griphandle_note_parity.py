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


# ── Task 2: serialization + back-compat ──────────────────────────────────────

def test_angle_and_box_height_round_trip(qapp):
    from firepro3d.network_codec import serialize_note
    note = NoteAnnotation("Hi", x=5, y=7)
    note._angle = 30.0
    note._box_height = 44.0
    d = serialize_note(note)
    assert d["angle"] == 30.0
    assert d["box_height"] == 44.0


def test_old_dict_without_new_keys_loads_as_identity(qapp):
    """A pre-upgrade serialized note (no angle/box_height) → 0/0 identity."""
    from firepro3d.model_space import Model_Space
    from firepro3d.network_codec import deserialize_note
    scene = Model_Space()
    entry = {"type": "note", "x": 1.0, "y": 2.0, "text_width": 0.0,
             "properties": {"Text": "Old"}, "level": "Level 1"}
    note = deserialize_note(scene, entry)
    assert note._angle == 0.0
    assert note._box_height == 0.0
    scene.cleanup()
