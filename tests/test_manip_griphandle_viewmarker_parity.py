"""SectionMarker on the manipulator (U3 grip protocol): four handles -- two endpoint
grips, the far-edge depth grip and the click-only FlipGripHandle -- driven through the
live SelectionManipulator on a shown Model_View. The retired ViewMarkerArrow /
SharedCropBox 8-crop-grip contract is gone with the shared box (spec s6)."""
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication

from firepro3d.section_marker import SectionMarker
from firepro3d.manip_handle import EndpointGripHandle, FlipGripHandle, GripHandle
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


def test_default_handles_are_four_with_the_right_classes(qapp, shown_model_view):
    _, scene = shown_model_view
    m = _placed(scene)
    hs = m.manip_handles()
    assert [type(h) for h in hs] == [EndpointGripHandle, EndpointGripHandle,
                                     GripHandle, FlipGripHandle]
    assert [h.index for h in hs] == [0, 1, 2, 3]
    assert all(h.role is HandleRole.GRIP for h in hs)
    assert hs[0].opposite_index == 1 and hs[1].opposite_index == 0
    assert hs[2].circular is False and hs[3].circular is True
    for h, p in zip(hs, m.grip_points()):
        assert h.scene_position(None) == p


def test_endpoint_drag_through_live_manipulator_moves_b_one_undo(qapp, shown_model_view):
    _, scene = shown_model_view
    m = _placed(scene)
    man = scene._live_manip()
    assert man is not None and man.wraps(m)
    before = len(scene._undo_stack)
    h = m.manip_handles()[1]
    start = QPointF(m.grip_points()[1])
    target = QPointF(6000.0, 3000.0)
    man._begin_handle(h, start, start)
    man._update(target, _NOMOD, target)
    man._finish(target, _NOMOD)
    assert m.cut_a == QPointF(0.0, 0.0)                 # the pivot end stays
    assert m.cut_b == QPointF(6000.0, 3000.0)
    assert m.depth == 3000.0
    assert len(scene._undo_stack) == before + 1         # exactly one undo state


def test_flip_click_through_live_manipulator_toggles_look_sign_one_undo(qapp, shown_model_view):
    _, scene = shown_model_view
    m = _placed(scene)
    man = scene._live_manip()
    before = len(scene._undo_stack)
    h = m.manip_handles()[3]
    p = QPointF(m.grip_points()[3])
    man._begin_handle(h, p, p)
    man._finish(p, _NOMOD)                               # press + release, no move
    assert m.look_sign == -1
    assert len(scene._undo_stack) == before + 1
    assert m.grip_points()[2] == QPointF(3000.0, 3000.0)


def test_escape_mid_drag_restores_b(qapp, shown_model_view):
    _, scene = shown_model_view
    m = _placed(scene)
    man = scene._live_manip()
    before = len(scene._undo_stack)
    h = m.manip_handles()[1]
    start = QPointF(m.grip_points()[1])
    target = QPointF(6000.0, 3000.0)
    man._begin_handle(h, start, start)
    man._update(target, _NOMOD, target)
    assert m.cut_b == target                             # live-applied
    man.cancel_drag()                                    # what Esc does
    assert m.cut_b == QPointF(6000.0, 0.0) and m.cut_a == QPointF(0.0, 0.0)
    assert len(scene._undo_stack) == before              # nothing committed
