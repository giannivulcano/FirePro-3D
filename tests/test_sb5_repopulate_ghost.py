"""SB5 plan Task 1 -- re-populate ghost-sprinkler probe (design section 5).

Outcome (probed 2026-11-13 at c437d5a9, source identical to base 2509b668,
re-proved at 2509b668 by plan Task 1 Step 3): REAL and pre-existing.
``SprinklerWorkflowController.auto_populate_room`` calls
``node.delete_sprinkler()`` on each replaced head; on a node that keeps its
pipes the old Sprinkler stays a visible child item of the node in the scene and
stays in ``sprinkler_system.sprinklers``. Filed as its own todo line; not fixed
in SB5. SB5's cascade never relies on scene membership (it is handed the
``_detect_sprinklers()`` list), so it does not depend on this bug either way.
"""
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QPointF

from tests._ph1_helpers import ph1_cleanup, scene  # noqa: F401
from tests.test_sb3b_room_tag_style import _add_room

REC = SimpleNamespace(manufacturer="Tyco", model="", type="Upright", k_factor=5.6,
                      coverage_area=130, min_pressure=7, temp_rating=155)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=(
    "todo_open: room re-populate leaves a ghost Sprinkler on a node that keeps "
    "its pipes (SB5 plan Task 1; pre-existing at 2509b668)"))
def test_repopulate_removes_the_old_head_from_a_piped_node(qapp):
    ms = scene()
    room = _add_room(ms, "Office")
    n = ms.add_node(500.0, 500.0)
    far = ms.add_node(500.0, 5000.0)
    ms.add_pipe(n, far)
    old = ms.add_sprinkler(n)
    n._room_name = "Office"
    ms.push_undo_state()
    ms.auto_populate_room(room, [QPointF(1500.0, 1500.0)], REC,
                          "Level 1", "Level 1", -50.8)
    assert n.scene() is ms and n.sprinkler is None       # the piped node survives, head-less
    assert old not in ms.sprinkler_system.sprinklers      # ghost: hydraulics still count it
    assert old.scene() is None                            # ghost: still a child in the scene
