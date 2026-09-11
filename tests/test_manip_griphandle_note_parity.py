"""U3 box-native migration guards for NoteAnnotation.

Mirrors tests/test_manip_griphandle_rect_parity.py. Each guard constructs a real
NoteAnnotation, drives observable behaviour, and asserts ground truth. Rotation
uses the bake-at-rest model ported from RectangleItem (data _angle, NO Qt
setRotation).
"""
from PyQt6.QtCore import QPointF, QEvent, Qt
from PyQt6.QtGui import QTransform, QMouseEvent

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


# ── Task 4: box-native manip_* + coexistence gate (angle 0) ──────────────────

def test_caps_are_box_native_when_unrotated(qapp):
    note = NoteAnnotation("Hi", x=0, y=0)
    assert note.manip_capabilities() == {"translate", "scale", "rotate"}


def test_manip_handles_gate_is_on(qapp):
    from firepro3d.selection_manipulator import _item_uses_manip_handles
    note = NoteAnnotation("Hi", x=0, y=0)
    note.setTextWidth(50.0)
    assert _item_uses_manip_handles(note) is True
    assert len(note.manip_handles()) == 9


def test_manip_bounds_is_local_box_in_scene(qapp):
    note = NoteAnnotation("Hi", x=10, y=20)
    note.setTextWidth(60.0)
    note._box_height = 30.0
    b = note.manip_bounds()
    assert abs(b.x() - 10) < 1e-6 and abs(b.y() - 20) < 1e-6
    assert abs(b.width() - 60) < 1e-6 and abs(b.height() - 30) < 1e-6


def test_manip_scale_matches_apply_grip_corner(qapp):
    """Baked scale about an anchor reproduces the box; anchor (TL) held."""
    note = NoteAnnotation("Hi", x=0, y=0)
    note.setTextWidth(100.0)
    note._box_height = 50.0
    note.manip_scale(2.0, 2.0, QPointF(0, 0))
    assert abs(note.textWidth() - 200.0) < 1e-6
    assert abs(note._box_height - 100.0) < 1e-6
    assert note.pos() == QPointF(0, 0)


# ── Task 5: bake-at-rest rotation ────────────────────────────────────────────

def test_rotate_bakes_angle_and_drops_scale_cap(qapp):
    note = NoteAnnotation("Hi", x=0, y=0)
    note.setTextWidth(100.0)
    note._box_height = 40.0
    note.manip_rotate(90.0, QPointF(50, 20))       # 90° about box centre
    assert abs(note._angle - 90.0) < 1e-6
    assert note.manip_capabilities() == {"translate", "rotate"}   # scale dropped


def test_rotated_grip_points_follow_transform(qapp):
    note = NoteAnnotation("Hi", x=0, y=0)
    note.setTextWidth(100.0)
    note._box_height = 40.0
    centre = note._local_box().center()            # (50, 20) local
    note.manip_rotate(90.0, note.mapToScene(centre))
    gp = note.grip_points()
    # Centre grip (8) is rotation-invariant → stays at the scene centre.
    assert abs(gp[8].x() - 50.0) < 1e-3 and abs(gp[8].y() - 20.0) < 1e-3
    # TL (0) moves off the origin under a 90° rotation about the centre.
    assert gp[0] != QPointF(0, 0)


def test_no_qt_item_rotation_set(qapp):
    """Bake-at-rest: Qt's own rotation() stays 0 — pose lives in data + paint."""
    note = NoteAnnotation("Hi", x=0, y=0)
    note.setTextWidth(100.0)
    note.manip_rotate(45.0, QPointF(50, 10))
    assert note.rotation() == 0.0


def test_grip_render_angle_tracks_baked_angle(qapp):
    note = NoteAnnotation("Hi", x=0, y=0)
    note.manip_rotate(30.0, QPointF(0, 0))
    assert abs(note.grip_render_angle(1) - 30.0) < 1e-6


def test_rotated_bounds_is_rotated_footprint(qapp):
    """boundingRect grows to the rotated footprint (Qt scene index tracks shape)."""
    note = NoteAnnotation("Hi", x=0, y=0)
    note.setTextWidth(100.0)
    note._box_height = 40.0
    base = note.boundingRect()
    note.manip_rotate(45.0, QPointF(50, 20))
    rotated = note.boundingRect()
    # A 100×40 box rotated 45° → ~99×99 footprint: the short dim grows and the
    # box is no longer axis-aligned (width changes off its original 100).
    assert rotated.height() > base.height()
    assert abs(rotated.width() - base.width()) > 1e-3


# ── Task 6: manipulator-driven parity (posted events) ────────────────────────
# Mirrors the helpers in test_manip_griphandle_rect_parity.py.  Per-item single-
# undo / Esc-restore are covered by the shared GripHandle framework suite
# (test_manip_handle_admissibility.py); NoteAnnotation adds no custom handle
# subclass (plain default_grip_handles), so the lifecycle is unchanged here.

def _drive_handle(item, index, drag_to, mods=Qt.KeyboardModifier.NoModifier):
    h = item.manip_handles()[index]

    class _Scene:
        _tools = None
        _grip_item = None
        _grip_dragging = False
        def get_effective_position(self, pt): return QPointF(pt)
    class _M:
        _commit_hook = None
        def scene(self_m): return sc
        def _reflow_live(self_m): pass
    sc = _Scene()
    m = _M()
    h.on_press(m)
    h.on_drag(m, QPointF(drag_to), mods)
    return h, m


def _post_drag(view, scene, path):
    from PyQt6.QtWidgets import QApplication
    for i, pt in enumerate(path):
        vp = view.mapFromScene(pt)
        etype = (QEvent.Type.MouseButtonPress if i == 0
                 else QEvent.Type.MouseButtonRelease if i == len(path) - 1
                 else QEvent.Type.MouseMove)
        btn = Qt.MouseButton.LeftButton
        ev = QMouseEvent(etype, vp.toPointF(),
                         view.viewport().mapToGlobal(vp).toPointF(),
                         btn, btn if etype != QEvent.Type.MouseButtonRelease
                         else Qt.MouseButton.NoButton,
                         Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(view.viewport(), ev)


def test_rotated_note_grip_apply_matches_live_drive(qapp):
    """Driving grip 3 through the live-apply lifecycle == calling apply_grip
    directly — proves the manipulator path carries the note's resize math."""
    legacy = NoteAnnotation("Hi", x=0, y=0)
    legacy.setTextWidth(100.0); legacy._box_height = 40.0
    legacy.set_angle(30.0, QPointF(50, 20))
    legacy.apply_grip(3, QPointF(130, 25))

    migrated = NoteAnnotation("Hi", x=0, y=0)
    migrated.setTextWidth(100.0); migrated._box_height = 40.0
    migrated.set_angle(30.0, QPointF(50, 20))
    _drive_handle(migrated, 3, QPointF(130, 25))

    assert abs(migrated.textWidth() - legacy.textWidth()) < 1e-6
    assert abs(migrated._box_height - legacy._box_height) < 1e-6
    assert abs(migrated.pos().x() - legacy.pos().x()) < 1e-6
    assert abs(migrated.pos().y() - legacy.pos().y()) < 1e-6


def test_posted_drag_centre_grip_moves_rotated_note(qapp):
    """End-to-end: a posted drag on the centre grip (8) of a rotated note,
    routed through the manipulator (no legacy path), translates the note."""
    from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(600, 600); view.show()
    qapp.processEvents()
    note = NoteAnnotation("Hi", x=0, y=0)
    note.setTextWidth(100.0); note._box_height = 40.0
    note.set_angle(30.0, QPointF(50, 20))
    scene.addItem(note)
    m = SelectionManipulator(scene)
    note.setSelected(True); qapp.processEvents()
    assert m.provides_handles_for(note) is False        # rotated → parametric grips
    c0 = note.grip_points()[8]
    target = QPointF(c0.x() + 40, c0.y() - 25)
    _post_drag(view, scene, [c0, QPointF(c0.x() + 20, c0.y() - 12), target])
    qapp.processEvents()
    c1 = note.grip_points()[8]
    assert abs(c1.x() - target.x()) < 1e-6
    assert abs(c1.y() - target.y()) < 1e-6
