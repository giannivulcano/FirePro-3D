"""Posted-event / lifecycle grip drag of a real GridlineItem == legacy apply_grip
outcome; ALL grips carry multi-select parallel-delta; endpoints Ctrl-constrain
against the opposite endpoint; one undo per gesture; Esc atomically restores the
dragged gridline AND every parallel-delta sibling; the legacy _PullTabGrip visuals
are gone and _find_grip_hit skips the migrated item.

U3 migration of GridlineItem onto manip_handles(). Mirrors
test_manip_griphandle_wall_parity.py, adapted for parallel-delta (all grips) +
bubble-standoff grips."""
import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication

from firepro3d.gridline import GridlineItem


def _add_gl(scene, p1, p2, label="1"):
    gl = GridlineItem(QPointF(*p1), QPointF(*p2), label=label)
    scene.addItem(gl)
    scene._gridlines.append(gl)
    return gl


# --------------------------------------------------------------------------
# Scene methods: parallel-delta + snapshot/restore
# --------------------------------------------------------------------------

def test_propagate_applies_same_delta_to_other_selected_gridlines(qapp, shown_model_view):
    view, scene = shown_model_view
    a = _add_gl(scene, (0, 0), (0, 5000), "1")      # vertical
    b = _add_gl(scene, (300, 0), (300, 5000), "2")  # vertical, parallel
    a.setSelected(True); b.setSelected(True)
    b0 = QPointF(b.grip_points()[1])
    scene._propagate_gridline_grip(a, 1, QPointF(0, 700))
    assert b.grip_points()[1] == QPointF(b0.x(), b0.y() + 700)


def test_propagate_skips_non_gridlines_and_locked_and_self(qapp, shown_model_view):
    view, scene = shown_model_view
    a = _add_gl(scene, (0, 0), (0, 5000), "1")
    locked = _add_gl(scene, (300, 0), (300, 5000), "2")
    locked._locked = True
    a.setSelected(True); locked.setSelected(True)
    before = QPointF(locked.grip_points()[1])
    scene._propagate_gridline_grip(a, 1, QPointF(0, 700))
    assert locked.grip_points()[1] == before          # locked apply_grip no-ops


def test_snapshot_excludes_dragged_and_restore_puts_back(qapp, shown_model_view):
    view, scene = shown_model_view
    a = _add_gl(scene, (0, 0), (0, 5000), "1")
    b = _add_gl(scene, (300, 0), (300, 5000), "2")
    a.setSelected(True); b.setSelected(True)
    snap = scene._snapshot_gridline_grips(a, 1)
    assert {rec[0] for rec in snap} == {b}             # a excluded
    b.apply_grip(1, QPointF(300, 9999))                # move b
    scene._restore_gridline_grips(snap)
    assert b.grip_points()[1] == QPointF(300, 5000)    # restored
