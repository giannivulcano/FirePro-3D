"""C1: Room canvas-selection restricted to its label-background rect when a
label is visible; falls back to the full polygon when there is no visible
label. Room.shape() is intentionally NOT narrowed (paint-culling); the
restriction lives in the HALO candidate gather + rubber-band commit.
"""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QTransform

from firepro3d.model_space import Model_Space
from firepro3d.room import Room


def _room(sc, with_label=True):
    """Build a real Room, add it to the scene, set/clear its name+label."""
    boundary = [QPointF(0, 0), QPointF(2000, 0),
                QPointF(2000, 2000), QPointF(0, 2000)]
    r = Room(boundary=boundary)
    if with_label:
        r.name = "R1"
        r._tag = "R1"
    else:
        r.name = ""
        r._tag = ""
    sc.addItem(r)
    sc._rooms.append(r)
    r._update_label()
    return r


def test_label_scene_rect_none_when_no_label(qapp):
    sc = Model_Space()
    r = _room(sc, with_label=False)
    assert r.label_scene_rect() is None


def test_labelled_room_has_label_scene_rect(qapp):
    sc = Model_Space()
    r = _room(sc, with_label=True)
    lr = r.label_scene_rect()
    assert lr is not None
    assert isinstance(lr, QRectF)
    assert not lr.isEmpty()


def test_labelled_room_candidate_only_via_label_rect(qapp):
    sc = Model_Space()
    r = _room(sc, with_label=True)
    lr = r.label_scene_rect()
    assert lr is not None
    # A point well inside the polygon but OUTSIDE the label rect (up-left of
    # the label, still inside the 0..2000 square) -> room not a candidate.
    interior = QPointF(lr.left() - 300, lr.top() - 300)
    assert 0 < interior.x() < 2000 and 0 < interior.y() < 2000
    assert r not in sc.halo_candidates_at(interior, 4.0, QTransform())
    # A point on the label rect -> room IS a candidate.
    assert r in sc.halo_candidates_at(lr.center(), 4.0, QTransform())


def test_labelless_room_falls_back_to_polygon(qapp):
    sc = Model_Space()
    r = _room(sc, with_label=False)
    assert r in sc.halo_candidates_at(QPointF(1000, 1000), 4.0, QTransform())
