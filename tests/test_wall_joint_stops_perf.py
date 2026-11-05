"""Level elevation edit budgets on a 480-wall grid (ratified 2026-11-04).

Base did no wall work here (0 ms).  One rebuild of every wall measures 5.2 s,
so Scene B's budget is that floor plus room for host noise.
"""
from __future__ import annotations

import statistics
import time

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space
from firepro3d.wall import WallSegment

CELLS = 15
STEP = 3000.0
SCENE_A_BUDGET_MS = 100.0
SCENE_B_BUDGET_MS = 8000.0


@pytest.fixture
def grid(qapp):
    s, lm = _build_grid()
    yield s, lm
    s._walls.clear()    # teardown would otherwise re-join wall by wall


def _build_grid():
    """Verticals top out at Level 2, horizontals at Level 1."""
    s = Model_Space()
    lm = s._level_manager = LevelManager()
    lm.add_level("Level 2", elevation=lm.get("Level 1").elevation + 3000.0)

    def add(a, b, top):
        w = WallSegment(QPointF(*a), QPointF(*b), thickness_mm=200)
        w._top_level = top
        s.addItem(w)
        walls.append(w)

    walls = []
    for i in range(CELLS + 1):
        for j in range(CELLS):
            add((i * STEP, j * STEP), (i * STEP, (j + 1) * STEP), "Level 2")
            add((j * STEP, i * STEP), ((j + 1) * STEP, i * STEP), "Level 1")
    # Join them only now: a full pool makes each queued add O(n)
    QApplication.processEvents()
    s._walls.extend(walls)
    for w in walls:
        w.invalidate_geometry()
    QApplication.processEvents()
    assert len(s._walls) == 480
    return s, lm


def _edit_ms(s, lm, elevation):
    lm.get("Level 2").elevation = elevation
    t0 = time.perf_counter()
    lm.update_elevations(s)
    QApplication.processEvents()
    return (time.perf_counter() - t0) * 1e3


@pytest.mark.perf
def test_level_edit_changing_no_joint_on_480_walls(grid):
    s, lm = grid
    base = lm.get("Level 2").elevation
    assert not any(w._stops_are_stale() for w in s._walls)
    lm.get("Level 2").elevation = base + 100.0
    assert not any(w._stops_are_stale() for w in s._walls), "scene changed"
    runs = [_edit_ms(s, lm, base + 100.0 * k) for k in (2, 3, 4, 5, 6)]
    print(f"Scene A ms: {[round(r, 1) for r in runs]}")
    assert statistics.median(runs) <= SCENE_A_BUDGET_MS


@pytest.mark.perf
def test_level_edit_flipping_every_joint_on_480_walls(grid):
    s, lm = grid
    high = lm.get("Level 2").elevation
    low = lm.get("Level 1").elevation - 3000.0
    lm.get("Level 2").elevation = low
    assert all(w._stops_are_stale() for w in s._walls), "scene must flip all"
    lm.get("Level 2").elevation = high
    runs = [_edit_ms(s, lm, e) for e in (low, high, low)]
    print(f"Scene B ms: {[round(r) for r in runs]}")
    assert statistics.median(runs) <= SCENE_B_BUDGET_MS
