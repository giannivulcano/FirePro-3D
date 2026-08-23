from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QImage, QPainter, QColor
from firepro3d.wall_opening import WallOpening
from firepro3d.wall import WallSegment


def _render_item(scene, item, size=200):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    br = item.mapToScene(item.boundingRect()).boundingRect()
    scene.render(p, QRectF(0, 0, size, size), br.adjusted(-50, -50, 50, 50))
    p.end()
    return img


def _has_non_white(img):
    return any(QColor(img.pixel(x, y)) != QColor("white")
               for x in range(0, img.width(), 3) for y in range(0, img.height(), 3))


def test_door_plan_symbol_draws_arc(qapp, model_scene):
    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    op = WallOpening(wall=w, feature_id="door_914", offset_along=500.0)
    scene.addItem(op); w.openings.append(op)
    op._reposition()
    assert not op.path().isEmpty()
    assert _has_non_white(_render_item(scene, op))


def test_hinge_mirror_changes_path(qapp, model_scene):
    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    op = WallOpening(wall=w, feature_id="door_914", offset_along=500.0)
    op._reposition(); before = op.path().boundingRect()
    op.mirror_hinge = True; op._reposition()
    assert op.path().boundingRect() != before


def test_blank_opening_has_no_swing(qapp, model_scene):
    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    op = WallOpening(wall=w, feature_id="blank_900", offset_along=500.0)
    op._reposition()
    br = op.path().boundingRect()
    assert br.height() <= w.half_thickness_scene() * 2 + 1.0
