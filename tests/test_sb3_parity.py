"""SB3 AC10 -- lifting bound_text_ops / paint_ops out of BlockInstance changes no
pixel and no op: goldens captured at base 23512cb3 by plan Task 0 (same machine,
same fonts -- regenerate with that script if the host font set changes)."""
import hashlib

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter

from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.room import Room

OPS_GOLDEN = "057e3d1c25d78f069866be6e0f5ff781093ed047d97fc938fbab4e2522b51ae6"
RENDER_GOLDEN = "0d799d5855bd4d4830fadae156d377c5f48179b28166d0e5acb5ab2656c8cfe2"


def _room(name="Office"):
    r = Room(boundary=[QPointF(0, 0), QPointF(6000, 0), QPointF(6000, 4000), QPointF(0, 4000)])
    r.name = name
    r.level = "Level 1"
    r._update_label()
    return r


def _render(scene, rect, w, h, bg=0xFF101010):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(bg)
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, w, h), rect, Qt.AspectRatioMode.IgnoreAspectRatio)
    p.end()
    return img


def _digest(img):
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    return hashlib.sha256(bytes(ptr)).hexdigest()


def _ops_digest(ops):
    h = hashlib.sha256()
    for op in ops:
        h.update(f"{op.kind}|{op.colour}|{op.text_frame}|{op.readable}|".encode())
        p = op.path
        for i in range(p.elementCount()):
            e = p.elementAt(i)
            h.update(f"{e.type.value}:{e.x:.3f}:{e.y:.3f};".encode())
    return h.hexdigest()


def _bound_instance():
    ms = Model_Space()
    room = _room()
    ms.addItem(room)
    ms._rooms.append(room)
    line = LineItem(QPointF(0, 0), QPointF(20, 0)).to_dict()
    prims = [line,
             {"type": "text", "text": "@[N]", "x": 0.0, "y": 0.0, "height_mm": 5.0, "angle": 0.0},
             {"type": "text", "text": "@[A]", "x": 0.0, "y": -10.0, "height_mm": 5.0, "angle": 0.0,
              "border": True}]
    d = BlockDefinition.new(name="Golden", library="", series="", origin=(0.0, 0.0),
                            primitives=prims)
    d.attributes = [normalise_attr({"key": "N", "source": "host", "host_key": "Name"}),
                    normalise_attr({"key": "A", "type": "number", "precision": 1,
                                    "source": "host", "host_key": "Area"})]
    d.host_category = "Room"
    ms.register_block_definition(d)
    inst = ms.place_block_instance(d.id, (0.0, 0.0), mirrored=True, scale=2.0)
    inst.element_host = room
    inst.refresh_bound()
    return ms, inst


def test_ac10_bound_ops_digest_unchanged_by_the_lift(qapp):
    _ms, inst = _bound_instance()
    assert _ops_digest(inst.render_ops()) == OPS_GOLDEN


def test_ac10_bound_instance_render_unchanged_by_the_lift(qapp):
    ms, _inst = _bound_instance()
    assert _digest(_render(ms, QRectF(-100.0, -100.0, 200.0, 200.0), 400, 400)) == RENDER_GOLDEN
