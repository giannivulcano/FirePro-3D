"""LT5 B3 / E5 (data half) -- Flip / Mirror keep each end on its physical end.

Q9: every ``manip_reflect`` of the 8 styled primitives toggles both ends'
``mirrored``; ``ArcItem.manip_reflect`` -- whose reflection makes the old
END the new START -- also swaps ``style.start`` / ``style.finish``. Driven
through the real Flip / Mirror tool (``ModifyToolsController.commit_reflect``
on a shown Block Editor view); ground truth = the reflected endpoints from
``CAD_Math.mirror_point`` and the records at those points.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.cad_math import CAD_Math
from tests._modify_tools_helpers import add_primitive
from tests._snap_polish_helpers import close_view
from tests.test_modify_tools_flip_mirror import (AXIS_X, GEOM, _axis_line,
                                                 _hover_and_click, _own,
                                                 make_view)

_A1, _A2 = QPointF(AXIS_X, -500), QPointF(AXIS_X, 500)
_X = {"end": "end-x", "visible": True}
_Y = {"end": "end-y", "visible": False}


def _close(p, q):
    return abs(p.x() - q.x()) < 1e-6 and abs(p.y() - q.y()) < 1e-6


def _ends(item):
    """The persisted end records (what undo / .fpd / paste carry)."""
    st = item.to_dict()["style"]
    return st["start"], st["finish"]


def _reflect(scene, view, tool, item, attr, axis_d):
    scene._modify_ctl.start(tool)
    _hover_and_click(view)
    if tool == "flip":
        return item
    lst = _own(scene, attr, axis_d)
    assert len(lst) == 2
    return next(it for it in lst if it is not item)


@pytest.mark.parametrize("tool", ["flip", "mirror"])
def test_e5_arc_end_records_stay_on_their_physical_ends(qapp, tool):
    view, scene = make_view(scale=1.0)
    try:
        axis_d = _axis_line(scene)
        arc, attr = add_primitive(scene, "arc")          # (0,0) r50, 0..90
        arc.style["start"], arc.style["finish"] = dict(_X), dict(_Y)
        scene.push_undo_state()
        _, s_pt, f_pt = arc.grip_points()                 # centre, start, end
        res = _reflect(scene, view, tool, arc, attr, axis_d)
        _, s2, f2 = res.grip_points()
        # Ground truth: reflection reverses the arc -- the old start's image
        # is the new FINISH grip, the old finish's image the new START.
        assert _close(f2, CAD_Math.mirror_point(s_pt, _A1, _A2))
        assert _close(s2, CAD_Math.mirror_point(f_pt, _A1, _A2))
        start, finish = _ends(res)
        assert finish == {**_X, "mirrored": True}                         # [RED]
        assert start == {**_Y, "mirrored": True}
        if tool == "mirror":
            assert _ends(arc) == (_X, _Y)                 # original untouched
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("name", ["line", "polyline_open", "spline"])
def test_open_strokes_keep_their_ends_and_toggle_mirrored(qapp, name):
    view, scene = make_view(scale=1.0)
    try:
        axis_d = _axis_line(scene)
        item, attr = add_primitive(scene, name)
        item.style["start"], item.style["finish"] = dict(_X), dict(_Y)
        scene.push_undo_state()
        g0 = item.grip_points()
        _reflect(scene, view, "flip", item, attr, axis_d)
        g1 = item.grip_points()
        # Vertex order is kept: grip i is the image of grip i.
        assert all(_close(b, CAD_Math.mirror_point(a, _A1, _A2))
                   for a, b in zip(g0, g1))
        assert _ends(item) == ({**_X, "mirrored": True}, {**_Y, "mirrored": True})
        _reflect(scene, view, "flip", item, attr, axis_d)   # flip back
        assert _ends(item) == (_X, _Y)            # toggled off: key omitted
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("name", [n for n in GEOM if n != "refline"])
def test_every_styled_primitive_toggles_both_ends(qapp, name):
    view, scene = make_view(scale=1.0)
    try:
        axis_d = _axis_line(scene)
        item, attr = add_primitive(scene, name)
        _reflect(scene, view, "flip", item, attr, axis_d)
        start, finish = _ends(item)
        assert start.get("mirrored") is True and finish.get("mirrored") is True
    finally:
        close_view(view, scene)


def test_flip_undo_restores_the_unmirrored_records(qapp):
    view, scene = make_view(scale=1.0)
    try:
        axis_d = _axis_line(scene)
        arc, attr = add_primitive(scene, "arc")
        arc.style["start"], arc.style["finish"] = dict(_X), dict(_Y)
        scene.push_undo_state()
        _reflect(scene, view, "flip", arc, attr, axis_d)
        scene.undo()
        (restored,) = _own(scene, attr, axis_d)
        assert _ends(restored) == (_X, _Y)
    finally:
        close_view(view, scene)
