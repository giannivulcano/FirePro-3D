"""BlockInstance mirror / scale pose (design DD2/DD3/DD6) -- rendered truth."""
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QStyleOptionGraphicsItem

from firepro3d import paper_display as pd
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.test_block_rotate import _ink        # paint-pixel bbox helper


def _l_def(ms):
    """Asymmetric L: 100 mm +X leg, 40 mm visually-up leg."""
    d = BlockDefinition.new(name="L", library="L", series="S", origin=(0.0, 0.0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict(),
                                        LineItem(QPointF(0, 0), QPointF(0, -40)).to_dict()])
    ms.register_block_definition(d)
    return d


def _endpoints(ms, inst):
    return sorted((round(p.x(), 6), round(p.y(), 6))
                  for k, p, _n in ms._snap_engine._collect(inst) if k == "endpoint")


def test_manip_reflect_mirrors_the_posed_geometry(qapp):
    ms = Model_Space()
    d = _l_def(ms)
    inst = ms.place_block_instance(d.id, (0.0, 0.0))
    inst.manip_reflect(QPointF(50.0, -100.0), QPointF(50.0, 100.0))   # x = 50
    x0, y0, x1, y1 = _ink(inst)
    assert x0 == pytest.approx(0.0, abs=1.5) and x1 == pytest.approx(100.0, abs=1.5)
    assert (inst.block_pos(), inst.block_mirrored()) == ((100.0, 0.0), True)
    # the up leg now hangs off the right end (x = 100), not the left
    assert set(_endpoints(ms, inst)) == {(100.0, 0.0), (0.0, 0.0), (100.0, -40.0)}


def test_manip_reflect_degenerate_axis_is_a_no_op(qapp):
    ms = Model_Space()
    inst = ms.place_block_instance(_l_def(ms).id, (10.0, 0.0))
    inst.manip_reflect(QPointF(5.0, 5.0), QPointF(5.0, 5.0))
    assert (inst.block_pos(), inst.block_mirrored()) == ((10.0, 0.0), False)


def test_manip_scale_about_scales_bounds_not_paper_pen(qapp):
    ms = Model_Space()
    inst = ms.place_block_instance(_l_def(ms).id, (0.0, 0.0))
    w1 = inst.geometric_rect().width()
    inst.manip_scale_about(QPointF(0.0, 0.0), 2.0)
    assert inst.geometric_rect().width() == pytest.approx(2.0 * w1)
    assert inst.block_scale() == pytest.approx(2.0)
    with pytest.raises(ValueError):
        inst.manip_scale_about(QPointF(0, 0), 0.0)


def test_manip_scale_about_moves_the_insertion_point(qapp):
    ms = Model_Space()
    inst = ms.place_block_instance(_l_def(ms).id, (10.0, 20.0))
    inst.manip_scale_about(QPointF(0.0, 0.0), 3.0)
    assert inst.block_pos() == pytest.approx((30.0, 60.0))
    assert set(_endpoints(ms, inst)) == {(30.0, 60.0), (330.0, 60.0), (30.0, -60.0)}


def test_set_block_scale_rejects_non_positive(qapp):
    ms = Model_Space()
    inst = ms.place_block_instance(_l_def(ms).id, (0.0, 0.0))
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            inst.set_block_scale(bad)
    assert inst.block_scale() == 1.0


def _paper_ink_thickness(ms, inst, scale):
    """Painted thickness (px = scene mm) of a horizontal leg on a real paper
    pass (``paper_display.apply_paper_overrides`` -> ``_apply_block``)."""
    inst.set_block_scale(scale)
    saved = pd.apply_paper_overrides(ms, QRectF(-1e5, -1e5, 2e5, 2e5),
                                     paper_scale=0.05)
    try:
        assert inst._paper_pen_width is not None
        x0, y0, x1, y1 = _ink(inst)
    finally:
        pd.restore_model_display(saved)
    assert inst._paper_pen_width is None
    return y1 - y0, x1 - x0


def test_paper_pen_width_does_not_scale(qapp):
    ms = Model_Space()
    d = BlockDefinition.new(name="H", library="L", series="S", origin=(0.0, 0.0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict()])
    ms.register_block_definition(d)
    inst = ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
    t1, len1 = _paper_ink_thickness(ms, inst, 1.0)
    t3, len3 = _paper_ink_thickness(ms, inst, 3.0)
    assert t1 > 2.0                                   # a measurable plotted pen
    assert len3 == pytest.approx(3.0 * len1, rel=0.1)  # geometry scales ...
    assert t3 == pytest.approx(t1, abs=1.0)           # ... the paper pen does not


def test_instances_with_equal_pose_part_share_one_variant_list(qapp):
    ms = Model_Space()
    d = _l_def(ms)
    a = ms.place_block_instance(d.id, (0.0, 0.0))
    b = ms.place_block_instance(d.id, (500.0, 0.0))
    for i in (a, b):
        i.set_block_mirrored(True)
        i.set_block_scale(2.0)
    assert a.render_ops() is b.render_ops()                                   # flyweight per variant
    assert a.render_ops() is d.render_ops_variant(True, 2.0)


def test_mirror_change_alone_reposes_the_cached_path(qapp):
    """No x / y / rot change: the posed-path cache must still re-key."""
    ms = Model_Space()
    inst = ms.place_block_instance(_l_def(ms).id, (0.0, 0.0))
    r0 = inst.geometric_rect()
    assert r0.left() == pytest.approx(0.0) and r0.right() == pytest.approx(100.0)
    inst.set_block_mirrored(True)
    r1 = inst.geometric_rect()
    assert r1.left() == pytest.approx(-100.0) and r1.right() == pytest.approx(0.0)


def _text_block(ms):
    d = BlockDefinition.new(name="T", library="L", series="S", origin=(0.0, 0.0),
                            primitives=[{"type": "text", "text": "FPT", "x": 50.0,
                                         "y": -20.0, "height_mm": 20.0}])
    ms.register_block_definition(d)
    return ms.place_block_instance(d.id, (0.0, 0.0))


_ZOOM = 4    # raster px per scene mm: glyph detail well above phase noise


def _raster(inst):
    r = inst.sceneBoundingRect().adjusted(-5, -5, 5, 5)
    img = QImage(int(r.width() * _ZOOM) + 1, int(r.height() * _ZOOM) + 1,
                 QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    p.scale(_ZOOM, _ZOOM)
    p.translate(-r.left(), -r.top())
    inst.paint(p, QStyleOptionGraphicsItem(), None)
    p.end()
    return img


def _signatures(img):
    """Per-column and per-row inked-pixel counts, trimmed to the ink."""
    w, h = img.width(), img.height()
    ink = [[1 if (img.pixel(x, y) >> 24) & 0xFF else 0 for x in range(w)]
           for y in range(h)]
    cols = [sum(ink[y][x] for y in range(h)) for x in range(w)]
    rows = [sum(r) for r in ink]

    def strip(v):
        i0 = next(i for i, c in enumerate(v) if c)
        i1 = len(v) - next(i for i, c in enumerate(reversed(v)) if c)
        return v[i0:i1]
    return strip(cols), strip(rows)


def _mismatch(a, b):
    """Relative L1 distance of two signatures at their best +-1 mm alignment
    (a mirrored + turned raster lands on a different sub-pixel phase)."""
    best = None
    for s in range(-_ZOOM, _ZOOM + 1):
        n = max(len(a), len(b) + s, len(b))
        aa = a + [0] * (n - len(a))
        bb = ([0] * s + b if s >= 0 else b[-s:])
        bb = bb + [0] * (n - len(bb))
        d = sum(abs(x - y) for x, y in zip(aa, bb)) / max(sum(a), 1)
        best = d if best is None else min(best, d)
    return best


def _same(a, b):
    """Signatures equal within antialias / phase noise."""
    return _mismatch(a, b) < 0.15


@pytest.mark.parametrize("rot", [0.0, 180.0])     # vertical-axis flip / top-bottom flip
def test_mirrored_text_reads_left_to_right_and_upright(qapp, rot):
    ms = Model_Space()
    cols0, rows0 = _signatures(_raster(_text_block(ms)))
    # sanity: "FPT" is asymmetric both ways, so a flip changes each signature
    assert not _same(cols0, cols0[::-1]) and not _same(rows0, rows0[::-1])
    m = _text_block(ms)
    m.set_block_mirrored(True)
    m.set_block_rotation(rot)
    cols, rows = _signatures(_raster(m))
    assert _same(cols, cols0), "mirrored text reads backwards"
    assert _same(rows, rows0), "mirrored text reads upside down"


def test_text_snap_box_follows_scale(qapp):
    ms = Model_Space()
    inst = _text_block(ms)
    before = [p for k, p, _n in ms._snap_engine._collect(inst)]
    inst.set_block_scale(2.0)
    after = [p for k, p, _n in ms._snap_engine._collect(inst)]
    bx = max(p.x() for p in before) - min(p.x() for p in before)
    ax = max(p.x() for p in after) - min(p.x() for p in after)
    assert ax == pytest.approx(2.0 * bx, rel=1e-6)


# ── Review round: rotation-dependent reflect, bounds, nested scale ───────

def _reflected(pts, p1, p2):
    from firepro3d.transform_ghost import reflect_transform
    t = reflect_transform(p1, p2)
    return {(round(q.x(), 6), round(q.y(), 6))
            for q in (t.map(QPointF(x, y)) for x, y in pts)}


@pytest.mark.parametrize("pos, rot, p1, p2, want_rot", [
    ((0.0, 0.0), 0.0, QPointF(-100, 0), QPointF(100, 0), 180.0),      # horizontal axis
    ((10.0, 20.0), 30.0, QPointF(50, -100), QPointF(50, 100), -30.0),  # rotated, vertical
    ((10.0, 20.0), 30.0, QPointF(0, 0),                                # rotated, 30 deg axis
     QPointF(86.60254037844386, -50.0), 210.0 - 360.0),
])
def test_manip_reflect_of_a_rotated_block_matches_the_pointwise_reflection(
        qapp, pos, rot, p1, p2, want_rot):
    ms = Model_Space()
    inst = ms.place_block_instance(_l_def(ms).id, pos, rotation=rot)
    before = set(_endpoints(ms, inst))
    inst.manip_reflect(p1, p2)
    assert inst.block_mirrored() is True
    assert ((inst.block_rotation() - want_rot + 180.0) % 360.0 - 180.0
            == pytest.approx(0.0, abs=1e-9))
    assert set(_endpoints(ms, inst)) == _reflected(before, p1, p2)


def _desc_block(ms, text="gjpq"):
    d = BlockDefinition.new(name="G", library="L", series="S", origin=(0.0, 0.0),
                            primitives=[{"type": "text", "text": text, "x": 50.0,
                                         "y": -20.0, "height_mm": 20.0}])
    ms.register_block_definition(d)
    return ms.place_block_instance(d.id, (0.0, 0.0))


def test_turned_text_ink_stays_inside_the_posed_bounds(qapp):
    """Mirrored rot-180 text is turned at paint (DD6): bounds / shape / halo
    must cover the turned glyphs, descenders included."""
    ms = Model_Space()
    inst = _desc_block(ms)
    inst.set_block_mirrored(True)
    inst.set_block_rotation(180.0)
    x0, y0, x1, y1 = _ink(inst)
    g = inst.geometric_rect().adjusted(-2.0, -2.0, 2.0, 2.0)   # pen margin
    assert g.left() <= x0 and x1 <= g.right()
    assert g.top() <= y0 and y1 <= g.bottom()


def _text_rot_block(ms, rot, mirrored):
    inst = _text_block(ms)
    inst.set_block_mirrored(mirrored)
    inst.set_block_rotation(rot)
    return inst


@pytest.mark.parametrize("rot", [90.0, -90.0])
def test_mirrored_text_turns_on_the_instance_rotation_sign(qapp, rot):
    """Upright decision uses frame angle + rot: mirrored at +90 reads like
    the plain block at +90; mirrored at -90 is turned to read like +90."""
    ms = Model_Space()
    cols0, rows0 = _signatures(_raster(_text_rot_block(ms, 90.0, False)))
    assert not _same(cols0, cols0[::-1]) and not _same(rows0, rows0[::-1])
    cols, rows = _signatures(_raster(_text_rot_block(ms, rot, True)))
    assert _same(cols, cols0) and _same(rows, rows0)


def test_mirrored_text_snap_box_is_the_full_pose_of_the_definition_box(qapp):
    from firepro3d.block_pose import pose_matrix
    ms = Model_Space()
    inst = _text_block(ms)
    inst.set_block_pos(10.0, 20.0)
    inst.set_block_rotation(30.0)
    inst.set_block_mirrored(True)
    inst.set_block_scale(2.0)
    eng = ms._snap_engine
    t = pose_matrix(10.0, 20.0, 30.0, True, 2.0)       # independent of the item
    want = {(k, round(p.x(), 6), round(p.y(), 6))
            for box in inst.definition().text_snap_points()
            for k, p, _n in eng._box_snaps([t.map(q) for q in box])}
    got = {(k, round(p.x(), 6), round(p.y(), 6)) for k, p, _n in eng._collect(inst)}
    assert want and want <= got


def _nested_host(ms, scale):
    child = _l_def(ms)
    rec = {"type": "block_instance", "block_id": child.id, "pos": [0.0, 0.0],
           "rotation": 0.0, "uid": "n1"}
    if scale is not None:
        rec["scale"] = scale
    host = BlockDefinition.new(name="H", library="L", series="S", origin=(0.0, 0.0),
                               primitives=[rec])
    ms.register_block_definition(host)
    return host, rec


def _op_points(ops):
    return [[(round(op.path.elementAt(i).x, 6), round(op.path.elementAt(i).y, 6))
             for i in range(op.path.elementCount())] for op in ops]


@pytest.mark.parametrize("bad", ["x", 0, -2.0])
def test_corrupt_nested_scale_compiles_as_identity(qapp, bad):
    from firepro3d.schematic_scene import materialize_primitives
    ms = Model_Space()
    good, _ = _nested_host(ms, None)
    host, rec = _nested_host(ms, bad)
    assert _op_points(host.render_ops()) == _op_points(good.render_ops())
    inst = ms.place_block_instance(host.id, (0.0, 0.0))      # host does not crash
    r = inst.geometric_rect()
    assert (r.left(), r.top(), r.right(), r.bottom()) == pytest.approx(
        (0.0, -40.0, 100.0, 0.0))
    ed = Model_Space(scene_role="block_editor")
    ed.register_block_definition(ms.get_block_definition(rec["block_id"]))
    materialize_primitives(ed, [rec])
    (seed,) = ed._block_instances
    assert seed.block_scale() == 1.0                            # editor agrees
    s = seed.geometric_rect()
    assert (s.left(), s.top(), s.right(), s.bottom()) == pytest.approx(
        (r.left(), r.top(), r.right(), r.bottom()))


def test_tiny_scale_variant_does_not_collapse(qapp):
    ms = Model_Space()
    d = _l_def(ms)
    v = d.render_ops_variant(False, 1e-12)
    w = max(op.path.boundingRect().width() for op in v)
    assert w == pytest.approx(100e-12, rel=1e-6)
    assert d.render_ops_variant(False, 2e-12) is not v
    assert d.render_ops_variant(False, 1.0000000001) is d.render_ops()


def test_orphan_placeholder_follows_mirror_and_scale(qapp):
    ms = Model_Space()
    inst = ms.place_block_instance("no-such-block", (0.0, 0.0))
    assert inst.geometric_rect().width() == pytest.approx(200.0)
    inst.set_block_scale(5.0)
    r = inst.geometric_rect()
    assert (r.width(), r.height()) == pytest.approx((1000.0, 1000.0))
