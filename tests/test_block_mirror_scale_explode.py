"""Explode of a mirrored / scaled block instance (design DD9 / DD10; G3, G5).

Rendered truth: the exploded primitives paint the same pixels the posed
instance painted; nested children land on the decomposed full pose; text
comes out as a readable TextItem on the mapped box centre.
"""
import math

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QImage, QPainter, QTransform
from PyQt6.QtWidgets import QStyleOptionGraphicsItem

from firepro3d import geometry_2d as g
from firepro3d.block_definition import BlockDefinition, _nested_pose
from firepro3d.block_explode import explode_instances
from firepro3d.block_instance import BlockInstance
from firepro3d.block_pose import decompose_pose, norm_deg
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.text_item import TextItem
from tests.lt5_support import half_arrow

_ZOOM = 3            # raster px per scene mm (antialias fringe << geometry)
# 1-px-tolerant symmetric difference / inked pixels (``_mismatch``). Measured
# 0.0 (geometry) and <= 0.001 (text at scale 1) over every pose; a missing or
# un-flipped primitive costs >= 10 %.
_PARITY = 0.01
_TEXT_PARITY = 0.01


def _editor(*defs):
    """A Block Editor scene (C1: the only scene Explode runs in)."""
    es = Model_Space(scene_role="block_editor")
    for d in defs:
        es.register_block_definition(d)
    return es


def _text_rec(**kw):
    rec = {"type": "text", "text": "FPT", "x": 20.0, "y": -30.0, "height_mm": 12.0}
    rec.update(kw)
    return rec


def _geom_def(es, end_id=None):
    """Asymmetric L + an arc + an open line carrying an asymmetric end (LT5)."""
    ln = LineItem(QPointF(20, 20), QPointF(80, 50))
    if end_id is not None:
        ln.style["finish"] = {"end": end_id, "visible": True}
    d = BlockDefinition.new(
        name="G", library="L", series="S", origin=(5.0, -5.0),
        primitives=[LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict(),
                    LineItem(QPointF(0, 0), QPointF(0, -40)).to_dict(),
                    g.ArcItem(QPointF(40, -40), 25, 10, 200).to_dict(),
                    ln.to_dict()])
    es.register_block_definition(d)
    return d


def _text_def(es, **kw):
    d = BlockDefinition.new(name="T", library="L", series="S", origin=(5.0, -5.0),
                            primitives=[_text_rec(**kw)])
    es.register_block_definition(d)
    return d


def _raster(items, rect):
    """Inked (alpha > 0) pixel set of *items* painted over scene *rect*."""
    img = QImage(int(rect.width() * _ZOOM) + 1, int(rect.height() * _ZOOM) + 1,
                 QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    for it in items:
        p.save()
        p.resetTransform()
        p.scale(_ZOOM, _ZOOM)
        p.translate(-rect.left(), -rect.top())
        p.setWorldTransform(it.sceneTransform(), True)
        it.paint(p, QStyleOptionGraphicsItem(), None)
        p.restore()
    p.end()
    w, h = img.width(), img.height()
    return {(x, y) for y in range(h) for x in range(w) if (img.pixel(x, y) >> 24) & 0xFF}


def _unmatched(a, b):
    """Pixels of *a* with no pixel of *b* within one pixel (Chebyshev):
    stair-step phase along a diagonal stroke is not a mismatch, a wrong-side
    glyph or a missing stroke (>= 3 px away) counts in full."""
    return sum(1 for (x, y) in a
               if not any((x + dx, y + dy) in b for dx in (-1, 0, 1) for dy in (-1, 0, 1)))


def _mismatch(before, after):
    """Symmetric 1-px-tolerant difference over the instance's inked count."""
    return (_unmatched(before, after) + _unmatched(after, before)) / max(len(before), 1)


def _endpoints(es, item):
    """Distinct endpoint snaps of *item* (a shared corner is listed once)."""
    return sorted({(round(p.x(), 4), round(p.y(), 4))
                   for k, p, _n in es._snap_engine._collect(item) if k == "endpoint"})


_POSES = [(True, 1.0, 0.0), (False, 2.0, 30.0), (True, 1.5, 180.0), (True, 1.0, 90.0)]


def _end():
    """A small asymmetric end glyph (printed mm x model scale): the lines
    and the arc, not the glyph, must dominate the inked count."""
    return half_arrow(length=0.2, h=0.1)


@pytest.mark.parametrize("mirrored, scale, rot", _POSES)
def test_exploded_geometry_paints_the_instance_pixels(qapp, mirrored, scale, rot):
    """G5: lines, an arc and an asymmetric end glyph -- same ink after Explode."""
    es = _editor()
    try:
        end = _end()
        es.register_block_definition(end)
        d = _geom_def(es, end.id)
        inst = es.place_block_instance(d.id, (200.0, 100.0), rotation=rot,
                                       mirrored=mirrored, scale=scale)
        rect = inst.sceneBoundingRect().adjusted(-10, -10, 10, 10)
        before = _raster([inst], rect)
        assert len(before) > 400
        # Exact pointwise truth: the full pose of the definition's own
        # endpoints (origin (5, -5); arc ends analytic, Y-up angles).
        P = inst.full_pose_transform()
        a0, a1 = math.radians(10.0), math.radians(210.0)
        local = [(0, 0), (100, 0), (0, -40), (20, 20), (80, 50),
                 (40 + 25 * math.cos(a0), -40 - 25 * math.sin(a0)),
                 (40 + 25 * math.cos(a1), -40 - 25 * math.sin(a1))]
        want_pts = sorted({(round(q.x(), 4), round(q.y(), 4))
                           for q in (P.map(QPointF(x - 5.0, y + 5.0)) for x, y in local)})
        new = explode_instances(es, [inst], flatten=False)
        assert inst.scene() is None and len(new) == 4
        assert not any(isinstance(i, BlockInstance) for i in new)
        after = _raster(new, rect)
        m = _mismatch(before, after)
        assert m < _PARITY, f"{m:.4f} of the ink differs"
        assert sorted(set().union(*(_endpoints(es, i) for i in new))) == want_pts
        # The end glyph is drawn and mirrored on the exploded line (LT5 Q9).
        ended = [i for i in new if isinstance(i, LineItem)
                 and i.style.get("finish", {}).get("end") == end.id]
        assert len(ended) == 1
        assert bool(ended[0].style["finish"].get("mirrored", False)) is mirrored
    finally:
        es.cleanup()


@pytest.mark.parametrize("mirrored, rot", [(True, 0.0), (False, 30.0), (True, 180.0),
                                           (True, 90.0), (False, 180.0)])
def test_exploded_text_paints_the_instance_glyphs(qapp, mirrored, rot):
    """G3 / G5 at scale 1: the TextItem's glyphs are the instance's pixels --
    reading upright and left-to-right when mirrored, legacy-turned when not."""
    es = _editor()
    try:
        d = _text_def(es)
        inst = es.place_block_instance(d.id, (200.0, 100.0), rotation=rot, mirrored=mirrored)
        rect = inst.sceneBoundingRect().adjusted(-10, -10, 10, 10)
        before = _raster([inst], rect)
        assert len(before) > 200
        (tx,) = explode_instances(es, [inst], flatten=False)
        assert isinstance(tx, TextItem)
        after = _raster([tx], rect)
        m = _mismatch(before, after)
        assert m < _TEXT_PARITY, f"{m:.4f} of the ink differs"
    finally:
        es.cleanup()


def _ink_box(pix):
    xs = [x for x, _ in pix]
    ys = [y for _, y in pix]
    return min(xs), min(ys), max(xs), max(ys)


@pytest.mark.parametrize("mirrored, scale, rot", [(False, 2.0, 30.0), (True, 1.5, 180.0),
                                                  (True, 2.0, 0.0), (False, 0.5, 0.0)])
def test_exploded_scaled_text_lands_on_the_instance_ink(qapp, mirrored, scale, rot):
    """Under a scale the TextItem lays its glyphs out at a different font
    pixel size (hinted metrics are not linear in the cap height), so pixel
    parity is inherently off; the ink must still sit on the instance's: its
    centre within 1.5 mm and its extents within 6 %, at x scale cap height."""
    es = _editor()
    try:
        d = _text_def(es)
        inst = es.place_block_instance(d.id, (200.0, 100.0), rotation=rot,
                                       mirrored=mirrored, scale=scale)
        rect = inst.sceneBoundingRect().adjusted(-10, -10, 10, 10)
        b = _ink_box(_raster([inst], rect))
        (tx,) = explode_instances(es, [inst], flatten=False)
        a = _ink_box(_raster([tx], rect))
        assert tx.data.height_mm == pytest.approx(12.0 * scale)
        dcx = ((a[0] + a[2]) - (b[0] + b[2])) / 2.0 / _ZOOM
        dcy = ((a[1] + a[3]) - (b[1] + b[3])) / 2.0 / _ZOOM
        assert math.hypot(dcx, dcy) < 1.5, (dcx, dcy)
        for i in (0, 1):
            wb, wa = b[i + 2] - b[i], a[i + 2] - a[i]
            assert abs(wa - wb) / wb < 0.06, (i, wb, wa)
    finally:
        es.cleanup()


def _nested_def(es, child, pos, rot=0.0, mirrored=False, scale=1.0, origin=(0.0, 0.0)):
    rec = {"type": "block_instance", "block_id": child.id, "pos": list(pos),
           "rotation": rot}
    if mirrored:
        rec["mirrored"] = True
    if scale != 1.0:
        rec["scale"] = scale
    d = BlockDefinition.new(name="H", library="L", series="S", origin=origin,
                            primitives=[rec])
    es.register_block_definition(d)
    return d, rec


def _l_def(es):
    d = BlockDefinition.new(name="L", library="L", series="S", origin=(0.0, 0.0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict(),
                                        LineItem(QPointF(0, 0), QPointF(0, -40)).to_dict()])
    es.register_block_definition(d)
    return d


def _pose(inst):
    x, y = inst.block_pos()
    return (round(x, 6), round(y, 6), round(norm_deg(inst.block_rotation()), 6),
            inst.block_mirrored(), round(inst.block_scale(), 6))


def test_nested_child_composes_mirror_and_scale(qapp):
    """DD9: host at the origin, mirrored, scale 2; child at (50, 0) -> the
    child lands at (-100, 0), mirrored, scale 2 -- and on the host's pixels."""
    es = _editor()
    try:
        c = _l_def(es)
        h, _rec = _nested_def(es, c, (50.0, 0.0))
        inst = es.place_block_instance(h.id, (0.0, 0.0), mirrored=True, scale=2.0)
        want_pts = _endpoints(es, inst)
        (child,) = explode_instances(es, [inst], flatten=False)
        assert isinstance(child, BlockInstance)
        assert _pose(child) == (-100.0, 0.0, 0.0, True, 2.0)
        assert _endpoints(es, child) == want_pts
        assert (-100.0, 0.0) in want_pts and (-300.0, 0.0) in want_pts
    finally:
        es.cleanup()


def test_nested_rotated_child_inside_a_mirrored_rotated_host(qapp):
    """Child rot 30 inside host rot 45 mirrored: rotation -30 + 45 = 15,
    mirrored, and the same full matrix as the compile composes."""
    es = _editor()
    try:
        c = _l_def(es)
        h, rec = _nested_def(es, c, (50.0, 0.0), rot=30.0, origin=(2.0, 3.0))
        inst = es.place_block_instance(h.id, (10.0, 20.0), rotation=45.0, mirrored=True)
        want_pts = _endpoints(es, inst)
        t = _nested_pose(rec) * QTransform.fromTranslate(-2.0, -3.0) * inst.full_pose_transform()
        x, y, r, m, s = decompose_pose(t)
        (child,) = explode_instances(es, [inst], flatten=False)
        assert _pose(child) == (round(x, 6), round(y, 6), round(r, 6), m, round(s, 6))
        assert (round(norm_deg(child.block_rotation()), 6), child.block_mirrored()) == (15.0, True)
        assert child.block_scale() == 1.0
        assert _endpoints(es, child) == want_pts
    finally:
        es.cleanup()


@pytest.mark.parametrize("host_rot, child_rot, host_mirrored, host_scale, want_rot", [
    (0.0, 30.0, False, 1.0, 30.0),      # old explode summed exactly -- keep it
    (90.0, 300.0, False, 1.0, 390.0),   # not normalised (old parity)
    (0.0, 270.0, False, 1.0, 270.0),
    (45.0, 15.0, False, 1.0, 60.0),
    (45.0, 30.0, True, 1.0, 15.0),      # mirrored host negates the child's rotation
])
def test_nested_child_pose_parts_are_exact(qapp, host_rot, child_rot, host_mirrored,
                                           host_scale, want_rot):
    """The exploded child's stored rotation / scale carry no atan2 / sqrt
    noise (review I1): they are persisted to the record and the panel."""
    es = _editor()
    try:
        c = _l_def(es)
        h, _rec = _nested_def(es, c, (50.0, 0.0), rot=child_rot, scale=2.0)
        inst = es.place_block_instance(h.id, (10.0, 20.0), rotation=host_rot,
                                       mirrored=host_mirrored, scale=host_scale)
        want_pts = _endpoints(es, inst)
        (child,) = explode_instances(es, [inst], flatten=False)
        assert child.block_rotation() == want_rot                            # exact
        assert child.block_scale() == 2.0 * host_scale                       # exact
        assert child.block_mirrored() is host_mirrored
        assert _endpoints(es, child) == want_pts
    finally:
        es.cleanup()


def test_flatten_explodes_a_mirrored_chain_to_posed_primitives(qapp):
    es = _editor()
    try:
        c = _l_def(es)
        mid, _ = _nested_def(es, c, (10.0, 0.0), mirrored=True)
        top, _ = _nested_def(es, mid, (50.0, 0.0), rot=30.0, mirrored=True, scale=1.5)
        inst = es.place_block_instance(top.id, (100.0, 50.0), rotation=45.0,
                                       mirrored=True, scale=2.0)
        want_pts = _endpoints(es, inst)
        rect = inst.sceneBoundingRect().adjusted(-10, -10, 10, 10)
        before = _raster([inst], rect)
        flat = explode_instances(es, [inst], flatten=True)
        assert len(flat) == 2 and all(isinstance(i, LineItem) for i in flat)
        assert es._block_instances == []
        got = sorted(set(sum((_endpoints(es, i) for i in flat), [])))
        assert got == want_pts
        assert _mismatch(before, _raster(flat, rect)) < _PARITY
    finally:
        es.cleanup()


@pytest.mark.parametrize("a0, mirrored, rot, want", [
    (0.0, True, 0.0, 0.0),        # vertical-axis flip: still reads upright
    (0.0, True, 180.0, 0.0),      # top-bottom flip: turned back upright
    (0.0, False, 180.0, 180.0),   # legacy: a plain block turned 180 stays turned
    (20.0, True, 0.0, -20.0),     # mirrored baseline angle negates
    (20.0, True, 90.0, 70.0),
    (20.0, True, 180.0, -20.0),   # 160 is not upright -> +180 -> -20
])
def test_text_angle_follows_the_readable_rule(qapp, a0, mirrored, rot, want):
    es = _editor()
    try:
        d = _text_def(es, angle=a0)
        inst = es.place_block_instance(d.id, (200.0, 100.0), rotation=rot, mirrored=mirrored)
        c_def = TextItem.from_dict(_text_rec(angle=a0)).grip_points()[8]
        target = inst.full_pose_transform().map(QPointF(c_def.x() - 5.0, c_def.y() + 5.0))
        (tx,) = explode_instances(es, [inst], flatten=False)
        assert norm_deg(tx._angle) == pytest.approx(want, abs=1e-9)
        assert norm_deg(tx.data.angle) == pytest.approx(want, abs=1e-9)
        c = tx.grip_points()[8]
        assert (c.x(), c.y()) == pytest.approx((target.x(), target.y()), abs=1e-6)
    finally:
        es.cleanup()


def test_text_size_fields_scale_and_centre_lands_on_the_pose(qapp):
    es = _editor()
    try:
        d = _text_def(es, wrap_width_mm=60.0, cell_padding_mm=2.0)
        inst = es.place_block_instance(d.id, (200.0, 100.0), rotation=30.0,
                                       mirrored=True, scale=2.5)
        c_def = TextItem.from_dict(_text_rec(wrap_width_mm=60.0, cell_padding_mm=2.0)
                                   ).grip_points()[8]
        target = inst.full_pose_transform().map(QPointF(c_def.x() - 5.0, c_def.y() + 5.0))
        (tx,) = explode_instances(es, [inst], flatten=False)
        assert tx.data.height_mm == pytest.approx(30.0)
        assert tx.data.wrap_width_mm == pytest.approx(150.0)
        assert tx.data.cell_padding_mm == pytest.approx(5.0)
        assert tx.data.box_height_mm == 0.0                 # auto stays auto
        c = tx.grip_points()[8]
        assert (c.x(), c.y()) == pytest.approx((target.x(), target.y()), abs=1e-6)
        assert norm_deg(tx._angle) == pytest.approx(30.0)      # -0 + rot
        assert tx in es._texts and tx.scene() is es
    finally:
        es.cleanup()
