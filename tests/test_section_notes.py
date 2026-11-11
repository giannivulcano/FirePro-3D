"""Elevation parity D4 / AC9: Notes owned by a section."""
import os

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.assets import system_blocks_path
from firepro3d.block_library import load_block_file
from tests.test_note_view_scope import place_note
from tests.test_section_classification import _placed_scene


def _note_scene(section_scene_for):
    """A placed section "Section 1" over a model holding the shipped Note block."""
    ms, sec = _placed_scene(section_scene_for, (0, 0), (10000, 0), 8000.0)
    ms.register_block_definition(load_block_file(
        os.path.join(system_blocks_path(), "Annotations", "Note.fpdb")))
    return ms, sec


def _copies(sec):
    from firepro3d.section_scene import _SectionNoteCopy
    return [i for i in sec.items() if isinstance(i, _SectionNoteCopy)]


def test_a_section_note_projects_as_a_copy_in_its_section_only(qapp, section_scene_for):
    """AC9: the note keyed to this section shows here at its stored pose;
    another section's and a plan view's notes do not; plan never shows it."""
    from firepro3d.section_scene import _ROLE_SOURCE
    ms, sec = _note_scene(section_scene_for)
    assert sec.active_view_key == "section:Section 1"
    mine = place_note(ms, "section:Section 1", (3000.0, -2000.0), text="MINE")
    place_note(ms, "section:Other", (3000.0, -2000.0), text="THEIRS")
    place_note(ms, "plan:Plan: Level 1", (3000.0, -2000.0), text="PLAN")
    sec.rebuild()
    (cp,) = _copies(sec)
    assert cp.data(_ROLE_SOURCE) is mine and cp.isVisible()
    assert cp.block_pos() == pytest.approx((3000.0, -2000.0))
    assert cp.attributes["Text"] == "MINE"
    ms.active_view_key = "plan:Plan: Level 1"
    ms._level_manager.apply_to_scene(ms)
    assert not mine.isVisible()                       # plan's view filter, unchanged


def test_dragging_the_copy_moves_the_model_note_in_one_undo_step(qapp, section_scene_for):
    """AC9 / AC11: a manipulator move of the copy lands on the model note,
    one step; rebuild re-projects there; undo puts it back."""
    from tests.test_hosted_blocks_edit import _drag_real
    ms, sec = _note_scene(section_scene_for)
    mine = place_note(ms, "section:Section 1", (3000.0, -2000.0))
    ms.push_undo_state()
    sec.rebuild()
    (cp,) = _copies(sec)
    pos = ms._undo_pos
    _drag_real(sec, [cp], 250.0, -100.0)
    assert mine.block_pos() == pytest.approx((3250.0, -2100.0))
    assert ms._undo_pos == pos + 1
    qapp.processEvents()                              # the deferred flush adds nothing
    assert ms._undo_pos == pos + 1
    sec.rebuild()
    (cp2,) = _copies(sec)
    assert cp2.block_pos() == pytest.approx((3250.0, -2100.0))
    ms.undo()
    sec.rebuild()
    (back,) = _copies(sec)
    assert back.block_pos() == pytest.approx((3000.0, -2000.0))


def test_delete_removes_the_model_note_in_one_step_and_undo_restores(qapp, section_scene_for):
    """AC9 / R2: Delete in the section removes the model note (one step)."""
    ms, sec = _note_scene(section_scene_for)
    mine = place_note(ms, "section:Section 1", (3000.0, -2000.0), text="GONE")
    mine.setVisible(False)                # plan's view filter hides it (a real note is never visible there)
    ms.push_undo_state()
    sec.rebuild()
    (cp,) = _copies(sec)
    cp.setSelected(True)
    pos = ms._undo_pos
    sec._delete_elev_selected()
    assert mine not in ms._block_instances and _copies(sec) == []
    assert ms._undo_pos == pos + 1
    ms.undo()
    sec.rebuild()
    (back,) = _copies(sec)
    assert back.attributes["Text"] == "GONE"
