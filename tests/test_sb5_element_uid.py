"""SB5 Task 2 -- element_uid helpers; uid on the to_dict / from_dict classes
(design section 1, Q1; AC1 for these kinds)."""
from PyQt6.QtCore import QPointF, QRectF

from firepro3d import element_uid
from firepro3d.detail_view import DetailMarker
from firepro3d.floor_opening import FloorOpening
from firepro3d.floor_slab import FloorSlab
from firepro3d.roof import RoofItem
from firepro3d.room import Room
from firepro3d.section_marker import SectionMarker
from firepro3d.wall import WallSegment
from firepro3d.wall_opening import WallOpening
from tests._ph1_helpers import SQ, VOID


def _all():
    room = Room(list(SQ))
    slab = FloorSlab(points=list(SQ))
    void = FloorOpening(list(VOID), host=slab)
    slab.add_opening(void)
    roof = RoofItem(list(SQ))
    wall = WallSegment(QPointF(0, 0), QPointF(4000, 0))
    door = WallOpening(wall, feature_id="door_914", offset_along=1000.0)
    wall.openings.append(door)
    sec = SectionMarker("Section 1", QPointF(0, 0), QPointF(5000, 0), 1, 3000.0)
    det = DetailMarker("Detail 1", QRectF(0, 0, 1000, 1000))
    return room, slab, void, roof, wall, door, sec, det


def test_new_uid_is_32_hex_and_unique():
    a, b = element_uid.new_uid(), element_uid.new_uid()
    assert len(a) == 32 and int(a, 16) >= 0 and a != b


def test_every_dict_class_mints_a_distinct_uid(qapp):
    uids = [it._uid for it in _all()]
    assert all(isinstance(u, str) and len(u) == 32 for u in uids)
    assert len(set(uids)) == len(uids)


def test_to_dict_from_dict_round_trip_the_uid(qapp):
    room, slab, void, roof, wall, door, sec, det = _all()
    assert room.to_dict()["uid"] == room._uid
    assert Room.from_dict(room.to_dict())._uid == room._uid
    s2 = FloorSlab.from_dict(slab.to_dict())
    assert s2._uid == slab._uid and s2.openings[0]._uid == void._uid
    assert RoofItem.from_dict(roof.to_dict())._uid == roof._uid
    assert wall.to_dict()["openings"][0]["uid"] == door._uid
    assert WallOpening.from_dict(door.to_dict(), wall=wall)._uid == door._uid
    assert SectionMarker.from_dict(sec.to_dict())._uid == sec._uid
    assert DetailMarker.from_dict(det.to_dict())._uid == det._uid


def test_a_record_without_uid_keeps_the_constructor_mint(qapp):
    room = _all()[0]
    d = element_uid.without_uid(room.to_dict())
    assert "uid" not in d
    r1, r2 = Room.from_dict(d), Room.from_dict(d)
    assert len(r1._uid) == 32 and len({r1._uid, r2._uid, room._uid}) == 3


def test_uid_from_dict_on_an_unindexed_item_just_sets_it(qapp):
    room = _all()[0]
    element_uid.uid_from_dict(room, {"uid": "a" * 32})
    assert room._uid == "a" * 32
    element_uid.uid_from_dict(room, {"uid": ""})          # junk keeps the current uid
    element_uid.uid_from_dict(room, {"uid": 7})
    element_uid.uid_from_dict(room, None)
    assert room._uid == "a" * 32
