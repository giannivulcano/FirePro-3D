"""CS4 Smart Dimension — headless guards (parametric-constraint-system D48–D55).

Real ``Model_Space(scene_role="block_editor")`` scenes and primitives."""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import constraint_dims as cd
from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.model_space import Model_Space


def _scene():
    return Model_Space(scene_role="block_editor")


def _line(sc, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b))
    sc.addItem(ln); sc._draw_lines.append(ln)
    return ln


def _rect(sc, a, b):
    r = RectangleItem(QPointF(*a), QPointF(*b))
    sc.addItem(r); sc._draw_rects.append(r)
    return r


def _len(ln):
    return math.hypot(ln._pt2.x() - ln._pt1.x(), ln._pt2.y() - ln._pt1.y())


def E(it, h="edge"):
    return {"uid": it._uid, "h": h}


# ── Task 3: dim <-> readout mapping ─────────────────────────────────────────

def test_readout_key_maps_edges_to_their_readouts(qapp):
    sc = _scene()
    ln = _line(sc, (0, 0), (300, 0))
    r = _rect(sc, (0, 0), (400, 200))
    assert cd.readout_key(ln, "edge") == "length"
    assert cd.readout_key(r, "top") == cd.readout_key(r, "bottom") == "width"
    assert cd.readout_key(r, "left") == cd.readout_key(r, "right") == "height"
    assert cd.readout_key(ln, "p1") is None


# ── Task 4: controller core (D50, D52-D55) ──────────────────────────────────

def test_add_takes_the_current_length_and_holds_it_on_an_edit(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    assert c is not None and c.driving and c.value == pytest.approx(300.0)
    with ctl.edit([ln]):                          # an untyped (transform-style) edit
        ln.set_length(500.0)
    assert _len(ln) == pytest.approx(300.0, abs=1e-6)    # the dim held it


def test_set_value_follows_the_readout_anchor_d55(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    n = len(sc._undo_stack)
    assert ctl.set_value(c.id, 250.0) is True
    assert (ln._pt1.x(), ln._pt1.y()) == pytest.approx((0.0, 0.0), abs=1e-9)   # p1 kept
    assert _len(ln) == pytest.approx(250.0, abs=1e-6)
    assert c.value == 250.0 and len(sc._undo_stack) == n + 1


def test_two_point_dim_least_change(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (0, 50)); b = _line(sc, (100, 0), (100, 50))
    c = ctl.add("dim_distance", [E(a, "p1"), E(b, "p1")])
    assert c.value == pytest.approx(100.0)
    assert ctl.set_value(c.id, 60.0)
    assert a._pt1.x() == pytest.approx(20.0, abs=1e-6)
    assert b._pt1.x() == pytest.approx(80.0, abs=1e-6)


def test_redundant_dim_is_auto_reference_d52(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    ctl.add("dim_distance", [E(ln)])
    c2 = ctl.add("dim_distance", [E(ln)])
    assert c2 is not None and not c2.driving and c2.id not in ctl.red


def test_unhonourable_value_is_rejected_d53(qapp):
    """Two driving dims on one edge: neither can change alone."""
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    c2 = ctl.add("dim_distance", [E(ln)])                  # auto-Reference (D52)
    ctl.set_driving(c2.id, True)                           # redundant: amber, admitted
    assert c2.driving and c2.id not in ctl.red
    n = len(sc._undo_stack)
    assert ctl.set_value(c.id, 250.0) is False             # c2 still demands 300
    assert _len(ln) == pytest.approx(300.0, abs=1e-6) and c.value == 300.0
    assert len(sc._undo_stack) == n                        # no undo step


def test_reference_dims_remove_no_dof_and_track_geometry(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    ctl.add("horizontal", [E(ln)])                         # ln participates either way
    before = ctl.sketch_dof()
    c = ctl.add("dim_distance", [E(ln)])
    assert ctl.sketch_dof() == before - 1
    ctl.set_driving(c.id, False)
    assert ctl.sketch_dof() == before
    ln.set_length(420.0)
    assert ctl.measure(c) == pytest.approx(420.0)
    ctl.set_driving(c.id, True)                            # re-drive from where it is
    assert c.value == pytest.approx(420.0) and _len(ln) == pytest.approx(420.0)


def test_zero_distance_pick_is_refused(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (10, 0)); b = _line(sc, (10, 0), (20, 0))
    assert ctl.add("dim_distance", [E(a, "p2"), E(b, "p1")]) is None
    assert ctl.constraints == []


def test_scale_edit_scales_inside_dims_d54(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    with ctl.edit([ln], scale=2.0):
        ln.manip_scale_about(QPointF(0, 0), 2.0)
    assert c.value == pytest.approx(600.0) and _len(ln) == pytest.approx(600.0, abs=1e-6)


def test_unscaled_transform_holds_dims_d54(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    with ctl.edit([ln]):                                   # box-resize style bake
        ln.manip_scale_about(QPointF(0, 0), 2.0)
    assert c.value == 300.0 and _len(ln) == pytest.approx(300.0, abs=1e-6)


def test_build_cache_sees_a_value_change(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    ctl.set_value(c.id, 200.0)
    ctl.set_value(c.id, 150.0)
    assert _len(ln) == pytest.approx(150.0, abs=1e-6)


def test_invalid_value_record_loads_inert(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    ctl.load([{"id": "d", "type": "dim_distance", "refs": [E(ln)], "value": -5}])
    assert ctl.constraints[0].inert
