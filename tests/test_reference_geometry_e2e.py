"""End-to-end guards for reference geometry (design G2, G3, G5, G6, G7) plus
the derive-piece colour (RG14) and hidden-style user counts (RG15)."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QRectF, QSettings
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.geometry_2d import ArcItem, CircleItem, LineItem


def _ring_lit(scene, rect=QRectF(-80, -80, 160, 160), size=160):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, size, size), rect)
    p.end()
    return sum(1 for x in range(size) for y in range(size)
               if img.pixelColor(x, y).value() > 40)


def _lit_count(img):
    return sum(1 for x in range(img.width()) for y in range(img.height())
               if img.pixelColor(x, y).value() < 200)    # dark ink on paper


@pytest.fixture
def _scratch_display_keys():
    keys = ("display/Reference Geometry/color", "display/2D Geometry/color")
    st = QSettings("GV", "FirePro3D")
    before = {k: st.value(k) for k in keys if st.contains(k)}
    yield
    st = QSettings("GV", "FirePro3D")
    for k in keys:
        st.remove(k)
    for k, v in before.items():
        st.setValue(k, v)
    st.sync()


def test_g2_scaffold_circle_absent_from_instance_and_explode_reseeded(qapp):
    from firepro3d.model_space import Model_Space
    from firepro3d.block_explode import explode_instances
    from firepro3d.block_definition import BlockDefinition
    from tests.test_block_definition_constraints import _editor
    proj = Model_Space()
    ref = CircleItem(QPointF(0, 0), 50.0)
    ref.reference = True
    defn = proj.commit_block_definition(
        block_id=None, name="B", library="L", series="S",
        primitives=[ref.to_dict()], origin=(0.0, 0.0), place_instance=False)
    w = _editor(proj)
    host = w.editor_scene
    base = _ring_lit(host)                               # origin cross etc.
    inst = host.place_block_instance(defn.id, (0.0, 0.0), rotation=0.0)
    assert _ring_lit(host) == base                        # not drawn in the instance
    assert explode_instances(host, [inst], flatten=False) == []
    host.remove_block_instance(inst)
    # reopen: a fresh editor re-seeds it as a reference circle
    w2 = _editor(proj)
    w2.seed_from_definition(BlockDefinition.from_dict(defn.to_dict()))
    seeded = w2.editor_scene._draw_circles
    assert len(seeded) == 1 and seeded[0].reference and not seeded[0].printed
    # printed on -> the instance renders it
    ref.printed = True
    defn2 = proj.commit_block_definition(
        block_id=None, name="B2", library="L", series="S",
        primitives=[ref.to_dict()], origin=(0.0, 0.0), place_instance=False)
    w3 = _editor(proj)
    base3 = _ring_lit(w3.editor_scene)
    w3.editor_scene.place_block_instance(defn2.id, (0.0, 0.0), rotation=0.0)
    assert _ring_lit(w3.editor_scene) > base3


def test_g3_schematic_paper_pass_drops_scaffold_keeps_printed(qapp):
    from tests.test_sv2_paper_primitives import _render
    from firepro3d.model_space import Model_Space
    s = Model_Space(scene_role="block_editor")
    off = CircleItem(QPointF(0, 0), 40.0)
    off.reference = True
    # RG12: a printed reference shape keeps its canvas pen (authored colour);
    # the default is white, so author dark ink to see it on white paper.
    off.style["colour"] = "#000000"
    s.addItem(off); s._draw_circles.append(off)
    assert _lit_count(_render(s)) == 0
    off.printed = True
    assert _lit_count(_render(s)) > 0


def test_g7_unit_refresh_category_display_colour_reaches_the_canvas(qapp, _scratch_display_keys):
    from firepro3d.display_manager import refresh_category_display
    from tests.test_reference_geometry import _render_item
    st = QSettings("GV", "FirePro3D")
    st.setValue("display/Reference Geometry/color", "#ff0000")
    off = CircleItem(QPointF(0, 0), 40.0)
    off.reference = True
    refresh_category_display(off)
    img = _render_item(off)                              # black canvas
    reds = [1 for x in range(img.width()) for y in range(img.height())
            if img.pixelColor(x, y).red() > 200
            and img.pixelColor(x, y).green() < 60
            and img.pixelColor(x, y).blue() < 60]
    assert len(reds) > 20                                # the ring is red


def test_g5_legacy_records_on_every_load_path(qapp):
    from firepro3d.model_space import Model_Space
    from firepro3d.block_definition import BlockDefinition
    legacy = {"type": "reference_line", "pt1": [0, 0], "pt2": [10, 0],
              "color": "#ffffff", "lineweight": 1.0, "printed": True}
    s = Model_Space(scene_role="block_editor")
    item = s._add_from_dict(legacy)                      # paste / clipboard path
    assert type(item) is LineItem and item.reference and item.printed
    assert item in s._draw_lines
    snap = s._capture_network()
    snap["reference_lines"] = [legacy]                   # an old in-memory snapshot
    s._restore_network(snap)
    flagged = [l for l in s._draw_lines if l.reference]
    assert len(flagged) == 2 and all(l.printed for l in flagged)
    d = BlockDefinition.new(name="n", library="", series="",
                            primitives=[legacy], origin=(0.0, 0.0))
    assert len(d.render_ops()) == 1                      # printed -> compiled


def test_g6_constraints_solve_on_a_reference_arc(qapp):
    from firepro3d.model_space import Model_Space
    sc = Model_Space(scene_role="block_editor")
    arc = ArcItem(QPointF(0, 50), 100.0, 0.0, 90.0)
    arc.reference = True
    sc.addItem(arc); sc._draw_arcs.append(arc)
    c = sc.constraint_ctl.add("horizontal", [{"uid": arc._uid, "h": "center"},
                                             {"ref": "origin"}])
    assert c is not None                                 # the reference arc participates
    assert arc._center.y() == pytest.approx(0.0)         # solved: centre on the X axis
    assert arc.reference is True                         # the solve kept the flag


def test_derive_pieces_take_the_reference_colour(qapp, _scratch_display_keys):
    from firepro3d.model_space import Model_Space
    st = QSettings("GV", "FirePro3D")
    st.setValue("display/Reference Geometry/color", "#ff0000")
    st.setValue("display/2D Geometry/color", "#00ff00")
    sc = Model_Space(scene_role="block_editor")
    ref = LineItem(QPointF(-50, 0), QPointF(50, 0))
    norm = LineItem(QPointF(-50, 20), QPointF(50, 20))
    ref.reference = True
    for ln in (ref, norm):
        sc.addItem(ln); sc._draw_lines.append(ln)
    sc._tools._break_item(ref, QPointF(-10, 0), QPointF(10, 0))
    sc._tools._break_item(norm, QPointF(-10, 20), QPointF(10, 20))
    pieces = [l for l in sc._draw_lines if l is not ref and l is not norm]
    ref_pieces = [l for l in pieces if l.reference]
    norm_pieces = [l for l in pieces if not l.reference]
    assert len(ref_pieces) == 2 and len(norm_pieces) == 2
    assert all(l._display_color == "#ff0000" for l in ref_pieces)
    assert all(l._display_color != "#ff0000" for l in norm_pieces)


def test_reference_line_is_not_a_linetype_or_end_user(qapp):
    from firepro3d.model_space import Model_Space
    from firepro3d.block_registry import end_users_in, linetype_users_in
    sc = Model_Space(scene_role="block_editor")
    ref = LineItem(QPointF(0, 0), QPointF(100, 0))
    norm = LineItem(QPointF(0, 20), QPointF(100, 20))
    for ln in (ref, norm):
        ln.style["linetype"] = "lt-x"
        ln.style["start"]["end"] = "end-x"
        sc.addItem(ln); sc._draw_lines.append(ln)
    ref.reference = True
    assert linetype_users_in(sc, "lt-x") == [norm]
    assert end_users_in(sc, "end-x") == [norm]
    ref.reference = False
    assert set(linetype_users_in(sc, "lt-x")) == {ref, norm}
    assert set(end_users_in(sc, "end-x")) == {ref, norm}


# -- seam fix round S1 (RG18): load / copy paths take the Reference colour ----

def _red_px(scene, rect=QRectF(-80, -80, 160, 160), size=160):
    scene.clearSelection()                               # no selection paint
    scene.constraint_ctl.show_status = False             # no D39 constraint tint
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, size, size), rect)
    p.end()
    # antialiased red-on-black keeps green / blue near 0 at any coverage
    return sum(1 for x in range(size) for y in range(size)
               if img.pixelColor(x, y).red() > 80
               and img.pixelColor(x, y).green() * 4 < img.pixelColor(x, y).red()
               and img.pixelColor(x, y).blue() * 4 < img.pixelColor(x, y).red())


def test_s1_block_editor_reopen_seeds_a_reference_circle_in_the_category_colour(
        qapp, _scratch_display_keys):
    from firepro3d.model_space import Model_Space
    from firepro3d.block_definition import BlockDefinition
    from tests.test_block_definition_constraints import _editor
    QSettings("GV", "FirePro3D").setValue("display/Reference Geometry/color",
                                          "#ff0000")
    proj = Model_Space()
    ref = CircleItem(QPointF(0, 0), 50.0)
    ref.reference = True
    defn = proj.commit_block_definition(
        block_id=None, name="S1", library="L", series="S",
        primitives=[ref.to_dict()], origin=(0.0, 0.0), place_instance=False)
    w = _editor(proj)
    w.seed_from_definition(BlockDefinition.from_dict(defn.to_dict()))
    seeded = w.editor_scene._draw_circles
    assert len(seeded) == 1 and seeded[0].reference
    assert _red_px(w.editor_scene) > 20                  # the ring is red


def test_s1_paste_of_a_reference_circle_renders_in_the_category_colour(
        qapp, _scratch_display_keys):
    from firepro3d.model_space import Model_Space
    QSettings("GV", "FirePro3D").setValue("display/Reference Geometry/color",
                                          "#ff0000")
    sc = Model_Space(scene_role="block_editor")
    ref = CircleItem(QPointF(0, 0), 50.0)
    ref.reference = True
    sc.addItem(ref); sc._draw_circles.append(ref)
    recs = sc._clipboard_item_dicts([ref])
    sc.removeItem(ref); sc._draw_circles.remove(ref)     # only the paste draws
    new = sc.paste_items(QPointF(0, 0), data=recs)
    assert len(new) == 1 and new[0].reference
    assert _red_px(sc) > 20                              # the pasted ring is red


# -- seam fix round S5 (RG15): hidden refs are not counted in refusal text ----

def test_s5_end_delete_refusal_counts_the_normal_line_not_the_reference(qapp):
    from firepro3d.model_space import Model_Space
    from tests.test_lt5_integrity import _arrow, _host, _rec
    ms = Model_Space()
    e = _arrow(ms)
    ref = _rec(e.id)
    ref["reference"] = True
    _host(ms, _rec(e.id), ref)
    assert ms.block_users_message(e.id) == (
        "“Arrow” is used by 1 line — change their ends first.")


def test_s5_linetype_refusal_ignores_a_reference_line_in_a_nesting_host(qapp):
    from firepro3d.model_space import Model_Space
    from tests.lt3_support import make_linetype
    from tests.test_lt5_integrity import _host, _rec
    ms = Model_Space()
    lt = make_linetype("Hidden")
    ms.register_block_definition(lt)
    ref = _rec(linetype=lt.id)
    ref["reference"] = True
    nested = {"type": "block_instance", "block_id": lt.id, "pos": [0.0, 0.0]}
    host = _host(ms, nested, ref, name="Nester")
    users = ms.block_registry.users_of(lt.id)
    assert users == {host.id}
    # only a hidden reference line names the linetype: pure nesting wording
    assert ms._linetype_users_message(lt, users) is None
