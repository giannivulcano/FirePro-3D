"""DS1 Scale Length (scene-tools D17 amendment, AC-S1 / AC-S2).

After the reference point the Scale HUD opens on Length (``scale_length``);
←/→ swaps Length <-> Factor at that step only. Real path: a shown Model_View
over a real Model_Space, real mouse + key events, the real HUD; ground truth
is the HUD's schema / field / value and the line's grip points. View zoom 1.0
and integer scene coordinates (the scene reads integer viewport pixels).
914.4 mm = 3 ft (3 x 12 in x 25.4 mm/in).
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from tests._modify_tools_helpers import add_primitive, grips
from tests._snap_polish_helpers import click, close_view, make_view, move
from tests.test_modify_tools_scale import _capture_status

REF_MM = 914.4              # 3 ft
LINE0 = [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]


def _calibrate(scene):
    """100 scene units == 914.4 mm (so a click at x = 100 is the 3 ft reference)."""
    scene.scale_manager.set_pixels_per_mm(100.0 / REF_MM)


def _at_cursor_step(view, scene, calibrated=False):
    """Scale tool live, base (0,0) and reference (100,0) picked."""
    scene.toggle_snap(False)
    scene.set_align_enabled(False)
    if calibrated:
        _calibrate(scene)
    assert scene._modify_ctl.start("scale") is True
    click(view, QPointF(0, 0))                         # base
    click(view, QPointF(100, 0))                       # reference
    assert scene._scale_ref is not None and scene.mode == "scale"


def _key(view, key):
    QTest.keyClick(view.viewport(), key)


def _type_into_field(view, scene, field, text):
    """Real keystrokes: a digit engages the HUD, then replace the field text."""
    _key(view, Qt.Key.Key_0)                           # engages + seeds
    ed = scene.dynamic_input.editor(field)
    assert QApplication.focusWidget() is ed
    ed.selectAll()
    QTest.keyClicks(ed, text)
    QTest.keyClick(ed, Qt.Key.Key_Return)


def _ghost_right(scene):
    """Rightmost scene x of the live ghost (the 0..100 line scaled about x = 0)."""
    assert scene._move_ghost
    return max(p.boundingRect().right() for p in scene._move_ghost)


def _tab_into_field(view, scene, field, text):
    """Real keys: a digit engages the HUD, replace the text, Tab (field commit)."""
    _key(view, Qt.Key.Key_0)
    ed = scene.dynamic_input.editor(field)
    ed.selectAll()
    QTest.keyClicks(ed, text)
    QTest.keyClick(ed, Qt.Key.Key_Tab)


def test_tab_on_a_typed_length_reghosts_the_scale(qapp):
    """Smoke 2026-11-01: Length + Tab re-ghosts at L / |ref - base|; no commit."""
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "line")
        _at_cursor_step(view, scene)
        move(view, QPointF(150, 0))
        assert _ghost_right(scene) == pytest.approx(150.0, abs=3.0)
        _tab_into_field(view, scene, "Length", "300")
        assert _ghost_right(scene) == pytest.approx(300.0, abs=3.0)      # [RED]
        assert scene.mode == "scale" and scene._scale_ref is not None
        scene.set_mode(None)
    finally:
        close_view(view, scene)


def test_tab_on_a_typed_factor_before_the_reference_reghosts_the_scale(qapp):
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "line")
        scene.toggle_snap(False)
        scene.set_align_enabled(False)
        scene._modify_ctl.start("scale")
        click(view, QPointF(0, 0))                     # base
        move(view, QPointF(40, 40))
        _tab_into_field(view, scene, "Factor", "2")
        assert _ghost_right(scene) == pytest.approx(200.0, abs=3.0)      # [RED]
        assert scene.mode == "scale" and scene._scale_ref is None
        scene.set_mode(None)
    finally:
        close_view(view, scene)


def test_hud_is_factor_until_the_reference_then_length(qapp):
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "line")
        scene.toggle_snap(False)
        scene.set_align_enabled(False)
        scene._modify_ctl.start("scale")
        click(view, QPointF(0, 0))                     # base
        assert scene.active_schema().name == "scale_factor"          # [RED]
        click(view, QPointF(100, 0))                   # reference
        assert scene.active_schema().name == "scale_length"          # [RED]
        move(view, QPointF(200, 0))
        hud = scene.dynamic_input
        assert hud is not None and hud.isVisible() and not hud.is_engaged()
        assert hud.field_names() == ("Length",)
        assert hud.field_label_text("Length") == "L"
        scene.set_mode(None)
    finally:
        close_view(view, scene)


def test_length_seed_is_the_live_cursor_distance_in_mm(qapp):
    """Uncalibrated 1 scene unit = 1 mm; calibrated 100 units = 914.4 mm."""
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "line")
        _at_cursor_step(view, scene)
        for x in (150, 137):
            move(view, QPointF(x, 0))
            assert scene.dynamic_input.editor("Length").value_mm() == \
                pytest.approx(float(x))                              # [RED]
        scene.set_mode(None)
    finally:
        close_view(view, scene)


def test_length_seed_converts_scene_to_mm_when_calibrated(qapp):
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "line")
        _at_cursor_step(view, scene, calibrated=True)
        move(view, QPointF(200, 0))                    # 200 units = 1828.8 mm
        assert scene.dynamic_input.editor("Length").value_mm() == \
            pytest.approx(2 * REF_MM)                                # [RED]
        scene.set_mode(None)
    finally:
        close_view(view, scene)


def test_arrow_swaps_length_and_factor_only_after_the_reference(qapp):
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "line")
        seen = []
        scene.instructionChanged.connect(seen.append)
        scene.toggle_snap(False)
        scene.set_align_enabled(False)
        scene._modify_ctl.start("scale")
        click(view, QPointF(0, 0))                     # base only
        _key(view, Qt.Key.Key_Right)                   # refused before the ref
        assert scene.active_schema().name == "scale_factor"
        click(view, QPointF(100, 0))                   # reference
        move(view, QPointF(150, 0))
        assert scene.active_schema().name == "scale_length"
        _key(view, Qt.Key.Key_Right)                   # Length -> Factor
        assert scene.active_schema().name == "scale_factor"          # [RED]
        hud = scene.dynamic_input
        assert hud.field_names() == ("Factor",)                      # [RED]
        assert hud.field_label_text("Factor") == "F"
        assert seen[-1].startswith("Factor (←/→ to change)")
        _key(view, Qt.Key.Key_Left)                    # Factor -> Length
        assert scene.active_schema().name == "scale_length"
        assert scene.dynamic_input.field_names() == ("Length",)
        assert seen[-1].startswith("Length (←/→ to change)")
        scene.set_mode(None)
    finally:
        close_view(view, scene)


def test_input_mode_gates_the_cycle(qapp):
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "line")
        _at_cursor_step(view, scene)
        move(view, QPointF(150, 0))
        assert scene.begin_dynamic_input() is True     # a HUD field holds focus
        assert scene.cycle_placement_variant(+1) is False           # [RED]
        assert scene.active_schema().name == "scale_length"
        scene.set_mode(None)
    finally:
        close_view(view, scene)


def test_variant_resets_to_length_on_entry(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        _at_cursor_step(view, scene)
        _key(view, Qt.Key.Key_Right)                   # now Factor
        assert scene.active_schema().name == "scale_factor"
        _key(view, Qt.Key.Key_Escape)                  # tool ends
        assert scene.mode in (None, "select")
        item.setSelected(True)
        assert scene._modify_ctl.start("scale") is True
        click(view, QPointF(0, 0))
        click(view, QPointF(100, 0))
        assert scene.active_schema().name == "scale_length"          # [RED]
        _key(view, Qt.Key.Key_Right)                   # one press = Factor
        assert scene.active_schema().name == "scale_factor"          # [RED]
        scene.set_mode(None)
    finally:
        close_view(view, scene)


def test_instructions_keep_the_base_prompt_and_name_the_length(qapp):
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "line")
        seen = []
        scene.instructionChanged.connect(seen.append)
        scene.toggle_snap(False)
        scene.set_align_enabled(False)
        scene._modify_ctl.start("scale")
        assert seen[-1] == "Pick base point"                         # [RED]
        click(view, QPointF(0, 0))
        click(view, QPointF(100, 0))
        assert seen[-1] == "Pick new size (or type a length)"
        scene.set_mode(None)
    finally:
        close_view(view, scene)


def test_typed_factor_after_swapping_to_factor_still_commits(qapp):
    """AC-S2 second half. Pre-change the HUD after the reference is already
    Factor, so the Length assertion first makes this fail at baseline."""
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        p0 = scene._undo_pos
        _at_cursor_step(view, scene)
        assert scene.active_schema().name == "scale_length"          # [RED]
        _key(view, Qt.Key.Key_Right)
        assert scene.dynamic_input.field_names() == ("Factor",)
        _type_into_field(view, scene, "Factor", "2")
        assert grips(item) == [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0)]
        assert scene._undo_pos == p0 + 1
        assert scene.mode in (None, "select")
    finally:
        close_view(view, scene)


def test_typed_length_scales_by_length_over_reference_distance(qapp):
    """AC-S1: reference 914.4 mm (3 ft, = 100 scene units), typed 1371.6 mm
    (4.5 ft) -> x1.5 about the base: (0,50,100) -> (0,75,150)."""
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        p0 = scene._undo_pos
        _at_cursor_step(view, scene, calibrated=True)
        move(view, QPointF(120, 0))
        _type_into_field(view, scene, "Length", "1371.6mm")
        assert grips(item) == [(0.0, 0.0), (75.0, 0.0), (150.0, 0.0)]  # [RED]
        assert scene._undo_pos == p0 + 1
        assert scene.mode in (None, "select") and item.isSelected()
        scene.undo()
        assert grips(scene._draw_lines[0]) == LINE0
    finally:
        close_view(view, scene)


def test_typed_length_uncalibrated_is_millimetres_per_scene_unit(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        _at_cursor_step(view, scene)                   # reference 100 = 100 mm
        _type_into_field(view, scene, "Length", "150")
        assert grips(item) == [(0.0, 0.0), (75.0, 0.0), (150.0, 0.0)]
    finally:
        close_view(view, scene)


def test_typed_length_equal_to_the_reference_is_a_no_op(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        msgs = _capture_status(scene)
        p0, n0 = scene._undo_pos, len(scene._undo_stack)
        _at_cursor_step(view, scene, calibrated=True)
        _type_into_field(view, scene, "Length", "914.4mm")   # == |ref - base|
        assert grips(item) == LINE0
        assert (scene._undo_pos, len(scene._undo_stack)) == (p0, n0)  # [RED]
        assert "Scale factor is 1 — nothing changed" in msgs
        assert scene.mode in (None, "select")
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("text", ["0", "-5"])
def test_non_positive_length_is_refused(qapp, text):
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        p0 = scene._undo_pos
        _at_cursor_step(view, scene)
        _type_into_field(view, scene, "Length", text)
        assert grips(item) == LINE0                                  # [RED]
        assert scene._undo_pos == p0
        assert scene.mode == "scale"
        assert scene.dynamic_input.has_invalid_field()
        scene.set_mode(None)
    finally:
        close_view(view, scene)


def test_click_at_the_cursor_still_commits_by_distance_ratio(qapp):
    """The mouse path is unchanged: |cursor - base| / |ref - base|."""
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        _at_cursor_step(view, scene)
        move(view, QPointF(200, 0))
        click(view, QPointF(200, 0))
        assert grips(item) == [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0)]
    finally:
        close_view(view, scene)
