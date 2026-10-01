"""A transform tool's ghost never leaks into Move / Duplicate (seam review I-1).

Flip, Mirror, Scale, Array and Rotate all draw their preview into the shared
``_move_ghost`` that ``Model_View`` paints (block 8). Switching to Move or
Duplicate (Shift+M / Shift+D, ribbon, context menu — all ``start()``) before
their base pick must show NO ghost: the old tool's silhouette is not the
selection riding the cursor. No handoff keeps a ghost
across ``set_mode``: every Move / Duplicate / Paste entry builds its own after
the mode switch (and a same-mode re-entry restarts the gesture).

Ground truth: viewport pixels sampled on the old ghost's own outline, against
a grab of the same canvas before any tool ran (grid, origin marker and items
included), plus the scene's ghost lists.
"""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from firepro3d.geometry_2d import ReferenceLineItem
from tests._modify_tools_helpers import add_primitive, grips, ignore_os_mouse
from tests._snap_polish_helpers import click, close_view, move
from tests._snap_polish_helpers import make_view as _make_view

AXIS_X = 200.0
EMPTY = QPointF(-300.0, 250.0)          # far from every item and ghost


def make_view(**kw):
    """The shared shown view, deaf to the real mouse (see ignore_os_mouse)."""
    view, scene = _make_view(**kw)
    return ignore_os_mouse(view), scene


def _grab(view):
    view.viewport().update()
    QApplication.processEvents()
    return view.viewport().grab().toImage()


def _px(view, img, spt):
    vp = view.mapFromScene(spt)
    return QColor(img.pixel(vp.x(), vp.y()))


def _seg_dist(p, a, b):
    dx, dy = b.x() - a.x(), b.y() - a.y()
    t = max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy)
                     / (dx * dx + dy * dy)))
    return math.hypot(p.x() - a.x() - t * dx, p.y() - a.y() - t * dy)


# Live geometry the probes must stay clear of: the line (0,0)-(100,0) and the
# short axis reference line x = AXIS_X, y -50..50.
_LIVE = [(QPointF(0, 0), QPointF(100, 0)),
         (QPointF(AXIS_X, -50), QPointF(AXIS_X, 50))]


def _ghost_probes(scene):
    """Points on the current ghost outline, >= 8 mm from any live item."""
    pts = []
    for path in scene._move_ghost:
        for i in range(201):
            p = path.pointAtPercent(i / 200)
            if all(_seg_dist(p, a, b) >= 8.0 for a, b in _LIVE):
                pts.append(p)
    return pts


def _build_ghost(view, scene, tool):
    """Run *tool* up to a live ghost (no commit)."""
    assert scene._modify_ctl.start(tool) is True
    if tool in ("flip", "mirror"):
        move(view, QPointF(AXIS_X + 2.0, 0.0))         # mirrored to x 300..400
    elif tool == "scale":
        click(view, QPointF(0, 0))                     # base
        click(view, QPointF(100, 0))                   # reference (= 1x)
        move(view, QPointF(0, -300))                   # x3 -> 0..300 along +X
    elif tool == "array":
        click(view, QPointF(0, 0))                     # base
        move(view, QPointF(0, -150))                   # copies 150 / 300 up
    elif tool == "rotate":
        click(view, QPointF(0, 0))                     # pivot
        click(view, QPointF(100, 0))                   # start ray
        move(view, QPointF(0, -100))                   # +90 -> (0,0)-(0,-100)


@pytest.mark.parametrize("dst", ["move", "duplicate"])
@pytest.mark.parametrize("src", ["flip", "mirror", "scale", "array", "rotate"])
def test_previous_tool_ghost_is_gone_before_the_base_pick(qapp, src, dst):
    view, scene = make_view(scale=1.0)
    try:
        rl = ReferenceLineItem(QPointF(AXIS_X, -50), QPointF(AXIS_X, 50))
        scene.addItem(rl)
        scene._reference_lines.append(rl)
        item, _ = add_primitive(scene, "line")         # selected
        move(view, EMPTY)
        ref = _grab(view)                              # no tool, no ghost
        _build_ghost(view, scene, src)
        probes = _ghost_probes(scene)
        assert len(probes) >= 20, src                  # precondition: a ghost
        img = _grab(view)
        assert sum(_px(view, img, p) != _px(view, ref, p)
                   for p in probes) >= 10              # precondition: painted
        assert scene._modify_ctl.start(dst) is True    # Shift+M / Shift+D
        assert scene.mode == dst and scene.node_start_pos is None
        move(view, EMPTY)                              # before the base pick
        img = _grab(view)
        assert sum(_px(view, img, p) != _px(view, ref, p)
                   for p in probes) == 0                                  # [RED]
        assert scene._move_ghost == [] and scene._move_ghost_base == []
        assert grips(item) == [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("entry", ["move_base_click", "begin_move_from"])
def test_move_builds_its_own_ghost_after_another_tools(qapp, entry):
    """The handoffs that DO exist all build Move's ghost after ``set_mode``
    (base click, ``begin_move_from`` for Block Editor import; ``begin_paste``
    likewise): after a Flip ghost, Move's own ghost still rides the cursor
    and the click commits."""
    view, scene = make_view(scale=1.0)
    try:
        rl = ReferenceLineItem(QPointF(AXIS_X, -50), QPointF(AXIS_X, 50))
        scene.addItem(rl)
        scene._reference_lines.append(rl)
        item, _ = add_primitive(scene, "line")
        _build_ghost(view, scene, "flip")
        assert scene._move_ghost
        if entry == "move_base_click":
            assert scene._modify_ctl.start("move") is True
            click(view, QPointF(0, 0))                 # base
        else:
            scene.begin_move_from(QPointF(0, 0))
        move(view, QPointF(0, -200))
        bg = _px(view, _grab(view), QPointF(-300, -200))
        img = _grab(view)
        riding = [QPointF(x, -200.0) for x in range(10, 91, 5)]
        assert sum(_px(view, img, p) != bg for p in riding) >= 10
        click(view, QPointF(0, -200))
        assert grips(item) == [(0.0, -200.0), (50.0, -200.0), (100.0, -200.0)]
    finally:
        close_view(view, scene)
