"""Persistence tests for the floor placement template (QSettings ``template/floor``).

Mirrors the pipe/sprinkler/text template persistence pattern in ``main.py``:
save-on-close, load-on-startup, ``QSettings("GV", "FirePro3D")``, raw internal
values.  Only ``_top_mode``, ``_top_offset_mm``, ``_bottom_mode``,
``_bottom_offset_mm``, ``_thickness_mm`` persist.  Level NAMES and absolute-Z
values are project-specific and are NOT persisted — on load they resolve to the
active level / seed from the active level's elevation.

Isolation: every test uses a QSettings backed by a temp INI file (no registry
writes), matching ``test_snapping_pane_settings.py``.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QSettings

from firepro3d.model_space import Model_Space
from firepro3d.level_manager import LevelManager
from firepro3d.scale_manager import ScaleManager


FLOOR_KEY = "template/floor"


@pytest.fixture
def ini_settings(tmp_path):
    """A QSettings pinned to a temp INI file (no real user store touched)."""
    ini_path = str(tmp_path / "floor_template_test.ini")
    return QSettings(ini_path, QSettings.Format.IniFormat)


def _scene_with_levels(*levels: tuple[str, float]) -> Model_Space:
    """Build a bare Model_Space with a LevelManager seeded with *levels*.

    ``levels`` is a sequence of ``(name, elevation_mm)``.  The first level is
    made the active level.  If empty, the default LevelManager (Level 1 @ 0.0)
    is used with Level 1 active.
    """
    s = Model_Space()
    lm = LevelManager()  # seeds "Level 1" @ 0.0
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


# ── 1. Save persists the 5 fields ────────────────────────────────────────────

def test_floor_template_saves_modes_offsets_thickness(qapp, ini_settings):
    scene = _scene_with_levels()
    tmpl = scene._get_floor_template()
    tmpl._bottom_mode = "level"
    tmpl._bottom_offset_mm = 25.0
    tmpl._top_offset_mm = -10.0
    tmpl._thickness_mm = 200.0
    tmpl._top_mode = "level"

    scene.save_floor_template_settings(ini_settings)

    blob = ini_settings.value(FLOOR_KEY)
    assert isinstance(blob, dict)
    assert blob["top_mode"] == "level"
    assert float(blob["top_offset_mm"]) == -10.0
    assert blob["bottom_mode"] == "level"
    assert float(blob["bottom_offset_mm"]) == 25.0
    assert float(blob["thickness_mm"]) == 200.0


# ── 2. Level names / abs-z / color are NOT persisted ─────────────────────────

def test_floor_template_does_not_persist_level_names_or_abs_z(qapp, ini_settings):
    scene = _scene_with_levels()
    tmpl = scene._get_floor_template()
    tmpl._top_level = "Roof"
    tmpl._bottom_level = "Foundation"
    tmpl._top_abs_z_mm = 1234.0
    tmpl._bottom_abs_z_mm = -567.0

    scene.save_floor_template_settings(ini_settings)

    blob = ini_settings.value(FLOOR_KEY)
    assert isinstance(blob, dict)
    for forbidden in ("top_level", "bottom_level", "top_abs_z_mm",
                      "bottom_abs_z_mm", "color", "name"):
        assert forbidden not in blob, f"{forbidden} must not be persisted"


# ── 3. Load resolves level-mode boundaries to the ACTIVE level ────────────────

def test_floor_template_loads_and_resolves_active_level(qapp, ini_settings):
    ini_settings.setValue(FLOOR_KEY, {
        "top_mode": "level",
        "top_offset_mm": -10.0,
        "bottom_mode": "level",
        "bottom_offset_mm": 25.0,
        "thickness_mm": 200.0,
    })

    # Active level is "Level 2"; a stale "Level 1" also exists.
    scene = _scene_with_levels(("Level 2", 3048.0))
    scene.load_floor_template_settings(ini_settings)

    tmpl = scene._get_floor_template()
    assert tmpl._top_level == "Level 2"
    assert tmpl._bottom_level == "Level 2"
    assert tmpl._top_mode == "level"
    assert tmpl._bottom_mode == "level"
    assert tmpl._top_offset_mm == -10.0
    assert tmpl._bottom_offset_mm == 25.0
    assert tmpl._thickness_mm == 200.0


# ── 4. Absolute-mode boundaries seed abs-z from active level's elevation ──────

def test_floor_template_absolute_seeds_from_active_elevation(qapp, ini_settings):
    ini_settings.setValue(FLOOR_KEY, {
        "top_mode": "absolute",
        "top_offset_mm": 0.0,
        "bottom_mode": "thickness",
        "bottom_offset_mm": 0.0,
        "thickness_mm": 150.0,
    })

    scene = _scene_with_levels(("Level 2", 3048.0))
    scene.load_floor_template_settings(ini_settings)

    tmpl = scene._get_floor_template()
    assert tmpl._top_mode == "absolute"
    assert tmpl._top_abs_z_mm == 3048.0  # seeded from active level's elevation


# ── 5. Save → load round-trips the 5 persisted fields ────────────────────────

def test_floor_template_survives_roundtrip(qapp, ini_settings):
    scene = _scene_with_levels(("Level 2", 3048.0))
    tmpl = scene._get_floor_template()
    tmpl._top_mode = "absolute"
    tmpl._top_offset_mm = 12.5
    tmpl._bottom_mode = "level"
    tmpl._bottom_offset_mm = -33.0
    tmpl._thickness_mm = 175.0

    scene.save_floor_template_settings(ini_settings)

    # Fresh scene loads what the first one saved.
    scene2 = _scene_with_levels(("Level 2", 3048.0))
    scene2.load_floor_template_settings(ini_settings)
    tmpl2 = scene2._get_floor_template()

    assert tmpl2._top_mode == "absolute"
    assert tmpl2._top_offset_mm == 12.5
    assert tmpl2._bottom_mode == "level"
    assert tmpl2._bottom_offset_mm == -33.0
    assert tmpl2._thickness_mm == 175.0
