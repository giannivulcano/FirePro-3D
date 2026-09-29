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
    d.origin = (10.0, 0.0)
    assert d.render_ops() is not first


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
    ok = proj.commit_block_definition(
        block_id=b.id, name="B", library="L", series="S",
        primitives=[_nested(a.id, 0, 0)], origin=(0.0, 0.0), place_instance=False)
    assert ok is None
    assert all(p["type"] != "block_instance" for p in b.primitives)


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
        assert calls["plan"] >= 1 and calls["editor"] >= 1
        assert plan_a.render_ops()[1][2].boundingRect().top() == 50.0
    finally:
        for w in (wa, wb):
            w.editor_scene.cleanup()
