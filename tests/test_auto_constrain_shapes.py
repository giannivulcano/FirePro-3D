"""AC3: rect / circle / arc / polygon / ellipse placement clicks on real
snaps record the AC1 join on the new shape's handle at that click (spec §13).
Shown view, posted presses (mods on the event), real snap engine."""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF, QSettings, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d import auto_constrain as ac
from firepro3d.constants import AUTO_CONSTRAIN_KEY
from firepro3d.geometry_2d import CircleItem, LineItem
from firepro3d.sketch_adapters import adapter_for
from tests._snap_polish_helpers import click, close_view, make_view, move

SHIFT = Qt.KeyboardModifier.ShiftModifier
NONE = Qt.KeyboardModifier.NoModifier


# ── pure helpers ──────────────────────────────────────────────────────────

def test_point_handle_at_returns_the_handle_on_the_point(qapp):
    c = CircleItem(QPointF(10, 20), 30.0)
    assert ac.point_handle_at(c, (10, 20)) == "center"
    assert ac.point_handle_at(c, (40, 20)) is None          # rim: no point handle


def test_point_handle_at_needs_a_uid_and_adapter(qapp):
    c = CircleItem(QPointF(10, 20), 30.0)
    c._uid = None
    assert ac.point_handle_at(c, (10, 20)) is None


def test_plan_rim_is_point_first_for_a_point_target():
    t = ac.Target("point", {"uid": "L", "h": "p2"}, (1.0, 2.0))
    assert ac.plan_rim("C", "curve", t) == [
        ("point_on_curve", [{"uid": "L", "h": "p2"}, {"uid": "C", "h": "curve"}])]


def test_plan_rim_ignores_edge_and_curve_targets():
    assert ac.plan_rim("C", "curve", ac.Target("edge", {"uid": "L", "h": "edge"}, (0, 0))) == []
    assert ac.plan_rim("C", "curve", ac.Target("curve", {"uid": "K", "h": "curve"}, (0, 0))) == []
