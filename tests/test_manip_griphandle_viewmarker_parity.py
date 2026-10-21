"""SectionMarker on the manipulator (U3 grip protocol): the crop box edits as a
rectangle in the cut frame -- DetailMarker's 8-grip layout (4 corners + 4 edge
midpoints, opposite corner fixed) plus the click-only FlipGripHandle -- driven through
the live SelectionManipulator on a shown Model_View (spec s6; smoke ruling 2026-10-21:
corners are never independent)."""
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication

from firepro3d.section_marker import SectionMarker
from firepro3d.manip_handle import FlipGripHandle, GripHandle
from firepro3d.manip_math import HandleRole

_NOMOD = Qt.KeyboardModifier.NoModifier


def _placed(scene):
    """A placed (non-cardinal) section selected in a quiet scene."""
    scene._snap_enabled = False
    m = SectionMarker("Section 1", QPointF(0.0, 0.0), QPointF(6000.0, 0.0), 1, 3000.0)
    scene.addItem(m)
    scene.set_mode("select")
    m.setSelected(True)
    QApplication.processEvents()
    return m


def test_default_handles_are_nine_with_the_right_classes(qapp, shown_model_view):
    _, scene = shown_model_view
    m = _placed(scene)
    hs = m.manip_handles()
    assert [type(h) for h in hs] == [GripHandle] * 8 + [FlipGripHandle]
    assert [h.index for h in hs] == list(range(9))
    assert all(h.role is HandleRole.GRIP for h in hs)
    assert [h.circular for h in hs] == [True] * 4 + [False] * 4 + [True]   # corners round, edge mids square
    for h, p in zip(hs, m.grip_points()):
        assert h.scene_position(None) == p


def test_corner_drag_through_live_manipulator_keeps_opposite_corner_one_undo(qapp, shown_model_view):
    _, scene = shown_model_view
    m = _placed(scene)
    man = scene._live_manip()
    assert man is not None and man.wraps(m)
    before = len(scene._undo_stack)
    h = m.manip_handles()[1]                             # near-right corner (B)
    start = QPointF(m.grip_points()[1])
    target = QPointF(7000.0, 1000.0)                     # +1000 along the cut, 1000 away from the far edge
    man._begin_handle(h, start, start)
    man._update(target, _NOMOD, target)
    man._finish(target, _NOMOD)
    assert m.cut_b == QPointF(7000.0, 1000.0)
    assert m.cut_a == QPointF(0.0, 1000.0)               # the cut line moved as one edge
    assert m.depth == 4000.0                             # far edge (y = -3000) stayed put
    assert m.grip_points()[3] == QPointF(0.0, -3000.0)   # opposite corner fixed
    assert len(scene._undo_stack) == before + 1         # exactly one undo state


def test_flip_click_through_live_manipulator_toggles_look_sign_one_undo(qapp, shown_model_view):
    _, scene = shown_model_view
    m = _placed(scene)
    man = scene._live_manip()
    before = len(scene._undo_stack)
    h = m.manip_handles()[SectionMarker.GRIP_FLIP]
    p = QPointF(m.grip_points()[SectionMarker.GRIP_FLIP])
    man._begin_handle(h, p, p)
    man._finish(p, _NOMOD)                               # press + release, no move
    assert m.look_sign == -1
    assert len(scene._undo_stack) == before + 1
    assert m.grip_points()[SectionMarker.GRIP_DEPTH] == QPointF(3000.0, 3000.0)


def test_escape_mid_drag_restores_b(qapp, shown_model_view):
    _, scene = shown_model_view
    m = _placed(scene)
    man = scene._live_manip()
    before = len(scene._undo_stack)
    h = m.manip_handles()[5]                             # B edge midpoint: B slides along the cut
    start = QPointF(m.grip_points()[5])
    target = QPointF(start.x() + 1000.0, start.y() + 400.0)
    man._begin_handle(h, start, start)
    man._update(target, _NOMOD, target)
    assert m.cut_b == QPointF(7000.0, 0.0)              # live-applied; the normal component is ignored
    man.cancel_drag()                                    # what Esc does
    assert m.cut_b == QPointF(6000.0, 0.0) and m.cut_a == QPointF(0.0, 0.0)
    assert len(scene._undo_stack) == before              # nothing committed


def test_flip_press_wander_release_is_ignored(qapp, shown_model_view):
    _, scene = shown_model_view
    m = _placed(scene)
    man = scene._live_manip()
    before = len(scene._undo_stack)
    h = m.manip_handles()[SectionMarker.GRIP_FLIP]
    p = QPointF(m.grip_points()[SectionMarker.GRIP_FLIP])
    far = QPointF(p.x() + 800.0, p.y() - 800.0)
    man._begin_handle(h, p, p)
    man._update(far, _NOMOD, far)
    man._finish(far, _NOMOD)
    assert man._moved is False                           # session closed
    assert m.look_sign == 1
    assert len(scene._undo_stack) == before
