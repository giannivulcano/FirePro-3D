"""CS5 smoke round 1 guards -- parametric-constraint-system D82 (dims show on
selection), D83 (angle extensions run to the vertex), D84 (angle radius
placement + drag). Real Block Editor scenes and a shown Model_View."""
import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d import constraint_dims as cd
from firepro3d import constraint_paint as cp
from firepro3d.geometry_2d import ArcItem, LineItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.scale_manager import ScaleManager


def R(it, h="edge"):
    return {"uid": it._uid, "h": h}


def _add(sc, it, lst="_draw_lines"):
    sc.addItem(it); getattr(sc, lst).append(it); return it


@pytest.fixture
def be(qapp):
    sc = Model_Space(scene_role="block_editor")
    sc.scale_manager = ScaleManager()
    v = Model_View(sc)
    v.resize(800, 600)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.resetTransform()
    v.centerOn(100, 0)
    sc.set_mode("select")
    QApplication.processEvents()
    yield v, sc
    sc.readouts.cancel_edit()
    sc.clearSelection()
    sc.cleanup()
    v.close()
    v.deleteLater()
    QApplication.processEvents()


def _pair(sc):
    l1 = _add(sc, LineItem(QPointF(0, 0), QPointF(150, 0)))
    l2 = _add(sc, LineItem(QPointF(0, 0), QPointF(75, -129.9038105677)))   # 60 deg
    return l1, l2, [R(l1), R(l2)]


def _placed_angle(sc, at=QPointF(60, -20)):
    l1, l2, refs = _pair(sc)
    ctl = sc.constraint_ctl
    h, lab = cd.placement_for(ctl, "dim_angle", refs, at)
    return l1, l2, ctl.add("dim_angle", refs, helper=h, label=lab)


def _r80():
    return QPointF(80 * math.cos(0.5), -80 * math.sin(0.5))


# -- D82: dims show on selection ----------------------------------------------

def _frame_ids(v, ctl):
    return [e.cid for e in cp._frame(v, ctl).dims]


def test_d82_dim_hidden_until_its_geometry_is_selected(be):
    v, sc = be; ctl = sc.constraint_ctl
    l1, l2, c = _placed_angle(sc)
    sc.clearSelection(); QApplication.processEvents()
    (full,) = cd.dim_entries(v, ctl)                  # layout of the dim, shown or not
    at = full.layout.center
    assert _frame_ids(v, ctl) == [] and cp.dim_at(v, ctl, at) is None
    assert cp.glyph_at(v, ctl, at) is None
    l1.setSelected(True)
    assert _frame_ids(v, ctl) == [c.id] and cp.dim_at(v, ctl, at) == c.id
    sc.clearSelection()
    assert _frame_ids(v, ctl) == [] and cp.dim_at(v, ctl, at) is None


def test_d82_unrelated_selection_keeps_it_hidden(be):
    v, sc = be; ctl = sc.constraint_ctl
    _placed_angle(sc)
    other = _add(sc, LineItem(QPointF(0, 300), QPointF(100, 300)))
    sc.clearSelection(); other.setSelected(True)
    assert _frame_ids(v, ctl) == []


def test_d82_selected_dim_itself_shows(be):
    v, sc = be; ctl = sc.constraint_ctl
    _l1, _l2, c = _placed_angle(sc)
    sc.clearSelection()
    ctl.selected_id = c.id
    assert _frame_ids(v, ctl) == [c.id]


def test_d82_show_constraints_shows_every_dim(be):
    v, sc = be; ctl = sc.constraint_ctl
    _l1, _l2, c = _placed_angle(sc)
    sc.clearSelection()
    assert _frame_ids(v, ctl) == []
    ctl.show_all = True
    assert _frame_ids(v, ctl) == [c.id]
    ctl.show_all = False
    assert _frame_ids(v, ctl) == []


def test_d82_smart_dimension_tool_live_shows_every_dim(be):
    v, sc = be; ctl = sc.constraint_ctl
    _l1, _l2, c = _placed_angle(sc)
    sc.clearSelection()
    assert _frame_ids(v, ctl) == []
    sc.set_mode("constrain_dim_distance")
    assert ctl.pick is not None and ctl.pick.ctype == "dim_distance"
    assert _frame_ids(v, ctl) == [c.id]
    sc.set_mode("select")
    assert _frame_ids(v, ctl) == []


def test_d82_ground_ref_dim_follows_its_item_ref(be):
    v, sc = be; ctl = sc.constraint_ctl
    ln = _add(sc, LineItem(QPointF(40, -40), QPointF(140, -140)))
    refs = [R(ln), {"ref": "x_axis"}]
    h, lab = cd.placement_for(ctl, "dim_angle", refs, QPointF(200, -30))
    c = ctl.add("dim_angle", refs, helper=h, label=lab)
    sc.clearSelection()
    assert _frame_ids(v, ctl) == []
    ln.setSelected(True)
    assert _frame_ids(v, ctl) == [c.id]


def test_d82_selection_change_repaints_the_viewport(be):
    v, sc = be; ctl = sc.constraint_ctl
    l1, _l2, _c = _placed_angle(sc)
    sc.clearSelection(); QApplication.processEvents()
    seen = []
    orig = ctl._repaint
    ctl._repaint = lambda: (seen.append(1), orig())
    l1.setSelected(True)
    assert seen


# -- D83: extensions to the vertex ---------------------------------------------

def _off_vertex(sc, v, cursor_deg):
    V = QPointF(0, -70)

    def up(r, deg):
        a = math.radians(deg)
        return QPointF(V.x() + r * math.cos(a), V.y() - r * math.sin(a))
    la = _add(sc, LineItem(up(140, 220), up(200, 220)))
    lb = _add(sc, LineItem(up(40, 320), up(90, 320)))
    ctl = sc.constraint_ctl
    refs = [R(la), R(lb)]
    h, _ = cd.placement_for(ctl, "dim_angle", refs, up(100, cursor_deg))
    c = ctl.add("dim_angle", refs, helper=h)
    return up, V, cd.entry_for(v, ctl, c)


def test_d83_missed_segment_extends_from_its_near_end_to_the_vertex(be):
    v, sc = be
    up, V, e = _off_vertex(sc, v, 270)
    (C, r, _st, _sp), = e.graphic.arcs
    vp = v.viewportTransform()
    Vp, A1 = vp.map(V), vp.map(up(140, 220))
    s, t = e.graphic.dashed[0]
    assert (s.x(), s.y()) == pytest.approx((A1.x(), A1.y()), abs=0.6)
    assert (t.x(), t.y()) == pytest.approx((Vp.x(), Vp.y()), abs=0.6)
    assert math.hypot(s.x() - C.x(), s.y() - C.y()) > r > 0     # passes through the arc


def _segments_cover_vertex_to_arc(v, V, up, deg, seg, e):
    """Every point of the arm from the vertex to the arc lies on the segment
    or on a dashed run (sampled at 2 px)."""
    (C, r, _st, _sp), = e.graphic.arcs
    vp = v.viewportTransform()
    a, b = vp.map(up(seg[0], deg)), vp.map(up(seg[1], deg))
    Vp = vp.map(V)
    ux, uy = (a.x() - Vp.x()), (a.y() - Vp.y())
    n = math.hypot(ux, uy); ux, uy = ux / n, uy / n

    def on(p, s, t):
        dx, dy = t.x() - s.x(), t.y() - s.y()
        L2 = dx * dx + dy * dy
        k = ((p[0] - s.x()) * dx + (p[1] - s.y()) * dy) / L2
        q = (s.x() + k * dx, s.y() + k * dy)
        return -0.02 <= k <= 1.02 and math.hypot(p[0] - q[0], p[1] - q[1]) < 0.6
    runs = [(a, b)] + list(e.graphic.dashed)
    for i in range(1, int(r // 2)):
        p = (Vp.x() + ux * 2 * i, Vp.y() + uy * 2 * i)
        assert any(on(p, s, t) for s, t in runs), f"gap at {2 * i} px from the vertex"


def test_d83_near_side_segment_short_of_a_dragged_arc_is_bridged_both_ways(be):
    """Edge B (40..90 mm from the vertex) inside an arc dragged out to 150 mm:
    dashes fill vertex..40 and 90..150 (smoke 2026-10-14)."""
    v, sc = be
    up, V, _e = _off_vertex(sc, v, 270)
    ctl = sc.constraint_ctl
    (c,) = [k for k in ctl.constraints if k.type == "dim_angle"]
    c.label = {"radius": 150.0}
    e = cd.entry_for(v, ctl, c)
    _segments_cover_vertex_to_arc(v, V, up, 320, (40, 90), e)
    _segments_cover_vertex_to_arc(v, V, up, 220, (140, 200), e)


def test_d83_segment_reaching_the_arc_still_runs_to_the_vertex(be):
    """Edge A (140..200 mm) with the arc dragged to 170 mm: the segment meets
    the arc, and a dash still bridges vertex..140."""
    v, sc = be
    up, V, _e = _off_vertex(sc, v, 270)
    ctl = sc.constraint_ctl
    (c,) = [k for k in ctl.constraints if k.type == "dim_angle"]
    c.label = {"radius": 170.0}
    e = cd.entry_for(v, ctl, c)
    _segments_cover_vertex_to_arc(v, V, up, 220, (140, 200), e)


def test_d83_opposite_side_segment_runs_through_the_vertex_to_the_arc(be):
    """Cursor on the 40 deg side: edge A (at 220 deg) lies behind the vertex,
    the dashed line goes from its near end through the vertex to the arc."""
    v, sc = be
    up, V, e = _off_vertex(sc, v, 40)
    (C, r, _st, _sp), = e.graphic.arcs
    vp = v.viewportTransform()
    A1, Vp = vp.map(up(140, 220)), vp.map(V)
    mine = [(s, t) for s, t in e.graphic.dashed
            if (s.x(), s.y()) == pytest.approx((A1.x(), A1.y()), abs=0.6)]
    assert len(mine) == 1
    s, t = mine[0]
    assert math.hypot(t.x() - C.x(), t.y() - C.y()) == pytest.approx(r, abs=0.6)
    # the vertex lies on the dashed run, between its ends
    ux, uy = t.x() - s.x(), t.y() - s.y()
    k = ((Vp.x() - s.x()) * ux + (Vp.y() - s.y()) * uy) / (ux * ux + uy * uy)
    assert 0.0 < k < 1.0
    assert math.hypot(s.x() + k * ux - Vp.x(), s.y() + k * uy - Vp.y()) < 0.6


# -- D84: radius placement + drag ----------------------------------------------

def test_d84_placement_stores_the_cursor_radius_and_draws_it(be):
    v, sc = be; ctl = sc.constraint_ctl
    l1, l2, refs = _pair(sc)
    h, lab = cd.placement_for(ctl, "dim_angle", refs, _r80())
    assert lab == {"radius": pytest.approx(80.0)}
    c = ctl.add("dim_angle", refs, helper=h, label=lab)
    assert c.label["radius"] == pytest.approx(80.0)
    e = cd.entry_for(v, ctl, c)
    (_C, r, _st, _sp), = e.graphic.arcs
    assert r == pytest.approx(80.0 * v.viewportTransform().m11(), abs=1e-6)


def test_d84_no_radius_is_auto(be):
    v, sc = be; ctl = sc.constraint_ctl
    l1, l2, refs = _pair(sc)
    h, _ = cd.placement_for(ctl, "dim_angle", refs, QPointF(60, -20))
    c = ctl.add("dim_angle", refs, helper=h)               # a record without label.radius
    e = cd.entry_for(v, ctl, c)
    (_C, r, _st, _sp), = e.graphic.arcs
    assert r == pytest.approx(max(25.0, 0.19 * 150.0), abs=1e-6)      # D75 readout rule


def test_d84_drag_changes_radius_and_sector_in_one_undo_step(be):
    v, sc = be; ctl = sc.constraint_ctl
    l1, l2, c = _placed_angle(sc)
    r0, h0 = c.label["radius"], dict(c.helper)
    n = len(sc._undo_stack)
    assert ctl.drag_dim_to_scene(c.id, QPointF(-120, -40))
    assert c.label["radius"] == pytest.approx(math.hypot(120, 40))
    assert c.label["radius"] != pytest.approx(r0) and c.helper != h0
    assert c.value == pytest.approx(120.0, abs=1e-6)
    assert ctl.end_dim_drag()
    assert len(sc._undo_stack) == n + 1


def test_d84_cancel_drag_restores_the_radius(be):
    v, sc = be; ctl = sc.constraint_ctl
    l1, l2, c = _placed_angle(sc)
    r0 = c.label["radius"]
    assert ctl.drag_dim_to_scene(c.id, QPointF(200, -60))
    assert c.label["radius"] != pytest.approx(r0)
    assert ctl.cancel_dim_drag()
    assert c.label["radius"] == pytest.approx(r0)


def _sweep(sc, at):
    a = _add(sc, ArcItem(QPointF(0, 0), 80, 20, 120), "_draw_arcs")
    ctl = sc.constraint_ctl
    h, lab = cd.placement_for(ctl, "dim_arc_angle", [R(a, "curve")], at)
    return a, ctl.add("dim_arc_angle", [R(a, "curve")], helper=h or None, label=lab)


def test_d84_arc_sweep_places_and_drags_in_radius(be):
    v, sc = be
    a, c = _sweep(sc, QPointF(0, -40))
    ctl = sc.constraint_ctl
    assert c.label["radius"] == pytest.approx(40.0)
    e = cd.entry_for(v, ctl, c)
    assert e.graphic.arcs[0][1] == pytest.approx(40.0 * v.viewportTransform().m11())
    ctl.begin_dim_drag(c.id, QPointF(0, 0))
    assert ctl.dim_drag is not None                       # the sweep is draggable now
    n = len(sc._undo_stack)
    assert ctl.drag_dim_to_scene(c.id, QPointF(0, -100))
    assert c.label["radius"] == pytest.approx(100.0)
    assert c.value == pytest.approx(120.0)                # geometry never moves
    assert ctl.end_dim_drag() and len(sc._undo_stack) == n + 1


def test_d84_scale_tool_scales_the_radius_but_rotate_and_flip_do_not(be):
    from firepro3d.axis_picker import AxisPick
    v, sc = be; ctl = sc.constraint_ctl
    l1, l2, c = _placed_angle(sc, _r80())
    assert c.label["radius"] == pytest.approx(80.0)
    sc._selected_items = [l1, l2]
    sc._rotate_pivot = QPointF(0, 0)
    assert sc._modify_ctl.commit_rotate(90.0) is True
    assert c.label["radius"] == pytest.approx(80.0)
    rl = LineItem(QPointF(-500, 10), QPointF(800, 10)); rl.reference = True
    _add(sc, rl)
    sc.mode = "flip"
    sc._selected_items = [l1, l2]
    sc._mirror_axis = AxisPick(QPointF(-500, 10), QPointF(800, 10), rl, 0.0)
    assert sc._modify_ctl.commit_reflect() is True
    assert c.label["radius"] == pytest.approx(80.0)
    sc._selected_items = [l1, l2]
    sc._scale_base = QPointF(0, 0)
    assert sc._modify_ctl.commit_scale(2.0) is True
    assert c.label["radius"] == pytest.approx(160.0)


def test_d84_mirror_copy_keeps_the_radius(qapp):
    from tests.test_constraint_cs5_controller import _flip, _mirror_copy
    sc = Model_Space(scene_role="block_editor")
    l1, l2, c = _placed_angle(sc, _r80())
    ctl = sc.constraint_ctl

    def copies():
        return [_add(sc, LineItem(_flip(s._pt1), _flip(s._pt2))) for s in (l1, l2)]
    (new,) = _mirror_copy(sc, ctl, [l1, l2], copies)
    assert new.label["radius"] == pytest.approx(80.0) and new.id != c.id


def test_d84_radius_round_trips_save_reopen(qapp):
    sc = Model_Space(scene_role="block_editor")
    _placed_angle(sc, _r80())
    ctl = sc.constraint_ctl
    recs = ctl.to_records()
    ctl.load(recs)
    (d,) = ctl.constraints
    assert d.label == {"radius": pytest.approx(80.0)}
    assert not d.inert
