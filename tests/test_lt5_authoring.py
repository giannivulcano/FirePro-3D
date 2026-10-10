"""LT5 D5 / E11 -- End type authoring: toggle (exclusive, symbol + nested
refusal, off refused while used), Continuous / plain-ends lock, EndFrame
(sample line ends at -trim, X-only trim grip = one undo step), panel rows
(On screen / Trim / Preview swatch) and the linetype default Start/Finish End."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d import stroke_style as ss
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_editor import BlockEditorWidget
from firepro3d.capability_panel import capability_rows, set_capability_property
from firepro3d.end_frame import EndFrame
from firepro3d.geometry_2d import GeometryTemplate, LineItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import hidden, make_linetype
from tests.lt5_support import end_id, scene_line, v_end


def _w(proj=None, defn=None):
    proj = proj or Model_Space()
    w = BlockEditorWidget(proj, block_id=defn.id if defn else None)
    if defn is not None:
        w.seed_from_definition(defn)
    msgs = []
    w.editor_scene._show_status = lambda m, t=5000: msgs.append(m)
    return proj, w, msgs


def _end_editor():
    proj, w, msgs = _w()
    for a, b in (((0, 0), (-3, -1)), ((0, 0), (-3, 1))):
        w._add_primitive(LineItem(QPointF(*a), QPointF(*b)))
    w.editor_scene.push_undo_state()
    assert w.toggle_capability("end")
    return proj, w, w.editor_scene, msgs


# ── toggle ──────────────────────────────────────────────────────────────────

def test_on_seeds_fixed_trim0_one_step_and_frame(qapp):
    _, w, _ = _w()
    sc = w.editor_scene
    n = len(sc._undo_stack)
    assert w.toggle_capability("end")
    assert sc.block_end == {"trim": 0.0, "screen": "fixed"}
    assert isinstance(sc.capability_frame_item(), EndFrame)
    assert len(sc._undo_stack) == n + 1
    sc.undo()
    assert sc.block_capability is None and sc.capability_frame_item() is None


def test_slot_normalises_the_end_record(qapp):
    _, w, _ = _w()
    sc = w.editor_scene
    sc.set_block_capability(("end", {"size": "bogus", "trim": -3.0}))
    assert sc.block_end == {"trim": 0.0}
    sc.set_block_capability(("end", {"size": "weight_relative", "trim": 2.0, "screen": "fixed"}))
    assert sc.block_end == {"trim": 2.0, "screen": "fixed"}


def test_three_way_exclusivity(qapp):
    _, w, msgs = _w()
    assert w.toggle_capability("tile")
    assert w.toggle_capability("end") is False
    assert msgs[-1] == ("Turn Pattern tile off first — a block is a pattern "
                        "or an end type, not both")
    assert w.toggle_capability("tile")                     # off
    assert w.toggle_capability("end")
    assert w.toggle_capability("repeat") is False
    assert msgs[-1] == ("Turn End type off first — a block is a linetype or "
                        "an end type, not both")
    assert w.toggle_capability("tile") is False
    assert msgs[-1] == ("Turn End type off first — a block is a pattern or "
                        "an end type, not both")


def test_on_refused_while_placed_as_symbol(qapp):
    proj = Model_Space()
    d = BlockDefinition.new(name="Sym", library="L", series="S", origin=(0, 0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(5, 0)).to_dict()])
    proj.register_block_definition(d)
    proj.place_block_instance(d.id, (0.0, 0.0))
    _, w, msgs = _w(proj, d)
    assert w.toggle_capability("end") is False
    assert w.editor_scene.block_capability is None
    assert msgs == ["Used as a symbol (1 placed) — remove those before "
                    "making it an end type"]


def test_on_refused_with_nested_blocks(qapp):
    proj = Model_Space()
    sym = BlockDefinition.new(name="Sym", library="L", series="S", origin=(0, 0),
                              primitives=[LineItem(QPointF(0, 0), QPointF(5, 0)).to_dict()])
    proj.register_block_definition(sym)
    _, w, msgs = _w(proj)
    w.editor_scene.place_block_instance(sym.id, (0.0, 0.0))
    assert w.toggle_capability("end") is False
    assert msgs[-1] == ("End types can't contain blocks — explode or remove "
                        "them first")


def test_off_refused_while_a_line_uses_it(qapp):
    proj = Model_Space()
    e = v_end("Arrow")
    proj.register_block_definition(e)
    scene_line(proj, finish={"end": e.id, "visible": True})
    _, w, msgs = _w(proj, e)
    sc = w.editor_scene
    assert sc.block_end == {"trim": 0.0}                    # seeded from defn
    assert w.toggle_capability("end") is False
    assert sc.block_end is not None
    assert msgs[-1] == "“Arrow” is used by 1 line — change their ends first."


def test_save_keeps_the_end_record(qapp):
    proj, w, sc, _ = _end_editor()
    sc.set_block_capability(("end", {"trim": 1.0, "screen": "fixed"}))
    d = w.commit_block("Round", "L", "End Types")
    assert d is not None and d.end == {"trim": 1.0, "screen": "fixed"}
    assert proj.instance_count(d.id) == 0


# ── lock (Q8) ───────────────────────────────────────────────────────────────

def test_on_locks_lines_to_continuous_plain_ends_in_one_step(qapp):
    proj, w, msgs = _w()
    lt = hidden(proj)
    eid = end_id(proj, name="Dot")
    a = LineItem(QPointF(0, 0), QPointF(-3, -1))
    a.style["linetype"] = lt
    b = LineItem(QPointF(0, 0), QPointF(-3, 1))
    b.style["finish"] = {"end": eid, "visible": True}
    for it in (a, b):
        w._add_primitive(it)
    w.editor_scene.push_undo_state()
    assert w.toggle_capability("end")
    sc = w.editor_scene
    assert {l.style["linetype"] for l in sc._draw_lines} == {ss.CONTINUOUS}
    assert {l.style["finish"]["end"] for l in sc._draw_lines} == {ss.BY_LINETYPE}
    assert msgs[-1] == "2 lines set to Continuous with plain ends"
    sc.undo()
    assert sc.block_capability is None
    assert sorted(l.style["linetype"] for l in sc._draw_lines) == sorted(
        [lt, ss.CONTINUOUS])


def test_commit_and_new_draws_stay_continuous(qapp):
    proj, w, sc, _ = _end_editor()
    lt = hidden(proj)
    ln = sc._draw_lines[0]
    ln.style["linetype"] = lt
    sc.push_undo_state()                                    # pre-capture hook
    assert ln.style["linetype"] == ss.CONTINUOUS
    ss.set_current(linetype=lt)
    new = LineItem(QPointF(0, 0), QPointF(-2, 0))
    ss.apply_current(new, sc)
    assert new.style["linetype"] == ss.CONTINUOUS
    assert ss.current_style()["linetype"] == lt              # current untouched


def test_panel_rows_locked_inside_an_end_type(qapp):
    proj, w, sc, _ = _end_editor()
    p = sc._draw_lines[0].get_properties()
    assert p["Linetype"]["disabled"] is True
    assert p["Linetype"]["tooltip"] == "Lines inside an end type are always Continuous"
    assert p["Finish End"]["disabled"] is True
    t = GeometryTemplate(sc).get_properties()
    assert t["Linetype"]["disabled"] is True
    assert t["Linetype"]["value"] == "Continuous"


# ── frame ───────────────────────────────────────────────────────────────────

def test_trim_grip_drag_is_one_undo_step_x_only_clamped(qapp):
    _, w, sc, _ = _end_editor()
    sc._snap_enabled = False
    f = sc.capability_frame_item()
    assert f.grip_points() == [QPointF(0.0, 0.0)]
    sc.clearSelection()
    f.setSelected(True)
    qapp.processEvents()
    m = sc._live_manip()
    h = [x.handle for x in m._host_pool if x.isVisible()][0]
    pos0 = sc._undo_pos
    nm = Qt.KeyboardModifier.NoModifier
    m._begin_handle(h, QPointF(0.0, 0.0), QPointF(0, 0))
    m._update(QPointF(-4.0, 3.0), nm, QPointF(200, 200))
    m._finish(QPointF(-4.0, 3.0), nm)
    assert sc.block_end["trim"] == 4.0                       # X only
    assert sc._undo_pos == pos0 + 1
    assert f.grip_points() == [QPointF(-4.0, 0.0)]
    f.apply_grip(0, QPointF(5.0, 0.0))                       # past the origin
    assert sc.block_end["trim"] == 0.0
    sc.push_undo_state()           # apply_grip never pushes (the drag's commit does)
    sc.undo()
    assert sc.block_end["trim"] == 4.0


def _render(sc):
    img = QImage(240, 40, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    sc.render(p, QRectF(0, 0, 240, 40), QRectF(-10.0, -1.0, 12.0, 2.0))
    p.end()
    return img


def _col(img, x):
    return tuple(img.pixel(x, y) for y in range(16, 25))


def test_sample_line_ends_at_minus_trim(qapp):
    """20 px / mm: column 160 = x -2 mm, column 80 = x -6 mm (axis rows)."""
    _, w, sc, _ = _end_editor()
    sc.clearSelection()
    t0 = _render(sc)
    sc.set_block_capability(("end", {"trim": 4.0, "screen": "fixed"}))
    t4 = _render(sc)
    assert _col(t0, 160) != _col(t4, 160)        # trim 4 clears x = -2
    assert _col(t0, 80) == _col(t4, 80)          # x = -6 drawn both times


# ── panel ───────────────────────────────────────────────────────────────────

def test_end_panel_rows_and_edits_are_one_step(qapp):
    from firepro3d.block_properties_info import BlockPropertiesInfo
    from firepro3d.property_manager import PropertyManager
    from firepro3d.ui_kit import PaintSwatch
    _, w, sc, _ = _end_editor()
    r = capability_rows(sc)
    for k in ("Repeat", "Pattern tile", "Linetype", "End type", "On screen",
              "Model scale", "Trim", "Preview", "Preview swatch"):        # ET1 Q12c
        assert k in r, k
    assert r["End type"]["value"] is True
    assert r["On screen"]["value"] == "Fixed size" and r["Trim"]["value_mm"] == 0.0
    for k, m in r.items():
        if m["type"] != "header":
            assert m.get("tooltip"), k
    pos0 = sc._undo_pos
    set_capability_property(sc, w, "On screen", "Scale with zoom")
    assert sc.block_end == {"trim": 0.0} and sc._undo_pos == pos0 + 1
    set_capability_property(sc, w, "On screen", "Scale with zoom")  # no-op
    set_capability_property(sc, w, "Trim", 2.5)
    assert sc.block_end["trim"] == 2.5 and sc._undo_pos == pos0 + 2
    set_capability_property(sc, w, "Trim", -1.0)                   # refused
    assert sc.block_end["trim"] == 2.5 and sc._undo_pos == pos0 + 2
    pm = PropertyManager()
    pm.show_properties(BlockPropertiesInfo(sc, "Arrow", w))
    qapp.processEvents()
    assert pm.findChildren(PaintSwatch)


def test_preview_swatch_draws_the_end_on_both_sample_lines(qapp):
    _, w, sc, _ = _end_editor()
    paint = capability_rows(sc)["Preview swatch"]["paint"]
    img = QImage(240, 64, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    paint(p, QRectF(0, 0, 240, 64))
    p.end()
    for yc, w_name in ((64 / 3.0, "Thin"), (128 / 3.0, "Heavy")):
        band = ss.canvas_px(w_name) / 2.0 + 1.5
        lit = sum(1 for x in range(214, 233) for y in range(64)
                  if abs(y - yc) > band and abs(y - yc) < 12
                  and QColor.fromRgba(img.pixel(x, y)).alpha() > 0)
        assert lit > 0, w_name


def test_linetype_default_end_rows(qapp):
    proj, w, _ = _w()
    a = end_id(proj, name="Arrow")
    assert w.toggle_capability("repeat")
    sc = w.editor_scene
    r = capability_rows(sc)
    assert r["Start End"]["options"] == ["None", "Arrow"]
    assert r["Start End"]["value"] == "None" and r["Finish End"]["tooltip"]
    pos0 = sc._undo_pos
    set_capability_property(sc, w, "Start End", "Arrow")
    assert sc.block_repeat["ends"] == {"start": a}
    assert sc._undo_pos == pos0 + 1
    assert capability_rows(sc)["Start End"]["value"] == "Arrow"
    set_capability_property(sc, w, "Start End", "Arrow")           # no-op
    assert sc._undo_pos == pos0 + 1
    set_capability_property(sc, w, "Start End", "None")
    assert "ends" not in sc.block_repeat and sc._undo_pos == pos0 + 2
    sc.undo()
    assert sc.block_repeat["ends"] == {"start": a}


def test_linetype_default_end_commit_redraws_placed_by_linetype_lines(qapp):
    """G1-review rule: a default-end edit reaches By Linetype users only
    through the commit's version bump -- a placed block's line drawn By
    Linetype shows the new end after Save (observable pixels)."""
    from tests.test_lt3_primitive_paint import _render
    proj = Model_Space()
    a = end_id(proj, name="Arrow")
    lt = make_linetype("Hidden")
    proj.register_block_definition(lt)
    ln = LineItem(QPointF(-1500.0, 0.0), QPointF(1500.0, 0.0))
    ln.style["linetype"] = lt.id
    ln.style["weight"] = "Thickest"
    host = BlockDefinition.new(name="Host", library="L", series="S",
                               origin=(0, 0), primitives=[ln.to_dict()])
    proj.register_block_definition(host)
    proj.place_block_instance(host.id, (0.0, 0.0))
    plan = QRectF(-2000.0, -2000.0, 4000.0, 4000.0)
    before = _render(proj, plan, 400, 400)
    v0 = lt.version
    _, w, _ = _w(proj, lt)
    sc = w.editor_scene
    set_capability_property(sc, w, "Finish End", "Arrow")
    assert sc.block_repeat["ends"] == {"finish": a}
    mid = _render(proj, plan, 400, 400)
    assert mid == before                       # the editor edit alone: no change
    d = w.commit_block(lt.name, lt.library, lt.series)
    after = _render(proj, plan, 400, 400)
    diff = sum(1 for y in range(400) if abs(y - 200) > 4
               for x in range(400) if before.pixel(x, y) != after.pixel(x, y))
    assert diff > 0                            # the arrow's arms draw
    assert d is lt and lt.version > v0 and lt.repeat["ends"] == {"finish": a}


def _swatch(sc):
    paint = capability_rows(sc)["Preview swatch"]["paint"]
    img = QImage(240, 64, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    paint(p, QRectF(0, 0, 240, 64))
    p.end()
    return img


def test_linetype_swatch_shows_the_default_ends(qapp):
    """Q11: the linetype panel swatch draws its default ends through the
    real end renderer (pixels change when Finish End = Arrow)."""
    proj, w, _ = _w()
    end_id(proj, name="Arrow", length=3.0, half=1.5)
    assert w.toggle_capability("repeat")
    sc = w.editor_scene
    before = _swatch(sc)
    set_capability_property(sc, w, "Finish End", "Arrow")
    after = _swatch(sc)
    diff = sum(1 for y in range(64) for x in range(240)
               if before.pixel(x, y) != after.pixel(x, y))
    assert diff > 0


# ── seam I3: ends inside linetype units / pattern tiles ─────────────────────

def _capability_editor_with_end_line(kind):
    proj, w, _ = _w()
    a = end_id(proj, name="Arrow")
    lt = hidden(proj)
    ln = LineItem(QPointF(0, 0), QPointF(6, 0))
    w._add_primitive(ln)
    w.editor_scene.push_undo_state()
    assert w.toggle_capability(kind)
    sc = w.editor_scene
    (ln,) = sc._draw_lines
    return proj, w, sc, ln, a, lt


def test_linetype_unit_end_rows_locked_and_ends_stripped_on_commit(qapp):
    proj, w, sc, ln, a, _lt = _capability_editor_with_end_line("repeat")
    p = ln.get_properties()
    for k in ("Start End", "Finish End", "Start Visible", "Finish Visible"):
        assert p[k]["disabled"] is True, k
        assert "plain ends" in p[k]["tooltip"], k
    pos0 = sc._undo_pos
    ln.set_property("Finish End", "Arrow")                   # refused
    assert ln.style["finish"]["end"] == ss.BY_LINETYPE and sc._undo_pos == pos0
    ln.style["finish"] = {"end": a, "visible": True, "mirrored": True}   # via data
    sc.push_undo_state()                                     # the commit hook
    assert ln.style["finish"] == {"end": ss.BY_LINETYPE, "visible": True,
                                  "mirrored": True}
    d = w.commit_block("Dashy", "L", "Linetypes")
    assert d is not None
    assert all(p.get("style", {}).get("finish", {}).get("end") != a
               for p in d.primitives)
    assert proj.delete_block_definition(a) is True           # not a use


def test_pattern_tile_end_rows_locked_and_ends_stripped_keep_linetype(qapp):
    proj, w, sc, ln, a, lt = _capability_editor_with_end_line("tile")
    p = ln.get_properties()
    assert p["Finish End"]["disabled"] is True
    assert p["Finish End"]["tooltip"] == "Lines inside a pattern tile draw plain ends"
    ln.style["linetype"] = lt
    ln.style["start"] = {"end": a, "visible": False}
    sc.push_undo_state()
    assert ln.style["start"] == {"end": ss.BY_LINETYPE, "visible": False}
    assert ln.style["linetype"] == lt                        # tiles keep linetypes
    d = w.commit_block("Tiley", "L", "Patterns")
    assert d is not None
    assert proj.delete_block_definition(a) is True


# ── fix round minors ───────────────────────────────────────────────────────

def test_trim_is_always_a_project_length(qapp):
    _, w, sc, _ = _end_editor()
    from firepro3d.scale_manager import DisplayUnit
    sc.scale_manager.display_unit = DisplayUnit.IMPERIAL    # a feet-inch project
    r = capability_rows(sc)
    assert "'" in r["Trim"]["value"] or '"' in r["Trim"]["value"]
    assert r["Trim"]["type"] == "dimension"
    set_capability_property(sc, w, "On screen", "Scale with zoom")
    assert capability_rows(sc)["Trim"]["type"] == "dimension"   # either sizing


def test_keyword_named_end_blocks_stay_pickable(qapp):
    proj = Model_Space()
    n = end_id(proj, name="None")
    b = end_id(proj, name="By Linetype")
    ln = scene_line(proj)
    opts = ln.get_properties()["Finish End"]["options"]
    assert "None" in opts and "None (block)" in opts and "By Linetype (block)" in opts
    ln.set_property("Finish End", "None (block)")
    assert ln.style["finish"]["end"] == n
    ln.set_property("Start End", "By Linetype (block)")
    assert ln.style["start"]["end"] == b
    ln.set_property("Finish End", "None")
    assert ln.style["finish"]["end"] == ss.NONE
    ln.set_property("Start End", "By Linetype (None)")
    assert ln.style["start"]["end"] == ss.BY_LINETYPE


def test_end_record_is_never_copied_on_paint(qapp, monkeypatch):
    """M5 copy-free rule: a warm paint of a line with ends never reads the
    copying ``BlockDefinition.end`` property."""
    proj = Model_Space()
    a = end_id(proj, name="Arrow")
    scene_line(proj, finish={"end": a, "visible": True})
    img = QImage(200, 40, QImage.Format.Format_ARGB32)

    def paint():
        p = QPainter(img)
        proj.render(p, QRectF(0, 0, 200, 40), QRectF(-5.0, -5.0, 40.0, 10.0))
        p.end()

    paint()                                                   # warm the caches
    reads = []
    orig = BlockDefinition.end
    monkeypatch.setattr(BlockDefinition, "end", property(
        lambda self: (reads.append(1), orig.fget(self))[1]))
    paint()
    assert reads == []
