"""RenderOp.mapped under a reflecting / scaling similarity (design DD5/DD6)."""
import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath, QTransform

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_pose import pose_matrix
from firepro3d.path_walk import Seg
from firepro3d.render_op import STROKE, TEXT, RenderOp
from firepro3d.text_item import TextItem

# Text glyph outlines need a QApplication (QFont / QTextDocument).
pytestmark = pytest.mark.usefixtures("qapp")


def _text_def(text="FDC", x=50.0, y=-20.0, angle=0.0):
    rec = {"type": "text", "text": text, "x": x, "y": y, "height_mm": 10.0}
    if angle:
        rec["angle"] = angle
    return BlockDefinition.new(name="T", library="L", series="S",
                               primitives=[rec], origin=(0.0, 0.0))


def _text_op(d):
    return next(o for o in d.render_ops() if o.kind == TEXT)


def _assert_same_path(want, got, tol=1e-6):
    assert want.elementCount() == got.elementCount() > 0
    for i in range(want.elementCount()):
        a, b = want.elementAt(i), got.elementAt(i)
        assert a.x == pytest.approx(b.x, abs=tol)
        assert a.y == pytest.approx(b.y, abs=tol)


def test_compiled_text_op_carries_its_box_frame():
    d = _text_def()
    op = _text_op(d)
    assert op.text_frame is not None
    item = TextItem.from_dict({"type": "text", "text": "FDC", "x": 50.0,
                               "y": -20.0, "height_mm": 10.0})
    c = item.grip_points()[8]
    assert op.text_frame[:2] == pytest.approx((c.x(), c.y()))
    assert op.text_frame[2] == pytest.approx(0.0)
    assert op.readable is False


def test_text_frame_centre_is_the_centre_of_the_glyphs_box():
    """The frame centre is the TL/BR midpoint of the text box that encloses
    the compiled glyphs (same frame as the glyph path, origin-relative)."""
    rec = {"type": "text", "text": "FDC", "x": 50.0, "y": -20.0,
           "height_mm": 10.0}
    d = BlockDefinition.new(name="T", library="L", series="S",
                            primitives=[dict(rec)], origin=(7.0, 3.0))
    op = _text_op(d)
    g = TextItem.from_dict(rec).grip_points()
    tl, br = g[0], g[4]
    l, t, r, b = tl.x() - 7.0, tl.y() - 3.0, br.x() - 7.0, br.y() - 3.0
    assert op.text_frame[:2] == pytest.approx(((l + r) / 2, (t + b) / 2))
    gb = op.path.boundingRect()
    assert l <= gb.left() and gb.right() <= r
    assert t <= gb.top() and gb.bottom() <= b


def test_mirrored_text_glyphs_are_not_backwards():
    """The mirrored op's glyph path equals the original glyphs TRANSLATED so
    the box centre lands on its mirrored spot (no glyph reversal)."""
    d = _text_def()
    op = _text_op(d)
    m = op.mapped(pose_matrix(0.0, 0.0, 0.0, mirrored=True))
    cx, cy, _a = op.text_frame
    assert m.text_frame[:2] == pytest.approx((-cx, cy))
    assert m.text_frame[2] == pytest.approx(0.0)
    assert m.readable is True
    want = QPainterPath(op.path).translated(-2.0 * cx, 0.0)
    got = m.path
    for i in range(0, want.elementCount(), max(1, want.elementCount() // 40)):
        a, b = want.elementAt(i), got.elementAt(i)
        assert (round(a.x, 4), round(a.y, 4)) == (round(b.x, 4), round(b.y, 4))  # [RED]


@pytest.mark.parametrize("angle", [30.0, -55.0, 120.0])
def test_mirrored_rotated_text_is_rotation_negated_not_backwards(angle):
    """A text record rotated by *angle* (Y-up CCW), mirrored across local x,
    reads as the UNROTATED glyphs rotated by -angle about the mirrored box
    centre -- i.e. a mirror negates the rotation but never reverses glyphs.

    Expected is built independently of ``RenderOp.mapped``: the angle-0
    compile of the same record (same box centre -- the rotation pivots on
    it) turned by Y-up ``-angle`` (Qt ``rotate(+angle)``) about the centre,
    then moved to the mirrored centre. A "no un-mirror" or "un-mirror about
    the baseline (horizontal) axis" mapping both differ element-wise.
    """
    flat = _text_op(_text_def())
    op = _text_op(_text_def(angle=angle))
    cx, cy, a = op.text_frame
    assert a == pytest.approx(angle)
    assert (cx, cy) == pytest.approx(flat.text_frame[:2])
    m = op.mapped(QTransform(-1, 0, 0, 1, 0, 0))
    assert m.readable is True
    assert m.text_frame == pytest.approx((-cx, cy, -angle))
    g = QTransform()
    g.translate(-cx, cy)          # Qt: last-called applies first to points
    g.rotate(angle)               # Y-up -angle
    g.translate(-cx, -cy)
    _assert_same_path(g.map(flat.path), m.path)


def test_scaled_text_frame_and_height_scale():
    d = _text_def()
    op = _text_op(d)
    m = op.mapped(pose_matrix(0.0, 0.0, 0.0, scale=2.0))
    assert m.path.boundingRect().height() == pytest.approx(
        2.0 * op.path.boundingRect().height(), rel=1e-6)
    cx, cy, _a = op.text_frame
    assert m.text_frame == pytest.approx((2.0 * cx, 2.0 * cy, 0.0))
    assert m.readable is False


def test_reflection_toggles_end_mirrored_flags_only():
    ends = ({"end": "a", "visible": True}, {"end": "b", "visible": True, "mirrored": True})
    path = QPainterPath(QPointF(0, 0))
    path.lineTo(10, 0)
    op = RenderOp(STROKE, path, pieces=(Seg(0, 0, 10, 0),), ends=ends,
                  weight="Medium", origin=QPointF(0, 0))
    m = op.mapped(QTransform(-1, 0, 0, 1, 0, 0))
    assert m.ends[0].get("mirrored") is True                                  # [RED]
    assert "mirrored" not in m.ends[1]                                        # [RED]
    assert (m.ends[0]["end"], m.ends[1]["end"]) == ("a", "b")                 # no swap
    assert op.ends[0] == {"end": "a", "visible": True}                        # flyweight untouched
    r = op.mapped(QTransform.fromTranslate(5, 0))
    assert r.ends == op.ends                                                  # rigid: unchanged


# ── Task 4: nested pose + per-(mirrored, scale) variant op cache ─────────────

from firepro3d.constants import BLOCK_VARIANT_CACHE_MAX  # noqa: E402
from firepro3d.path_walk import Arc, point_at, length  # noqa: E402
from firepro3d.render_op import STROKE as _STROKE  # noqa: E402


def _arc_def():
    rec = {"type": "arc", "cx": 40.0, "cy": 0.0, "radius": 10.0,
           "start_deg": 0.0, "span_deg": 90.0}     # ArcItem.to_dict keys (verified)
    return BlockDefinition.new(name="A", library="L", series="S",
                               primitives=[rec], origin=(0.0, 0.0))


def test_variant_identity_is_the_shared_list():
    d = _arc_def()
    assert d.render_ops_variant(False, 1.0) is d.render_ops()


def test_variant_is_cached_and_shared_per_key():
    d = _arc_def()
    a = d.render_ops_variant(True, 2.0)
    assert d.render_ops_variant(True, 2.0) is a
    assert d.render_ops_variant(True, 2.0000000001) is a       # rounded key
    assert d.render_ops_variant(False, 2.0) is not a


def test_variant_drops_on_recompile():
    d = _arc_def()
    a = d.render_ops_variant(True, 1.0)
    d.invalidate_cache()
    assert d.render_ops_variant(True, 1.0) is not a


def test_invalidate_cache_releases_the_variants():
    d = _arc_def()
    d.render_ops_variant(True, 2.0)
    assert d._variants is not None
    d.invalidate_cache()
    assert d._variants is None


def test_set_primitives_releases_the_variants():
    d = _arc_def()
    d.render_ops_variant(True, 2.0)
    d.set_primitives(list(d.primitives))
    assert d._variants is None


def test_variant_identity_holds_on_the_rounded_key():
    d = _arc_def()
    assert d.render_ops_variant(False, 1.0000000001) is d.render_ops()


def test_variant_cache_evicts_least_recently_used():
    """Touching the oldest key makes it recent: the next insert past the
    cap evicts the second-oldest instead (LRU, not FIFO)."""
    d = _arc_def()
    scales = [1.0 + 0.5 * (i + 1) for i in range(BLOCK_VARIANT_CACHE_MAX + 1)]
    lists = [d.render_ops_variant(False, s) for s in scales[:-1]]   # fill to cap
    assert d.render_ops_variant(False, scales[0]) is lists[0]        # touch
    d.render_ops_variant(False, scales[-1])                          # one past cap
    assert d.render_ops_variant(False, scales[0]) is lists[0]        # survived
    assert d.render_ops_variant(False, scales[1]) is not lists[1]    # evicted


def test_variant_cache_is_lru_capped():
    d = _arc_def()
    scales = [1.0 + 0.5 * (i + 1) for i in range(BLOCK_VARIANT_CACHE_MAX + 1)]
    first = d.render_ops_variant(False, scales[0])
    lists = [first] + [d.render_ops_variant(False, s) for s in scales[1:]]
    assert d.render_ops_variant(False, scales[-1]) is lists[-1]     # newest kept
    assert d.render_ops_variant(False, scales[1]) is lists[1]       # still inside cap
    assert d.render_ops_variant(False, scales[0]) is not first      # evicted -> rebuilt


def test_variant_mirrored_text_op_is_readable():
    d = _text_def()
    (op,) = [o for o in d.render_ops_variant(True, 1.0) if o.kind == TEXT]
    assert op.readable is True
    assert _text_op(d).readable is False                           # base untouched


def test_variant_mirrored_scaled_arc_geometry():
    """Mirror x2 of the arc: centre (40, 0) -> (-80, 0), radius 20; start
    (50, 0) -> (-100, 0); end (40, -10) -> (-80, -20)."""
    d = _arc_def()
    op = next(o for o in d.render_ops_variant(True, 2.0) if o.pieces)
    (p,) = op.pieces
    assert (p.cx, p.cy, p.r) == pytest.approx((-80.0, 0.0, 20.0))
    s0, s1 = point_at(p, 0.0), point_at(p, length(p))
    assert (round(s0.x(), 6), round(s0.y(), 6)) == (-100.0, 0.0)
    assert (round(s1.x(), 6), round(s1.y(), 6)) == (-80.0, -20.0)


def test_nested_mirrored_scaled_arc_has_hand_derived_geometry():
    """Host nests the arc block mirrored x2 at (100, 0): the arc centre
    (40, 0) maps to (100 - 80, 0) = (20, 0); radius 20; its start (50, 0)
    maps to (0, 0); its end (40, -10) maps to (20, -20)."""
    child = _arc_def()
    host = BlockDefinition.new(
        name="H", library="L", series="S", origin=(0.0, 0.0),
        primitives=[{"type": "block_instance", "block_id": child.id,
                     "pos": [100.0, 0.0], "rotation": 0.0,
                     "mirrored": True, "scale": 2.0, "uid": "n1"}])
    host._resolve = lambda i: child if i == child.id else None
    op = next(o for o in host.render_ops() if o.kind == _STROKE and o.pieces)
    (p,) = op.pieces
    assert isinstance(p, Arc)
    assert (p.cx, p.cy, p.r) == pytest.approx((20.0, 0.0, 20.0))          # [RED]
    s0, s1 = point_at(p, 0.0), point_at(p, length(p))
    assert (round(s0.x(), 6), round(s0.y(), 6)) == (0.0, 0.0)
    assert (round(s1.x(), 6), round(s1.y(), 6)) == (20.0, -20.0)


# ── Frame angle under rotating / reflecting poses (review round) ─────────────


def _nested_text_frame(rotation, mirrored, text_angle=0.0):
    """The host's TEXT op frame for a text child nested at *rotation*."""
    child = _text_def(angle=text_angle)
    host = BlockDefinition.new(
        name="H", library="L", series="S", origin=(0.0, 0.0),
        primitives=[{"type": "block_instance", "block_id": child.id,
                     "pos": [0.0, 0.0], "rotation": rotation,
                     "mirrored": mirrored, "scale": 1.0, "uid": "n1"}])
    host._resolve = lambda i: child if i == child.id else None
    return _text_op(host).text_frame


def test_direct_rotation_turns_the_frame_angle():
    """A 0 deg text op mapped through a rigid 90 deg (Y-up CCW) pose: the
    baseline now points up, centre (cx, cy) -> (cy, -cx) in Y-down scene."""
    op = _text_op(_text_def())
    cx, cy, _a = op.text_frame
    m = op.mapped(pose_matrix(0.0, 0.0, 90.0))
    assert m.text_frame == pytest.approx((cy, -cx, 90.0))
    assert m.readable is False


@pytest.mark.parametrize("rotation, mirrored, text_angle, want", [
    (90.0, False, 0.0, 90.0),       # rigid: 0 + 90
    (30.0, True, 0.0, 30.0),        # mirror negates 0 -> -0, then + 30
    (30.0, True, 20.0, 10.0),       # mirror: -20, then + 30
    (180.0, True, 0.0, 180.0),      # -0 + 180, folded into (-180, 180]
])
def test_nested_frame_angle_is_hand_derived(rotation, mirrored, text_angle, want):
    """pose = T.R(rot).M: the mirror (innermost) negates the text angle,
    then the record rotation adds; the frame angle lies in (-180, 180]."""
    _x, _y, a = _nested_text_frame(rotation, mirrored, text_angle)
    assert a == pytest.approx(want, abs=1e-9)
    assert -180.0 < a <= 180.0
