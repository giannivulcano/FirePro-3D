"""Nested block constraint handles (design NB1-NB9) -- headless guards.

Drives a real ``Model_Space(scene_role="block_editor")`` with the Snap block
(tests/_block_snap_helpers) placed as a nested instance plus loose
primitives; observable scene geometry is the ground truth.
"""
from __future__ import annotations

import math

import numpy as np
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import CircleItem, LineItem
from firepro3d.model_space import Model_Space
from firepro3d.sketch_adapters import adapter_for
from tests._block_snap_helpers import oracle, register_snap_block


def _scene():
    return Model_Space(scene_role="block_editor")


def _line(sc, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b))
    sc.addItem(ln)
    sc._draw_lines.append(ln)
    return ln


def _circle(sc, c, r):
    it = CircleItem(QPointF(*c), r)
    sc.addItem(it)
    sc._draw_circles.append(it)
    return it


def _key(d, i):
    return d.primitives[i].get("uid") or f"#{i}"


def _instance(sc, pos=(40.0, 20.0), rot=0.0, mirrored=False, scale=1.0):
    d = register_snap_block(sc, nested=True)
    inst = sc.place_block_instance(d.id, pos, rotation=rot, mirrored=mirrored, scale=scale)
    sc.push_undo_state()
    return d, inst


def _near(p: QPointF, q: QPointF, tol=1e-5) -> bool:
    return math.hypot(p.x() - q.x(), p.y() - q.y()) <= tol


def _status(sc):
    """Capture status-bar messages (the controller's ``_status`` calls
    ``scene._show_status``) -- the test_constraint_controller idiom."""
    msgs = []
    sc._show_status = lambda m, *a, **k: msgs.append(m)
    return msgs


# ── Task 4 guards ────────────────────────────────────────────────────────────

def test_pick_candidates_include_interior_handles_with_midpoint_triangles(qapp):
    """NB8 / AC7: pick mode offers the child handles; midpoints tagged "mid";
    hidden child handles (polygon radius, ellipse rx/ry) never; a curve's
    radius comes from the constant."""
    from firepro3d.constraint_controller import PickState
    sc = _scene()
    d, inst = _instance(sc)
    pk = PickState(sc.constraint_ctl, "coincident")
    cands = list(pk._candidates())
    names = {(k, r.get("h")) for k, r, _a, _b in cands if isinstance(r, dict) and r.get("uid") == inst._uid}
    assert ("point", f"{_key(d, 0)}:p1") in names
    assert ("edge", f"{_key(d, 0)}:edge") in names
    assert ("curve", f"{_key(d, 2)}:curve") in names
    mid = [b for k, r, a, b in cands if isinstance(r, dict) and r.get("h") == f"{_key(d, 0)}:mid"]
    assert mid == ["mid"]
    (rad,) = [b for k, r, a, b in cands if isinstance(r, dict) and r.get("h") == f"{_key(d, 2)}:curve"]
    assert rad[0] == pytest.approx(40.0)


def test_driving_radius_dim_on_a_nested_curve_is_refused_reference_measures(qapp):
    """NB7 / AC8."""
    from firepro3d.constraint_controller import INVALID_STATUS
    sc = _scene()
    d, inst = _instance(sc)
    ctl = sc.constraint_ctl
    msgs = _status(sc)
    ref = {"uid": inst._uid, "h": f"{_key(d, 2)}:curve"}
    assert ctl.add("dim_radius", [ref], value=45.0) is None
    assert INVALID_STATUS in msgs
    c = ctl.add("dim_radius", [ref])              # current measure, then Reference
    assert c is not None
    ctl.set_driving(c.id, False)
    assert ctl.measure(c) == pytest.approx(40.0)
    assert c in ctl.constraints and c.id not in {x.id for x in ctl.active()}


def test_dof_of_a_nested_instance_is_three(qapp):
    """AC7: x y rot."""
    sc = _scene()
    d, inst = _instance(sc)
    ad = adapter_for(inst)
    assert ad.nvars(inst) == 3


def test_symmetric_of_a_nested_curve_and_a_loose_circle_is_refused(qapp):
    """R1: a nested curve has a fixed radius (r is None), so the radius alias
    of a two-curve Symmetric has nothing to alias -- refused as invalid."""
    from firepro3d.constraint_controller import INVALID_STATUS
    sc = _scene()
    d, inst = _instance(sc)
    loose = _circle(sc, (200.0, 200.0), 15.0)
    axis = _line(sc, (0.0, -500.0), (0.0, 500.0))
    ctl = sc.constraint_ctl
    msgs = _status(sc)
    c = ctl.add("symmetric", [{"uid": inst._uid, "h": f"{_key(d, 2)}:curve"},
                              {"uid": loose._uid, "h": "curve"},
                              {"uid": axis._uid, "h": "edge"}])
    assert c is None
    assert INVALID_STATUS in msgs
