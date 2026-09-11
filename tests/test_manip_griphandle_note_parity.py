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


# ── Task 3: 9-grip box geometry + pinned-edge resize (angle 0) ───────────────

def test_grip_points_are_nine_box_corners_at_angle_zero(qapp):
    note = NoteAnnotation("Hello world", x=100, y=200)
    note.setTextWidth(80.0)
    note._box_height = 40.0
    gp = note.grip_points()
    assert len(gp) == 9
    assert gp[0] == QPointF(100, 200)          # TL at pos()
    assert gp[4] == QPointF(180, 240)          # BR at pos()+(W,H)
    assert gp[8] == QPointF(140, 220)          # Centre


def test_mr_grip_changes_only_wrap_not_font_or_height(qapp):
    note = NoteAnnotation("Hello", x=0, y=0)
    note.setTextWidth(100.0)
    note._box_height = 50.0
    font_pt = note.font().pointSize()
    note.apply_grip(3, QPointF(140, 25))       # right-mid to x=140
    assert abs(note.textWidth() - 140.0) < 1e-6
    assert abs(note._box_height - 50.0) < 1e-6
    assert note.font().pointSize() == font_pt   # FONT untouched
    assert note.pos() == QPointF(0, 0)          # right-drag pins left → no re-anchor


def test_lm_grip_pins_right_edge_and_reanchors_pos(qapp):
    note = NoteAnnotation("Hello", x=0, y=0)
    note.setTextWidth(100.0)
    note._box_height = 50.0
    note.apply_grip(7, QPointF(30, 25))        # left-mid right to x=30 (shrink)
    assert abs(note.textWidth() - 70.0) < 1e-6  # 100 - 30
    assert abs(note.pos().x() - 30.0) < 1e-6    # left edge moved → pos re-anchored
    assert abs(note.pos().y() - 0.0) < 1e-6


def test_bm_grip_changes_only_box_height(qapp):
    note = NoteAnnotation("Hello", x=0, y=0)
    note.setTextWidth(100.0)
    note._box_height = 50.0
    note.apply_grip(5, QPointF(50, 80))        # bottom-mid down
    assert abs(note._box_height - 80.0) < 1e-6
    assert abs(note.textWidth() - 100.0) < 1e-6


def test_first_resize_from_auto_width_seeds_wrap(qapp):
    """text_width==0 (auto) → first horizontal drag seeds wrap from content."""
    note = NoteAnnotation("Hello", x=0, y=0)   # unwrapped
    assert note.textWidth() <= 0
    content_w = note.boundingRect().width()
    note.apply_grip(3, QPointF(content_w + 20, 5))
    assert note.textWidth() > 0
    assert abs(note.textWidth() - (content_w + 20)) < 1.0
