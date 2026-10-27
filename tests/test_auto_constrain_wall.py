"""Slice 3 (G10/G11): wall placement Auto Constrain."""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QEvent, QPointF, QSettings, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from firepro3d import auto_constrain as ac
from firepro3d.constants import AUTO_CONSTRAIN_KEY
from firepro3d.sketch_adapters import adapter_for
from firepro3d.wall import ALIGN_LEFT, ALIGN_RIGHT, WallSegment


def _w(a, b, align=None, uid="u"):
    w = WallSegment(QPointF(*a), QPointF(*b))
    if align is not None:
        w._alignment = align
    w._uid = uid
    return w


def _adapter_points(w) -> dict:
    """handle -> (x, y) from the REAL adapter (the test_auto_constrain_shapes
    ``_pos`` idiom: read the vars, eval each PointExpr)."""
    import numpy as np
    ad = adapter_for(w)
    x = np.array(ad.read(w), dtype=float)
    return {h: tuple(e.eval(x)[0]) for h, e in ad.points(w, 0).items()}


@pytest.mark.parametrize("align,expect", [
    (None, ("p1", "p2", "edge")),
    (ALIGN_LEFT, ("p1r", "p2r", "face_r")),
    (ALIGN_RIGHT, ("p1l", "p2l", "face_l")),
])
def test_drawn_handles_sit_on_the_click_line(align, expect):
    w = _w((0, 0), (3000, 0), align)
    assert ac.wall_drawn_handles(w) == expect
    got = _adapter_points(w)                 # ground truth: the adapter's own math
    for h, p in ((expect[0], w._pt1), (expect[1], w._pt2)):
        assert math.hypot(got[h][0] - p.x(), got[h][1] - p.y()) < 1e-6, h


def test_join_records():
    a = _w((0, 0), (2000, 0), ALIGN_LEFT, "A")
    b = _w((2000, 0), (2000, 1500), None, "B")
    assert ac.plan_wall_join(b, 0, a, 1) == [
        ("coincident", [{"uid": "B", "h": "p1"}, {"uid": "A", "h": "p2r"}])]
    assert ac.plan_wall_join(b, 0, a) == [
        ("point_on_curve", [{"uid": "B", "h": "p1"}, {"uid": "A", "h": "face_r"}])]


def test_hv_and_rect_records():
    h = _w((0, 0), (2000, 0), None, "H")
    s = _w((0, 0), (2000, 3), None, "S")
    assert ac.plan_wall_hv(h) == [("horizontal", [{"uid": "H", "h": "edge"}])]
    assert ac.plan_wall_hv(s) == []
    ws = [_w((0, 0), (1, 0), None, f"R{i}") for i in range(4)]
    assert ac.plan_wall_rect(ws) == [
        ("perpendicular", [{"uid": f"R{i}", "h": "edge"}, {"uid": f"R{i + 1}", "h": "edge"}])
        for i in range(3)]


@pytest.mark.parametrize("toggle,shift,on", [(True, False, True), (True, True, False),
                                             (False, False, False), (False, True, True)])
def test_infer_on_is_toggle_xor_shift(toggle, shift, on):
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, toggle)
    try:
        assert ac.infer_on(shift) is on
    finally:
        QSettings("GV", "FirePro3D").remove(AUTO_CONSTRAIN_KEY)
