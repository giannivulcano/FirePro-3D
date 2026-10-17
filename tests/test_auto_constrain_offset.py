"""AC4: an Offset in the Block Editor ties its copy to the source (spec §13,
D155-D156): line -> parallel + driving point-line gap dim; circle / arc ->
concentric; every other shape -> nothing. Shown view, posted events."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QSettings, Qt
from PyQt6.QtTest import QTest

from firepro3d import auto_constrain as ac
from firepro3d.constants import AUTO_CONSTRAIN_KEY
from firepro3d.geometry_2d import ArcItem, CircleItem, LineItem, RectangleItem
from tests._modify_tools_helpers import add_primitive
from tests._snap_polish_helpers import click, close_view, make_view, move

SHIFT = Qt.KeyboardModifier.ShiftModifier


# -- pure planner -------------------------------------------------------------

def test_plan_offset_line_is_parallel_then_gap_dim(qapp):
    a, b = LineItem(QPointF(0, 0), QPointF(100, 0)), LineItem(QPointF(0, 30), QPointF(100, 30))
    assert ac.plan_offset(a, b) == [
        ("parallel", [{"uid": b._uid, "h": "edge"}, {"uid": a._uid, "h": "edge"}]),
        ("dim_point_line", [{"uid": b._uid, "h": "mid"}, {"uid": a._uid, "h": "edge"}])]


@pytest.mark.parametrize("make", [
    lambda r: CircleItem(QPointF(0, 0), r),
    lambda r: ArcItem(QPointF(0, 0), r, 0.0, 90.0)])
def test_plan_offset_curve_is_concentric(qapp, make):
    a, b = make(50.0), make(55.0)
    assert ac.plan_offset(a, b) == [
        ("concentric", [{"uid": b._uid, "h": "curve"}, {"uid": a._uid, "h": "curve"}])]


def test_plan_offset_other_shapes_record_nothing(qapp):
    a = RectangleItem(QPointF(0, 0), QPointF(100, -50))
    b = RectangleItem(QPointF(-5, 5), QPointF(105, -55))
    assert ac.plan_offset(a, b) == []


def test_plan_offset_needs_both_uids(qapp):
    a, b = LineItem(QPointF(0, 0), QPointF(100, 0)), LineItem(QPointF(0, 30), QPointF(100, 30))
    b._uid = None
    assert ac.plan_offset(a, b) == []
