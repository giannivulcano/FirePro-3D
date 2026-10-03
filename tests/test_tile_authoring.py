"""Block Editor pattern-tile authoring (hatch D-A32/D-A34, HD4a)."""
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_editor import BlockEditorWidget
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _editor_with(prims=()):
    proj = Model_Space()
    w = BlockEditorWidget(proj)
    for d in prims:
        w._add_primitive(LineItem.from_dict(d))
    return proj, w


def test_toggle_seeds_frame_from_content_extents(qapp):
    proj, w = _editor_with([LineItem(QPointF(0, 0), QPointF(20, -8)).to_dict()])
    assert w.toggle_pattern_tile()
    t = w.editor_scene.block_tile
    assert (t["w"], t["h"], t["row_shift"], t["size"]) == (20.0, 8.0, 0.0, "model")  # D-A38
    assert w.editor_scene.tile_frame_item() is not None


def test_empty_block_seeds_10x10(qapp):
    proj, w = _editor_with()
    w.toggle_pattern_tile()
    assert (w.editor_scene.block_tile["w"], w.editor_scene.block_tile["h"]) == (10.0, 10.0)


def test_tile_saved_on_commit_and_undoable(qapp):
    proj, w = _editor_with([LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()])
    w.toggle_pattern_tile()                       # one undo step (w = 5)
    sc = w.editor_scene
    sc.set_block_tile({**sc.block_tile, "w": 7.0})  # one undo step (w = 7)
    sc.undo()
    assert sc.block_tile["w"] == 5.0
    assert sc.tile_frame_item().grip_points()[0] == QPointF(5.0, -5.0)
    defn = w.commit_block("Zig", "L", "S")
    assert defn.tile["w"] == 5.0


def test_undo_past_toggle_removes_frame_and_reopen_restores_it(qapp):
    proj, w = _editor_with([LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()])
    sc = w.editor_scene
    w.toggle_pattern_tile()
    frame = sc.tile_frame_item()
    sc.undo()
    assert sc.block_tile is None and sc.tile_frame_item() is None
    assert frame.scene() is None
    sc.redo()
    assert sc.block_tile["w"] == 5.0 and sc.tile_frame_item().scene() is sc
    defn = w.commit_block("Zig", "L", "S")
    w2 = BlockEditorWidget(proj, block_id=defn.id)
    w2.seed_from_definition(defn)
    assert w2.editor_scene.block_tile == defn.tile
    assert w2.editor_scene.tile_frame_item() is not None
    w2.editor_scene.undo()                        # the seed is the baseline
    assert w2.editor_scene.block_tile == defn.tile


def test_tile_on_refused_for_a_placed_symbol(qapp):
    proj = Model_Space()
    d = BlockDefinition.new(name="Sym", library="L", series="S", origin=(0, 0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(5, 0)).to_dict()])
    proj.register_block_definition(d)
    proj.place_block_instance(d.id, (0.0, 0.0))
    proj.place_block_instance(d.id, (50.0, 0.0))
    w = BlockEditorWidget(proj, block_id=d.id)
    w.seed_from_definition(d)
    msgs = []
    w.editor_scene._show_status = lambda m, t=5000: msgs.append(m)
    assert w.toggle_pattern_tile() is False
    assert w.editor_scene.block_tile is None
    assert msgs == ["Used as a symbol (2 placed) — remove those before "
                    "making it a pattern"]


def test_tile_on_refused_for_a_nested_symbol(qapp):
    proj = Model_Space()
    d = BlockDefinition.new(name="Sym", library="L", series="S", origin=(0, 0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(5, 0)).to_dict()])
    proj.register_block_definition(d)
    host = BlockDefinition.new(name="Host", library="L", series="S", origin=(0, 0),
                               primitives=[{"type": "block_instance", "block_id": d.id,
                                            "pos": [0.0, 0.0], "rotation": 0.0}])
    proj.register_block_definition(host)
    proj.place_block_instance(d.id, (0.0, 0.0))
    w = BlockEditorWidget(proj, block_id=d.id)
    w.seed_from_definition(d)
    msgs = []
    w.editor_scene._show_status = lambda m, t=5000: msgs.append(m)
    assert w.toggle_pattern_tile() is False
    assert w.editor_scene.block_tile is None
    assert msgs == ["Used as a symbol (1 placed, 1 nested in other blocks) "
                    "— remove those before making it a pattern"]


def test_frame_survives_delete_and_is_not_gathered(qapp):
    proj, w = _editor_with([LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()])
    w.toggle_pattern_tile()
    sc = w.editor_scene
    frame = sc.tile_frame_item()
    frame.setSelected(True)
    pos0 = sc._undo_pos
    sc.delete_selected_items()
    assert sc.tile_frame_item() is frame and frame.scene() is sc
    assert sc._undo_pos == pos0, "a frame-only delete must not push an empty step"
    assert frame not in w.gather_primitives()
    # Mixed selection: the line goes, the frame stays.
    line = w.gather_primitives()[0]
    line.setSelected(True)
    frame.setSelected(True)
    sc.delete_selected_items()
    assert w.gather_primitives() == [] and frame.scene() is sc
    assert sc._undo_pos == pos0 + 1


def test_frame_is_not_a_snap_target(qapp):
    """The real snap engine finds nothing on the frame's corner / edges (only
    the frame there; the origin cross is far away at this zoom)."""
    from PyQt6.QtGui import QTransform
    from firepro3d.snap_engine import SnapEngine
    proj, w = _editor_with()
    w.toggle_pattern_tile()
    sc = w.editor_scene
    sc.set_block_tile({**sc.block_tile, "w": 100.0, "h": 100.0})
    eng = SnapEngine()
    for pt in (QPointF(100, -100), QPointF(100, -50), QPointF(50, -100)):
        assert eng.find(pt, sc, QTransform()) is None, pt
    # The engine's shared eligibility rule refuses it (also HandleSnapSession's
    # gate): the end-to-end query above has no extractor for the frame's type,
    # so this is the seam the "tile_frame" tag actually pins.
    from firepro3d.snap_engine import is_snap_target
    assert not is_snap_target(sc.tile_frame_item(), skip_pipes=False)


def test_manipulator_renders_frame_grips_after_real_selection(qapp):
    """U3 lesson: the live manipulator (not a direct manip_handles() call)
    shows the two frame grips once the frame is selected."""
    proj, w = _editor_with([LineItem(QPointF(0, 0), QPointF(20, -8)).to_dict()])
    w.toggle_pattern_tile()
    sc = w.editor_scene
    frame = sc.tile_frame_item()
    frame.setSelected(True)
    qapp.processEvents()
    m = sc._live_manip()
    assert m.isVisible()
    hosts = [h for h in m._host_pool if h.isVisible()]
    assert len(hosts) == 2
    want = {(20.0, -8.0), (0.0, -8.0)}
    got = {(round(h.scenePos().x(), 6), round(h.scenePos().y(), 6)) for h in hosts}
    assert got == want


def test_corner_grip_drag_is_one_undo_step(qapp):
    proj, w = _editor_with([LineItem(QPointF(0, 0), QPointF(20, -8)).to_dict()])
    w.toggle_pattern_tile()
    sc = w.editor_scene
    sc._snap_enabled = False
    frame = sc.tile_frame_item()
    frame.setSelected(True)
    qapp.processEvents()
    m = sc._live_manip()
    h = [x.handle for x in m._host_pool if x.isVisible()][0]
    assert h.index == 0
    pos0 = sc._undo_pos
    nm = Qt.KeyboardModifier.NoModifier
    m._begin_handle(h, QPointF(20, -8), QPointF(0, 0))
    m._update(QPointF(31, -12), nm, QPointF(200, 200))
    m._finish(QPointF(31, -12), nm)
    t = sc.block_tile
    assert (round(t["w"], 6), round(t["h"], 6)) == (31.0, 12.0)
    assert sc._undo_pos == pos0 + 1
    sc.undo()
    assert (sc.block_tile["w"], sc.block_tile["h"]) == (20.0, 8.0)


def test_panel_rows_edit_the_tile(qapp):
    from firepro3d.block_properties_info import BlockPropertiesInfo
    proj, w = _editor_with([LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()])
    info = BlockPropertiesInfo(w.editor_scene, "Zig", editor=w)
    assert info.get_properties()["Pattern tile"]["value"] is False
    info.set_property("Pattern tile", True)
    props = info.get_properties()
    assert props["Pattern tile"]["value"] is True
    assert props["Width"]["value_mm"] == 5.0 and props["Width"]["tooltip"]
    info.set_property("Width", 12.0)
    info.set_property("Row shift", 3.0)
    info.set_property("Size", "Model")
    assert w.editor_scene.block_tile == {"w": 12.0, "h": 5.0, "row_shift": 3.0,
                                         "size": "model"}
    info.set_property("Pattern tile", False)
    assert w.editor_scene.block_tile is None


def test_panel_rows_carry_tooltips(qapp):
    from PyQt6.QtWidgets import QLabel
    from firepro3d.block_properties_info import BlockPropertiesInfo
    from firepro3d.property_manager import PropertyManager
    proj, w = _editor_with([LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()])
    w.toggle_pattern_tile()
    pm = PropertyManager()
    pm.show_properties(BlockPropertiesInfo(w.editor_scene, "Zig", editor=w))
    qapp.processEvents()
    tips = {l.text(): l.toolTip() for l in pm.findChildren(QLabel)}
    for key in ("Pattern tile", "Width", "Height", "Row shift", "Size"):
        assert tips.get(key), key


def test_place_click_refused_when_block_became_a_pattern(qapp):
    """Edge case: place_block armed, then the block is saved as a pattern in
    the Block Editor — the next click places nothing and leaves the mode."""
    proj = Model_Space()
    d = BlockDefinition.new(name="Sym", library="L", series="S", origin=(0, 0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()])
    proj.register_block_definition(d)
    proj.set_mode("place_block", template=d.id)
    assert proj.mode == "place_block"
    w = BlockEditorWidget(proj, block_id=d.id)
    w.seed_from_definition(d)
    assert w.toggle_pattern_tile()
    w.commit_block("Sym", "L", "S")
    assert proj.get_block_definition(d.id).tile is not None
    p = QPointF(100.0, 100.0)
    proj._press_place_block(None, p, p, None, None, None)
    assert proj.instance_count(d.id) == 0
    assert proj.mode != "place_block"


def test_pattern_badge_is_cached_per_dpr(qapp):
    from firepro3d import blocks_browser
    a = blocks_browser._pattern_badge(1.0)
    assert blocks_browser._pattern_badge(1.0) is a
    b = blocks_browser._pattern_badge(2.0)
    assert b is not a
    pm = b.pixmap(blocks_browser._BADGE_PX, blocks_browser._BADGE_PX)
    assert not pm.isNull()


def test_frame_body_drag_pushes_no_undo_step(qapp):
    """The frame is anchored at the origin (D-A32): a body drag moves nothing,
    so it must not leave an empty step on the undo stack."""
    proj, w = _editor_with([LineItem(QPointF(0, 0), QPointF(20, -8)).to_dict()])
    w.toggle_pattern_tile()
    sc = w.editor_scene
    frame = sc.tile_frame_item()
    frame.setSelected(True)
    qapp.processEvents()
    m = sc._live_manip()
    n0, pos0 = len(sc._undo_stack), sc._undo_pos
    nm = Qt.KeyboardModifier.NoModifier
    m._begin("move", QPointF(10, -8), QPointF(0, 0))
    m._update(QPointF(40, -30), nm, QPointF(200, 200))
    m._finish(QPointF(40, -30), nm)
    assert (len(sc._undo_stack), sc._undo_pos) == (n0, pos0)
    assert frame.grip_points()[0] == QPointF(20.0, -8.0)
    assert frame.transform().isIdentity()


# ── G5: editing a pattern repaints every user (hatch HD4a) ───────────────────

def _g5_scene():
    """Pattern Zig (Model 5 mm) used by a ±200 mm hatched host instance at the
    origin, plus an unrelated plain instance far away."""
    from firepro3d import hatch_render
    from firepro3d.geometry_2d import RectangleItem
    proj, w = _editor_with([LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()])
    w.toggle_pattern_tile()
    sc = w.editor_scene
    sc.set_block_tile({**sc.block_tile, "size": "model"})
    pat = w.commit_block("Zig", "L", "S")
    r = RectangleItem(QPointF(-200, -200), QPointF(200, 200))
    r.fill_type, r.fill_pattern = "hatch", pat.id
    r._display_fill_color, r.fill_opacity = "#ff0000", 1.0
    host_def = BlockDefinition.new(name="Host", library="L", series="S",
                                   origin=(0, 0), primitives=[r.to_dict()])
    proj.register_block_definition(host_def)
    host = proj.place_block_instance(host_def.id, (0.0, 0.0))
    plain = BlockDefinition.new(name="Plain", library="L", series="S", origin=(0, 0),
                                primitives=[LineItem(QPointF(0, 0), QPointF(50, 0)).to_dict()])
    proj.register_block_definition(plain)
    far = proj.place_block_instance(plain.id, (5000.0, 5000.0))
    s0 = hatch_render.STATS["stamped_cells"]
    before = _g5_snap(proj)
    assert hatch_render.STATS["stamped_cells"] > s0, "composition: no cells stamped"
    assert any(QColor(before.pixel(x, 200)).red() > 200
               and QColor(before.pixel(x, 200)).green() < 90
               for x in range(400)), "composition: the host's hatch never rendered"
    return proj, w, host, far, before


def _g5_snap(proj):
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QImage, QPainter
    img = QImage(400, 400, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    proj.render(p, QRectF(0, 0, 400, 400), QRectF(-400, -400, 800, 800))
    p.end()
    return img


def _g5_edit_and_record(qapp, proj, w):
    """Commit a pattern edit through the Block Editor; return the union of the
    scene's ``changed`` rects it caused."""
    from PyQt6.QtCore import QRectF
    qapp.processEvents()                       # flush pending updates first
    rects = []
    proj.changed.connect(lambda rs: rects.extend(rs))
    w._add_primitive(LineItem(QPointF(0, -2.5), QPointF(5, -2.5)))
    w.commit_block("Zig", "L", "S")
    qapp.processEvents()
    u = QRectF()
    for r in rects:
        u = u.united(r)
    return u


def test_g5_pattern_edit_repaints_plan_users(qapp):
    proj, w, host, far, before = _g5_scene()
    u = _g5_edit_and_record(qapp, proj, w)
    assert u.intersects(host.sceneBoundingRect()), "the pattern's user was not repainted"
    assert _g5_snap(proj) != before, "the next paint does not show the edit"


def test_g5_users_repaint_without_the_whole_scene_fallback(qapp, monkeypatch):
    """Pins the registry path (``users_of`` via ``referenced_ids`` ->
    ``on_definition_changed``) on its own: with the commit's whole-scene
    ``update()`` suppressed, the host still repaints and the unrelated far
    instance does not."""
    proj, w, host, far, before = _g5_scene()
    monkeypatch.setattr(proj, "update", lambda *a, **k: None)
    u = _g5_edit_and_record(qapp, proj, w)
    assert u.intersects(host.sceneBoundingRect()), "the pattern's user was not repainted"
    assert not u.intersects(far.sceneBoundingRect()), "an unrelated block repainted"


# ── review fix round (I1, M1-M3, M6, M7) ─────────────────────────────────────

def _framed_line():
    proj, w = _editor_with([LineItem(QPointF(0, 0), QPointF(20, -8)).to_dict()])
    w.toggle_pattern_tile()
    sc = w.editor_scene
    return proj, w, sc, sc.tile_frame_item(), w.gather_primitives()[0]


def test_frame_stays_put_during_a_live_body_drag(qapp):
    proj, w, sc, frame, line = _framed_line()
    frame.setSelected(True)
    qapp.processEvents()
    m = sc._live_manip()
    nm = Qt.KeyboardModifier.NoModifier
    m._begin("move", QPointF(10, -8), QPointF(0, 0))
    m._update(QPointF(40, -30), nm, QPointF(200, 200))
    assert frame.transform().isIdentity(), "frame slid with the cursor"
    assert m.transform().isIdentity(), "manipulator box slid with the cursor"
    m._finish(QPointF(40, -30), nm)


def test_mixed_frame_and_line_drag_moves_only_the_line_live(qapp):
    proj, w, sc, frame, line = _framed_line()
    frame.setSelected(True)
    line.setSelected(True)
    qapp.processEvents()
    m = sc._live_manip()
    nm = Qt.KeyboardModifier.NoModifier
    p0 = line.grip_points()[0]
    m._begin("move", QPointF(10, -4), QPointF(0, 0))
    m._update(QPointF(20, -4), nm, QPointF(200, 200))
    assert frame.transform().isIdentity()
    assert abs(line.sceneTransform().map(p0).x() - (p0.x() + 10)) < 1e-6
    m._finish(QPointF(20, -4), nm)
    assert abs(line.grip_points()[0].x() - (p0.x() + 10)) < 1e-6
    assert frame.grip_points()[0] == QPointF(20.0, -8.0)


def test_retyping_the_same_value_pushes_no_undo_step(qapp):
    from firepro3d.tile_frame import set_tile_property
    proj, w, sc, frame, line = _framed_line()
    pos0 = sc._undo_pos
    set_tile_property(sc, w, "Width", 20.0)
    set_tile_property(sc, w, "Size", "Model")   # the D-A38 seed
    assert sc._undo_pos == pos0


def test_typed_edits_keep_row_shift_within_width(qapp):
    from firepro3d.tile_frame import set_tile_property
    proj, w, sc, frame, line = _framed_line()
    set_tile_property(sc, w, "Row shift", 50.0)          # past W = 20
    assert sc.block_tile["row_shift"] == 20.0
    set_tile_property(sc, w, "Row shift", 15.0)
    set_tile_property(sc, w, "Width", 5.0)               # W shrinks under it
    assert (sc.block_tile["w"], sc.block_tile["row_shift"]) == (5.0, 5.0)


def test_move_tool_skips_the_anchored_frame(qapp):
    proj, w, sc, frame, line = _framed_line()
    frame.setSelected(True)
    pos0 = sc._undo_pos
    assert sc._modify_ctl._transformable([frame]) == []
    assert sc._modify_ctl.start("move") is False      # nothing to move
    assert sc.mode != "move"
    assert sc._undo_pos == pos0
    # Mixed selection: Move acts on the line only.
    line.setSelected(True)
    assert sc._modify_ctl._transformable(sc.selectedItems()) == [line]
    assert frame.grip_points()[0] == QPointF(20.0, -8.0)


def test_copy_base_point_ignores_the_frame(qapp):
    import json
    from PyQt6.QtWidgets import QApplication
    proj, w, sc, frame, line = _framed_line()
    # A tile larger than the line: the frame's bounds centre differs from the line's.
    sc.set_block_tile({**sc.block_tile, "w": 100.0, "h": 50.0})
    line.setSelected(True)
    sc.copy_selected_items()
    want = json.loads(QApplication.clipboard().text())["base"]
    frame.setSelected(True)
    sc.copy_selected_items()
    payload = json.loads(QApplication.clipboard().text())
    assert payload["base"] == want
    assert len(payload["items"]) == 1


def test_clear_scene_resets_the_tile(qapp):
    proj, w, sc, frame, line = _framed_line()
    sc._clear_scene()
    assert sc.block_tile is None and sc.tile_frame_item() is None
    sc.set_block_tile({"w": 5.0, "h": 5.0, "row_shift": 0.0, "size": "model"})
    assert sc.tile_frame_item().scene() is sc


# ── VC9 seam fixes: D-A34 at save / paste time, D-A36 panel, self-pickers ────

def _status_sink(scene):
    msgs = []
    scene._show_status = lambda m, t=5000: msgs.append(m)
    return msgs


def test_seeded_pattern_save_places_nothing_and_keeps_the_source(qapp):
    """(a) Create Block from a selection -> Pattern tile on -> Save: the
    pattern is registered, no replacement instance, the source stays."""
    proj = Model_Space()
    src = LineItem(QPointF(100, 100), QPointF(110, 90))
    proj.addItem(src)
    proj._draw_lines.append(src)
    msgs = _status_sink(proj)
    w = BlockEditorWidget(proj)
    w.seed_from_selection([src.to_dict()], source_items=[src])
    assert w.toggle_pattern_tile()
    defn = w.commit_block("Pat", "L", "S")
    assert defn is not None and defn.tile is not None
    assert proj.get_block_definition(defn.id) is defn
    assert proj.instance_count(defn.id) == 0
    assert src.scene() is proj and src in proj._draw_lines
    assert msgs[-1] == ("Saved pattern \u2018Pat\u2019 \u2014 patterns aren't placed; "
                        "your original geometry is unchanged.")


def test_pattern_save_refused_when_placed_meanwhile(qapp):
    """(b) Tile on while unplaced -> the block is placed in the plan -> Save
    is refused with the toggle's message; nothing is committed."""
    proj = Model_Space()
    d = BlockDefinition.new(name="Sym", library="L", series="S", origin=(0, 0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()])
    proj.register_block_definition(d)
    w = BlockEditorWidget(proj, block_id=d.id)
    w.seed_from_definition(d)
    assert w.toggle_pattern_tile()
    proj.place_block_instance(d.id, (0.0, 0.0))
    msgs = _status_sink(proj)
    v0 = d.version
    assert w.commit_block("Sym", "L", "S") is None
    assert d.tile is None and d.version == v0
    assert msgs == ["Used as a symbol (1 placed) \u2014 remove those before "
                    "making it a pattern"]


def test_paste_skips_instances_of_a_block_that_became_a_pattern(qapp):
    """(c) Copy an instance, remove it, make the block a pattern, paste: no
    instance is re-created and the status says why."""
    proj = Model_Space()
    d = BlockDefinition.new(name="Sym", library="L", series="S", origin=(0, 0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()])
    proj.register_block_definition(d)
    inst = proj.place_block_instance(d.id, (0.0, 0.0))
    inst.setSelected(True)
    proj.copy_selected_items()
    proj.delete_items([inst])
    w = BlockEditorWidget(proj, block_id=d.id)
    w.seed_from_definition(d)
    assert w.toggle_pattern_tile()
    assert w.commit_block("Sym", "L", "S") is not None
    msgs = _status_sink(proj)
    new = proj.paste_items(QPointF(50.0, 50.0))
    assert new == [] and proj.instance_count(d.id) == 0
    from firepro3d import block_library
    assert msgs == [block_library.PATTERN_REASON]


def _hatched_rect(scene, ref):
    from firepro3d.geometry_2d import RectangleItem
    r = RectangleItem(QPointF(0, 0), QPointF(40, -40))
    scene.addItem(r)
    r.fill_type, r.fill_pattern = "hatch", ref
    return r


def test_panel_shows_missing_for_an_unresolvable_ref_and_keeps_it(qapp, shipped_hatches):
    from firepro3d.hatch_patterns import BUILTIN_DIAGONAL, MISSING_PATTERN_LABEL
    from firepro3d.property_manager import PropertyManager
    proj = Model_Space()
    shipped_hatches(proj)                 # D-A39: Diagonal is a project block
    r = _hatched_rect(proj, "deadbeef-no-such-tile")
    pm = PropertyManager()
    pm.show_properties([r])
    qapp.processEvents()
    combo = pm._prop_widgets["Pattern"]
    assert combo.currentText() == MISSING_PATTERN_LABEL
    r.set_property("Pattern", MISSING_PATTERN_LABEL)
    assert r.fill_pattern == "deadbeef-no-such-tile"
    r.set_property("Pattern", "Diagonal")
    assert r.fill_pattern == BUILTIN_DIAGONAL


def test_editor_pickers_exclude_the_edited_block_and_cycles(qapp):
    tile = {"w": 5, "h": 5, "row_shift": 0, "size": "model"}
    proj = Model_Space()
    x = BlockDefinition.new(name="Xpat", library="L", series="S", origin=(0, 0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()],
                            tile=tile)
    proj.register_block_definition(x)
    y = BlockDefinition.new(name="Ypat", library="L", series="S", origin=(0, 0),
                            primitives=[{"type": "block_instance", "block_id": x.id,
                                         "pos": [0.0, 0.0], "rotation": 0.0}],
                            tile=tile)
    proj.register_block_definition(y)
    z = BlockDefinition.new(name="Zpat", library="L", series="S", origin=(0, 0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(5, 0)).to_dict()],
                            tile=tile)
    proj.register_block_definition(z)
    w = BlockEditorWidget(proj, block_id=x.id)
    w.seed_from_definition(x)
    r = _hatched_rect(w.editor_scene, z.id)
    opts = r.get_properties()["Pattern"]["options"]
    assert "Zpat" in opts
    assert "Xpat" not in opts and "Ypat" not in opts      # self + would-cycle
    plan = _hatched_rect(proj, z.id).get_properties()["Pattern"]["options"]
    assert {"Xpat", "Ypat", "Zpat"} <= set(plan)
