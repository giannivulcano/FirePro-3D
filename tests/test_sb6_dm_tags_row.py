"""SB6 AC2 (Display Manager half) / D10 -- the Tags row in "Annotation & Geometry":
its Weight and End combos restyle every tag leader on the canvas (pixels), Cancel
restores them, and the values save with the project and apply on open / new."""
from PyQt6.QtCore import QRectF

from firepro3d import paper_display as pd
from firepro3d.display_manager import (DisplayManager, apply_default_display_settings,
                                       apply_project_display_settings,
                                       get_display_settings_for_save)
from tests._sb6_helpers import add_wall, ink, place_tag, render

RECT = QRectF(-1500.0, -4000.0, 3000.0, 4500.0)


def _leader_scene(make_model_space):
    from firepro3d.level_manager import LevelManager
    ms = make_model_space()
    ms._level_manager = LevelManager()
    w = add_wall(ms)
    ms.push_undo_state()
    return ms, place_tag(ms, w, leader=True, u=0.0, v=-3000.0)


def _weights():
    rows = sorted(pd.project_line_weights(), key=lambda d: d.width_mm)
    return rows[0].name, rows[-1].name


def test_row_sits_in_annotation_and_geometry(qapp, make_model_space):
    d = DisplayManager(make_model_space())
    try:
        row = d._tags_row
        assert row.parent().text(0) == "Annotation & Geometry"
        assert d._tag_weight_combo.count() > 0 and d._tag_end_combo.count() > 0
    finally:
        d.reject()


def test_dm_weight_combo_restyles_every_tag_leader(qapp, make_model_space, real_system_library):
    ms, _tag = _leader_scene(make_model_space)
    lo, hi = _weights()
    d = DisplayManager(ms)
    try:
        box = (-100.0, -1600.0, 100.0, -1400.0)
        d._tag_weight_combo.setCurrentText(lo)
        thin = ink(render(ms, RECT, 300, 450), RECT, *box)
        d._tag_weight_combo.setCurrentText(hi)
        assert pd.tag_leader_weight() == hi
        thick = ink(render(ms, RECT, 300, 450), RECT, *box)
        assert thick > thin > 0                                         # [RED: DM handler]
    finally:
        d.reject()


def test_dm_end_combo_switches_the_leader_end(qapp, make_model_space, real_system_library):
    ms, _tag = _leader_scene(make_model_space)
    d = DisplayManager(ms)
    try:
        box = (-100.0, -90.0, 100.0, -10.0)         # Task 7's End box: the arrow body in the wall band
        arrow = ink(render(ms, RECT, 300, 450), RECT, *box)
        label = {r: n for n, r in d._tag_end_choices}["none"]
        d._tag_end_combo.setCurrentText(label)
        assert pd.tag_leader_end() == "none"
        plain = ink(render(ms, RECT, 300, 450), RECT, *box)
        assert arrow > plain                                            # [RED: DM handler]
    finally:
        d.reject()


def test_cancel_restores_the_tags_row(qapp, make_model_space):
    _lo, hi = _weights()
    before = (pd.tag_leader_end(), pd.tag_leader_weight())
    d = DisplayManager(make_model_space())
    d._tag_weight_combo.setCurrentText(hi)
    assert pd.tag_leader_weight() == hi
    d.reject()
    assert (pd.tag_leader_end(), pd.tag_leader_weight()) == before      # [RED: snapshot]


def test_tags_row_saves_with_the_project_and_applies(qapp, make_model_space):
    ms = make_model_space()
    _lo, hi = _weights()
    pd.set_tag_leader_end("none")
    pd.set_tag_leader_weight(hi)
    saved = get_display_settings_for_save()
    assert saved["Tags"] == {"leader_end": "none", "leader_weight": hi}
    pd.set_tag_leader_end(None)
    pd.set_tag_leader_weight(None)
    apply_project_display_settings(ms, saved)                        # Open
    assert (pd.tag_leader_end(), pd.tag_leader_weight()) == ("none", hi)
    apply_default_display_settings(ms)                               # New project: factory
    assert pd.tag_leader_end() == "system-endtypes-arrow"            # constants.TEXT_LEADER_END_ID
