"""Slice 8 guards — smooth periodic closed splines (scene-tools P1 batch DD7).

Ground truth is the DRAWN QPainterPath (sampled), ezdxf's own periodic
evaluator (independent reference) and real serialization paths (undo snapshot,
.fpd block-definition file, paste) — never the flag the test set.
"""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import SplineItem

# Y-down scene square (a CCW-on-screen control loop).
SQUARE = [(0, 0), (100, 0), (100, -100), (0, -100)]


def _cp(pts):
    return [QPointF(x, y) for x, y in pts]


def _seam_turn_deg(path, eps=1e-4):
    """Angle (deg) between the tangent leaving the path start and the tangent
    arriving at the path end, sampled from the drawn path."""
    p0, p1 = path.pointAtPercent(0.0), path.pointAtPercent(1.0)
    a, b = path.pointAtPercent(eps), path.pointAtPercent(1.0 - eps)
    t_out = (a.x() - p0.x(), a.y() - p0.y())
    t_in = (p1.x() - b.x(), p1.y() - b.y())
    n_out, n_in = math.hypot(*t_out), math.hypot(*t_in)
    c = (t_out[0] * t_in[0] + t_out[1] * t_in[1]) / (n_out * n_in)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _start_end_gap(path):
    p0, p1 = path.pointAtPercent(0.0), path.pointAtPercent(1.0)
    return math.hypot(p1.x() - p0.x(), p1.y() - p0.y())


def _inside_hull(path, pts, pad=1e-6):
    br = path.boundingRect()
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (br.left() >= min(xs) - pad and br.right() <= max(xs) + pad
            and br.top() >= min(ys) - pad and br.bottom() <= max(ys) + pad)


def test_periodic_seam_is_closed_with_continuous_tangent(qapp):
    s = SplineItem(_cp(SQUARE), closed=True)
    path = s.path()
    assert _start_end_gap(path) < 1e-9                     # [RED] closed
    assert _seam_turn_deg(path) < 0.5                      # smooth seam
    assert _inside_hull(path, SQUARE)                      # no garbage tail
    assert s.is_closed() and s.is_periodic() and s.is_fillable()
    assert s._degree == 3 and s._knots is None and s._weights is None


def test_periodic_path_matches_ezdxf_reference(qapp):
    """Independent ground truth: every point ezdxf's closed_uniform_bspline
    evaluates on its valid domain lies on the drawn path (<= 0.05 mm)."""
    from ezdxf.math import Vec3, closed_uniform_bspline
    pts = [(0, 0), (120, 10), (90, -80), (10, -60), (-30, -20)]
    s = SplineItem(_cp(pts), closed=True)
    # dense arc-length sampling of the drawn path (Qt's own polygon
    # flattening is ~0.2 mm coarse at this size — too coarse a reference)
    poly = [s.path().pointAtPercent(i / 2000) for i in range(2001)]

    def _dist_to_poly(x, y):
        best = math.inf
        for a, b in zip(poly, poly[1:]):
            ax, ay, bx, by = a.x(), a.y(), b.x(), b.y()
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
            best = min(best, math.hypot(x - (ax + t * dx), y - (ay + t * dy)))
        return best

    sp = closed_uniform_bspline([Vec3(x, y) for x, y in pts], order=4)
    k = list(sp.knots())
    lo, hi = k[sp.order - 1], k[sp.count]
    worst = max(_dist_to_poly(*sp.point(lo + (hi - lo) * i / 64).vec2)
                for i in range(65))
    assert worst < 0.05, worst


def test_three_control_points_suffice(qapp):
    s = SplineItem(_cp([(0, 0), (100, 0), (50, -80)]), closed=True)
    assert s.is_periodic()
    assert _start_end_gap(s.path()) < 1e-9
    assert _seam_turn_deg(s.path()) < 0.5


def test_closed_needs_three_control_points(qapp):
    s = SplineItem(_cp([(0, 0), (100, 0)]), closed=True)
    assert s.is_periodic() is False and s.is_closed() is False


def test_closed_is_always_a_uniform_nonrational_cubic(qapp):
    s = SplineItem(_cp(SQUARE + [(-20, -40)]), degree=2,
                   knots=[0, 0, 0, 1, 2, 3, 3, 3], weights=[1, 2, 1, 1, 1],
                   closed=True)
    assert (s._degree, s._knots, s._weights) == (3, None, None)
    assert s.to_dict()["degree"] == 3


def test_to_dict_writes_closed_only_when_set(qapp):
    open_d = SplineItem(_cp(SQUARE)).to_dict()
    assert "closed" not in open_d
    d = SplineItem(_cp(SQUARE), closed=True).to_dict()
    assert d["closed"] is True
    back = SplineItem.from_dict(d)
    assert back.is_periodic() and back.to_dict() == d
    assert SplineItem.from_dict(open_d).is_periodic() is False


def test_legacy_coincident_end_spline_is_unchanged(qapp):
    """A saved coincident-end spline (no "closed" key) stays the kinked
    clamped curve: closed + fillable, NOT periodic, dict unchanged."""
    legacy = SplineItem(_cp(SQUARE + [(0, 0)])).to_dict()
    assert "closed" not in legacy
    s = SplineItem.from_dict(legacy)
    assert s.is_closed() and s.is_fillable() and not s.is_periodic()
    p0 = s.path().pointAtPercent(0.0)
    assert (p0.x(), p0.y()) == pytest.approx((0.0, 0.0), abs=1e-6)   # clamped
    assert _seam_turn_deg(s.path()) > 45.0                            # still kinked
    assert s.to_dict() == legacy


def test_closed_survives_the_undo_snapshot(qapp):
    """Undo path (_capture_network / _restore_network) on a real scene."""
    from firepro3d.model_space import Model_Space
    scene = Model_Space(scene_role="block_editor")
    s = SplineItem(_cp(SQUARE), closed=True)
    scene.addItem(s)
    scene._draw_splines.append(s)
    state = scene._capture_network()
    scene._restore_network(state)
    assert len(scene._draw_splines) == 1
    r = scene._draw_splines[0]                       # refs invalidated by restore
    assert r is not s
    assert r.is_periodic()                                         # [RED]
    assert _start_end_gap(r.path()) < 1e-9 and _seam_turn_deg(r.path()) < 0.5


def test_closed_survives_paste(qapp):
    """Clipboard records -> paste_items -> _add_from_dict (Paste/Duplicate)."""
    from firepro3d.model_space import Model_Space
    scene = Model_Space(scene_role="block_editor")
    s = SplineItem(_cp(SQUARE), closed=True)
    scene.addItem(s)
    scene._draw_splines.append(s)
    new = scene.paste_items(QPointF(500, 0),
                            data=scene._clipboard_item_dicts([s]))
    assert len(new) == 1 and isinstance(new[0], SplineItem)
    assert new[0].is_periodic()                                    # [RED]
    assert new[0].grip_points()[1] == QPointF(600, 0)
    assert _seam_turn_deg(new[0].path()) < 0.5


def test_closed_survives_block_definition_file_round_trip(model_space, tmp_path):
    """File path: a block definition primitive -> .fpd -> load -> the
    _PRIMITIVE_FACTORY compile draws the periodic curve."""
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.model_space import Model_Space
    prim = SplineItem(_cp(SQUARE), closed=True).to_dict()
    d = BlockDefinition.new(name="Loop", library="L", series="S",
                            primitives=[prim], origin=(0.0, 0.0))
    model_space.register_block_definition(d)
    model_space.place_block_instance(d.id, (0.0, 0.0))
    fpath = str(tmp_path / "loop.fpd")
    assert model_space.save_to_file(fpath)
    ms2 = Model_Space()
    ms2.load_from_file(fpath)
    d2 = ms2._block_definitions[d.id]
    assert d2.primitives[0].get("closed") is True                  # [RED]
    ops = d2.render_ops()
    assert len(ops) == 1
    path = ops[0][2]
    assert _start_end_gap(path) < 1e-6
    assert _seam_turn_deg(path) < 0.5
    assert _inside_hull(path, SQUARE, pad=1e-3)
