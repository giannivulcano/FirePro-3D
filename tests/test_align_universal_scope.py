"""tests/test_align_universal_scope.py — ALIGN armed in every point-asking mode.

The LOCKED spec (2026-08-26-align-tracking-design.md) mandates *universal client
scope*: ALIGN acquire/track/path-snap must be live in EVERY point-asking placement
command, not just the original four (draw_gridline/paste/move/wall).

Both the ALIGN tier in ``get_effective_position`` and the dwell feed in
``mouseMoveEvent`` gate on ``_align_active_item is not None``.  This test cycles
every point-asking placement mode through the *real* ``set_mode(...)`` and asserts
the seam is armed, and asserts it is NOT armed for the pure-select mode.
"""

from __future__ import annotations

import pytest

from firepro3d.model_space import Model_Space


@pytest.fixture
def scene(qapp):
    return Model_Space()


# Point-asking placement modes named by the review + spec acceptance criteria.
_ARMED_MODES = [
    "draw_line",
    "draw_rectangle",
    "draw_circle",
    "draw_arc",
    "polygon",
    "polyline",
    "draw_gridline",
    "wall",
    "pipe",
    "design_area",
    "move",
    "paste",
]


@pytest.mark.parametrize("mode", _ARMED_MODES)
def test_align_armed_in_point_asking_mode(scene, mode):
    scene.set_mode(mode)
    assert scene._align_active_item is not None, (
        f"ALIGN seam inert in point-asking mode {mode!r} "
        f"(_align_active_item is None) — acquire/track silently dead")


def test_align_not_armed_in_select(scene):
    scene.set_mode("select")
    assert scene._align_active_item is None


def test_move_paste_self_exclude_preserved(scene):
    # move/paste must NOT use the shared placement sentinel as their whole
    # purpose here is self-exclusion of the moved item; the sentinel is fine as
    # the *armed* marker before an item is acquired, but the mode must still be
    # armed (non-None).  The real self-exclude item is set later on the press
    # path — the invariant this test guards is that arming did not regress into
    # None for move/paste.
    for m in ("move", "paste"):
        scene.set_mode(m)
        assert scene._align_active_item is not None
