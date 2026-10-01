"""DD1 per-item transforms: ``manip_reflect(p1, p2)`` / ``manip_scale_about(base, f)``.

Governing: docs/superpowers/specs/2026-10-01-scene-tools-p1-batch-design.md DD1
(folded into selection-manipulator.md at Account).

Ground truth is convention-free Euclidean geometry: the painted outline
(``halo_scene_path`` — the item's drawn geometry) after the transform must equal
the original painted outline mapped point-by-point through
``CAD_Math.mirror_point`` / ``CAD_Math.scale_point`` — checked both ways (every
expected point lies on the new outline and every new point on the expected
one). Y-up convention-critical cases (an arc across x = 0 lands in visual Q2)
are asserted on sampled painted points, never on a stored angle.
"""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.cad_math import CAD_Math
from firepro3d.geometry_2d import ArcItem, RectangleItem, ReferenceLineItem
from firepro3d.halo import halo_scene_path
from tests._modify_tools_helpers import PRIMITIVES

GEOM = [n for n in PRIMITIVES if not n.startswith("text")]
AXES = {
    "vertical_x0": (QPointF(0, 0), QPointF(0, -100)),
    "diagonal": (QPointF(300, 0), QPointF(400, -100)),
    "horizontal": (QPointF(0, 200), QPointF(100, 200)),
    "skew": (QPointF(-50, 30), QPointF(80, 170)),
}
# A reflected / scaled Bézier circle starts at a different curve parameter, so
# the two painted curves differ by <= ~0.005 mm (probe 2026-10-01); a
# convention error is off by tens of mm.
TOL_MM = 0.02
_DENSE = 480
_STEP = 8


@pytest.fixture
def scene(qapp):
    return QGraphicsScene()


def _make(scene, name):
    item = PRIMITIVES[name][0]()
    scene.addItem(item)
    return item


def _dense(path):
    return [path.pointAtPercent(i / _DENSE) for i in range(_DENSE + 1)]


def _dist_to_polyline(p, pts):
    best = math.inf
    for a, b in zip(pts, pts[1:]):
        dx, dy = b.x() - a.x(), b.y() - a.y()
        l2 = dx * dx + dy * dy
        t = 0.0 if l2 < 1e-18 else max(0.0, min(1.0, (
            (p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / l2))
        best = min(best, math.hypot(p.x() - a.x() - t * dx,
                                    p.y() - a.y() - t * dy))
    return best


def _assert_same_outline(expected, item):
    """*expected* (dense scene points) and the item's painted outline coincide."""
    new = _dense(halo_scene_path(item))
    fwd = max(_dist_to_polyline(p, new) for p in expected[::_STEP])
    back = max(_dist_to_polyline(p, expected) for p in new[::_STEP])
    assert fwd < TOL_MM and back < TOL_MM, (fwd, back)


# ── manip_reflect ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("axis", list(AXES))
@pytest.mark.parametrize("name", GEOM)
def test_reflect_outline_is_the_mirror_image(scene, name, axis):
    item = _make(scene, name)
    p1, p2 = AXES[axis]
    before = _dense(halo_scene_path(item))
    cls, lw, d0 = type(item), item.pen().widthF(), item.to_dict()
    item.manip_reflect(QPointF(p1), QPointF(p2))
    _assert_same_outline(
        [CAD_Math.mirror_point(p, p1, p2) for p in before], item)    # [RED]
    assert type(item) is cls                     # type kept (RefLine stays one)
    assert item.pen().widthF() == lw             # lineweight never changes
    d1 = item.to_dict()
    assert d1["type"] == d0["type"]
    assert d1.get("color") == d0.get("color")
    assert d1.get("closed") == d0.get("closed")  # closed flag kept


def test_arc_reflected_across_x0_lands_in_visual_q2(scene):
    """Convention-critical (M2): an upper-right arc mirrored across the vertical
    axis x = 0 paints in the visual upper-LEFT quadrant: scene x < 0 and
    y < 0 (scene Y is down). The legacy ``_apply_mirror`` put it in Q4."""
    arc = ArcItem(QPointF(200, 0), 100.0, 0.0, 90.0)
    scene.addItem(arc)
    arc.manip_reflect(QPointF(0, 0), QPointF(0, -100))
    path = arc.mapToScene(arc.path())
    pts = [path.pointAtPercent(i / 20) for i in range(21)]
    assert all(p.x() < 0 and p.y() <= 1e-6 for p in pts)            # [RED]
    mid = path.pointAtPercent(0.5)
    assert (round(mid.x(), 2), round(mid.y(), 2)) == (-270.71, -70.71)


def test_reflect_keeps_closed_polyline_fill(scene):
    pl = _make(scene, "polyline_closed")
    pl.fill_type = "solid"
    fill0 = pl.to_dict()["fill"]
    pl.manip_reflect(QPointF(500, 0), QPointF(500, -10))
    assert pl.is_closed()                                            # [RED]
    assert pl.to_dict()["fill"] == fill0


@pytest.mark.parametrize("pivot", [None, QPointF(0, 0)])
def test_rotated_rect_reflects_as_a_rect_any_pivot(scene, pivot):
    """Rect keeps its type and its pivot semantics (centre-following stays
    centre-following; an explicit pivot is carried to its mirror image)."""
    r = RectangleItem(QPointF(0, 0), QPointF(100, -50))
    r.set_angle(30.0, pivot)
    scene.addItem(r)
    p1, p2 = AXES["skew"]
    before = _dense(halo_scene_path(r))
    r.manip_reflect(QPointF(p1), QPointF(p2))
    _assert_same_outline([CAD_Math.mirror_point(p, p1, p2) for p in before], r)  # [RED]
    assert (r._pivot is None) == (pivot is None)


def test_plain_rect_reflected_axis_aligned_stays_unrotated(scene):
    """An axis-aligned rect mirrored across an axis-aligned line folds to
    angle 0 (no redundant 180° rotation that would show the manip frame)."""
    r = _make(scene, "rect")
    r.manip_reflect(QPointF(0, 0), QPointF(0, -100))
    assert r.manip_frame_redundant()                                 # [RED]


def test_reference_line_stays_a_reference_line(scene):
    rl = _make(scene, "refline")
    rl.manip_reflect(QPointF(0, 50), QPointF(10, 50))
    assert type(rl) is ReferenceLineItem                             # [RED]
    assert rl.to_dict()["type"] == "reference_line"
    assert [(round(p.x(), 6), round(p.y(), 6)) for p in rl.grip_points()] == [
        (0.0, 100.0), (50.0, 100.0), (100.0, 100.0)]


# ── manip_scale_about ───────────────────────────────────────────────────────

SCALES = {"grow": (QPointF(50, 80), 1.5), "shrink": (QPointF(-40, 10), 0.5)}


@pytest.mark.parametrize("case", list(SCALES))
@pytest.mark.parametrize("name", GEOM)
def test_scale_outline_is_the_uniform_image(scene, name, case):
    item = _make(scene, name)
    base, f = SCALES[case]
    before = _dense(halo_scene_path(item))
    cls, lw, d0 = type(item), item.pen().widthF(), item.to_dict()
    item.manip_scale_about(QPointF(base), f)
    _assert_same_outline(
        [CAD_Math.scale_point(p, base, f) for p in before], item)    # [RED]
    assert type(item) is cls
    assert item.pen().widthF() == lw             # lineweights never scale
    d1 = item.to_dict()
    assert d1["type"] == d0["type"]
    assert d1.get("closed") == d0.get("closed")


@pytest.mark.parametrize("pivot", [None, QPointF(0, 0)])
def test_rotated_rect_scales_about_base_any_pivot(scene, pivot):
    r = RectangleItem(QPointF(0, 0), QPointF(100, -50))
    r.set_angle(30.0, pivot)
    scene.addItem(r)
    base = QPointF(50, 80)
    before = _dense(halo_scene_path(r))
    r.manip_scale_about(QPointF(base), 1.5)
    _assert_same_outline([CAD_Math.scale_point(p, base, 1.5) for p in before], r)  # [RED]
    assert r._angle == pytest.approx(30.0)
    assert (r._pivot is None) == (pivot is None)


def test_scale_keeps_arc_angles_on_screen(scene):
    """Scaling never turns an arc: its painted ends keep their Y-up headings
    about the (scaled) centre."""
    arc = ArcItem(QPointF(200, 0), 100.0, 0.0, 90.0)
    scene.addItem(arc)
    arc.manip_scale_about(QPointF(0, 0), 2.0)
    path = arc.mapToScene(arc.path())
    a, b = path.pointAtPercent(0.0), path.pointAtPercent(1.0)
    assert (round(a.x(), 2), round(a.y(), 2)) == (600.0, 0.0)        # [RED]
    assert (round(b.x(), 2), round(b.y(), 2)) == (400.0, -200.0)


# ── Capability boundary (selection-manipulator: "scale" iff manip_scale) ────

@pytest.mark.parametrize("name", GEOM)
def test_new_methods_do_not_make_primitives_box_resizable(scene, name):
    """``manip_scale_about`` must not be ``manip_scale``: the manipulator's
    rigid resize handles would replace the parametric grips."""
    from firepro3d.selection_manipulator import item_capabilities
    item = _make(scene, name)
    assert hasattr(item, "manip_reflect") and hasattr(item, "manip_scale_about")
    assert "scale" not in item_capabilities(item)


def test_text_and_blocks_have_no_reflect_or_scale_about():
    """DD1: Flip / Mirror / Scale skip text and block instances by capability."""
    from firepro3d.block_instance import BlockInstance
    from firepro3d.text_item import TextItem
    for cls in (TextItem, BlockInstance):
        assert not hasattr(cls, "manip_reflect"), cls
        assert not hasattr(cls, "manip_scale_about"), cls
