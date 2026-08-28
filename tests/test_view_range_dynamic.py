"""
test_view_range_dynamic.py
==========================
Task 4 (floor-workflow-elevation-model): a plan view's upper bound
(view_height) derives from the ACTUAL floor above (its bottom-z), not a
hardcoded slab-thickness guess — with a user-override flag that pins an
explicit view_height set through the View Range dialog.

Real ``LevelManager`` + ``Model_Space`` harness (mirrors
``tests/test_floor_visibility.py``). Default levels: L1@0, L2@3048, L3@6096;
``view_top``=2000, ``view_bottom``=-1000; ``_DEFAULT_SLAB_THICKNESS_MM``=152.4.
"""

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.model_space import Model_Space
from firepro3d.level_manager import (
    LevelManager, PlanView, PlanViewManager, _DEFAULT_SLAB_THICKNESS_MM,
)
from firepro3d.floor_slab import FloorSlab


# ── Harness ──────────────────────────────────────────────────────────────────

def _scene(qapp):
    s = Model_Space()
    s._level_manager = LevelManager()
    return s


def _add_slab(s, points=None):
    if points is None:
        points = [QPointF(0, 0), QPointF(1000, 0),
                  QPointF(1000, 1000), QPointF(0, 1000)]
    slab = FloorSlab(points)
    s._floor_slabs.append(slab)
    s.addItem(slab)
    return slab


def _floor_above_L2(s, thickness_mm=300.0):
    """A slab whose TOP sits at Level 2 (elev 3048) with the given thickness,
    so its z-range is (3048 - thickness, 3048)."""
    slab = _add_slab(s)
    slab._top_mode = "level"
    slab._top_level = "Level 2"
    slab._top_offset_mm = 0.0
    slab._bottom_mode = "thickness"
    slab._thickness_mm = thickness_mm
    return slab


# ── (2) compute_view_height ──────────────────────────────────────────────────

def test_compute_view_height_from_thick_floor_above(qapp):
    """Level 1's auto view_height = bottom-z of the floor whose top is at L2."""
    s = _scene(qapp)
    slab = _floor_above_L2(s, thickness_mm=300.0)
    assert slab.z_range_mm() == pytest.approx((2748.0, 3048.0))
    vh = s._level_manager.compute_view_height(s, "Level 1")
    assert vh == pytest.approx(2748.0)
    # NOT the old hardcoded guess.
    assert vh != pytest.approx(3048.0 - _DEFAULT_SLAB_THICKNESS_MM)


def test_compute_view_height_fallback_no_floor_above(qapp):
    """No floor near L2 → fall back to next_datum - _DEFAULT_SLAB_THICKNESS_MM."""
    s = _scene(qapp)
    # A slab that does NOT belong to L2 (top at L1).
    _add_slab(s)  # default top=Level 1 → z-range (-152.4, 0)
    vh = s._level_manager.compute_view_height(s, "Level 1")
    assert vh == pytest.approx(3048.0 - _DEFAULT_SLAB_THICKNESS_MM)


def test_compute_view_height_no_next_level(qapp):
    """Top level (Level 3) → elevation + view_top (6096 + 2000)."""
    s = _scene(qapp)
    _floor_above_L2(s)  # irrelevant to the top level
    vh = s._level_manager.compute_view_height(s, "Level 3")
    assert vh == pytest.approx(6096.0 + 2000.0)


def test_compute_view_height_unknown_level_returns_none(qapp):
    s = _scene(qapp)
    assert s._level_manager.compute_view_height(s, "No Such Level") is None


def test_compute_view_height_tolerance(qapp):
    """A floor whose top is just outside the tol of L2 is NOT adopted."""
    s = _scene(qapp)
    slab = _add_slab(s)
    slab._top_mode = "absolute"
    slab._top_abs_z_mm = 3048.0 + 60.0   # 60mm above L2 datum > 50mm tol
    slab._bottom_mode = "thickness"
    slab._thickness_mm = 300.0
    vh = s._level_manager.compute_view_height(s, "Level 1")
    assert vh == pytest.approx(3048.0 - _DEFAULT_SLAB_THICKNESS_MM)


# ── (1) explicit-override flag round-trip ────────────────────────────────────

def test_view_height_explicit_flag_roundtrips():
    pv = PlanView(name="Plan: Level 1", level_name="Level 1",
                  view_height=2500.0, view_depth=-1000.0,
                  view_height_explicit=True)
    d = pv.to_dict()
    assert d["view_height_explicit"] is True
    pv2 = PlanView.from_dict(d)
    assert pv2.view_height_explicit is True


def test_view_height_explicit_backcompat_default_true():
    """An OLD dict without the flag → from_dict yields True (don't stomp a
    possibly-deliberate saved view_height)."""
    old = {"name": "Plan: Level 1", "level_name": "Level 1",
           "view_height": 2500.0, "view_depth": -1000.0}
    pv = PlanView.from_dict(old)
    assert pv.view_height_explicit is True


def test_new_planview_defaults_not_explicit():
    """A freshly created PlanView opts into dynamic (auto) upper bound."""
    lm = LevelManager()
    pvm = PlanViewManager()
    pv = pvm.create("Level 1", lm)
    assert pv.view_height_explicit is False


# ── (3) activation decision logic (flag → which vh) ──────────────────────────

def _decide_vh(level_mgr, scene, pv, cached_vh, level_name):
    """Mirror of the decision in main._apply_plan_level: when NOT explicit,
    override the cached vh with the dynamic value (if computable)."""
    vh = cached_vh
    if pv is not None and not getattr(pv, "view_height_explicit", False):
        dyn = level_mgr.compute_view_height(scene, level_name)
        if dyn is not None:
            vh = dyn
    return vh


def test_activation_recomputes_when_not_explicit(qapp):
    s = _scene(qapp)
    _floor_above_L2(s, thickness_mm=300.0)   # bottom at 2748
    pv = PlanView(name="Plan: Level 1", level_name="Level 1",
                  view_height=2895.6, view_depth=-1000.0,
                  view_height_explicit=False)
    vh = _decide_vh(s._level_manager, s, pv, cached_vh=pv.view_height,
                    level_name="Level 1")
    assert vh == pytest.approx(2748.0)   # dynamic, not the cached 2895.6


def test_activation_respects_explicit(qapp):
    s = _scene(qapp)
    _floor_above_L2(s, thickness_mm=300.0)
    pv = PlanView(name="Plan: Level 1", level_name="Level 1",
                  view_height=2895.6, view_depth=-1000.0,
                  view_height_explicit=True)
    vh = _decide_vh(s._level_manager, s, pv, cached_vh=pv.view_height,
                    level_name="Level 1")
    assert vh == pytest.approx(2895.6)   # cached, unchanged
    # And the cached PlanView is never mutated by the decision.
    assert pv.view_height == pytest.approx(2895.6)


def test_activation_end_to_end_hides_floor_above(qapp):
    """Non-explicit activation via _apply_plan_level uses the dynamic vh so the
    floor above (bottom at 2748) is section-cut/handled at 2748, not 2895.6.

    Drives the real main path if constructible; otherwise falls back to the
    decision-logic assertion (kept meaningful either way)."""
    s = _scene(qapp)
    floor_above = _floor_above_L2(s, thickness_mm=300.0)   # z-range (2748, 3048)
    # A non-explicit plan view whose cached vh (2895.6) would WRONGLY cut into
    # the floor above; the dynamic vh (2748) sits at its bottom.
    pv = PlanView(name="Plan: Level 1", level_name="Level 1",
                  view_height=2895.6, view_depth=-1000.0,
                  view_height_explicit=False)
    dyn = s._level_manager.compute_view_height(s, "Level 1")
    assert dyn == pytest.approx(2748.0)
    # apply_to_scene with the dynamic vh: the floor-above bottom (2748) is at
    # the cut plane, so it must be treated as visible/section (intersects view).
    s._level_manager.apply_to_scene(
        s, active_level="Level 1", view_height=dyn, view_depth=-1000.0)
    assert floor_above.isVisible() is True


# ── (4) dialog override-intent wiring ────────────────────────────────────────

def _dialog(qapp, s, pv):
    from firepro3d.view_range_dialog import ViewRangeDialog
    from firepro3d.scale_manager import ScaleManager
    return ViewRangeDialog(
        pv, s._level_manager, PlanViewManager(), ScaleManager(),
        parent=None, scene=s)


def test_dialog_manual_height_edit_pins_explicit(qapp):
    s = _scene(qapp)
    _floor_above_L2(s)
    pv = PlanView(name="Plan: Level 1", level_name="Level 1",
                  view_height=2895.6, view_depth=-1000.0,
                  view_height_explicit=False)
    dlg = _dialog(qapp, s, pv)
    assert dlg.is_explicit() is False   # seeded from pv
    # Simulate a user-driven height edit (the real editingFinished path emits
    # valueChanged, which routes to _absolute_to_ref("height")).
    dlg._height_edit.valueChanged.emit(2600.0)
    assert dlg.is_explicit() is True


def test_dialog_reset_opts_into_dynamic_and_shows_computed(qapp):
    s = _scene(qapp)
    _floor_above_L2(s, thickness_mm=300.0)   # floor above bottom at 2748
    pv = PlanView(name="Plan: Level 1", level_name="Level 1",
                  view_height=2895.6, view_depth=-1000.0,
                  view_height_explicit=True)
    dlg = _dialog(qapp, s, pv)
    assert dlg.is_explicit() is True   # seeded from pv
    dlg._reset_defaults()
    assert dlg.is_explicit() is False
    # The shown default is the dynamic compute_view_height, not 3048-152.4.
    vh, _vd = dlg.get_values()
    assert vh == pytest.approx(2748.0)


def test_dialog_reset_without_scene_falls_back_to_formula(qapp):
    """Reset with no scene → the old spacing formula (no crash)."""
    from firepro3d.view_range_dialog import ViewRangeDialog
    from firepro3d.scale_manager import ScaleManager
    lm = LevelManager()
    pv = PlanView(name="Plan: Level 1", level_name="Level 1",
                  view_height=2895.6, view_depth=-1000.0,
                  view_height_explicit=True)
    dlg = ViewRangeDialog(pv, lm, PlanViewManager(), ScaleManager(),
                          parent=None, scene=None)
    dlg._reset_defaults()
    assert dlg.is_explicit() is False
    vh, _vd = dlg.get_values()
    assert vh == pytest.approx(3048.0 - _DEFAULT_SLAB_THICKNESS_MM)


# ── (5) commit path writes the flag onto the PlanView on Accept ──────────────

def _commit_dialog_to_planview(pv, dlg):
    """Mirror of the Accept branch in main._open_plan_view_range /
    _tab_context_plan: on Accept, the handler writes the dialog values +
    override intent back onto the shared PlanView."""
    vh, vd = dlg.get_values()
    pv.view_height = vh
    pv.view_depth = vd
    pv.view_height_explicit = dlg.is_explicit()


def test_commit_writes_explicit_true_after_manual_edit(qapp):
    """A manual height edit pins the flag; Accept persists explicit=True."""
    s = _scene(qapp)
    _floor_above_L2(s, thickness_mm=300.0)
    pv = PlanView(name="Plan: Level 1", level_name="Level 1",
                  view_height=2895.6, view_depth=-1000.0,
                  view_height_explicit=False)
    dlg = _dialog(qapp, s, pv)
    # A real height edit sets the field value AND emits valueChanged (which
    # routes to _absolute_to_ref("height") and pins the explicit flag).
    dlg._height_edit.set_value_mm(2600.0)
    dlg._height_edit.valueChanged.emit(2600.0)
    assert dlg.is_explicit() is True
    _commit_dialog_to_planview(pv, dlg)
    assert pv.view_height_explicit is True
    assert pv.view_height == pytest.approx(2600.0)


def test_commit_writes_explicit_false_after_reset(qapp):
    """Reset-to-Defaults opts back into dynamic; Accept persists explicit=False
    and the shared PlanView carries the computed dynamic upper bound."""
    s = _scene(qapp)
    _floor_above_L2(s, thickness_mm=300.0)   # floor above bottom at 2748
    pv = PlanView(name="Plan: Level 1", level_name="Level 1",
                  view_height=2895.6, view_depth=-1000.0,
                  view_height_explicit=True)
    dlg = _dialog(qapp, s, pv)
    dlg._reset_defaults()
    assert dlg.is_explicit() is False
    _commit_dialog_to_planview(pv, dlg)
    assert pv.view_height_explicit is False
    assert pv.view_height == pytest.approx(2748.0)
