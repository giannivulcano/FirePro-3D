"""SB3 AC7 / G7 -- the approved RoomTag look is frozen: a pixel-sampled sha256 of the
reference scene (plan Task 0's three rooms, rebuilt here) rendered through the real System
tier (firepro3d/system_blocks/Tags/RoomTag.fpdb). The user approved this look at the visual
gate (U4, 2026-10-29: bound text hugs its value, 7021a2f5); the digest was captured by plan
Task 15 step 2 right after. A re-authored RoomTag re-runs the gate and re-captures; nothing
else may move these pixels."""
import hashlib

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter

from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space
from firepro3d.room import Room

ROOMS = [("Office", 0.0, 0.0), ("Lobby", 6000.0, 0.0), ("Storage", 0.0, 4000.0)]
VIEW = QRectF(-500.0, -500.0, 13000.0, 9000.0)      # 10 scene mm per px (as the Task 0 base shot)
PNG_W, PNG_H = 1300, 900
PAD_PX = 10
GOLDEN = "c29e7ae70c917d9d6f437fb25cca2fdec5d61111bf065fd9c9951f85f0d9f420"   # Task 15 step 2, 2026-10-29


def _room(name, x0, y0):
    r = Room(boundary=[QPointF(x0, y0), QPointF(x0 + 6000.0, y0),
                       QPointF(x0 + 6000.0, y0 + 4000.0), QPointF(x0, y0 + 4000.0)])
    r.name = name
    r.level = "Level 1"
    r._update_label()
    return r


def _digest(img):
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    return hashlib.sha256(bytes(ptr)).hexdigest()


def _sample_rect(tag):
    """The device-px window round the tag's scene bbox (+ PAD_PX): pixel-sampled, not the whole frame."""
    r = tag.sceneBoundingRect()
    sx, sy = PNG_W / VIEW.width(), PNG_H / VIEW.height()
    x0 = int((r.left() - VIEW.left()) * sx) - PAD_PX
    y0 = int((r.top() - VIEW.top()) * sy) - PAD_PX
    x1 = int((r.right() - VIEW.left()) * sx) + PAD_PX
    y1 = int((r.bottom() - VIEW.top()) * sy) + PAD_PX
    return QRect(x0, y0, x1 - x0, y1 - y0)


def test_g7_room_tag_pixels_locked(qapp, real_system_library):
    ms = Model_Space()
    ms._level_manager = LevelManager()
    rooms = []
    for name, x0, y0 in ROOMS:
        r = _room(name, x0, y0)
        r._scale_manager_ref = ms.scale_manager
        ms.addItem(r)
        ms._rooms.append(r)
        rooms.append(r)
    assert ms.annotation_block("Room") is not None            # the shipped RoomTag through SYSTEM_DEFAULTS
    assert all(r._tag.paints() for r in rooms)
    img = QImage(PNG_W, PNG_H, QImage.Format.Format_RGB32)
    img.fill(0xFF101010)
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, PNG_W, PNG_H), VIEW, Qt.AspectRatioMode.IgnoreAspectRatio)
    p.end()
    crop = img.copy(_sample_rect(rooms[0]._tag))               # the "Office" tag window
    assert crop.width() > 2 * PAD_PX and crop.height() > 2 * PAD_PX
    got = _digest(crop)
    assert got == GOLDEN, f"room-tag sample digest {got} (GOLDEN is {GOLDEN!r})"
