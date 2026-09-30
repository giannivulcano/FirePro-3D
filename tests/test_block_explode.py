"""Explode a block instance in the Block Editor (AC6, AC7)."""
import math
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_instance import BlockInstance
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _proj_and_editor(*defs):
    from firepro3d.block_editor import BlockEditorWidget
    proj = Model_Space()
    for d in defs:
        proj.register_block_definition(d)
    w = BlockEditorWidget(proj)
    return proj, w, w.editor_scene


def _line_def(name, p1, p2, origin=(0.0, 0.0), extra=()):
    return BlockDefinition.new(name=name, library="L", series="S", origin=origin,
                               primitives=[LineItem(QPointF(*p1), QPointF(*p2)).to_dict(), *extra])


def _render(scene):
    img = QImage(500, 500, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.black)
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, 500, 500), QRectF(-250, -250, 500, 500))
    p.end()
    return img


def _lit(img):
    return {(x, y) for x in range(0, 500, 5) for y in range(0, 500, 5)
            if QColor(img.pixel(x, y)).lightness() > 60}


def test_explode_matches_the_instance_exactly_and_undoes(qapp):
    b = _line_def("B", (10, 0), (110, 0), origin=(10.0, 0.0))
    proj, w, es = _proj_and_editor(b)
    try:
        inst = es.place_block_instance(b.id, (20.0, 30.0), rotation=30.0)
        es.push_undo_state()
        before = _render(es)
        inst.setSelected(True)
        new = es.explode_selected_blocks()      # the real path: select + one undo step
        ln = [i for i in new if isinstance(i, LineItem)][0]
        c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
        # origin-relative (0,0)->(100,0) rotated 30° Y-up CCW, placed at (20,30)
        assert abs(ln._pt1.x() - 20) < 1e-6 and abs(ln._pt1.y() - 30) < 1e-6
        assert abs(ln._pt2.x() - (20 + 100 * c)) < 1e-6
        assert abs(ln._pt2.y() - (30 - 100 * s)) < 1e-6
        assert inst.scene() is None and all(i.isSelected() for i in new)
        es.clearSelection()     # selection highlight differs by type; compare geometry
        assert len(_lit(_render(es)) ^ _lit(before)) <= 6      # same pixels (AA fringe)
        es.undo()
        assert len(es._block_instances) == 1 and es._draw_lines == []
    finally:
        es.cleanup()


def _every_primitive():
    from firepro3d import geometry_2d as g
    from firepro3d.text_item import TextAnnotationData, TextItem
    out = []
    r = g.RectangleItem(QPointF(0, 0), QPointF(60, 30)); r.set_angle(15)
    out.append(r.to_dict())
    out.append(g.CircleItem(QPointF(-40, 20), 15).to_dict())
    out.append(g.ArcItem(QPointF(40, -40), 25, 10, 200).to_dict())
    p = g.PolylineItem(QPointF(-80, -60))
    p.append_point(QPointF(-40, -90)); p.append_point(QPointF(-10, -60))
    out.append(p.to_dict())
    out.append(g.RegularPolygonItem(QPointF(90, 40), 5, 20).to_dict())
    out.append(g.EllipseItem(QPointF(-90, 60), 25, 10, 20).to_dict())
    out.append(g.SplineItem([QPointF(0, 80), QPointF(30, 110),
                             QPointF(60, 70), QPointF(90, 100)]).to_dict())
    tx = TextItem(TextAnnotationData(text="AB", x=-60, y=100, height_mm=15,
                                     color="#ffffff"))
    tx.set_angle(20)
    out.append(tx.to_dict())
    return out


def _lit_all(img):
    return {(x, y) for x in range(500) for y in range(500)
            if QColor(img.pixel(x, y)).lightness() > 60}


@pytest.mark.parametrize("answer", ["level", "all"])
def test_explode_matches_every_primitive_type_and_nesting(qapp, monkeypatch, answer):
    """Every primitive type + a rotated nested block, origin-shifted, rotated
    30° — the exploded pixels equal the placed instance's own render."""
    from firepro3d import geometry_2d as g
    c = _line_def("C", (0, 0), (0, 50), extra=[g.CircleItem(QPointF(10, 10), 8).to_dict()])
    b = BlockDefinition.new(
        name="B", library="L", series="S", origin=(10.0, 5.0),
        primitives=_every_primitive() + [{"type": "block_instance", "block_id": c.id,
                                          "pos": [100, -60], "rotation": 45.0}])
    proj, w, es = _proj_and_editor(c, b)
    try:
        inst = es.place_block_instance(b.id, (20.0, 30.0), rotation=30.0)
        before = _lit_all(_render(es))
        inst.setSelected(True)
        monkeypatch.setattr("firepro3d.themed_message.themed_choice",
                            lambda *a, **k: answer)
        new = es.explode_selected_blocks()
        assert len(new) >= 9 and inst.scene() is None
        es.clearSelection()
        diff = before ^ _lit_all(_render(es))
        assert len(before) > 800 and len(diff) <= 25, sorted(diff)[:20]   # AA fringe only
    finally:
        es.cleanup()


def test_explode_one_level_keeps_nested_blocks_live(qapp):
    c = _line_def("C", (0, 0), (0, 50))
    b = _line_def("B", (0, 0), (100, 0),
                  extra=[{"type": "block_instance", "block_id": c.id,
                          "pos": [100, 0], "rotation": 90.0}])
    proj, w, es = _proj_and_editor(c, b)
    try:
        inst = es.place_block_instance(b.id, (0.0, 0.0), rotation=0.0)
        from firepro3d.block_explode import explode_instances
        new = explode_instances(es, [inst], flatten=False)
        nested = [i for i in new if isinstance(i, BlockInstance)]
        assert [(n.block_id, n.block_pos(), n.block_rotation()) for n in nested] == \
               [(c.id, (100.0, 0.0), 90.0)]
        flat = explode_instances(es, nested, flatten=True)
        assert not any(isinstance(i, BlockInstance) for i in flat)
    finally:
        es.cleanup()


@pytest.mark.parametrize("answer,expect_blocks", [("level", 1), ("all", 0)])
def test_prompt_choice_controls_depth(qapp, monkeypatch, answer, expect_blocks):
    c = _line_def("C", (0, 0), (0, 50))
    b = _line_def("B", (0, 0), (100, 0),
                  extra=[{"type": "block_instance", "block_id": c.id,
                          "pos": [100, 0], "rotation": 0.0}])
    proj, w, es = _proj_and_editor(c, b)
    try:
        inst = es.place_block_instance(b.id, (0.0, 0.0))
        inst.setSelected(True)
        asked = []
        monkeypatch.setattr("firepro3d.themed_message.themed_choice",
                            lambda *a, **k: asked.append(a) or answer)
        es.explode_selected_blocks()
        assert len(asked) == 1
        assert len(es._block_instances) == expect_blocks
    finally:
        es.cleanup()


def test_explode_ignores_non_blocks_and_needs_no_prompt_without_nesting(qapp, monkeypatch):
    b = _line_def("B", (0, 0), (100, 0))
    proj, w, es = _proj_and_editor(b)
    try:
        loose = LineItem(QPointF(0, 200), QPointF(50, 200))
        es.addItem(loose); es._draw_lines.append(loose)
        inst = es.place_block_instance(b.id, (0.0, 0.0))
        loose.setSelected(True); inst.setSelected(True)
        monkeypatch.setattr("firepro3d.themed_message.themed_choice",
                            lambda *a, **k: pytest.fail("no prompt without nesting"))
        es.explode_selected_blocks()
        assert es._block_instances == [] and loose in es._draw_lines
        assert len(es._draw_lines) == 2
    finally:
        es.cleanup()
