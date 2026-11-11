"""Guards: HALO / click / crossing band hit a block on its drawn primitives,
not its empty interior (selection-mode §4.1; Phase 2 rulings 2026-10-14).

Real path: shown plan Model_View, posted moves / clicks / drags in select
mode. Ground truth: scene.halo_item() and the selection. Scene points come
from the instance's own full pose (oracle) on hand-written local coordinates.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.text_item import TextAnnotationData, TextItem
from tests._block_snap_helpers import oracle
from tests._snap_polish_helpers import click, close_view, drag, make_view, move

# Hollow rect x 100..180, y -30..30 (its centre is >= 30 local from every
# edge: > the 15 px aperture at scale 1), solid-filled circle centre (0,100)
# r 30, text at (-150,-80).
_PRIMS = [
    {"type": "draw_rectangle", "x": 100.0, "y": -30.0, "w": 80.0, "h": 60.0,
     "color": "#ffffff", "lineweight": 1.0},
    {"type": "draw_circle", "cx": 0.0, "cy": 100.0, "radius": 30.0,
     "color": "#ffffff", "lineweight": 1.0,
     "fill": {"type": "solid", "color": "#888888", "opacity": 0.45}},
]
_POSES = [((40.0, 20.0), 0.0, False, 1.0), ((50.0, -30.0), 90.0, True, 1.5)]
_IDS = ["plain", "rot90-mirror-x1.5"]


def _setup(pose):
    view, scene = make_view(role="plan", scale=1.0, mode="select")
    txt = TextItem(TextAnnotationData(text="AB", x=-150.0, y=-80.0,
                                      height_mm=20.0)).to_dict()
    d = BlockDefinition.new(name="H", library="L", series="S",
                            origin=(0.0, 0.0), primitives=[*_PRIMS, txt])
    scene.register_block_definition(d)
    pos, rot, mir, s = pose
    inst = scene.place_block_instance(d.id, pos, rotation=rot, mirrored=mir,
                                      scale=s)
    vp = view.viewport().rect()
    for p in (oracle(inst, 140.0, 0.0), oracle(inst, 0.0, 100.0)):
        assert vp.contains(view.mapFromScene(p))          # on screen
    return view, scene, inst, d


def _hover(view, scene, p):
    move(view, p)
    return scene.halo_item()


@pytest.mark.parametrize("pose", _POSES, ids=_IDS)
def test_hover_hits_strokes_fills_and_text_but_not_empty_interior(qapp, pose):
    view, scene, inst, d = _setup(pose)
    try:
        assert _hover(view, scene, oracle(inst, 140.0, 0.0)) is None     # [RED]
        assert _hover(view, scene, oracle(inst, 180.0, 0.0)) is inst     # edge
        assert _hover(view, scene, oracle(inst, 0.0, 110.0)) is inst     # fill
        box = d.text_snap_points()[0]
        c = inst.full_pose_transform().map(box[8])                      # text box
        assert _hover(view, scene, c) is inst
    finally:
        close_view(view, scene)


def _hover_click(view, p):
    move(view, p)            # a real click follows a hover (HALO updates on move)
    click(view, p)


def test_click_in_empty_interior_selects_nothing(qapp):
    view, scene, inst, _d = _setup(_POSES[1])
    try:
        _hover_click(view, oracle(inst, 140.0, 0.0))
        assert not inst.isSelected()                                    # [RED]
        _hover_click(view, oracle(inst, 180.0, 0.0))
        assert inst.isSelected()
    finally:
        close_view(view, scene)


def test_crossing_band_inside_the_interior_misses_the_block(qapp):
    view, scene, inst, _d = _setup(_POSES[0])
    try:
        a, b = oracle(inst, 160.0, -10.0), oracle(inst, 120.0, 10.0)
        start = QPointF(max(a.x(), b.x()), min(a.y(), b.y()))   # R->L = crossing
        end = QPointF(min(a.x(), b.x()), max(a.y(), b.y()))
        move(view, start)                     # a real drag starts from a hover
        drag(view, start, end)
        assert not inst.isSelected()                                    # [RED]
        assert inst.block_pos() == (40.0, 20.0)       # a band, never a move
    finally:
        close_view(view, scene)


_RING_N = 500             # heavily overlapping circles (calibrated 2026-11-11:
_RING_R = 100.0           # the band's union with one text box alone took 11.7 s;
_RING_COLS = 40           # few ops, so the fixed hover's per-op costs stay small)
_RING_PITCH = 30.0


def _ring_prims(n=_RING_N):
    """A detailed block: rows of heavily overlapping circles (thousands of
    band crossings), like the 26307 pump-room block that froze Section 1."""
    return [{"type": "draw_circle",
             "cx": 25.0 + (i % _RING_COLS) * _RING_PITCH,
             "cy": 25.0 + (i // _RING_COLS) * _RING_PITCH, "radius": _RING_R,
             "color": "#ffffff", "lineweight": 1.0} for i in range(n)]


def test_hover_on_a_detailed_block_with_a_text_box_stays_fast(qapp):
    # 2026-11-11 smoke: hovering a gridline-hosted block with 4119 strokes and
    # one text box froze the app for minutes -- shape() unioned the ~10 px
    # stroke band with the text-box area (QPainterPath.united). The real hover
    # path (posted move -> HALO -> items(IntersectsItemShape)) must stay well
    # inside an interactive budget and still pick the block on a stroke and
    # in its text box.
    import time
    view, scene = make_view(role="plan", scale=1.0, mode="select")
    try:
        txt = TextItem(TextAnnotationData(text="PUMP ROOM", x=-150.0, y=-80.0,
                                          height_mm=20.0)).to_dict()
        d = BlockDefinition.new(name="G", library="L", series="S",
                                origin=(0.0, 0.0),
                                primitives=[*_ring_prims(), txt])
        scene.register_block_definition(d)
        inst = scene.place_block_instance(d.id, (40.0, 20.0))
        inst.render_ops()                       # compile outside the timed hover
        on_ring = oracle(inst, 25.0 + _RING_R, 25.0)   # first ring's right-hand point
        t0 = time.perf_counter()
        hit = _hover(view, scene, on_ring)
        elapsed = time.perf_counter() - t0
        assert hit is inst
        # Measured 2026-11-11 (move + flushed repaint of 500 big rings): fixed
        # ~2.5 s (4.5 s on a loaded host), the old union 16.3-19 s.
        assert elapsed < 10.0, f"hover took {elapsed:.2f}s"             # [RED]
        box = d.text_snap_points()[0]
        assert _hover(view, scene, inst.full_pose_transform().map(box[8])) is inst
        # Off the block: 75 mm outside the nearest ring (centre (25, 265)).
        assert _hover(view, scene, oracle(inst, -150.0, 250.0)) is None
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("pose", _POSES, ids=_IDS)
def test_point_hit_where_a_stroke_crosses_the_text_box(qapp, pose):
    # S1 review I1/I2: shape() composes the stroke band and the area paths
    # without a union, so where a stroke crosses the text box their windings
    # can cancel (a mirrored pose flips one) and shape() reads a hole there.
    # Qt's point / pixel hit tests must still hit the block: they go through
    # BlockInstance.contains / collidesWithPath, which test each part.
    # Only the mirrored param can go RED (the plain pose's windings agree);
    # the plain param is the control.
    view, scene = make_view(role="plan", scale=1.0, mode="select")
    try:
        txt = TextItem(TextAnnotationData(text="AB", x=-150.0, y=-80.0,
                                          height_mm=20.0)).to_dict()
        probe = BlockDefinition.new(name="T", library="L", series="S",
                                    origin=(0.0, 0.0), primitives=[txt])
        c = probe.text_snap_points()[0][8]               # text box centre (local)
        line = {"type": "draw_line", "pt1": [c.x() - 120.0, c.y()],
                "pt2": [c.x() + 120.0, c.y()], "color": "#ffffff",
                "lineweight": 1.0}
        d = BlockDefinition.new(name="X", library="L", series="S",
                                origin=(0.0, 0.0), primitives=[line, txt])
        scene.register_block_definition(d)
        pos, rot, mir, s = pose
        inst = scene.place_block_instance(d.id, pos, rotation=rot,
                                          mirrored=mir, scale=s)
        box = d.text_snap_points()[0]
        cross = inst.full_pose_transform().map(box[8])   # on the line, in the box
        assert inst in scene.items(cross)                                # [RED]
        assert inst in view.items(view.mapFromScene(cross))              # [RED]
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("scale", [1.0, 0.1])
def test_qt_hit_test_reaches_the_stroke_band_outside_the_bounds(qapp, scale):
    # T5 review: Qt rejects by boundingRect before shape(); the strokes' ~5 px
    # half-band must fit inside at every zoom, like loose primitives. The
    # selection frame (manip_bounds) must not grow with it.
    from PyQt6.QtCore import QPoint
    view, scene = make_view(role="plan", scale=scale, mode="select")
    try:
        d = BlockDefinition.new(name="E", library="L", series="S",
                                origin=(0.0, 0.0), primitives=list(_PRIMS[:1]))
        scene.register_block_definition(d)
        inst = scene.place_block_instance(d.id, (40.0, 20.0))
        frame = inst.manip_bounds()
        edge = view.mapFromScene(oracle(inst, 180.0, 0.0))     # right edge
        probe = QPoint(edge.x() + 3, edge.y())                  # 3 px outside
        assert inst in view.items(probe)                                # [RED]
        assert inst not in view.items(QPoint(edge.x() + 12, edge.y()))
        # The frame is the geometry + 2 mm at every zoom (never the band).
        assert abs(frame.right() - (oracle(inst, 180.0, 0.0).x() + 2.0)) < 1e-6
    finally:
        close_view(view, scene)
