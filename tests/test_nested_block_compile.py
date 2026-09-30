"""Nested blocks — registry, compile, live update, placeholder (AC3, AC12, AC14)."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_registry import BlockRegistry
from firepro3d.geometry_2d import LineItem


def _line_def(name, x0=0.0, x1=100.0, y=0.0, origin=(0.0, 0.0), extra=()):
    prims = [LineItem(QPointF(x0, y), QPointF(x1, y)).to_dict(), *extra]
    return BlockDefinition.new(name=name, library="L", series="S",
                               primitives=prims, origin=origin)


def _nested(block_id, x, y, rot=0.0):
    return {"type": "block_instance", "block_id": block_id,
            "pos": [x, y], "rotation": rot}


def _reg(*defs):
    store = {}
    r = BlockRegistry(store)
    for d in defs:
        r.add(d)
    return r, store


def test_registry_users_of_is_transitive(qapp):
    c = _line_def("C")
    b = _line_def("B", extra=[_nested(c.id, 0, 0)])
    a = _line_def("A", extra=[_nested(b.id, 0, 0)])
    other = _line_def("X")
    r, _ = _reg(c, b, a, other)
    assert r.users_of(c.id) == {b.id, a.id}
    assert r.users_of(b.id) == {a.id}
    assert r.users_of(a.id) == set()


def test_registry_would_cycle(qapp):
    c = _line_def("C")
    b = _line_def("B", extra=[_nested(c.id, 0, 0)])
    a = _line_def("A", extra=[_nested(b.id, 0, 0)])
    r, _ = _reg(c, b, a)
    assert r.would_cycle(a.id, a.id)          # A into A
    assert r.would_cycle(c.id, a.id)          # A (⊃B⊃C) into C
    assert not r.would_cycle(a.id, c.id)      # C into A is fine
    assert not r.would_cycle(None, a.id)      # unsaved host


def test_registry_get_injects_resolver_for_direct_dict_writes(qapp):
    b = _line_def("B")
    store = {b.id: b}                         # written directly (undo restore / load)
    r = BlockRegistry(store)
    assert r.get(b.id)._resolve is not None


def test_registry_missing_nested(qapp):
    a = _line_def("A", extra=[_nested("deadbeef", 0, 0)])
    r, _ = _reg(a)
    assert r.missing_nested() == {"deadbeef": {a.id}}


from firepro3d.model_space import Model_Space


def test_editor_scene_resolves_through_borrowed_project_registry(qapp):
    from firepro3d.block_editor import BlockEditorWidget
    proj = Model_Space()
    b = _line_def("B")
    proj.register_block_definition(b)
    w = BlockEditorWidget(proj)
    try:
        es = w.editor_scene
        assert es.get_block_definition(b.id) is b
        es.push_undo_state()
        es.undo()                                  # editor restore wipes ITS dict only
        assert proj.get_block_definition(b.id) is b
        assert es.get_block_definition(b.id) is b
    finally:
        w.editor_scene.cleanup()
        w.deleteLater()
        QApplication.processEvents()


def test_project_reset_keeps_registry_store_identity(qapp):
    proj = Model_Space()
    store = proj._block_definitions
    proj._clear_scene()                      # scene_io reset (holds the old rebind)
    assert proj._block_definitions is store
    b = _line_def("B")
    proj.register_block_definition(b)
    assert proj.get_block_definition(b.id) is b


from PyQt6.QtGui import QColor, QImage, QPainter


def _render(scene, rect):
    from PyQt6.QtCore import QRectF, Qt
    img = QImage(400, 400, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.black)
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, 400, 400), rect)
    p.end()
    return img


def _lit_count(img):
    n = 0
    for x in range(0, img.width(), 2):
        for y in range(0, img.height(), 2):
            c = QColor(img.pixel(x, y))
            if c.red() + c.green() + c.blue() > 200:
                n += 1
    return n


def test_nested_ops_are_flattened_through_the_pose(qapp):
    from PyQt6.QtCore import QRectF
    sc = Model_Space()
    b = _line_def("B", 0, 0, 0)                          # replaced below
    b = BlockDefinition.new(name="B", library="L", series="S", origin=(0.0, 0.0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(0, 100)).to_dict()])
    sc.register_block_definition(b)
    a = _line_def("A", 0, 10, 0, extra=[_nested(b.id, 500, 0, rot=90.0)])
    sc.register_block_definition(a)
    ops = a.render_ops()
    assert len(ops) == 2
    # B's line points +Y in the Y-DOWN scene (screen-down); 90° Y-up CCW turns
    # screen-down into screen-right, so it spans x 500..600 at y 0.
    br = ops[1][2].boundingRect()
    assert abs(br.left() - 500) < 1e-6 and abs(br.right() - 600) < 1e-6
    assert abs(br.top()) < 1e-6 and abs(br.bottom()) < 1e-6
    # Parity with a PLACED B at the same pose (D2: the BlockInstance convention).
    placed = sc.place_block_instance(b.id, (500.0, 0.0), rotation=90.0)
    ref = placed.pose_transform().map(b.render_ops()[0][2]).boundingRect()
    assert ref == br


def test_placed_A_renders_nested_B_and_follows_B_edits(qapp):
    from PyQt6.QtCore import QRectF
    sc = Model_Space()
    b = _line_def("B", 0, 100, 0)
    sc.register_block_definition(b)
    a = _line_def("A", 0, 1, 0, extra=[_nested(b.id, 200, 200)])
    sc.register_block_definition(a)
    sc.place_block_instance(a.id, (0.0, 0.0))
    area = QRectF(150, 150, 200, 200)                    # around B only
    before = _lit_count(_render(sc, area))
    assert before > 0                                    # B drawn inside A
    b.set_primitives([LineItem(QPointF(0, 50), QPointF(100, 50)).to_dict(),
                      LineItem(QPointF(0, -50), QPointF(100, -50)).to_dict()])
    sc.block_registry.invalidate(b.id)
    after = _lit_count(_render(sc, area))
    assert after > before                                # A repainted with the new B


def test_missing_nested_definition_draws_placeholder(qapp):
    sc = Model_Space()
    a = _line_def("A", 0, 1, 0, extra=[_nested("deadbeef", 300, 300)])
    sc.register_block_definition(a)
    ops = a.render_ops()
    placeholder = [op for op in ops if op[0].color() == QColor("#c0392b")]
    assert len(placeholder) == 1
    assert placeholder[0][2].boundingRect().contains(QPointF(300, 300))


def test_nested_text_snap_points_are_mapped(qapp):
    from firepro3d.text_item import TextAnnotationData, TextItem
    sc = Model_Space()
    text = TextItem(TextAnnotationData(text="X", x=0.0, y=0.0, height_mm=50.0)).to_dict()
    b = BlockDefinition.new(name="B", library="L", series="S", origin=(0.0, 0.0),
                            primitives=[text])
    sc.register_block_definition(b)
    a = _line_def("A", extra=[_nested(b.id, 100, 0)])
    sc.register_block_definition(a)
    own = b.text_snap_points()[0][8]                     # B's text centre (index 8 = C)
    got = a.text_snap_points()[0][8]
    assert abs(got.x() - (own.x() + 100)) < 1e-6 and abs(got.y() - own.y()) < 1e-6


def test_origin_assignment_clears_caches(qapp):
    d = _line_def("B")
    first = d.render_ops()
    before = first[0][2].boundingRect()
    d.origin = (10.0, 0.0)
    assert d.render_ops() is not first
    after = d.render_ops()[0][2].boundingRect()
    assert after == before.translated(-10.0, 0.0)          # geometry moved too


def test_compile_survives_a_corrupt_cycle(qapp):
    sc = Model_Space()
    a = _line_def("A")
    b = _line_def("B")
    a.primitives.append(_nested(b.id, 0, 0))
    b.primitives.append(_nested(a.id, 0, 0))             # corrupt file: A⊃B⊃A
    sc._block_definitions[a.id] = a
    sc._block_definitions[b.id] = b
    ops = sc.get_block_definition(a.id).render_ops()     # must terminate
    assert any(op[0].color() == QColor("#c0392b") for op in ops)


def _editor(proj, block_id=None):
    from firepro3d.block_editor import BlockEditorWidget
    return BlockEditorWidget(proj, block_id=block_id)


def test_editor_saves_nested_reference_and_reopens_it(qapp):
    proj = Model_Space()
    b = _line_def("B")
    proj.register_block_definition(b)
    a = _line_def("A")
    proj.register_block_definition(a)
    w = _editor(proj, a.id)
    try:
        w.seed_from_definition(a)
        w.editor_scene.place_block_instance(b.id, (300.0, 0.0), rotation=30.0)
        w.commit_block(a.name, a.library, a.series)
        recs = [p for p in a.primitives if p["type"] == "block_instance"]
        assert recs == [{"type": "block_instance", "block_id": b.id,
                         "pos": [300.0, 0.0], "rotation": 30.0}]
        w2 = _editor(proj, a.id)
        w2.seed_from_definition(a)
        insts = w2.editor_scene._block_instances
        assert [(i.block_id, i.block_pos(), i.block_rotation()) for i in insts] == \
               [(b.id, (300.0, 0.0), 30.0)]
        w2.editor_scene.cleanup()
    finally:
        w.editor_scene.cleanup()
        QApplication.processEvents()


def test_instances_only_block_is_savable(qapp, monkeypatch):
    # A False _has_geometry opens a modal info box; fail instead of hanging.
    monkeypatch.setattr("firepro3d.themed_message.themed_info",
                        lambda *a, **k: pytest.fail("modal: no geometry"))
    proj = Model_Space()
    b = _line_def("B")
    proj.register_block_definition(b)
    w = _editor(proj)
    try:
        w.editor_scene.place_block_instance(b.id, (0.0, 0.0))
        assert w._has_geometry(None)
        d = w.commit_block("Only", "L", "S")
        assert d is not None and d.primitives[0]["type"] == "block_instance"
    finally:
        w.editor_scene.cleanup()


def test_commit_refuses_a_cycle(qapp):
    proj = Model_Space()
    b = _line_def("B")
    proj.register_block_definition(b)
    a = _line_def("A", extra=[_nested(b.id, 0, 0)])
    proj.register_block_definition(a)
    status = []
    proj._show_status = lambda msg, timeout=5000: status.append(msg)
    ok = proj.commit_block_definition(
        block_id=b.id, name="B", library="L", series="S",
        primitives=[_nested(a.id, 0, 0)], origin=(0.0, 0.0), place_instance=False)
    assert ok is None
    assert all(p["type"] != "block_instance" for p in b.primitives)
    assert status == ["A block can't contain itself"]   # exact user-visible text


def test_saving_B_repaints_open_A_editor_and_plan_A(qapp):
    proj = Model_Space()
    b = _line_def("B", 0, 100, 0)
    proj.register_block_definition(b)
    a = _line_def("A", extra=[_nested(b.id, 0, 0)])
    proj.register_block_definition(a)
    plan_a = proj.place_block_instance(a.id, (0.0, 0.0))
    wa = _editor(proj, a.id)
    wa.seed_from_definition(a)
    nested_b = wa.editor_scene._block_instances[0]
    wb = _editor(proj, b.id)
    wb.seed_from_definition(b)
    try:
        calls = {"plan": 0, "editor": 0}
        plan_a.on_definition_changed = lambda: calls.__setitem__("plan", calls["plan"] + 1)
        nested_b.on_definition_changed = lambda: calls.__setitem__("editor", calls["editor"] + 1)
        wb.editor_scene._draw_lines[0].translate(0.0, 50.0)
        wb.commit_block(b.name, b.library, b.series)
        assert calls["plan"] >= 1
        assert calls["editor"] >= 1
        assert plan_a.render_ops()[1][2].boundingRect().top() == 50.0
    finally:
        for w in (wa, wb):
            w.editor_scene.cleanup()


def _undo_redo_cycles(scene, n):
    for _ in range(n):
        scene.undo()
        scene.redo()


def test_editor_undo_redo_leaves_project_backrefs_unchanged(qapp):
    proj = Model_Space()
    b = _line_def("B")
    proj.register_block_definition(b)
    a = _line_def("A", extra=[_nested(b.id, 0, 0)])
    proj.register_block_definition(a)
    proj.place_block_instance(b.id, (0.0, 0.0))
    n0 = len(b._instances)
    w = _editor(proj, a.id)
    try:
        w.seed_from_definition(a)
        w.editor_scene.place_block_instance(b.id, (300.0, 0.0))
        w.editor_scene.push_undo_state()
        _undo_redo_cycles(w.editor_scene, 5)
        assert len(b._instances) == n0
    finally:
        w.editor_scene.cleanup()


def test_closed_editor_scene_is_freed(qapp):
    import gc
    import weakref
    from PyQt6.QtWidgets import QTabWidget
    from PyQt6.QtCore import QEvent
    from firepro3d.block_editor import BlockEditorManager
    proj = Model_Space()
    b = _line_def("B")
    proj.register_block_definition(b)
    a = _line_def("A", extra=[_nested(b.id, 0, 0)])
    proj.register_block_definition(a)
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, proj)
    refs = []
    for mode in ("close", "forget"):
        w = mgr.open_for_definition(a.id)
        w.seed_from_definition(a)
        refs.append(weakref.ref(w.editor_scene))
        w.editor_scene.cleanup()
        if mode == "close":
            mgr.close(w)
        else:                                  # main.py tab-close order
            mgr.forget(w)
            tabs.removeTab(tabs.indexOf(w))
            w.deleteLater()
        del w
    for _ in range(3):
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        QApplication.processEvents()
        gc.collect()
    assert [r() for r in refs] == [None, None]
    assert len(b._instances) == 0


def test_default_origin_excludes_instance_pen_margin(qapp):
    proj = Model_Space()
    b = _line_def("B", 0, 100, 0)
    proj.register_block_definition(b)
    w = _editor(proj)
    try:
        w.editor_scene.place_block_instance(b.id, (0.0, 0.0))
        ln = LineItem(QPointF(0, 50), QPointF(100, 50))
        w._add_primitive(ln)
        o = w.origin_point()
        assert (o.x(), o.y()) == (0.0, 0.0)
    finally:
        w.editor_scene.cleanup()


def test_nested_placeholder_pen_is_cosmetic(qapp):
    sc = Model_Space()
    a = _line_def("A", 0, 1, 0, extra=[_nested("deadbeef", 300, 300)])
    sc.register_block_definition(a)
    ph = [op for op in a.render_ops() if op[0].color() == QColor("#c0392b")]
    assert ph and ph[0][0].isCosmetic()


# ── Task 13: missing nested definitions warn on load (D12; AC14) ─────────────

def test_project_load_warns_about_missing_nested_blocks(qapp, tmp_path, monkeypatch):
    from PyQt6.QtCore import QRectF
    proj = Model_Space()
    a = _line_def("A", extra=[_nested("deadbeef", 300, 300)])
    proj.register_block_definition(a)
    proj.place_block_instance(a.id, (0.0, 0.0))
    path = str(tmp_path / "p.fpd")
    proj.save_to_file(path)
    warned = []
    monkeypatch.setattr("firepro3d.themed_message.themed_warn",
                        lambda *args, **k: warned.append(args))
    fresh = Model_Space()
    fresh.load_from_file(path)
    texts = [" ".join(map(str, w)) for w in warned]
    assert any("Missing Nested Blocks" in t and "deadbeef" in t and "used in A" in t
               for t in texts)
    assert a.id in fresh._block_definitions      # A still loads
    assert len(fresh._block_instances) == 1      # ... and its placed instance
    # ... and the reopened A still DRAWS the red placeholder for the missing id
    ph = [op for op in fresh._block_definitions[a.id].render_ops()
          if op[0].color() == QColor("#c0392b")]
    assert len(ph) == 1 and ph[0][2].boundingRect().contains(QPointF(300, 300))
    img = _render(fresh, QRectF(200, 200, 200, 200))       # around the placeholder
    red = sum(1 for x in range(0, 400, 2) for y in range(0, 400, 2)
              if (lambda c: c.red() > 150 and c.green() < 100 and c.blue() < 100)(
                  QColor(img.pixel(x, y))))
    assert red > 0


def test_project_load_without_missing_nested_blocks_does_not_warn(qapp, tmp_path, monkeypatch):
    proj = Model_Space()
    b = _line_def("B")
    a = _line_def("A", extra=[_nested(b.id, 0, 0)])
    proj.register_block_definition(b); proj.register_block_definition(a)
    path = str(tmp_path / "p.fpd")
    proj.save_to_file(path)
    warned = []
    monkeypatch.setattr("firepro3d.themed_message.themed_warn",
                        lambda *args, **k: warned.append(args))
    Model_Space().load_from_file(path)
    assert not any("Missing Nested" in " ".join(map(str, w)) for w in warned)


def test_library_load_summary_lists_missing_nested(qapp, tmp_path):
    import json
    a = _line_def("A", extra=[_nested("deadbeef", 0, 0)])
    path = str(tmp_path / "a.fpdb")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(a.to_dict(), fh)                   # schema 1, no bundle
    sc = Model_Space()
    summary = sc.load_blocks_from_files([path])
    assert a.id in sc._block_definitions
    assert summary["missing"] == ["deadbeef"]


def test_load_summary_text_reports_loops_and_missing(qapp, tmp_path):
    """The Block Manager's Load-from-Library summary names a looping file's
    reason and the missing nested blocks (not "name in use")."""
    import json
    from firepro3d import block_library
    from firepro3d.block_manager import _format_load_summary
    c = _line_def("C"); b = _line_def("B", extra=[_nested(c.id, 0, 0)])
    a = _line_def("A", extra=[_nested(b.id, 0, 0)])
    looping_c = BlockDefinition.from_dict(c.to_dict())
    looping_c.primitives.append(_nested(a.id, 0, 0))
    loop = str(tmp_path / "loop.fpdb")
    rec = b.to_dict(); rec["schema"] = 2; rec["bundled"] = {c.id: looping_c.to_dict()}
    with open(loop, "w", encoding="utf-8") as fh:
        json.dump(rec, fh)
    orphan = _line_def("Orphan", extra=[_nested("deadbeef", 0, 0)])
    orphan_path = str(tmp_path / "orphan.fpdb")
    with open(orphan_path, "w", encoding="utf-8") as fh:
        json.dump(orphan.to_dict(), fh)
    sc = Model_Space()
    sc.register_block_definition(a)
    summary = sc.load_blocks_from_files([loop, orphan_path])
    text = _format_load_summary(summary)
    assert "can't contain itself" in text and "name in use" not in text
    assert "nested block(s) missing" in text
    assert block_library.load_failure_message("B", sc.load_blocks_from_files([loop])) \
        == "Could not load \u201cB\u201d: a block can't contain itself."


# ── G5 review: one-pass users map (Block Manager "Used in" perf) ─────────────

def test_registry_users_map_matches_per_id_users_of(qapp):
    """users_map() == {id: users_of(id)} over direct, indirect, unrelated
    and missing-nested references (a diamond included)."""
    d = _line_def("D")
    c = _line_def("C", extra=[_nested(d.id, 0, 0)])
    b = _line_def("B", extra=[_nested(c.id, 0, 0), _nested(d.id, 5, 0)])
    e = _line_def("E", extra=[_nested(c.id, 0, 0), _nested("deadbeef", 0, 0)])
    a = _line_def("A", extra=[_nested(b.id, 0, 0), _nested(e.id, 0, 0)])
    x = _line_def("X")
    r, store = _reg(d, c, b, e, a, x)
    um = r.users_map()
    assert set(um) == set(store)
    for i in store:
        assert um[i] == r.users_of(i), i
    assert um[d.id] == {c.id, b.id, e.id, a.id}
    assert um[x.id] == set() and um[a.id] == set()


def test_nested_compile_is_shared_across_instances(qapp, monkeypatch):
    """200 plan instances of a 2-level nested block share one op list.

    B is ALSO nested in a second host (A2) and placed directly, so a host
    that bypasses B's cache (compiling B itself instead of reading
    ``B.render_ops()``) recompiles B per host and is caught.
    """
    sc = Model_Space()
    c = _line_def("C")
    b = _line_def("B", extra=[_nested(c.id, 0, 0)])
    a = _line_def("A", extra=[_nested(b.id, 0, 0)])
    a2 = _line_def("A2", extra=[_nested(b.id, 50, 0)])
    for d in (c, b, a, a2):
        sc.register_block_definition(d)
    calls = {"n": 0}
    real = BlockDefinition._compile

    def counting(self):
        calls["n"] += 1
        return real(self)

    monkeypatch.setattr(BlockDefinition, "_compile", counting)
    insts = [sc.place_block_instance(a.id, (i * 10.0, 0.0)) for i in range(200)]
    ops = {id(i.render_ops()) for i in insts}
    assert len(ops) == 1                         # one shared list
    assert calls["n"] == 3                       # A, B, C compiled once each
    # Second host of B + B placed directly: B's cached list is reused.
    b_ops = b.render_ops()
    hosts2 = [sc.place_block_instance(a2.id, (i * 10.0, 500.0)) for i in range(50)]
    direct_b = [sc.place_block_instance(b.id, (i * 10.0, 900.0)) for i in range(50)]
    assert len({id(i.render_ops()) for i in hosts2}) == 1
    assert {id(i.render_ops()) for i in direct_b} == {id(b_ops)}
    assert b.render_ops() is b_ops               # B never recompiled
    assert calls["n"] == 4                       # + A2 only; B and C stay at one
