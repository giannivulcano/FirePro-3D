"""SectionMarker guards: dict round-trip, cardinal seed, auto-extent, PAPER_EXCLUDED."""
import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.section_marker import (SectionMarker, building_bbox, cardinal_cut,
                                      CROP_MARGIN, FALLBACK_HALF)


def test_to_dict_round_trip_all_fields():
    m = SectionMarker("Section 7", QPointF(100.0, 200.0), QPointF(900.0, 650.0),
                      look_sign=-1, depth=3200.0)
    m.gridline_z_overrides["A"] = {"v_top": -5000.0, "v_bot": 500.0}
    d = m.to_dict()
    assert d == {"name": "Section 7", "cut_a": [100.0, 200.0], "cut_b": [900.0, 650.0],
                 "look_sign": -1, "depth": 3200.0, "cardinal": None,
                 "auto_extent": False,
                 "gridline_z_overrides": {"A": {"v_top": -5000.0, "v_bot": 500.0}}}
    m2 = SectionMarker.from_dict(d)
    assert m2.to_dict() == d


def test_cardinal_cut_scene_coordinates_match_basis_table():
    box = QRectF(-10000.0, -5000.0, 20000.0, 10000.0)   # scene: top = -5000 = world y_max
    assert cardinal_cut("north", box) == ((10000.0, -5000.0), (-10000.0, -5000.0), 10000.0)
    assert cardinal_cut("south", box) == ((-10000.0, 5000.0), (10000.0, 5000.0), 10000.0)
    assert cardinal_cut("east", box) == ((10000.0, 5000.0), (10000.0, -5000.0), 20000.0)
    assert cardinal_cut("west", box) == ((-10000.0, -5000.0), (-10000.0, 5000.0), 20000.0)


def test_building_bbox_unions_gridlines_and_items_with_fallback(qapp):
    from firepro3d.model_space import Model_Space
    from firepro3d.gridline import GridlineItem
    from firepro3d.wall import WallSegment
    ms = Model_Space()
    assert building_bbox(ms) == QRectF(-FALLBACK_HALF - CROP_MARGIN, -FALLBACK_HALF - CROP_MARGIN,
                                       2 * (FALLBACK_HALF + CROP_MARGIN), 2 * (FALLBACK_HALF + CROP_MARGIN))
    gl = GridlineItem(QPointF(-1200.0, 500.0), QPointF(1200.0, 500.0), label="A")
    ms._gridlines.append(gl); ms.addItem(gl)
    w = WallSegment(QPointF(0.0, 0.0), QPointF(4000.0, 0.0))
    ms._walls.append(w); ms.addItem(w)
    bb = building_bbox(ms)
    raw = gl.sceneBoundingRect().united(w.sceneBoundingRect())
    assert bb == raw.adjusted(-CROP_MARGIN, -CROP_MARGIN, CROP_MARGIN, CROP_MARGIN)


def test_marker_scene_units_convert_to_world_mm_at_ppm_2(qapp, section_scene_for):
    """Marker geometry is plan-scene units; at ppm 2 the basis is world mm."""
    from firepro3d.section_scene import SectionScene
    ms, _ = section_scene_for("south")
    ms.scale_manager.set_pixels_per_mm(2.0)
    assert ms.scale_manager.is_calibrated
    m = SectionMarker("S", QPointF(0.0, 0.0), QPointF(4000.0, 0.0), 1, 4000.0)
    sec = SectionScene(m, ms, ms._level_manager, ms.scale_manager)
    assert sec.basis.depth == 2000.0
    wx, wy = sec._scene_to_world(2000.0, 0.0)
    assert sec.basis.h(wx, wy) == pytest.approx(1000.0)     # D = +x: h = wx


def test_paper_excluded_only_on_cardinals():
    c = SectionMarker.for_cardinal("north", QRectF(-100.0, -100.0, 200.0, 200.0))
    p = SectionMarker("Section 1", QPointF(0.0, 0.0), QPointF(1000.0, 0.0))
    assert c.PAPER_EXCLUDED is True and c.cardinal == "north" and c.auto_extent is True
    assert p.PAPER_EXCLUDED is False and p.cardinal is None and p.auto_extent is False


# -- Task 8: visuals, grips, flip, menu, properties --------------------------------

class _Mgr:
    """Stub of the SectionManager surface the marker calls."""
    def __init__(self):
        self.calls = []
    def open_section(self, name): self.calls.append(("open", name))
    def rename_section(self, old, new): self.calls.append(("rename", old, new))
    def delete_section(self, name): self.calls.append(("delete", name))
    def on_marker_geometry_changed(self, marker): self.calls.append(("geom", marker.name))


def _plan_with_marker(cardinal=None):
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    if cardinal:
        m = SectionMarker.for_cardinal(cardinal, QRectF(-5000.0, -5000.0, 10000.0, 10000.0))
    else:
        m = SectionMarker("Section 1", QPointF(0.0, 0.0), QPointF(6000.0, 0.0), 1, 3000.0)
    m._manager = _Mgr()
    ms.addItem(m)
    return ms, m


def test_grip_points_are_the_rect_layout_plus_flip(qapp):
    ms, m = _plan_with_marker()
    pts = m.grip_points()
    assert len(pts) == 9
    # A=(0,0) B=(6000,0) depth 3000, look side = scene-up (normal (0,-1)).
    assert pts[0] == QPointF(0.0, 0.0) and pts[1] == QPointF(6000.0, 0.0)
    assert pts[2] == QPointF(6000.0, -3000.0) and pts[3] == QPointF(0.0, -3000.0)   # far corners
    assert pts[4] == QPointF(3000.0, 0.0)                                            # near (cut) mid
    assert pts[5] == QPointF(6000.0, -1500.0) and pts[7] == QPointF(0.0, -1500.0)   # side mids
    assert pts[SectionMarker.GRIP_DEPTH] == QPointF(3000.0, -3000.0)                # far mid
    _ms2, shallow = _plan_with_marker()
    shallow.set_geometry(QPointF(0.0, 0.0), QPointF(6000.0, 0.0), 400.0)
    sp = shallow.grip_points()                         # depth < 2R: flip grip must not sit on the depth grip
    assert abs(sp[SectionMarker.GRIP_FLIP].y()) < abs(sp[SectionMarker.GRIP_DEPTH].y())


def test_corner_grips_keep_the_opposite_corner_fixed(qapp):
    ms, m = _plan_with_marker()
    m.apply_grip(1, QPointF(7000.0, 1000.0))           # near-right corner: B along the cut, cut line moves, far edge stays
    assert m.cut_a == QPointF(0.0, 1000.0) and m.cut_b == QPointF(7000.0, 1000.0)
    assert m.depth == pytest.approx(4000.0)
    assert m.grip_points()[3] == QPointF(0.0, -3000.0)
    assert ("geom", "Section 1") in m._manager.calls
    ms, m = _plan_with_marker()
    m.apply_grip(3, QPointF(-500.0, -2000.0))          # far-left corner: A along the cut, depth shrinks, B corner fixed
    assert m.cut_a == QPointF(-500.0, 0.0) and m.cut_b == QPointF(6000.0, 0.0)
    assert m.depth == pytest.approx(2000.0)
    assert m.grip_points()[1] == QPointF(6000.0, 0.0)


def test_edge_mid_grips_move_one_edge_only(qapp):
    ms, m = _plan_with_marker()
    m.apply_grip(7, QPointF(-1000.0, -900.0))          # A edge mid: A slides along the cut; the normal component is ignored
    assert m.cut_a == QPointF(-1000.0, 0.0) and m.cut_b == QPointF(6000.0, 0.0) and m.depth == 3000.0
    m.apply_grip(4, QPointF(5000.0, 1000.0))           # near mid: the cut line moves, far edge fixed
    assert m.cut_a == QPointF(-1000.0, 1000.0) and m.cut_b == QPointF(6000.0, 1000.0)
    assert m.depth == pytest.approx(4000.0)
    m.apply_grip(4, QPointF(5000.0, -9000.0))          # dragged past the far edge: clamped to the minimum depth
    assert m.depth == pytest.approx(100.0)
    assert m.cut_a.y() == pytest.approx(-2900.0)


def test_depth_grip_is_constrained_along_normal(qapp):
    ms, m = _plan_with_marker()
    m.apply_grip(SectionMarker.GRIP_DEPTH, QPointF(4500.0, -5000.0))   # off-axis drag: only the normal component counts
    assert m.depth == pytest.approx(5000.0)
    assert m.cut_a == QPointF(0.0, 0.0) and m.cut_b == QPointF(6000.0, 0.0)
    m.apply_grip(SectionMarker.GRIP_DEPTH, QPointF(4500.0, 2000.0))    # dragged through the cut line: clamped to the minimum
    assert m.depth == pytest.approx(100.0)


def test_flip_grip_toggles_look_sign_one_undo_step(qapp):
    from firepro3d.manip_handle import FlipGripHandle
    ms, m = _plan_with_marker()
    handles = m.manip_handles()
    flip = [h for h in handles if isinstance(h, FlipGripHandle)]
    assert len(flip) == 1 and flip[0].index == SectionMarker.GRIP_FLIP
    pushes = []
    class _M:                                            # minimal manipulator surface
        _moved = False
        def scene(self): return ms
        def _end_drag(self): pass
        _commit_hook = staticmethod(lambda mode: pushes.append(mode))
    flip[0].on_press(_M())
    flip[0].on_release(_M(), QPointF(0.0, 0.0), 0)
    assert m.look_sign == -1 and pushes == ["grip"]
    assert m.grip_points()[SectionMarker.GRIP_DEPTH] == QPointF(3000.0, 3000.0)   # far edge now on the other side


def test_cardinal_grip_clears_auto_extent(qapp):
    ms, m = _plan_with_marker("north")
    assert m.auto_extent
    m.apply_grip(SectionMarker.GRIP_DEPTH, m.grip_points()[SectionMarker.GRIP_DEPTH] + QPointF(0.0, 500.0))
    assert m.auto_extent is False


def test_manip_translate_moves_line_and_box(qapp):
    ms, m = _plan_with_marker()
    m.manip_translate(100.0, -50.0)
    assert m.cut_a == QPointF(100.0, -50.0) and m.cut_b == QPointF(6100.0, -50.0)
    assert m.manip_bounds() == m.box_polygon().boundingRect()


def test_double_click_emits_open_view_requested(qapp):
    class _Ev:                                   # QGraphicsSceneMouseEvent cannot be instantiated from Python
        def accept(self): pass
    got = []
    ms, m = _plan_with_marker()
    ms.openViewRequested.connect(lambda t, n: got.append((t, n)))
    ev = _Ev()
    m.mouseDoubleClickEvent(ev)
    assert got == [("section", "Section 1")]
    ms2, c = _plan_with_marker("north")
    ms2.openViewRequested.connect(lambda t, n: got.append((t, n)))
    c.mouseDoubleClickEvent(ev)
    assert got[-1] == ("elevation", "north")


def test_cardinal_menu_disables_rename_delete(qapp):
    ms, m = _plan_with_marker("north")
    menu = m.build_context_menu()
    acts = {a.text(): a for a in menu.actions()}
    assert set(acts) == {"Open", "Rename", "Flip", "Delete"}
    assert not acts["Rename"].isEnabled() and not acts["Delete"].isEnabled()
    assert acts["Open"].isEnabled() and acts["Flip"].isEnabled()
    ms2, p = _plan_with_marker()
    menu2 = p.build_context_menu()               # keep a ref: actions die with the menu
    acts2 = {a.text(): a for a in menu2.actions()}
    assert all(a.isEnabled() for a in acts2.values())
    acts2["Delete"].trigger()
    assert ("delete", "Section 1") in p._manager.calls
    acts2["Open"].trigger()
    assert ("open", "Section 1") in p._manager.calls


def test_marker_visible_on_every_level(qapp):
    from firepro3d.level_manager import LevelManager
    ms, m = _plan_with_marker()
    lm = LevelManager(); lm.add_level("Level 2", 3500.0)
    ms._level_manager = lm
    lm.apply_to_scene(ms, active_level="Level 2")
    assert m.isVisible()
    lm.apply_to_scene(ms, active_level="Level 1")
    assert m.isVisible()


def test_marker_shape_covers_line_bubbles_and_box_edge_only_when_selected(qapp):
    ms, m = _plan_with_marker()
    assert m.shape().contains(QPointF(3000.0, 0.0))          # on the cut line
    assert not m.shape().contains(QPointF(3000.0, -1500.0))  # inside the box, unselected: not hittable
    m.setSelected(True)
    assert m.shape().contains(QPointF(3000.0, -3000.0))      # far edge, selected


def test_get_properties_and_set_property(qapp):
    ms, m = _plan_with_marker()
    props = m.get_properties()
    assert props["Name"]["value"] == "Section 1"
    assert props["Cardinal"]["readonly"] is True and props["Cardinal"]["value"] == "-"
    assert props["Flip"]["type"] == "bool" and props["Flip"]["value"] is False
    m.set_property("Depth", "4500")
    assert m.depth == pytest.approx(4500.0)
    m.set_property("Flip", True)
    assert m.look_sign == -1
    m.set_property("Name", "Stair")
    assert ("rename", "Section 1", "Stair") in m._manager.calls


def test_depth_property_parses_units_and_ignores_garbage(qapp):
    from firepro3d.scale_manager import ScaleManager
    ms, m = _plan_with_marker()
    m.set_property("Depth", "4.5 m")
    assert m.depth == pytest.approx(4500.0)
    ft = ScaleManager.parse_dimension("14'-9\"")
    assert ft is not None
    m.set_property("Depth", "14'-9\"")
    assert m.depth == pytest.approx(ft)
    assert m.depth == pytest.approx(4495.8, abs=0.1)
    m.set_property("Depth", "garbage")
    assert m.depth == pytest.approx(ft)


def _render_box_region(ms) -> str:
    """Rasterize the marker's whole crop-box region (10 units/px); return a digest of the pixels."""
    import hashlib
    from PyQt6.QtGui import QImage, QPainter
    img = QImage(700, 700, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, 700, 700), QRectF(-500.0, -3500.0, 7000.0, 7000.0))
    p.end()
    return hashlib.sha256(bytes(img.constBits().asarray(img.sizeInBytes()))).hexdigest()


def test_selected_crop_box_draws_on_canvas_but_never_in_a_paper_pass(qapp):
    """VC9 M4: the paper pass does not clear selection, so a marker selected on the
    plan must not plot its dashed crop box into a sheet viewport / PDF."""
    from firepro3d.paper_display import apply_paper_overrides, restore_model_display
    ms, m = _plan_with_marker()
    ms.setSceneRect(QRectF(-20000, -20000, 40000, 40000))
    m.setSelected(False)
    canvas_plain = _render_box_region(ms)
    m.setSelected(True)
    canvas_selected = _render_box_region(ms)
    assert canvas_selected != canvas_plain                 # selection chrome draws on canvas
    saved = apply_paper_overrides(ms, QRectF(-20000, -20000, 40000, 40000))
    try:
        paper_selected = _render_box_region(ms)
        m.setSelected(False)
        paper_plain = _render_box_region(ms)
    finally:
        restore_model_display(saved)
    assert paper_selected == paper_plain                   # no crop box / highlight on paper


# -- glyph geometry (smoke ruling 2026-10-21, D6r) ------------------------------------

def _dist_point_line(p, a, b):
    import math
    dx, dy = b.x() - a.x(), b.y() - a.y()
    return abs(dy * (p.x() - a.x()) - dx * (p.y() - a.y())) / math.hypot(dx, dy)


def test_section_head_triangle_is_tangent_to_the_bubble_apex_on_the_look_side(qapp):
    from firepro3d.gridline import BUBBLE_RADIUS_MM
    ms, m = _plan_with_marker()                        # A(0,0) B(6000,0), look side = scene-up
    R = 2.0 * BUBBLE_RADIUS_MM
    for end in (m.cut_a, m.cut_b):
        tri = m._head_polygon(end)
        p0, apex, p1 = tri[0], tri[1], tri[2]
        assert p0.y() == pytest.approx(end.y()) and p1.y() == pytest.approx(end.y())   # base on the cut line
        assert apex.y() < end.y()                                                        # apex on the look side
        for a, b in ((p0, apex), (apex, p1)):                                            # sides tangent to the circle
            assert _dist_point_line(end, a, b) == pytest.approx(R, rel=1e-9)
        stick_side = abs(p0.x() - end.x()) - R
        stick_front = abs(apex.y() - end.y()) - R
        assert stick_side == pytest.approx(stick_front)                                  # equal stick-out
    m.flip()
    assert m._head_polygon(m.cut_a)[1].y() > 0.0                                         # apex follows the flip


def test_cardinal_glyph_tip_sits_25mm_outside_its_own_box_edge(qapp):
    from PyQt6.QtCore import QRectF
    from firepro3d.gridline import BUBBLE_RADIUS_MM
    import math
    box = QRectF(-2000.0, -1000.0, 16000.0, 12000.0)
    for d, tip_expected, outward in (
            ("north", QPointF(6000.0, -1025.0), (0.0, -1.0)),
            ("south", QPointF(6000.0, 11025.0), (0.0, 1.0)),
            ("east", QPointF(14025.0, 5000.0), (1.0, 0.0)),
            ("west", QPointF(-2025.0, 5000.0), (-1.0, 0.0))):
        m = SectionMarker.for_cardinal(d, box)
        c, _t1, _t2, tip, _a2, _sw = m._wedge_geometry()
        assert tip.x() == pytest.approx(tip_expected.x()) and tip.y() == pytest.approx(tip_expected.y()), d
        D = 3.0 * BUBBLE_RADIUS_MM / math.sin(math.radians(40))
        assert c.x() == pytest.approx(tip.x() + outward[0] * D) and c.y() == pytest.approx(tip.y() + outward[1] * D), d
        assert m._R == pytest.approx(3.0 * BUBBLE_RADIUS_MM)


def test_label_angle_reads_along_the_cut_and_never_upside_down(qapp):
    ms, m = _plan_with_marker()
    for a, b, want in (((0, 0), (6000, 0), 0.0), ((6000, 0), (0, 0), 0.0),        # rightward / leftward
                       ((0, 0), (3000, 3000), 45.0), ((3000, 3000), (0, 0), 45.0),
                       ((0, 0), (0, -4000), -90.0), ((0, 0), (0, 4000), -90.0)):  # exactly vertical, both signs
        m.set_geometry(QPointF(*a), QPointF(*b), 3000.0)
        assert m._label_angle() % 360.0 == pytest.approx(want % 360.0), (a, b)


def test_shape_covers_the_drawn_glyphs(qapp):
    ms, m = _plan_with_marker()
    sh = m.shape()
    assert sh.contains(m._head_polygon(m.cut_b)[1] + QPointF(0.0, 5.0))      # just inside the apex
    assert sh.contains(QPointF(3000.0, 0.0))                                  # a cut-line point
    from PyQt6.QtCore import QRectF
    c = SectionMarker.for_cardinal("north", QRectF(0.0, 0.0, 6000.0, 6000.0))
    _c, _t1, _t2, tip, _a2, _sw = c._wedge_geometry()
    assert c.shape().contains(tip + QPointF(0.0, -5.0))                       # just inside the wedge tip
    assert c.shape().contains(_c)
    assert not c.shape().contains(QPointF(3000.0, 3000.0))                    # box interior never hittable
    for it in (m, c):
        assert it.boundingRect().contains(it.shape().boundingRect())


def test_grip_ends_never_cross_and_bad_indices_are_no_ops(qapp):
    ms, m = _plan_with_marker()
    m.apply_grip(0, QPointF(9000.0, 0.0))              # A dragged past B: refused, look side kept
    assert m.cut_a == QPointF(0.0, 0.0) and m.normal_scene() == pytest.approx((0.0, -1.0))
    m.apply_grip(5, QPointF(-9000.0, -1500.0))         # B dragged past A: refused
    assert m.cut_b == QPointF(6000.0, 0.0)
    m.apply_grip(1, QPointF(50.0, 0.0))                # shorter than MIN_CUT_LEN: refused
    assert m.cut_b == QPointF(6000.0, 0.0)
    for idx in (SectionMarker.GRIP_FLIP, 9, -1):
        m.apply_grip(idx, QPointF(123.0, 456.0))
    assert (m.cut_a, m.cut_b, m.depth, m.look_sign) == (QPointF(0.0, 0.0), QPointF(6000.0, 0.0), 3000.0, 1)
