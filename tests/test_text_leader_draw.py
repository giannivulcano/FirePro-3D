"""Leader drawn on a real paper scene, in the Block Editor and on placements."""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter
from firepro3d.block_definition import text_box_ops
from firepro3d.render_op import STROKE
from firepro3d.model_space import Model_Space
from firepro3d.text_item import TextAnnotationData, TextItem
from PyQt6.QtGui import QTransform

LEADER = {"edge": "R", "t": 0.5, "shoulder_mm": 6.0, "tip_x": 80.0, "tip_y": 60.0,
          "end": "none", "weight": ""}


def _text(leader=LEADER):
    return TextItem(TextAnnotationData(text="note", wrap_width_mm=30.0, box_height_mm=10.0,
                                       height_mm=3.0, leader=dict(leader) if leader else None))


def test_box_ops_carry_one_stroke_with_three_points_and_a_tip_end(qapp):
    item = _text()
    _under, over = text_box_ops(item, QTransform())
    strokes = [o for o in over if o.kind == STROKE and o.pieces]
    assert len(strokes) == 1 and len(strokes[0].pieces) == 2
    last = strokes[0].pieces[-1]
    assert (last.x1, last.y1) == (80.0, 60.0)
    assert strokes[0].ends[0]["end"] == "none"


def test_no_leader_adds_no_op(qapp):
    _u, over = text_box_ops(_text(None), QTransform())
    assert not [o for o in over if o.pieces]


def test_bounds_and_shape_reach_the_tip(qapp):
    item = _text()
    tip = item.mapFromScene(QPointF(80.0, 60.0))
    assert item.boundingRect().contains(tip)
    assert item.contains(tip)


def test_block_editor_scene_paints_the_leader(qapp):
    sc = Model_Space(scene_role="block_editor")
    sc.setSceneRect(QRectF(0, 0, 100, 80))
    item = _text()
    sc.addItem(item)
    img = QImage(400, 320, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    sc.render(p, QRectF(0, 0, 400, 320), QRectF(0, 0, 100, 80))
    p.end()
    # Sample on the leader's mid-point, well outside the text box.
    mid = (int(((36.0 + 80.0) / 2) * 4), int(((5.0 + 60.0) / 2) * 4))
    hits = [img.pixelColor(mid[0] + dx, mid[1] + dy) != QColor("white")
            for dx in range(-12, 13) for dy in range(-12, 13)]
    assert any(hits)


def test_rotated_box_keeps_the_shoulder_perpendicular_to_the_turned_edge(qapp):
    item = _text()
    item.set_angle(90.0)
    _u, over = text_box_ops(item, QTransform())
    shoulder = next(o for o in over if o.pieces).pieces[0]
    r = item._box_rect_local()
    to_p = lambda p: item.mapToParent(item._rotation_transform().map(p))
    top, bot = to_p(r.topRight()), to_p(r.bottomRight())      # the turned right edge
    ex, ey = bot.x() - top.x(), bot.y() - top.y()
    sx, sy = shoulder.x1 - shoulder.x0, shoulder.y1 - shoulder.y0
    assert abs(ex * sx + ey * sy) < 1e-6 * (abs(ex) + abs(ey)) * (abs(sx) + abs(sy))
    # the attach lies on the turned edge
    cross = (shoulder.x0 - top.x()) * ey - (shoulder.y0 - top.y()) * ex
    assert abs(cross) < 1e-6 * (abs(ex) + abs(ey))


def test_paper_scene_paints_the_leader(qapp):
    from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
    sc = PaperScene(Sheet.create_default(), ViewResolver(None, None, None, None))
    d = TextAnnotationData(text="note", x=10.0, y=10.0, wrap_width_mm=30.0,
                           box_height_mm=10.0, height_mm=3.0,
                           leader=dict(LEADER, tip_x=90.0, tip_y=70.0))
    item = sc.add_annotation(d)
    area = QRectF(0, 0, 100, 80)
    img = QImage(400, 320, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    sc.render(p, QRectF(0, 0, 400, 320), area)
    p.end()
    mx, my = (46.0 + 90.0) / 2.0, (15.0 + 70.0) / 2.0          # leader mid, outside the box
    hits = [img.pixelColor(int(mx * 4) + dx, int(my * 4) + dy) != QColor("white")
            for dx in range(-8, 9) for dy in range(-8, 9)]
    assert item is not None and any(hits)
