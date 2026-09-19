"""Scene dirty flag + can_undo/can_redo helpers (chrome-revamp header rail).

The header rail reads these to grey the Undo/Redo buttons at the stack bounds
and show the unsaved-changes dot. Reuses the session-scoped ``qapp`` fixture.
"""
from firepro3d.model_space import Model_Space


def test_can_undo_redo_and_dirty(qapp):
    s = Model_Space()
    assert s.can_undo() is False        # _undo_pos == 0 after the seed push
    assert s.is_dirty() is False        # the seed push is not a user mutation
    s.push_undo_state()
    assert s.is_dirty() is True         # a mutation snapshot marks dirty
    assert s.can_undo() is True
    s.undo()
    assert s.can_redo() is True
    s.mark_saved()
    assert s.is_dirty() is False
