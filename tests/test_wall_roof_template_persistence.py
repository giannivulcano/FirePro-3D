"""Wall / roof placement-template persistence (QSettings ``template/wall`` /
``template/roof``) + wall placement taking every template row.

Mirrors ``test_floor_template_persistence.py``: INI-backed QSettings, raw
internal values, level names / material never stored.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QSettings

from firepro3d.constants import PHASE_EXISTING
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space
from firepro3d.scale_manager import ScaleManager


@pytest.fixture
def ini_settings(tmp_path):
    return QSettings(str(tmp_path / "wall_roof_template_test.ini"),
                     QSettings.Format.IniFormat)


def _scene(*levels: tuple[str, float]) -> Model_Space:
    s = Model_Space()
    lm = LevelManager()                     # seeds "Level 1" @ 0.0
    for name, elev in levels:
        if lm.get(name) is None:
            lm.add_level(name, elevation=elev)
        else:
            lm.get(name).elevation = elev
    s._level_manager = lm
    s.scale_manager = ScaleManager()
    if levels:
        s.active_level = levels[0][0]
    return s


def _set_offsets_and_joins(ms):
    t = ms._get_wall_template()
    t._base_offset_mm = 150.0
    t._top_offset_mm = -300.0
    t._join_mode_pt1 = "Butt"
    t._join_mode_pt2 = "Solid"


def _assert_offsets_and_joins(wall):
    assert wall._base_offset_mm == 150.0
    assert wall._top_offset_mm == -300.0
    assert wall._join_mode_pt1 == "Butt"
    assert wall._join_mode_pt2 == "Solid"
    # Ground truth: the placed wall's height reflects the offsets
    # (Level 1 @ 0 → Level 2 @ 3000, base +150, top -300 → 2550).
    assert wall._computed_height_mm() == pytest.approx(2550.0)


def test_chain_wall_takes_template_offsets_and_joins(qapp):
    ms = _scene(("Level 1", 0.0), ("Level 2", 3000.0))
    _set_offsets_and_joins(ms)
    ms._wall_ctl._press_wall(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    ms._wall_ctl._press_wall(None, QPointF(2000, 0), QPointF(2000, 0), None, None, None)
    assert len(ms._walls) == 1
    _assert_offsets_and_joins(ms._walls[0])


def test_rect_walls_take_template_offsets_and_joins(qapp):
    ms = _scene(("Level 1", 0.0), ("Level 2", 3000.0))
    _set_offsets_and_joins(ms)
    ms._wall_rect_sized_pt1, ms._wall_rect_sized_pt2 = QPointF(0, 0), QPointF(4000, 3000)
    ms._wall_rect_pivot = QPointF(0, 0)
    assert ms._wall_ctl._commit_wall_rect_rotated(0.0)
    assert len(ms._walls) == 4
    for w in ms._walls:
        _assert_offsets_and_joins(w)
