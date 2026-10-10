"""ET1 smoke amendment Q12 -- Model scale for end types.

On MODEL canvases (plan, detail views, block and schematic editors) a Scale
with zoom end previews at its Model scale: the line end's override, else the
end type's, else Project (the scene's drawing scale = today). Sheets / PDF
print true mm; Fixed size ends ignore it. Guards 1-7 of the amendment brief:
pixels at known px/mm, real PDFs, the real panel and the real round trips.
"""
import json

import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d import block_library
from firepro3d import stroke_style as ss
from firepro3d.block_definition import BlockDefinition, _norm_end
from firepro3d.capability_panel import capability_rows, set_capability_property
from firepro3d.constants import FIXED_END_PX_PER_MM
from firepro3d.geometry_2d import GeometryTemplate, LineItem, RectangleItem
from firepro3d.model_space import Model_Space
from tests.lt5_support import arrow, set_ends
from tests.test_et1_raw import _head_width, _render
from tests.test_lt1_block_paper import _export
from tests.test_lt5_render_raw import _S, _fills
from tests.wm2_support import scene_with

# 0.4 px/mm crop whose right edge is the finish attach point (x = 2000).
_CROP = QRectF(1000.0, -250.0, 1000.0, 500.0)
_W, _H = 400, 200


def _model(a, n):
    """Give end type *a* a Model scale of 1:*n* (None = Project)."""
    rec = dict(a.end)
    rec.pop("model_scale", None)
    if n is not None:
        rec["model_scale"] = n
    a.set_end(rec)
    return a


def _plan_line(n=None, screen="scale", scale=None, length=2000.0, half=1.0):
    """1:100 plan (the Model_Space default) with one line whose finish is a
    3 mm arrow end type at Model scale 1:*n*."""
    ms = Model_Space()
    assert ms.scale_manager.drawing_scale == 100.0              # composition
    a = _model(arrow(length=3.0, half=half, screen=screen), n)
    ms.register_block_definition(a)
    ln = LineItem(QPointF(0.0, 0.0), QPointF(length, 0.0))
    set_ends(ln, finish=a.id, scale=scale)
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    return ms, ln, a


def _head(ms, crop=_CROP, w=_W, h=_H):
    return _head_width(_render(ms, crop, w, h))


# ── Guard 1: end-type Model scale on plan; PDF unchanged ────────────────────

def test_q12_g1_end_type_model_scale_on_plan_and_pdf_prints_true_mm(qapp, tmp_path):
    ms30, _, _ = _plan_line(30.0)
    ms_p, _, _ = _plan_line(None)
    h30, hp = _head(ms30), _head(ms_p)
    assert abs(h30 - 36) <= 3, h30            # 3 mm x 30 = 90 mm = 36 px
    assert abs(hp - 120) <= 3, hp             # Project: 3 mm x 100 = 300 mm = 120 px
    # the same 1:30 end type on a real PDF still prints 3 mm
    ms = Model_Space()
    a = _model(arrow(), 30.0)
    ms.register_block_definition(a)
    ln = LineItem(QPointF(-1500.0, 0.0), QPointF(1500.0, 0.0))
    set_ends(ln, finish=a.id)
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    fills = _fills(_export(tmp_path, ms, _S, "q12_g1.pdf"))
    assert len(fills) == 1, fills
    assert abs((fills[0][2] - fills[0][0]) - 3.0) <= 0.05, fills


# ── Guard 2: line override precedence; per-end Scale multiplies ─────────────

def test_q12_g2_line_override_beats_the_end_type_and_scale_multiplies(qapp):
    ms, ln, _ = _plan_line(30.0)
    ln.set_property("Finish Model scale", "1:50")
    assert ln.style["finish"]["model_scale"] == 50.0
    assert abs(_head(ms) - 60) <= 3, _head(ms)          # 3 mm x 50 = 150 mm
    ln.set_property("Finish Model scale", "By End Type (1:30)")
    assert "model_scale" not in ln.style["finish"]
    assert abs(_head(ms) - 36) <= 3, _head(ms)          # back to the end type: 90 mm
    ms2, _, _ = _plan_line(30.0, scale=2.0)
    assert abs(_head(ms2) - 72) <= 3, _head(ms2)        # 2 x 3 mm x 30 = 180 mm


# ── Guard 3: block / schematic editors and placed blocks ────────────────────

@pytest.mark.parametrize("kind", ["block", "schematic"])
def test_q12_g3_editors_honour_model_scale(qapp, kind):
    from firepro3d.block_editor import BlockEditorWidget
    proj = Model_Space()
    w = BlockEditorWidget(proj, kind=kind)
    try:
        sc = w.editor_scene
        assert sc.scale_manager.drawing_scale == 100.0         # composition
        heads = []
        for n in (30.0, None):
            a = _model(arrow(length=3.0, half=1.0, name=f"A{n}"), n)
            sc.register_block_definition(a)
            y = 300.0 if n else 1300.0
            ln = LineItem(QPointF(0, y), QPointF(2000, y))
            set_ends(ln, finish=a.id)
            sc.addItem(ln)
            sc._draw_lines.append(ln)
            heads.append(_head(sc, QRectF(0, y - 100, 2000, 200), 400, 40))
        assert abs(heads[0] - 18) <= 3, heads           # 90 mm at 0.2 px/mm
        assert abs(heads[1] - 60) <= 3, heads           # Project 1:100: 300 mm
    finally:
        w.close()
        w.deleteLater()
        qapp.processEvents()


def _placed(a, override=None, name="B"):
    ln = LineItem(QPointF(0.0, 0.0), QPointF(2000.0, 0.0))
    set_ends(ln, finish=a.id)
    if override is not None:
        ln.style["finish"]["model_scale"] = override
    return BlockDefinition.new(name=name, library="L", series="S",
                               primitives=[ln.to_dict()], origin=(0.0, 0.0))


def test_q12_g3_placed_line_follows_its_override_and_the_end_type(qapp):
    a = _model(arrow(length=3.0, half=1.0), 30.0)
    d_type, d_over = _placed(a), _placed(a, 50.0, name="B50")
    ms1, _ = scene_with([a, d_type], d_type.id)
    ms2, _ = scene_with([a, d_over], d_over.id)
    assert abs(_head(ms1) - 36) <= 3, _head(ms1)        # end type 1:30: 90 mm
    assert abs(_head(ms2) - 60) <= 3, _head(ms2)        # authored 1:50 override: 150 mm


# ── Guard 4: Fixed size ignores Model scale ─────────────────────────────────

def test_q12_g4_fixed_size_end_ignores_model_scale(qapp):
    ms, ln, _ = _plan_line(30.0, screen="fixed")
    ln.set_property("Finish Model scale", "1:50")                # ignored too
    near = _head(ms, QRectF(1800.0, -100.0, 200.0, 100.0), 400, 200)    # 2 px/mm
    far = _head(ms, QRectF(0.0, -1000.0, 2000.0, 1000.0), 400, 200)     # 0.2 px/mm
    want = 3.0 * FIXED_END_PX_PER_MM
    assert abs(near - want) <= 2 and abs(far - want) <= 2, (near, far)


# ── Guard 5: panel rows ─────────────────────────────────────────────────────

def test_q12_g5_end_type_model_scale_row(qapp):
    from tests.test_lt5_authoring import _end_editor
    _, w, sc, _ = _end_editor()
    r = capability_rows(sc)
    keys = list(r)
    assert keys.index("Model scale") == keys.index("On screen") + 1
    m = r["Model scale"]
    assert m["type"] == "enum" and m["value"] == "Project (1:100)"
    assert m["options"][0] == "Project (1:100)"
    assert m["options"][1:] == [lbl for lbl, _ in __import__(
        "firepro3d.paper_space", fromlist=["SCALE_PRESETS"]).SCALE_PRESETS]
    assert "1:30" in m["options"] and "\n" in m["tooltip"]
    pos0 = sc._undo_pos
    set_capability_property(sc, w, "Model scale", "1:30")
    assert sc.block_end.get("model_scale") == 30.0 and sc._undo_pos == pos0 + 1
    assert capability_rows(sc)["Model scale"]["value"] == "1:30"
    set_capability_property(sc, w, "Model scale", "1:30")            # same value: no step
    assert sc._undo_pos == pos0 + 1
    set_capability_property(sc, w, "Model scale", "Project (1:100)")
    assert "model_scale" not in sc.block_end and sc._undo_pos == pos0 + 2
    set_capability_property(sc, w, "Model scale", "1/4\"=1'-0\"")    # imperial: 1 / ratio
    assert sc.block_end["model_scale"] == 48.0 and sc._undo_pos == pos0 + 3
    sc.undo()
    assert "model_scale" not in sc.block_end


def test_q12_g5_line_rows_order_label_pick_and_hidden(qapp):
    ms, ln, a = _plan_line(30.0)
    ms.push_undo_state()
    props = ln.get_properties()
    keys = [k for k in props if k.startswith(("Start ", "Finish "))]
    assert keys == ["Start End", "Start Visible", "Start Scale", "Start Model scale",
                    "Finish End", "Finish Visible", "Finish Scale", "Finish Model scale"]
    f = props["Finish Model scale"]
    assert f["type"] == "enum" and f["value"] == "By End Type (1:30)"
    assert f["options"][0] == "By End Type (1:30)" and "1:50" in f["options"]
    assert "\n" in f["tooltip"]
    assert props["Start Model scale"]["value"] == "By End Type (Project 1:100)"
    n = len(ms._undo_stack)
    ln.set_property("Finish Model scale", "1:50")
    assert ln.style["finish"]["model_scale"] == 50.0 and len(ms._undo_stack) == n + 1
    assert ln.get_properties()["Finish Model scale"]["value"] == "1:50"
    ln.set_property("Finish Model scale", "1:50")                    # same: no step
    ln.set_property("Finish Model scale", "< mixed >")               # refused
    assert ln.style["finish"]["model_scale"] == 50.0 and len(ms._undo_stack) == n + 1
    ln.set_property("Finish Model scale", "By End Type (1:30)")
    assert "model_scale" not in ln.style["finish"] and len(ms._undo_stack) == n + 2
    # the end type set back to Project: the label follows the resolved scale
    _model(a, None)
    assert ln.get_properties()["Finish Model scale"]["value"] == "By End Type (Project 1:100)"
    # hidden on closed items, the Geometry template and placements
    rect = RectangleItem(QPointF(0, 0), QPointF(10, 10))
    ms.addItem(rect)
    assert "Start Model scale" not in rect.get_properties()
    assert "Start Model scale" not in GeometryTemplate(ms).get_properties()
    d = BlockDefinition.new(name="Sym", library="L", series="S", origin=(0, 0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(5, 0)).to_dict()])
    ms.register_block_definition(d)
    inst = ms.place_block_instance(d.id, (0.0, 0.0))
    assert "Start Model scale" not in inst.get_properties()


def test_q12_g5_two_line_edit_through_the_real_panel_is_one_step(qapp):
    from firepro3d.property_manager import PropertyManager
    from tests.lt5_support import end_id, scene_line
    ms = Model_Space()
    end_id(ms)
    a = scene_line(ms)
    b = scene_line(ms, p1=(0.0, 10.0), p2=(30.0, 10.0))
    pm = PropertyManager()
    pm.show_properties([a, b])
    qapp.processEvents()
    pos0 = ms._undo_pos
    pm._prop_widgets["Finish Model scale"].setCurrentText("1:30")
    qapp.processEvents()
    assert [ln.style["finish"].get("model_scale") for ln in (a, b)] == [30.0, 30.0]
    assert ms._undo_pos == pos0 + 1
    ms.undo()
    assert ms._draw_lines and not any(
        "model_scale" in ln.style["finish"] for ln in ms._draw_lines)


def test_q12_g5_line_rows_locked_in_capability_editors(qapp):
    from tests.test_lt5_authoring import _end_editor
    _, w, sc, _ = _end_editor()
    ln = next(it for it in sc.items() if isinstance(it, LineItem))
    r = ln.get_properties()
    assert r["Start Model scale"]["disabled"] is True
    assert r["Start Model scale"]["tooltip"] == r["Start End"]["tooltip"]
    pos0 = sc._undo_pos
    ln.set_property("Start Model scale", "1:30")                     # locked: refused
    assert "model_scale" not in ln.style["start"] and sc._undo_pos == pos0


# ── Guard 6: records and round trips ────────────────────────────────────────

def test_q12_g6_normalisers_keep_only_valid_model_scales(qapp):
    assert _norm_end({"trim": 1.0, "model_scale": 30}) == {"trim": 1.0, "model_scale": 30.0}
    assert _norm_end({"trim": 1.0, "screen": "fixed", "model_scale": 30.0}) == {
        "trim": 1.0, "screen": "fixed", "model_scale": 30.0}
    for bad in (0, -1, "x", float("inf"), float("nan"), 1e9, 0.5, True, None):
        assert _norm_end({"trim": 1.0, "model_scale": bad}) == {"trim": 1.0}, bad
        assert ss._end({"end": "a", "model_scale": bad}) == {"end": "a", "visible": True}, bad
    assert ss._end({"end": "a", "scale": 2.0, "model_scale": 50}) == {
        "end": "a", "visible": True, "scale": 2.0, "model_scale": 50.0}
    a = _model(arrow(), 30.0)
    rec = json.loads(json.dumps(a.to_dict()))
    assert rec["end"]["model_scale"] == 30.0
    assert BlockDefinition.from_dict(rec).end["model_scale"] == 30.0
    s, f = ss.resolve_ends({"finish": {"end": a.id, "model_scale": 50.0}}, None, {a.id: a})
    assert f.model_scale == 50.0 and s.model_scale is None


FIN = {"end": None, "visible": True, "scale": 2.0, "model_scale": 50.0}


def _ms_line(a, x0=0.0, x1=2000.0):
    ln = LineItem(QPointF(x0, 0.0), QPointF(x1, 0.0))
    ln.style["finish"] = {**FIN, "end": a.id}
    return ln


def test_q12_g6_fpd_and_fpdb_keep_model_scale(qapp, tmp_path):
    ms = Model_Space()
    a = _model(arrow(), 30.0)
    d = BlockDefinition.new(name="M", library="L", series="S",
                            primitives=[_ms_line(a).to_dict()], origin=(0.0, 0.0))
    ms.register_block_definition(a)
    ms.register_block_definition(d)
    ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
    path = tmp_path / "q12.fpd"
    ms.save_to_file(str(path))
    ms2 = Model_Space()
    ms2.load_from_file(str(path))
    (prim,) = ms2.get_block_definition(d.id).primitives
    assert prim["style"]["finish"] == {**FIN, "end": a.id}
    assert ms2.get_block_definition(a.id).end["model_scale"] == 30.0
    for blk in (a, d):
        loaded = block_library.load_block_file(
            block_library.save_to_library(blk, root=str(tmp_path / blk.name)))
        assert loaded is not None and loaded is not blk
        if blk is a:
            assert loaded.end["model_scale"] == 30.0
        else:
            assert loaded.primitives[0]["style"]["finish"] == {**FIN, "end": a.id}


def test_q12_g6_paste_and_explode_keep_model_scale(qapp):
    from firepro3d.block_explode import explode_instances
    from tests.test_wm2_nested_explode import _editor_scene
    a = arrow()
    ms = Model_Space()
    ms.register_block_definition(a)
    (it,) = ms.paste_items(QPointF(0.0, 0.0), data=[_ms_line(a).to_dict()])
    assert it.style["finish"] == {**FIN, "end": a.id}
    d = BlockDefinition.new(name="X", library="L", series="S",
                            primitives=[_ms_line(a, -300.0, 300.0).to_dict()],
                            origin=(0.0, 0.0))
    w, es = _editor_scene([a, d])
    try:
        inst = es.place_block_instance(d.id, (0.0, 0.0), level=es.active_level)
        (item,) = explode_instances(es, [inst], flatten=False)
        assert isinstance(item, LineItem)
        assert item.style["finish"] == {**FIN, "end": a.id}
    finally:
        w.close()
        w.deleteLater()
        qapp.processEvents()


def _both(item):
    for k, n in (("start", 40.0), ("finish", 50.0)):
        item.style[k] = {"end": "end-marker", "visible": True, "model_scale": n}
    return item


def test_q12_g6_fresh_cut_ends_drop_model_scale(qapp):
    ms = Model_Space(scene_role="block_editor")
    ln = _both(LineItem(QPointF(0, 0), QPointF(100, 0)))
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    ms._tools._break_item(ln, QPointF(40, 0), QPointF(60, 0))     # copy_style(fresh_ends=)
    l1, l2 = ms._draw_lines
    assert "model_scale" not in l1.style["finish"], l1.style["finish"]
    assert "model_scale" not in l2.style["start"], l2.style["start"]
    assert l1.style["start"]["model_scale"] == 40.0               # physical ends keep it
    assert l2.style["finish"]["model_scale"] == 50.0
    from tests._snap_polish_helpers import click, close_view, make_view
    view, scene = make_view(scale=1.0, mode=None)
    try:
        ln = _both(LineItem(QPointF(0, 0), QPointF(100, 0)))
        scene.addItem(ln)
        scene._draw_lines.append(ln)
        edge = LineItem(QPointF(50, -100), QPointF(50, 100))
        scene.addItem(edge)
        scene._draw_lines.append(edge)
        scene.set_mode("trim")
        click(view, QPointF(50, 80))
        click(view, QPointF(10, 0))                                # _fresh_end
        assert "model_scale" not in ln.style["start"], ln.style["start"]
        assert ln.style["finish"]["model_scale"] == 50.0
    finally:
        close_view(view, scene)


# ── Guard 7: bounds cover a Model-scaled head ───────────────────────────────

def test_q12_g7_raw_bounds_cover_a_1_300_override_head(qapp):
    ms, ln, _ = _plan_line(None)                       # half = 1 mm
    top_p = ln.boundingRect().top()
    assert -150.0 < top_p <= -100.0 + 1.0, top_p       # Project: 100 mm half-height
    ln.set_property("Finish Model scale", "1:300")
    top = ln.boundingRect().top()
    assert top <= -300.0 + 1.0 and top < top_p, (top, top_p)    # 300 mm half-height


def test_q12_g7_placed_bounds_follow_an_end_type_model_scale_edit(qapp):
    """The placed pad memo (``_end_pad_rows``) re-resolves when the end type
    it read changes version: a Model scale set on the definition after a
    first bounds read grows the pad (version-invalidation path)."""
    a = arrow(length=3.0, half=1.0)
    d = _placed(a)
    ms, inst = scene_with([a, d], d.id)
    top_p = inst.boundingRect().top()
    reach = 300.0 * (10.0 ** 0.5)
    assert top_p > -reach / 2.0, top_p                           # Project pad first
    reg_a = ms.get_block_definition(a.id)
    _model(reg_a, 300.0)                                         # set_end bumps the version
    top_o = inst.boundingRect().top()
    assert -reach - 10.0 < top_o <= -reach + 1.0, (top_o, top_p)


def test_q12_placed_model_scaled_line_prints_true_mm(qapp, tmp_path):
    """Parity: a placed block whose line carries a Model scale override still
    prints the true 3 mm on a real PDF (the paper pass's printed path)."""
    a = _model(arrow(), 30.0)
    ln = LineItem(QPointF(-1500.0, 0.0), QPointF(1500.0, 0.0))
    set_ends(ln, finish=a.id)
    ln.style["finish"]["model_scale"] = 50.0
    d = BlockDefinition.new(name="P", library="L", series="S",
                            primitives=[ln.to_dict()], origin=(0.0, 0.0))
    ms, _ = scene_with([a, d], d.id)
    fills = _fills(_export(tmp_path, ms, _S, "q12_placed.pdf"))
    assert len(fills) == 1, fills
    assert abs((fills[0][2] - fills[0][0]) - 3.0) <= 0.05, fills


def test_q12_g7_placed_bounds_cover_a_1_300_override_head(qapp):
    a = arrow(length=3.0, half=1.0)
    d_p, d_o = _placed(a), _placed(a, 300.0, name="B300")
    _, inst_p = scene_with([a, d_p], d_p.id)
    _, inst_o = scene_with([a, d_o], d_o.id)
    top_p, top_o = inst_p.boundingRect().top(), inst_o.boundingRect().top()
    # the radial pad covers the head's farthest corner (3 mm x 1 mm reach)
    reach = 300.0 * (10.0 ** 0.5)
    assert -reach - 10.0 < top_o <= -reach + 1.0, top_o    # covered, not x the printed factor
    assert top_o < top_p, (top_o, top_p)
