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


def test_dim_label_shows_with_nothing_selected_and_picks(be):
    v, sc = be; ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    c = ctl.add("dim_distance", [E(ln)])
    sc.clearSelection()
    ents = cd.dim_entries(v, ctl)
    assert [e.cid for e in ents] == [c.id]
    assert cp.dim_at(v, ctl, ents[0].layout.center) == c.id
    assert cp.glyph_at(v, ctl, ents[0].layout.center) == c.id      # select path
    assert all(cid != c.id for cid, _r in cp.glyph_layouts(v, ctl))  # no box (D51)


def test_dim_text_in_the_dimension_colour_pixel(be):
    v, sc = be; ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    ctl.add("dim_distance", [E(ln)])
    sc.clearSelection()
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


def test_duplicate_transient_readout_is_suppressed_d51(be):
    v, sc = be; ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (300, 0))
    ln.setSelected(True)
    assert [s.key for _i, s in sc.readouts.entries()] == ["length"]
    ctl.add("dim_distance", [E(ln)])
    ln.setSelected(True)
    assert [s.key for _i, s in sc.readouts.entries()] == []


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
    sc.clearSelection()
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
