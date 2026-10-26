"""Editor/Build slice 2 Task 1: the per-scene constraint capability.

Design: docs/superpowers/specs/2026-10-24-editor-build-tabs-design.md s2
(capability, gate audit, no origin / axes in plan). Guard T11.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d import theme as th
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.scale_manager import ScaleManager
from tests.test_constraint_paint import _dist, _grab, _px


def test_capability_per_role(qapp):
    from firepro3d.gridline import GridlineItem
    from firepro3d.wall import WallSegment
    plan = Model_Space()
    be = Model_Space(scene_role="block_editor")
    try:
        assert plan.constraint_ctl.enabled is True
        assert plan.constraint_ctl.block_editor is False
        assert set(plan.constraint_ctl.ref_types) == {WallSegment, GridlineItem}
        assert be.constraint_ctl.enabled is True
        assert be.constraint_ctl.block_editor is True
        assert be.constraint_ctl.ref_types is None
    finally:
        plan.cleanup()
        be.cleanup()


def _line_in(sc):
    ln = LineItem(QPointF(-100, 50), QPointF(100, 50))
    sc.addItem(ln)
    sc._draw_lines.append(ln)      # illegal in plan (C1) -- forced to prove the filter
    return ln


@pytest.mark.parametrize("role,offered", [("plan", False), ("block_editor", True)])
def test_2d_geometry_participates_only_in_the_block_editor(qapp, role, offered):
    sc = Model_Space(scene_role=role)
    try:
        ln = _line_in(sc)
        assert (ln in sc.constraint_ctl.items()) is offered
        assert (ln._uid in sc.constraint_ctl.primitive_uids()) is offered
    finally:
        sc.cleanup()


@pytest.mark.parametrize("role,grounds", [("plan", False), ("block_editor", True)])
def test_reserved_grounds_offered_only_in_the_block_editor(qapp, role, grounds):
    """T11 (pick half): no origin / X / Y axis candidate in plan."""
    sc = Model_Space(scene_role=role)
    try:
        ctl = sc.constraint_ctl
        ctl.begin_pick("coincident")
        assert ctl.pick is not None
        refs = [ref for _k, ref, _a, _b in ctl.pick._candidates()]
        found = {r.get("ref") for r in refs if isinstance(r, dict)} & {
            "origin", "x_axis", "y_axis"}
        assert bool(found) is grounds
    finally:
        sc.cleanup()


@pytest.fixture(params=["plan", "block_editor"])
def shown(qapp, request):
    sc = Model_Space(scene_role=request.param)
    sc.scale_manager = ScaleManager()
    v = Model_View(sc)
    v.resize(800, 600)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.resetTransform()
    v.centerOn(0, 0)
    sc.set_mode("select")
    QApplication.processEvents()
    yield request.param, v, sc
    sc.clearSelection()
    sc.cleanup()
    v.close()
    v.deleteLater()
    QApplication.processEvents()


def test_ground_axes_paint_only_in_the_block_editor(shown):
    """T11 (paint half): the dash-dot X / Y axes through the origin (Block
    Editor precedent: test_constraint_paint.py
    test_axes_paint_dash_dot_through_the_origin) never paint in plan. The
    decorative origin cross (+-10 px about the origin, view-centred) is far
    from both sample points (x = 5 and 13.5 px from the viewport's left)."""
    role, v, sc = shown
    img, dpr = _grab(v)
    o = v.mapFromScene(QPointF(0, 0))
    muted = th.detect().color("muted")
    on = _px(img, dpr, 5, o.y())
    gap = _px(img, dpr, 13.5, o.y())
    if role == "block_editor":                  # control: the axes paint
        assert _dist(on, muted) < _dist(gap, muted)
    else:
        assert on == gap, "an X-axis dash painted in the plan view"
