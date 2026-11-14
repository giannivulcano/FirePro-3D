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


WALL_KEY = "template/wall"


def test_wall_template_round_trips_its_recipe(qapp, ini_settings):
    a = _scene(("Level 1", 0.0), ("Level 2", 3000.0))
    t = a._get_wall_template()
    t._thickness_mm = 203.2
    t._alignment = "Left"
    t._colour = "#123456"
    t._fill_mode = "Solid"
    t._base_offset_mm = 50.0
    t._top_offset_mm = -75.0
    t.phase = PHASE_EXISTING
    a.save_wall_template_settings(ini_settings)

    blob = ini_settings.value(WALL_KEY, {})
    # AC3: no project-specific keys are stored.
    assert set(blob) == {"thickness_mm", "alignment", "colour", "fill_mode",
                         "base_offset_mm", "top_offset_mm", "phase"}

    b = _scene(("Level 3", 6000.0), ("Level 4", 9000.0))
    b.load_wall_template_settings(ini_settings)
    u = b._get_wall_template()
    assert u._thickness_mm == pytest.approx(203.2)
    assert u._alignment == "Left"
    assert b._wall_alignment == "Left"          # scene alignment follows
    assert u._colour == "#123456"
    assert u._fill_mode == "Solid"
    assert u._base_offset_mm == pytest.approx(50.0)
    assert u._top_offset_mm == pytest.approx(-75.0)
    assert u.phase == PHASE_EXISTING
    # Levels re-seed from the new project's active level, not the old one.
    assert u._base_level == "Level 3"
    names = [l.name for l in b._level_manager.levels]   # raw source: level order
    assert u._top_level == names[names.index("Level 3") + 1]


def test_wall_load_without_key_or_with_garbage_keeps_factory(qapp, ini_settings):
    ms = _scene()
    ms.load_wall_template_settings(ini_settings)          # no key → no-op
    ini_settings.setValue(WALL_KEY, {"alignment": "Diagonal", "fill_mode": "Plaid",
                                     "thickness_mm": "abc"})
    ms.load_wall_template_settings(ini_settings)
    t = ms._get_wall_template()
    assert t._alignment == "Center"
    assert t._fill_mode == "None"
    assert t._thickness_mm == pytest.approx(152.4)


def test_restored_wall_template_drives_the_next_placed_wall(qapp, ini_settings):
    a = _scene(("Level 1", 0.0), ("Level 2", 3000.0))
    a._get_wall_template()._thickness_mm = 254.0
    a._get_wall_template()._top_offset_mm = -500.0
    a.save_wall_template_settings(ini_settings)
    b = _scene(("Level 1", 0.0), ("Level 2", 3000.0))
    b.load_wall_template_settings(ini_settings)
    b._wall_ctl._press_wall(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    b._wall_ctl._press_wall(None, QPointF(2000, 0), QPointF(2000, 0), None, None, None)
    w = b._walls[0]
    assert w._thickness_mm == pytest.approx(254.0)
    assert w._computed_height_mm() == pytest.approx(2500.0)
