"""SB6 AC8 / G7 -- the approved shipped tag looks are frozen: a pixel-sampled sha256 of the
four tags (WallTag W1, DoorTag 101, WindowTag A, OpeningTag O1) rendered through the real
System tier (firepro3d/system_blocks/Tags/*.fpdb). Captured right after the user's mockup
approval (plan Task 1 Step 8); a re-authored tag re-runs the gate and re-captures."""
import hashlib

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter

from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space

TAGS = [("system-tags-walltag", "W1", 1000.0), ("system-tags-doortag", "101", 2500.0),
        ("system-tags-windowtag", "A", 4000.0), ("system-tags-openingtag", "O1", 5500.0)]
VIEW = QRectF(0.0, -1000.0, 7000.0, 2000.0)         # 5 scene units per px; every tag clear of the (0,0) origin cross
PNG_W, PNG_H = 1400, 400
PAD_PX = 10
GOLDEN = "2878cc3130b3c344aa08bd5d6b30e665f67ef8bb6bfaf61af5ee12f91387a11f"   # captured 2026-11-16 after the user's mockup approval (6d8dab58)


def _sample_rect(inst):
    r = inst.sceneBoundingRect()
    sx, sy = PNG_W / VIEW.width(), PNG_H / VIEW.height()
    x0 = int((r.left() - VIEW.left()) * sx) - PAD_PX
    y0 = int((r.top() - VIEW.top()) * sy) - PAD_PX
    x1 = int((r.right() - VIEW.left()) * sx) + PAD_PX
    y1 = int((r.bottom() - VIEW.top()) * sy) + PAD_PX
    return QRect(x0, y0, x1 - x0, y1 - y0)


def _bytes(img):
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    return bytes(ptr)


def test_g7_shipped_tag_pixels_locked(qapp, real_system_library):
    ms = Model_Space()
    ms._level_manager = LevelManager()
    try:
        insts = []
        for bid, mark, x in TAGS:
            assert ms.ensure_system_block(bid) is not None, bid
            inst = ms.place_block_instance(bid, (x, 0.0))
            inst.set_attributes({"Mark": mark})        # a host key's presence is its override (A4)
            insts.append(inst)
        img = QImage(PNG_W, PNG_H, QImage.Format.Format_RGB32)
        img.fill(0xFF101010)
        p = QPainter(img)
        ms.render(p, QRectF(0, 0, PNG_W, PNG_H), VIEW, Qt.AspectRatioMode.IgnoreAspectRatio)
        p.end()
        h = hashlib.sha256()
        for inst in insts:
            crop = img.copy(_sample_rect(inst))
            assert crop.width() > 2 * PAD_PX and crop.height() > 2 * PAD_PX
            h.update(_bytes(crop))
        got = h.hexdigest()
        assert got == GOLDEN, f"shipped-tag sample digest {got} (GOLDEN is {GOLDEN!r})"
    finally:
        ms.cleanup()
