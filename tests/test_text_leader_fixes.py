"""Group L fix round: mirrored explode, End bounds and zoom, hit strip, pen."""
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_editor import BlockEditorWidget
from firepro3d.constants import TEXT_LEADER_END_ID
from firepro3d.model_space import Model_Space
from firepro3d.render_op import STROKE
from firepro3d.text_item import TextAnnotationData, TextItem
from firepro3d.text_leader import _to_parent, box_frame_points
from tests.lt5_support import arrow


def _leader(**kw):
    rec = {"edge": "R", "t": 0.5, "shoulder_mm": 6.0, "tip_x": 60.0, "tip_y": -30.0,
           "end": "none", "weight": ""}
    rec.update(kw)
    return rec


# -- 1. explode matches the placement, mirrored or not -----------------------

def _placement_points(inst):
    """The placement's leader (attach, knee, tip) in the scene: the STROKE op
    that carries ends, through the rigid pose the painter applies."""
    op = next(o for o in inst.render_ops() if o.kind == STROKE and o.ends and o.pieces)
    t = inst.pose_transform()
    pts = [QPointF(op.pieces[0].x0, op.pieces[0].y0), QPointF(op.pieces[0].x1, op.pieces[0].y1),
           QPointF(op.pieces[1].x1, op.pieces[1].y1)]
    return [t.map(p) for p in pts]


def _exploded_points(item):
    a, k, _t = box_frame_points(item)
    rec = item.data.leader
    return [_to_parent(item, a), _to_parent(item, k), QPointF(rec["tip_x"], rec["tip_y"])]


@pytest.mark.parametrize("edge", ["R", "L", "T", "B"])
@pytest.mark.parametrize("mirrored,rotation,scale", [
    (True, 0.0, 1.0), (True, 30.0, 1.0), (False, 30.0, 1.0), (True, 30.0, 2.0)])
def test_explode_draws_the_leader_the_placement_drew(qapp, edge, mirrored, rotation, scale):
    from tests.test_block_explode import _proj_and_editor
    rec = TextItem(TextAnnotationData(
        text="AB", x=-20.0, y=10.0, wrap_width_mm=30.0, box_height_mm=10.0,
        height_mm=3.0, color="#ffffff",
        leader=_leader(edge=edge, t=0.3))).to_dict()
    b = BlockDefinition.new(name="B", library="L", series="S", origin=(0.0, 0.0),
                            primitives=[rec])
    proj, w, es = _proj_and_editor(b)
    try:
        inst = es.place_block_instance(b.id, (100.0, 0.0), rotation=rotation,
                                       mirrored=mirrored, scale=scale)
        want = _placement_points(inst)
        inst.setSelected(True)
        new = es.explode_selected_blocks()
        item = next(i for i in new if isinstance(i, TextItem))
        got = _exploded_points(item)
        for g, wnt in zip(got, want):
            assert (g.x(), g.y()) == pytest.approx((wnt.x(), wnt.y()), abs=1e-6)
    finally:
        es.cleanup()


# -- 2. End bounds and zoom (real Arrow, Block Editor, real drawing scale) ---

def _editor(scale=100.0):
    proj = Model_Space()
    w = BlockEditorWidget(proj)
    sc = w.editor_scene
    sc.scale_manager.drawing_scale = scale
    return proj, w, sc


def _arrow_text(sc, edge, tip, t=0.5):
    item = TextItem(TextAnnotationData(
        text="n", wrap_width_mm=30.0, box_height_mm=10.0, height_mm=3.0,
        color="#ffffff", leader=_leader(edge=edge, t=t, tip_x=tip[0], tip_y=tip[1],
                                        end=TEXT_LEADER_END_ID)))
    sc.addItem(item)
    sc._texts.append(item)
    item.set_property("Leader End", "Arrow")        # the real load path (ensure_end_available)
    assert item.data.leader["end"] == TEXT_LEADER_END_ID
    return item


def _lit_scene_rect(sc, area, px_per_mm=1.0):
    for it in getattr(sc, "_origin_cross_items", ()):
        it.setVisible(False)
    w, h = int(area.width() * px_per_mm), int(area.height() * px_per_mm)
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    sc.render(p, QRectF(0, 0, w, h), area)
    p.end()
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            if QColor(img.pixel(x, y)).lightness() > 100:
                xs.append(x)
                ys.append(y)
    return QRectF(area.left() + min(xs) / px_per_mm, area.top() + min(ys) / px_per_mm,
                  (max(xs) - min(xs) + 1) / px_per_mm, (max(ys) - min(ys) + 1) / px_per_mm)


@pytest.mark.parametrize("edge,tip,t", [("R", (400.0, 5.0), 0.5), ("B", (30.0, 400.0), 1.0)])
def test_bounds_contain_the_drawn_arrow_end(qapp, edge, tip, t):
    """The shipped Arrow at 1:100 is ~90 mm long and +-15 mm wide: a flat
    pad cannot hold it, the bounds must be the end's own extent."""
    proj, w, sc = _editor(100.0)
    try:
        item = _arrow_text(sc, edge, tip, t)       # B at t=1: the head's width leaves the box
        lit = _lit_scene_rect(sc, QRectF(-60, -60, 560, 560))
        bounds = item.sceneBoundingRect().adjusted(-1.5, -1.5, 1.5, 1.5)
        assert bounds.contains(lit), (bounds, lit)
        assert lit.height() > 25 or lit.width() > 25          # the head really drew wide
    finally:
        sc.cleanup()


def _fixed_end_item(sc):
    fx = arrow(length=3.0, half=1.0, screen="fixed", name="FixedArrow")
    sc.register_block_definition(fx)
    item = TextItem(TextAnnotationData(
        text="n", wrap_width_mm=30.0, box_height_mm=10.0, height_mm=3.0,
        color="#ffffff", leader=_leader(edge="R", tip_x=1500.0, tip_y=5.0, end=fx.id)))
    sc.addItem(item)
    sc._texts.append(item)
    return item


def test_a_fixed_size_end_grows_the_bounds_after_a_zoom(qapp):
    from tests.test_et1_zoom import _view, _wheel
    proj, w, sc = _editor(100.0)
    v = _view(sc, 1.0)
    try:
        item = _fixed_end_item(sc)
        v.viewport().repaint()
        qapp.processEvents()
        assert item in sc._screen_end_items                      # the bounds / paint marked it
        before = item.boundingRect().united(QRectF()).height()
        for _ in range(12):
            _wheel(v, up=False)                                  # zoom out
        qapp.processEvents()
        after = item.boundingRect().height()
        assert after > before * 1.5, (before, after)
    finally:
        v.close()
        sc.cleanup()


# -- 3. hit strip follows the zoom -------------------------------------------

def test_leader_hit_strip_is_about_ten_screen_pixels(qapp):
    from tests.test_et1_zoom import _view
    proj, w, sc = _editor(100.0)
    v = _view(sc, 0.1)                                           # 0.1 px per scene mm
    try:
        item = _arrow_text(sc, "R", (400.0, 5.0))
        qapp.processEvents()
        zoom = abs(v.transform().m11())
        hit = item._leader_hit_mm()
        assert hit == pytest.approx(10.0 / zoom, rel=0.05)       # 10 screen px, not a fixed 5 mm
        assert hit > 20.0                                        # the flat 5 mm was far too thin
        # a point a quarter strip off the leader line is still a hit at this zoom
        assert item.contains(item.mapFromScene(QPointF(200.0, 5.0 + hit / 4.0)))
    finally:
        v.close()
        sc.cleanup()


# -- 4. the leader pen no longer rides on border fields ----------------------

class _SpyData(TextAnnotationData):
    writes: list = []

    def __setattr__(self, k, v):
        if k in ("border_weight", "border_line_type") and getattr(self, "_armed", False):
            type(self).writes.append(k)
        object.__setattr__(self, k, v)


def _paper_text(weight):
    from firepro3d.paper_space import PaperScene, Sheet
    from tests.test_paper_annotations import _stub_resolver
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    d = _SpyData(text="n", x=20.0, y=20.0, wrap_width_mm=30.0, box_height_mm=10.0,
                 height_mm=3.0, color="#000000",
                 leader=_leader(tip_x=90.0, tip_y=60.0, weight=weight))
    item = TextItem(d)
    scene.addItem(item)
    item.setPos(20.0, 20.0)
    return scene, item, d


def test_leader_pen_prints_its_own_weight_and_never_writes_the_frame_fields(qapp):
    from firepro3d.paper_display import resolve_line_weight_mm, weight_names
    names = weight_names()
    scene, item, d = _paper_text(names[-1])
    assert item.is_device_independent()
    assert names[-1] != d.border_weight
    s = item.scale()
    pen = item._leader_pen(s)
    assert not pen.isCosmetic()
    assert pen.widthF() == pytest.approx(resolve_line_weight_mm(names[-1]), rel=1e-6)   # printed mm
    # a paint touches the pen path and must not write the shared fields
    _SpyData.writes = []
    d._armed = True
    img = QImage(300, 200, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, 300, 200), QRectF(0, 0, 150, 100))
    p.end()
    assert _SpyData.writes == []
    assert item._leader_pen(s).widthF() == pytest.approx(resolve_line_weight_mm(names[-1]), rel=1e-6)
    # no weight of its own: the frame's
    d.leader["weight"] = ""
    assert item._leader_pen(s).widthF() == pytest.approx(
        resolve_line_weight_mm(d.border_weight), rel=1e-6)
