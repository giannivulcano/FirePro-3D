"""Schematic redraw: no false cover clip, cached corner wedges."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QTransform
from PyQt6.QtWidgets import QGraphicsView

import firepro3d.block_instance as bi
import firepro3d.stroke_style as ss
from firepro3d import paper_display as pd
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.model_space import Model_Space
from firepro3d.render_op import PoseXf
from firepro3d.stroke_style import BY_LINETYPE
from tests._block_stack_helpers import ink, lines_def, rect_def, render
from tests.test_stroke_joins import (_BP, _BSIZE, _block_def, _block_scene, _core, _core_inked,
                                     _corner_pair, _dark, _dashed_corner, _patch_px,
                                     _pick_corner, _prims, _snap)

VIEW = QRectF(-20, -60, 260, 180)
CORNER = [((0, 0), (100, 0)), ((100, 0), (100, 100))]    # joined at (100, 0)


@pytest.fixture
def be(qapp):
    s = Model_Space(scene_role="block_editor")
    s.opaque_blocks = True
    yield s
    s.cleanup()


def _stack(be, mask_x):
    """A joined corner under an opaque rect whose left edge is at *mask_x*."""
    a = be.place_block_instance(lines_def(be, "Corner", CORNER).id, (0.0, 0.0))
    b = be.place_block_instance(rect_def(be, "Top").id, (mask_x, -30.0))
    return a, b


def _spy_keep(monkeypatch):
    calls = []
    real = bi.keep_path
    monkeypatch.setattr(bi, "keep_path", lambda f, c: (calls.append(1), real(f, c))[1])
    return calls


def _view(be, zoom):
    v = QGraphicsView(be)
    v.scale(zoom, zoom)
    return v


@pytest.mark.parametrize("zoom, mask_x, clips", [(1.0, 106.0, 0), (0.25, 106.0, 1)])
def test_cover_clip_follows_the_ink_reach_at_this_zoom(be, monkeypatch, zoom, mask_x, clips):
    """A 1 px corner reaches 2.06 px, so the rect ends at x = 102.56 at zoom 1 and
    108.74 at zoom 0.25 (frame 102 + reach + weld 0.5 - margin 2). The worst-case
    41 px pad would clip at both. Observable: the real paint path calls
    ``keep_path`` only when a mask can touch ink."""
    a, _b = _stack(be, mask_x)
    monkeypatch.setattr(ss, "canvas_px", lambda w: 1.0)
    monkeypatch.setattr(bi, "canvas_px", lambda w: 1.0)
    v = _view(be, zoom)
    calls = _spy_keep(monkeypatch)
    try:
        render(be, VIEW)
    finally:
        v.setScene(None)
    assert len(calls) == clips


def _thin_rect_def(be):
    """An opaque-able rect whose own outline is ``Thin``: at the same 20 px as
    the block below, its stroke would paint over the ink a guard measures."""
    it = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    it.style["weight"] = "Thin"
    d = BlockDefinition.new(name="Thin Top", library="L", series="S",
                            primitives=[it.to_dict()], origin=(0.0, 0.0))
    be.register_block_definition(d)
    return d


def test_a_mask_inside_a_wide_wedge_still_hides_it(be, monkeypatch):
    """20 px pen under a 2x render: the stroke reaches 5 mm past x = 100, past
    the 2 mm frame margin. A mask starting at x = 103 must still hide it. The
    column x 104..105 is inside the mask, clear of its 1 mm outline."""
    px = lambda w: 2.0 if w == "Thin" else 20.0
    monkeypatch.setattr(ss, "canvas_px", px)
    monkeypatch.setattr(bi, "canvas_px", px)
    a = be.place_block_instance(lines_def(be, "Corner", CORNER).id, (0.0, 0.0))
    b = be.place_block_instance(_thin_rect_def(be).id, (103.0, -30.0))
    region = QRectF(104, -4, 1, 20)
    assert ink(be, a, region, VIEW) == 0
    b.set_opaque(False)
    assert ink(be, a, region, VIEW) > 0                    # premise: ink is there


def test_a_held_preview_of_the_lower_block_uses_its_moved_rect(be, monkeypatch):
    """A manipulator hold moves the block by Qt transform: the rect follows it,
    so a block held under the mask is hidden there."""
    monkeypatch.setattr(ss, "canvas_px", lambda w: 1.0)
    monkeypatch.setattr(bi, "canvas_px", lambda w: 1.0)
    a, b = _stack(be, 112.0)
    a.setTransform(QTransform.fromTranslate(30.0, 0.0))
    assert ink(be, a, QRectF(114, -3, 14, 6), VIEW) == 0
    b.set_opaque(False)
    assert ink(be, a, QRectF(114, -3, 14, 6), VIEW) > 0


def _diff(a, b):
    n, mx = 0, 0
    for y in range(a.height()):
        for x in range(a.width()):
            p, q = a.pixel(x, y), b.pixel(x, y)
            if p != q:
                n += 1
                mx = max(mx, *(abs(((p >> s) & 255) - ((q >> s) & 255)) for s in (0, 8, 16)))
    return n, mx


def _force_live(monkeypatch):
    monkeypatch.setattr(bi, "_joint_static", lambda ops, j: False)


def test_a_repaint_rebuilds_no_wedge(qapp, monkeypatch):
    """The bug's second cost: partners, attrs and wedges per op per paint.
    After a warm paint, a repaint computes none of them."""
    sc, _inst = _block_scene(monkeypatch, 30.0)
    try:
        _snap(sc)
        calls = []
        real = bi.BlockInstance._op_joint_attrs
        monkeypatch.setattr(bi.BlockInstance, "_op_joint_attrs",
                            lambda *a: (calls.append(1), real(*a))[1])
        real_w = bi.wedge_for_pair
        monkeypatch.setattr(bi, "wedge_for_pair",
                            lambda *a: (calls.append(1), real_w(*a))[1])
        _snap(sc)
        assert not calls
    finally:
        sc.cleanup()


@pytest.mark.parametrize("rot", [0.0, 30.0, 90.0])
@pytest.mark.parametrize("nested", [False, True])
def test_cached_wedges_match_the_live_path(qapp, monkeypatch, rot, nested):
    """Ruling: up to 2/255 on a few pixels. Same scene, cached then live."""
    sc, _inst = _block_scene(monkeypatch, rot, nested=nested)
    try:
        cached = _snap(sc)
        with monkeypatch.context() as m:
            _force_live(m)
            _inst._joint_wedge_cache = None
            live = _snap(sc)
        n, mx = _diff(cached, live)
        assert mx <= 2, (n, mx)
    finally:
        sc.cleanup()


def test_a_mirror_after_a_warm_paint_moves_the_wedges(qapp, monkeypatch):
    """The cache follows the compiled list. An L, because the shared equilateral
    triangle is its own mirror image and hides a stale wedge. Warm against cold
    on the same instance; the live path itself is pinned by the g6 oracles."""
    _patch_px(monkeypatch)
    sc = Model_Space()
    d = _block_def(_prims([LineItem(QPointF(-80, 40), QPointF(60, 40)),
                           LineItem(QPointF(60, 40), QPointF(60, -60))]))
    sc.register_block_definition(d)
    inst = sc.place_block_instance(d.id, (_BP.x(), _BP.y()), level=sc.active_level)
    try:
        before = _snap(sc, _BSIZE)
        inst.set_block_mirrored(True)
        warm = _snap(sc, _BSIZE)
        inst._joint_wedge_cache = None
        cold = _snap(sc, _BSIZE)
        assert _diff(warm, cold)[0] == 0
        assert _diff(before, cold)[0] > 0                  # premise: the drawing moved
    finally:
        sc.cleanup()


def test_a_warm_cache_follows_a_dash_that_moves_off_the_corner(qapp, monkeypatch):
    """A linetype op's ``inked`` belongs to this paint: its pair stays live, so
    a drawing scale that moves the dash off the corner flattens it on the same
    instance. The g6 dashed guard builds a fresh scene per case and cannot see
    a decision cached across paints."""
    _patch_px(monkeypatch)
    cx = _pick_corner(True)
    sc, items, _ia, _ib = _dashed_corner(cx)
    d = _block_def(_prims(items))
    sc.register_block_definition(d)
    sc.place_block_instance(d.id, (0.0, 0.0), level=sc.active_level)
    try:
        assert _core(cx, 150) <= _dark(_snap(sc))          # on ink: sharp
        sc.scale_manager.drawing_scale = 1.3               # measured: the corner lands in a gap
        assert not _core(cx, 150) <= _dark(_snap(sc))
        sc.scale_manager.drawing_scale = 1.0
        assert _core(cx, 150) <= _dark(_snap(sc))
    finally:
        sc.cleanup()


def test_a_model_blocks_weight_change_refilters_the_corner(qapp, monkeypatch):
    """By Linetype maps to the Display Manager's Model Blocks weight: a warm
    cache must follow it. Heavy + By Linetype joins only while Blocks = Heavy."""
    _patch_px(monkeypatch)
    sc = Model_Space()
    a, b = _corner_pair()
    a.style["weight"] = "Heavy"
    b.style["weight"] = BY_LINETYPE
    d = _block_def(_prims([a, b]))
    sc.register_block_definition(d)
    sc.place_block_instance(d.id, (0.0, 0.0), level=sc.active_level)
    keep = pd.model_blocks_weight()
    try:
        pd.set_model_blocks_weight("Heavy")
        assert _core_inked(_snap(sc)) == _core(150, 150)
        pd.set_model_blocks_weight("Thin")
        assert not _core_inked(_snap(sc))
        pd.set_model_blocks_weight("Heavy")
        assert _core_inked(_snap(sc)) == _core(150, 150)
    finally:
        pd.set_model_blocks_weight(keep)
        sc.cleanup()


def test_a_non_similar_painter_stays_live(qapp, monkeypatch):
    """A cosmetic pen under a stretched painter: device-space wedges, no scaled
    unit polygon. Pixels match the live path exactly, the gate's own proof."""
    sc, inst = _block_scene(monkeypatch, 30.0)

    def grab():
        img = QImage(600, 200, QImage.Format.Format_ARGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        sc.render(p, QRectF(img.rect()), QRectF(0, 0, 300, 200),
                  Qt.AspectRatioMode.IgnoreAspectRatio)
        p.end()
        return img
    try:
        cached = grab()
        with monkeypatch.context() as m:
            _force_live(m)
            inst._joint_wedge_cache = None
            live = grab()
        assert _diff(cached, live)[0] == 0
    finally:
        sc.cleanup()


def test_a_paper_pen_scales_past_a_frame_k(qapp, monkeypatch):
    """Non-cosmetic: half_w is in the item frame, so a Fixed-size frame k (0.5
    here, the triangle stays in the image) divides it out of the local wedge.
    Cached against live."""
    sc, inst = _block_scene(monkeypatch, 30.0)

    def grab():
        img = QImage(300, 300, QImage.Format.Format_ARGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pose = inst._rigid_pose()
        pose.scale(0.5, 0.5)
        xf = PoseXf(p, pose)
        pen = QPen(QColor("black"))
        pen.setWidthF(12.0)
        pen.setCosmetic(False)
        ops = inst.render_ops()
        jm = inst._joint_map()
        ctx = bi._JointCtx(None, False, None, True)
        for i in sorted(jm[1]):
            inst._paint_op_joints(p, pose, xf, ops, i, pen, jm, ctx)
        xf.unposed()
        p.end()
        return img
    try:
        cached = grab()
        with monkeypatch.context() as m:
            _force_live(m)
            inst._joint_wedge_cache = None
            live = grab()
        n, mx = _diff(cached, live)
        assert mx <= 2, (n, mx)
        assert any(live.pixel(x, y) != 0xffffffff for y in range(300) for x in range(300))  # premise
    finally:
        sc.cleanup()
