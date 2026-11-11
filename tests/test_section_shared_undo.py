"""R13 / AC11: a section's undo / redo step the ONE shared plan stack."""
import pytest
from PyQt6.QtCore import QPointF, Qt

from tests.test_hosted_blocks_edit import _setup


def test_section_undo_redo_step_the_plan_stack(qapp, section_scene_for):
    """A hosted drag's deferred step is pushed before the undo, so the undo
    reverts the drag (not the placement before it); redo re-applies it."""
    ms, sec, gl, inst = _setup(section_scene_for)
    cp = sec._hosted_copies[id(inst)]
    cp.translate(300.0, -200.0)          # push deferred (QTimer 0, no event loop yet)
    assert sec._hosted_push_pending is True                     # precondition
    assert sec.can_undo() is True and sec.can_undo() == ms.can_undo()
    sec.undo()
    (back,) = ms.hosted_blocks_on(ms.gridline_by_uid(gl._uid))  # [RED] placement undone
    assert back.host["along_mm"] == pytest.approx(2500.0)      # _setup's placement x
    assert sec.can_redo() is True and sec.can_redo() == ms.can_redo()
    sec.redo()
    (fwd,) = ms.hosted_blocks_on(ms.gridline_by_uid(gl._uid))
    assert fwd.host["along_mm"] == pytest.approx(2800.0)       # 2500 + the 300 mm drag


def test_section_undo_is_refused_mid_manipulator_drag(qapp, section_scene_for):
    """As plan's _manip_drag_blocks_undo: no restore under a live gesture."""
    ms, sec, gl, inst = _setup(section_scene_for)
    cp = sec._hosted_copies[id(inst)]
    m = sec._live_manip()                 # rebuild() deletes it; heal BEFORE selecting
    sec.clearSelection()
    cp.setSelected(True)
    qapp.processEvents()
    start = QPointF(*cp.block_pos())
    m._begin("move", start, start)
    try:
        assert m.is_dragging()                                  # precondition
        pos0 = ms._undo_pos
        sec.undo()
        assert ms._undo_pos == pos0                             # [RED] restored mid-drag
    finally:
        m._finish(start, Qt.KeyboardModifier.NoModifier)
