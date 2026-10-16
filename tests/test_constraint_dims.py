"""CS4 Smart Dimension — headless guards (parametric-constraint-system D48–D55).

Real ``Model_Space(scene_role="block_editor")`` scenes and primitives."""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import constraint_dims as cd
from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.model_space import Model_Space


def _scene():
    return Model_Space(scene_role="block_editor")


def _line(sc, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b))
    sc.addItem(ln); sc._draw_lines.append(ln)
    return ln


def _rect(sc, a, b):
    r = RectangleItem(QPointF(*a), QPointF(*b))
    sc.addItem(r); sc._draw_rects.append(r)
    return r


def _len(ln):
    return math.hypot(ln._pt2.x() - ln._pt1.x(), ln._pt2.y() - ln._pt1.y())


def E(it, h="edge"):
    return {"uid": it._uid, "h": h}


# ── Task 3: dim <-> readout mapping ─────────────────────────────────────────

def test_readout_key_maps_edges_to_their_readouts(qapp):
    sc = _scene()
    ln = _line(sc, (0, 0), (300, 0))
    r = _rect(sc, (0, 0), (400, 200))
    assert cd.readout_key(ln, "edge") == "length"
    assert cd.readout_key(r, "top") == cd.readout_key(r, "bottom") == "width"
    assert cd.readout_key(r, "left") == cd.readout_key(r, "right") == "height"
    assert cd.readout_key(ln, "p1") is None


# ── Task 4: controller core (D50, D52-D55) ──────────────────────────────────

def test_add_takes_the_current_length_and_holds_it_on_an_edit(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    assert c is not None and c.driving and c.value == pytest.approx(300.0)
    with ctl.edit([ln]):                          # an untyped (transform-style) edit
        ln.set_length(500.0)
    assert _len(ln) == pytest.approx(300.0, abs=1e-6)    # the dim held it


def test_set_value_follows_the_readout_anchor_d55(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    n = len(sc._undo_stack)
    assert ctl.set_value(c.id, 250.0) is True
    assert (ln._pt1.x(), ln._pt1.y()) == pytest.approx((0.0, 0.0), abs=1e-9)   # p1 kept
    assert _len(ln) == pytest.approx(250.0, abs=1e-6)
    assert c.value == 250.0 and len(sc._undo_stack) == n + 1


def test_two_point_dim_least_change(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (0, 50)); b = _line(sc, (100, 0), (100, 50))
    c = ctl.add("dim_distance", [E(a, "p1"), E(b, "p1")])
    assert c.value == pytest.approx(100.0)
    assert ctl.set_value(c.id, 60.0)
    assert a._pt1.x() == pytest.approx(20.0, abs=1e-6)
    assert b._pt1.x() == pytest.approx(80.0, abs=1e-6)


def _implied_pair(sc, ctl):
    """A line with p1 on the origin and a 300 edge dim, then a dim origin->p2:
    the same length, implied through Coincident (not a literal repeat, D56)."""
    ln = _line(sc, (0, 0), (300, 0))
    ctl.add("coincident", [E(ln, "p1"), {"ref": "origin"}])
    c = ctl.add("dim_distance", [E(ln)])
    c2 = ctl.add("dim_distance", [{"ref": "origin"}, E(ln, "p2")])
    return ln, c, c2


def test_redundant_dim_is_auto_reference_d52(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    _ln, _c, c2 = _implied_pair(sc, ctl)
    assert c2 is not None and not c2.driving and c2.id not in ctl.red


def test_unhonourable_value_is_rejected_d53(qapp):
    """Two driving dims fixing one length: neither can change alone."""
    sc = _scene(); ctl = sc.constraint_ctl
    ln, c, c2 = _implied_pair(sc, ctl)                     # c2 auto-Reference (D52)
    ctl.set_driving(c2.id, True)                           # redundant: amber, admitted
    assert c2.driving and c2.id not in ctl.red
    n = len(sc._undo_stack)
    assert ctl.set_value(c.id, 250.0) is False             # c2 still demands 300
    assert _len(ln) == pytest.approx(300.0, abs=1e-6) and c.value == 300.0
    assert len(sc._undo_stack) == n                        # no undo step


def test_reference_dims_remove_no_dof_and_track_geometry(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    ctl.add("horizontal", [E(ln)])                         # ln participates either way
    before = ctl.sketch_dof()
    c = ctl.add("dim_distance", [E(ln)])
    assert ctl.sketch_dof() == before - 1
    ctl.set_driving(c.id, False)
    assert ctl.sketch_dof() == before
    ln.set_length(420.0)
    assert ctl.measure(c) == pytest.approx(420.0)
    ctl.set_driving(c.id, True)                            # re-drive from where it is
    assert c.value == pytest.approx(420.0) and _len(ln) == pytest.approx(420.0)


def test_zero_distance_pick_is_refused(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (10, 0)); b = _line(sc, (10, 0), (20, 0))
    assert ctl.add("dim_distance", [E(a, "p2"), E(b, "p1")]) is None
    assert ctl.constraints == []


def test_scale_edit_scales_inside_dims_d54(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    with ctl.edit([ln], scale=2.0):
        ln.manip_scale_about(QPointF(0, 0), 2.0)
    assert c.value == pytest.approx(600.0) and _len(ln) == pytest.approx(600.0, abs=1e-6)


def test_unscaled_transform_holds_dims_d54(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    with ctl.edit([ln]):                                   # box-resize style bake
        ln.manip_scale_about(QPointF(0, 0), 2.0)
    assert c.value == 300.0 and _len(ln) == pytest.approx(300.0, abs=1e-6)


def test_build_cache_sees_a_value_change(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    ctl.set_value(c.id, 200.0)
    ctl.set_value(c.id, 150.0)
    assert _len(ln) == pytest.approx(150.0, abs=1e-6)


def test_invalid_value_record_loads_inert(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    ctl.load([{"id": "d", "type": "dim_distance", "refs": [E(ln)], "value": -5}])
    assert ctl.constraints[0].inert


# -- Task 5: canvas -- paint, pick, suppression, HUD edit ---------------------

from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from firepro3d import constraint_paint as cp  # noqa: E402
from firepro3d import theme as th  # noqa: E402
from firepro3d.model_view import Model_View  # noqa: E402
from firepro3d.scale_manager import ScaleManager  # noqa: E402


@pytest.fixture
def be(qapp):
    """(view, scene): a shown Block Editor scene at 1 px / mm."""
    sc = Model_Space(scene_role="block_editor")
    sc.scale_manager = ScaleManager()
    v = Model_View(sc)
    v.resize(800, 600)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.resetTransform()
    v.centerOn(150, 0)
    sc.set_mode("select")
    QApplication.processEvents()
    yield v, sc
    sc.readouts.cancel_edit()
    sc.clearSelection()
    sc.cleanup()
    v.close()
    v.deleteLater()
    QApplication.processEvents()


def test_dim_label_shows_on_its_geometry_selection_and_picks_d82(be):
    v, sc = be; ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    ln.setSelected(True)  # D82: a dim shows on its geometry's selection
    ents = cd.dim_entries(v, ctl)
    assert [e.cid for e in ents] == [c.id]
    assert cp.dim_at(v, ctl, ents[0].layout.center) == c.id
    assert cp.glyph_at(v, ctl, ents[0].layout.center) == c.id      # select path
    assert all(cid != c.id for cid, _r in cp.glyph_layouts(v, ctl))  # no box (D51)


def test_dim_text_in_the_dimension_colour_pixel(be):
    v, sc = be; ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    ctl.add("dim_distance", [E(ln)])
    ln.setSelected(True)  # D82: a dim shows on its geometry's selection
    (e,) = cd.dim_entries(v, ctl)
    v.viewport().repaint(); QApplication.processEvents()
    img = v.viewport().grab().toImage(); dpr = img.devicePixelRatio()
    want = th.detect().color("dimension")
    lay = e.layout
    hits = 0
    for dx in range(-int(lay.width / 2), int(lay.width / 2)):
        for dy in range(-6, 7):
            q = img.pixelColor(int((lay.center.x() + dx) * dpr),
                               int((lay.center.y() + dy) * dpr))
            if (abs(q.red() - want.red()) + abs(q.green() - want.green())
                    + abs(q.blue() - want.blue())) < 60:
                hits += 1
    assert hits > 5


def test_reference_text_is_parenthesised_and_muted(be):
    v, sc = be; ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    ctl.set_driving(c.id, False)
    (e,) = cd.dim_entries(v, ctl)
    assert e.layout.text.startswith("(") and e.layout.text.endswith(")")
    t = th.detect()
    assert cd.dim_colour(ctl, c, ctl.diagnostics(), t) == t.color("muted")


def test_no_transient_linear_readouts_d57(be):
    """D57 (smoke ruling 2026-10-03) + CS5 D68: Smart Dimension owns every
    measure -- the selection readouts no longer show length / width / height /
    segment, and (retired from 'stay until CS5') no radius / angle either."""
    from firepro3d.geometry_2d import ArcItem, PolylineItem
    v, sc = be
    ln = _line(sc, (0, 0), (300, 0))
    r = _rect(sc, (0, 100), (400, 300))
    pl = PolylineItem(QPointF(0, 400))
    for q in (QPointF(100, 430), QPointF(200, 400)):
        pl.append_point(q)
    sc.addItem(pl); sc._polylines.append(pl)
    arc = ArcItem(QPointF(600, 0), 50.0, 0.0, 90.0)
    sc.addItem(arc); sc._draw_arcs.append(arc)
    for it in (ln, r, pl, arc):
        it.setSelected(True)
    keys = sorted(s.key for _i, s in sc.readouts.entries())
    assert not any(k in ("length", "width", "height") or k.startswith("seg:")
                   for k in keys)
    assert keys == []                                    # D68: none at all


def test_dim_hud_commit_drives_the_constraint(be):
    v, sc = be; ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    assert ctl.open_dim_edit(c.id, v)
    assert sc.readouts.is_editing() and sc.readouts.editing_key() == ("dim", c.id)
    sc.readouts._on_committed({"Length": 250.0})
    assert not sc.readouts.is_editing()
    assert _len(ln) == pytest.approx(250.0, abs=1e-6) and c.value == 250.0


def test_reference_dim_does_not_open_an_edit(be):
    v, sc = be; ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    ctl.set_driving(c.id, False)
    assert ctl.open_dim_edit(c.id, v) is False and not sc.readouts.is_editing()


# -- Task 7: Scale tool, copies, undo, persistence (D54, section 11 #3/#4) -----

def test_scale_tool_commit_scales_dims_d54(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    sc._selected_items = [ln]
    sc._scale_base = QPointF(0, 0)
    assert sc._modify_ctl.commit_scale(2.0) is True
    assert c.value == pytest.approx(600.0) and _len(ln) == pytest.approx(600.0, abs=1e-6)


def test_mirror_and_rotated_copies_keep_dims_d54(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    ctl.add("dim_distance", [E(ln)])
    recs = ctl.internal_records([ln])
    cp1 = _line(sc, (0, 50), (300, 50))
    ctl.paste_records(recs, {ln._uid: cp1._uid},
                      mirror_axis=(QPointF(0, 0), QPointF(1, 1)))
    cp2 = _line(sc, (0, 90), (300, 90))
    ctl.paste_records(recs, {ln._uid: cp2._uid}, rotation_deg=37.0)
    dims = [c for c in ctl.constraints if c.type == "dim_distance"]
    assert len(dims) == 3 and all(d.value == pytest.approx(300.0) for d in dims)
    assert not any(d.inert for d in dims)


def test_undo_redo_add_value_driving(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    sc.push_undo_state()
    c = ctl.add("dim_distance", [E(ln)])
    ctl.set_value(c.id, 200.0)
    ctl.set_driving(c.id, False)
    sc.undo()
    (d,) = ctl.constraints
    assert d.driving and d.value == pytest.approx(200.0)
    sc.undo()
    (l2,) = sc._draw_lines
    assert _len(l2) == pytest.approx(300.0) and ctl.constraints[0].value == pytest.approx(300.0)
    sc.undo()
    assert ctl.constraints == []
    sc.redo(); sc.redo()
    assert ctl.constraints[0].value == pytest.approx(200.0)
    (l3,) = sc._draw_lines
    assert _len(l3) == pytest.approx(200.0)


def test_save_reopen_round_trips_the_dim(qapp):
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.block_editor import BlockEditorWidget
    project = Model_Space()
    ln = LineItem(QPointF(0, 0), QPointF(300, 0))
    defn = BlockDefinition.new(
        name="B", library="L", series="S", primitives=[ln.to_dict()], origin=(0.0, 0.0),
        constraints=[{"id": "d1", "type": "dim_distance", "value": 250.0,
                      "driving": True, "refs": [{"uid": ln._uid, "h": "edge"}]},
                     {"id": "d2", "type": "dim_distance", "value": 999.0,
                      "driving": False, "refs": [{"uid": ln._uid, "h": "edge"}]}])
    project.register_block_definition(defn)
    w = BlockEditorWidget(project)
    w.seed_from_definition(defn)
    sc = w.editor_scene; ctl = sc.constraint_ctl
    (l,) = sc._draw_lines
    assert _len(l) == pytest.approx(250.0, abs=1e-6)                # driving applied on open
    assert [(c.id, c.driving) for c in ctl.constraints] == [("d1", True), ("d2", False)]
    out = ctl.to_records()
    assert out[0]["value"] == 250.0 and out[1]["driving"] is False
    assert project.constraint_ctl.constraints == []                 # never in the plan (C1/C8)


# -- Review fix round (whole-diff review F1-F5, F7) ---------------------------

def test_pasted_stale_reference_dim_is_not_red_f1(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    ctl.set_driving(c.id, False)
    ln.set_length(420.0)                                   # Reference: free to move
    recs = ctl.internal_records([ln])
    cp1 = _line(sc, (0, 50), (420, 50))
    ctl.paste_records(recs, {ln._uid: cp1._uid})
    assert ctl.red == set()
    assert ctl.sketch_state()[1] != "conflict"


def test_suppressed_dim_refuses_value_edits_f2(be):
    v, sc = be; ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (0, 50)); b = _line(sc, (100, 0), (100, 50))
    c = ctl.add("dim_distance", [E(a, "p1"), E(b, "p1")])
    ctl.set_enabled(c.id, False)
    n = len(sc._undo_stack)
    assert ctl.set_value(c.id, 60.0) is False
    assert c.value == pytest.approx(100.0) and len(sc._undo_stack) == n
    assert ctl.open_dim_edit(c.id, v) is False and not sc.readouts.is_editing()


def test_scale_scales_a_suppressed_internal_dim_too_f3(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    ctl.set_enabled(c.id, False)                           # nothing active touches ln
    sc._selected_items = [ln]
    sc._scale_base = QPointF(0, 0)
    assert sc._modify_ctl.commit_scale(2.0) is True
    assert c.value == pytest.approx(600.0) and _len(ln) == pytest.approx(600.0)


def test_scale_body_exception_restores_dim_values_f4(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    with pytest.raises(RuntimeError):
        with ctl.edit([ln], scale=2.0):
            raise RuntimeError("boom")
    assert c.value == 300.0


def test_unchanged_value_pushes_no_undo_f5(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    n = len(sc._undo_stack)
    assert ctl.set_value(c.id, 300.0) is True
    assert len(sc._undo_stack) == n


def test_short_edge_dim_is_still_pickable_f7(be):
    v, sc = be; ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (25, 0))                        # label wider than the edge
    c = ctl.add("dim_distance", [E(ln)])
    ln.setSelected(True)  # D82: a dim shows on its geometry's selection
    (e,) = cd.dim_entries(v, ctl)
    assert not e.layout.fits
    assert cp.dim_at(v, ctl, e.layout.center) == c.id


# -- D56 (smoke ruling 2026-10-03): a repeat of an existing measurement is refused

@pytest.mark.parametrize("second", [
    lambda ln, r, pl: [E(ln)],                               # same edge
    lambda ln, r, pl: [E(ln, "p1"), E(ln, "p2")],            # the edge's own ends
    lambda ln, r, pl: [E(ln, "p2"), E(ln, "p1")],            # ... either order
])
def test_repeat_of_a_line_dim_is_refused_d56(qapp, second):
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    ctl.add("dim_distance", [E(ln)])
    n = len(sc._undo_stack)
    assert ctl.add("dim_distance", second(ln, None, None)) is None
    assert len(ctl.constraints) == 1 and len(sc._undo_stack) == n


def test_rect_opposite_edge_and_two_point_repeats_are_refused_d56(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    r = _rect(sc, (0, 0), (400, 200))
    a = _line(sc, (0, 300), (0, 350)); b = _line(sc, (100, 300), (100, 350))
    assert ctl.add("dim_distance", [E(r, "top")]) is not None
    assert ctl.add("dim_distance", [E(r, "bottom")]) is None          # same width
    assert ctl.add("dim_distance", [E(r, "left")]) is not None        # height is new
    assert ctl.add("dim_distance", [E(a, "p1"), E(b, "p1")]) is not None
    assert ctl.add("dim_distance", [E(b, "p1"), E(a, "p1")]) is None  # same points
    assert len(ctl.constraints) == 3


# -- Smoke round 2 (2026-10-03): own-ends normalisation, rect message, no snap --

def test_two_point_dim_on_an_edges_own_ends_is_stored_as_the_edge(qapp):
    from firepro3d.geometry_2d import PolylineItem
    sc = _scene(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln, "p2"), E(ln, "p1")])
    assert c.refs == [E(ln)]
    r = _rect(sc, (0, 100), (400, 300))
    c2 = ctl.add("dim_distance", [E(r, "tr"), E(r, "tl")])
    assert c2.refs == [E(r, "top")]
    pl = PolylineItem(QPointF(0, 400))
    for q in (QPointF(100, 430), QPointF(200, 400)):
        pl.append_point(q)
    sc.addItem(pl); sc._polylines.append(pl)
    c3 = ctl.add("dim_distance", [E(pl, "v2"), E(pl, "v1")])
    assert c3.refs == [E(pl, "s1")]
    assert ctl.set_value(c.id, 250.0)                     # edge anchor law (D55)
    assert (ln._pt1.x(), ln._pt1.y()) == pytest.approx((0.0, 0.0), abs=1e-9)


def test_rect_opposite_side_status_names_the_shared_width(qapp):
    sc = _scene(); ctl = sc.constraint_ctl
    msgs = []
    sc._show_status = lambda m, *_a: msgs.append(m)
    r = _rect(sc, (0, 0), (400, 200))
    ctl.add("dim_distance", [E(r, "top")])
    assert ctl.add("dim_distance", [E(r, "bottom")]) is None
    assert "opposite sides share one width" in msgs[-1]
    ctl.add("dim_distance", [E(r, "right")])
    assert ctl.add("dim_distance", [E(r, "left")]) is None
    assert "opposite sides share one height" in msgs[-1]


@pytest.mark.parametrize("mode", ["constrain_dim_distance", "constrain_horizontal",
                                  "constrain_vertical", "constrain_coincident",
                                  "constrain_concentric", "constrain_symmetric",
                                  "constrain_fix", "constrain_parallel",
                                  "constrain_perpendicular", "constrain_equal",
                                  "constrain_tangent", "constrain_collinear"])
def test_constraint_pick_modes_do_not_snap(be, mode):
    v, sc = be
    _line(sc, (0, 0), (300, 0))
    sc.set_mode(mode)
    raw = QPointF(302.0, 1.5)                              # beside the endpoint
    out = sc.get_effective_position(raw)
    assert (out.x(), out.y()) == (raw.x(), raw.y())
    assert sc._snap_result is None
    sc.set_mode("select")


# -- CS4b D60-D62/D64: drawn dims, legacy auto, dim-line pick -----------------

from firepro3d import dim_graphics as dg  # noqa: E402
from firepro3d import constants as K  # noqa: E402


def _near(img, dpr, vp, want, r=1):
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            q = img.pixelColor(int((vp.x() + dx) * dpr), int((vp.y() + dy) * dpr))
            if (abs(q.red() - want.red()) + abs(q.green() - want.green())
                    + abs(q.blue() - want.blue())) < 60:
                return True
    return False


def _grab(v):
    v.viewport().repaint(); QApplication.processEvents()
    img = v.viewport().grab().toImage()
    return img, img.devicePixelRatio()


def test_placed_dim_draws_dim_line_and_witness_lines_pixel(be):
    v, sc = be; ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    ctl.add("dim_distance", [E(ln)], label={"offset": -40.0})   # n=(0,1): -40 = above
    ln.setSelected(True)  # D82: a dim shows on its geometry's selection
    img, dpr = _grab(v)
    want = th.detect().color("dimension")
    assert _near(img, dpr, QPointF(v.mapFromScene(QPointF(60, -40))), want)    # dim line
    assert _near(img, dpr, QPointF(v.mapFromScene(QPointF(0, -20))), want)     # witness
    assert not _near(img, dpr, QPointF(v.mapFromScene(QPointF(150, -20))), want)


def test_dim_without_a_label_draws_at_the_auto_offset(be):
    v, sc = be; ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    assert c.label is None
    (e,) = cd.dim_entries(v, ctl)
    A0 = QPointF(v.mapFromScene(QPointF(0, 0)))
    assert e.graphic.a.y() == pytest.approx(A0.y() - K.DIM_AUTO_OFFSET_PX, abs=1e-6)


def test_dim_line_picks_the_dim_a_witness_line_does_not(be):
    v, sc = be; ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)], label={"offset": -40.0})
    ln.setSelected(True)  # D82: a dim shows on its geometry's selection
    assert cp.dim_at(v, ctl, QPointF(v.mapFromScene(QPointF(60, -40)))) == c.id
    assert cp.dim_at(v, ctl, QPointF(v.mapFromScene(QPointF(0, -20)))) is None


def test_two_point_dim_has_no_dashed_point_to_point_line(be):
    v, sc = be; ctl = sc.constraint_ctl
    a = _line(sc, (0, -100), (0, -50)); b = _line(sc, (200, -100), (200, -50))
    ctl.add("dim_distance", [E(a, "p1"), E(b, "p1")], label={"offset": -40.0})
    sc.clearSelection()
    img, dpr = _grab(v)
    muted = th.detect().color("muted")
    # a 40 px run along the old dashed line (dash 6 / gap 4): any dash hits
    assert not any(_near(img, dpr, QPointF(v.mapFromScene(QPointF(x, -100))), muted, r=0)
                   for x in range(80, 121))


def test_placed_offset_round_trips_save_reopen(qapp):
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.block_editor import BlockEditorWidget
    project = Model_Space()
    ln = LineItem(QPointF(0, 0), QPointF(300, 0))
    defn = BlockDefinition.new(
        name="B", library="L", series="S", primitives=[ln.to_dict()], origin=(0.0, 0.0),
        constraints=[{"id": "d1", "type": "dim_distance", "value": 300.0,
                      "driving": True, "refs": [{"uid": ln._uid, "h": "edge"}],
                      "label": {"offset": -40.0}},
                     {"id": "d2", "type": "dim_distance", "value": 300.0,
                      "driving": False, "refs": [{"uid": ln._uid, "h": "p2"},
                                                 {"ref": "origin"}]}])
    project.register_block_definition(defn)
    w = BlockEditorWidget(project)
    w.seed_from_definition(defn)
    ctl = w.editor_scene.constraint_ctl
    assert dg.offset_of(ctl.find("d1").label) == -40.0
    assert ctl.find("d2").label is None                            # legacy = auto
    out = {r["id"]: r for r in ctl.to_records()}
    assert out["d1"]["label"] == {"offset": -40.0} and "label" not in out["d2"]


@pytest.fixture(params=["DARK", "LIGHT"])
def themed_be(request, qapp, monkeypatch):
    """(view, scene, theme): a shown Block Editor view at 1 px / mm painting
    the theme's canvas ground (the test_readout_paint pattern)."""
    from PyQt6.QtGui import QBrush, QColor
    t = getattr(th, request.param)
    monkeypatch.setattr(th, "detect", lambda: t)
    sc = Model_Space(scene_role="block_editor")
    sc.scale_manager = ScaleManager()
    sc.setBackgroundBrush(QBrush(QColor(t.canvas_bg)))
    v = Model_View(sc)
    v.resize(800, 600)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.resetTransform()
    v.centerOn(150, 0)
    sc.set_mode("select")
    QApplication.processEvents()
    yield v, sc, t
    sc.clearSelection()
    sc.cleanup()
    v.close()
    v.deleteLater()
    QApplication.processEvents()


def test_placed_dim_pixels_in_both_themes(themed_be):
    v, sc, t = themed_be; ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    ctl.add("dim_distance", [E(ln)], label={"offset": -40.0})
    ln.setSelected(True)  # D82: a dim shows on its geometry's selection
    img, dpr = _grab(v)
    want = t.color("dimension")
    assert _near(img, dpr, QPointF(v.mapFromScene(QPointF(60, -40))), want)     # dim line
    assert _near(img, dpr, QPointF(v.mapFromScene(QPointF(300, -20))), want)    # witness
    assert not _near(img, dpr, QPointF(v.mapFromScene(QPointF(150, -20))), want)


def test_dirty_rect_covers_every_painted_dim_pixel(be):
    """The repaint region holds the whole drawn dim, a wide terminator too
    (an 8 mm bar pointing outward = 20 px past each dim-line end, beyond
    the glow pad; the label and witness lines never reach there)."""
    import json
    import os
    from PyQt6.QtCore import QSettings
    from firepro3d.app_data import end_types_dir
    d = end_types_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "Wide.fpdb")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"schema": 1, "id": "widebar01", "version": 1, "name": "Wide",
                   "library": "System", "series": "End Types",
                   "scale_mode": "real_size", "origin": [0.0, 0.0], "attributes": [],
                   "primitives": [{"type": "polyline", "closed": True, "uid": "wb1",
                                   "points": [[0, -1], [8, -1], [8, 1], [0, 1]],
                                   "fill": {"type": "solid", "opacity": 1.0}}],
                   "end": {"trim": 0.0}}, fh)
    QSettings("GV", "FirePro3D").setValue(K.DIM_TERMINATOR_KEY, "Wide")
    try:
        v, sc = be; ctl = sc.constraint_ctl
        ln = _line(sc, (0, 0), (300, 0))
        ctl.add("dim_distance", [E(ln)], label={"offset": -40.0})
        ln.setSelected(True)  # D82: a dim shows on its geometry's selection
        img, dpr = _grab(v)
        want = th.detect().color("dimension")
        r = cp.dirty_rect(v, ctl)
        inked = 0
        for x in range(0, v.viewport().width(), 1):
            for y in range(150, 330):
                q = img.pixelColor(int(x * dpr), int(y * dpr))
                if (abs(q.red() - want.red()) + abs(q.green() - want.green())
                        + abs(q.blue() - want.blue())) < 60:
                    inked += 1
                    assert r.contains(x, y), (x, y, r)
        assert inked > 50
    finally:
        QSettings("GV", "FirePro3D").remove(K.DIM_TERMINATOR_KEY)
        os.remove(path)


# -- CS4b D65: placed dims through rotate / flip / mirror / scale --------------

from firepro3d.axis_picker import AxisPick  # noqa: E402


def _dim_mid_vp(v, ctl, cid):
    (e,) = [e for e in cd.dim_entries(v, ctl) if e.cid == cid]
    g = e.graphic
    return QPointF((g.a.x() + g.b.x()) / 2, (g.a.y() + g.b.y()) / 2)


def _close(p, q, tol=1.0):
    return abs(p.x() - q.x()) <= tol and abs(p.y() - q.y()) <= tol


def _hx_axis(sc, y):
    rl = LineItem(QPointF(-500, y), QPointF(800, y))
    rl.reference = True
    sc.addItem(rl); sc._draw_lines.append(rl)
    return AxisPick(QPointF(-500, y), QPointF(800, y), rl, 0.0)


def test_rotate_commit_carries_a_placed_dim_round(be):
    """Rotate 90 deg (Y-up CCW) about the origin maps scene (x, y) -> (y, -x):
    the dim-line middle (150, -40) lands at (-40, -150)."""
    v, sc = be; ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)], label={"offset": -40.0})
    sc._selected_items = [ln]
    sc._rotate_pivot = QPointF(0, 0)
    assert sc._modify_ctl.commit_rotate(90.0) is True
    assert _close(_dim_mid_vp(v, ctl, c.id), QPointF(v.mapFromScene(QPointF(-40, -150))))


def test_flip_mirrors_a_placed_dim_to_the_other_side(be):
    """Reflection across y = 10 maps (x, y) -> (x, 20 - y): (150, -40) -> (150, 60)."""
    v, sc = be; ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)], label={"offset": -40.0})
    sc.mode = "flip"
    sc._selected_items = [ln]
    sc._mirror_axis = _hx_axis(sc, 10.0)
    assert sc._modify_ctl.commit_reflect() is True
    assert _close(_dim_mid_vp(v, ctl, c.id), QPointF(v.mapFromScene(QPointF(150, 60))))


def test_mirror_copy_dim_lands_on_the_mirrored_side(be):
    v, sc = be; ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)], label={"offset": -40.0})
    sc.mode = "mirror"
    sc._selected_items = [ln]
    sc._mirror_axis = _hx_axis(sc, 10.0)
    assert sc._modify_ctl.commit_reflect() is True
    (copy_c,) = [d for d in ctl.constraints if d.type == "dim_distance" and d.id != c.id]
    assert _close(_dim_mid_vp(v, ctl, copy_c.id), QPointF(v.mapFromScene(QPointF(150, 60))))
    assert _close(_dim_mid_vp(v, ctl, c.id), QPointF(v.mapFromScene(QPointF(150, -40))))


def test_scale_commit_scales_a_placed_dim_offset(be):
    """Scale x2 about the origin: (150, -40) -> (300, -80)."""
    v, sc = be; ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)], label={"offset": -40.0})
    sc._selected_items = [ln]
    sc._scale_base = QPointF(0, 0)
    assert sc._modify_ctl.commit_scale(2.0) is True
    assert _close(_dim_mid_vp(v, ctl, c.id), QPointF(v.mapFromScene(QPointF(300, -80))))


def test_grip_style_edit_and_auto_dims_keep_their_offset(be):
    v, sc = be; ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)], label={"offset": -40.0})
    ln2 = _line(sc, (0, 200), (300, 200))
    c2 = ctl.add("dim_distance", [E(ln2)])                       # auto
    with ctl.edit([ln, ln2]):                                    # no point_map (box resize etc.)
        ln.manip_rotate(90.0, QPointF(0, 0))
        ln2.manip_rotate(90.0, QPointF(0, 200))
    assert dg.offset_of(c.label) == pytest.approx(-40.0)
    assert c2.label is None


def test_flip_and_scale_carry_a_placed_reference_dim(be):
    """A Reference dim is the only constraint on its line (not 'active'): it
    is still carried (D65) -- (150, -40) -> flip y = 10 -> (150, 60), then
    scale x2 about the origin -> (300, 120)."""
    v, sc = be; ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)], label={"offset": -40.0})
    ctl.set_driving(c.id, False)
    sc.mode = "flip"
    sc._selected_items = [ln]
    sc._mirror_axis = _hx_axis(sc, 10.0)
    assert sc._modify_ctl.commit_reflect() is True
    assert _close(_dim_mid_vp(v, ctl, c.id), QPointF(v.mapFromScene(QPointF(150, 60))))
    sc._selected_items = [ln]
    sc._scale_base = QPointF(0, 0)
    assert sc._modify_ctl.commit_scale(2.0) is True
    assert _close(_dim_mid_vp(v, ctl, c.id), QPointF(v.mapFromScene(QPointF(300, 120))))


def test_flipped_rect_dim_measures_the_mirrored_edge(be):
    """Rect y in [0, 100], width dim on its top edge 40 above. Flip across
    y = 200 puts the rect at y in [300, 400]; the old top edge's image is
    y = 400 and the dim line lands at y = 440 -- its witness lines span only
    the 40 px offset (+ ext - gap), never the rect's height."""
    v, sc = be; ctl = sc.constraint_ctl
    r = _rect(sc, (0, 0), (300, 100))
    c = ctl.add("dim_distance", [E(r, "top")], label={"offset": -40.0})
    sc.mode = "flip"
    sc._selected_items = [r]
    sc._mirror_axis = _hx_axis(sc, 200.0)
    assert sc._modify_ctl.commit_reflect() is True
    assert _close(_dim_mid_vp(v, ctl, c.id), QPointF(v.mapFromScene(QPointF(150, 440))))
    (e,) = [e for e in cd.dim_entries(v, ctl) if e.cid == c.id]
    (ws, we), _w2 = e.graphic.witness
    assert abs(we.y() - ws.y()) == pytest.approx(40 + K.DIM_WITNESS_EXT_PX - K.DIM_WITNESS_GAP_PX, abs=1.0)


def test_mirror_copied_rect_dim_measures_the_mirrored_edge(be):
    """As the flip guard, for the Mirror tool's copy (paste_records path)."""
    v, sc = be; ctl = sc.constraint_ctl
    r = _rect(sc, (0, 0), (300, 100))
    c = ctl.add("dim_distance", [E(r, "top")], label={"offset": -40.0})
    sc.mode = "mirror"
    sc._selected_items = [r]
    sc._mirror_axis = _hx_axis(sc, 200.0)
    assert sc._modify_ctl.commit_reflect() is True
    (cc,) = [d for d in ctl.constraints if d.type == "dim_distance" and d.id != c.id]
    assert _close(_dim_mid_vp(v, ctl, cc.id), QPointF(v.mapFromScene(QPointF(150, 440))))
    (e,) = [e for e in cd.dim_entries(v, ctl) if e.cid == cc.id]
    (ws, we), _w2 = e.graphic.witness
    assert abs(we.y() - ws.y()) == pytest.approx(40 + K.DIM_WITNESS_EXT_PX - K.DIM_WITNESS_GAP_PX, abs=1.0)
