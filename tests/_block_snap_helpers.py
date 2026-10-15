"""Shared builders for the block-primitive SNAP / ALIGN / HALO guards.

Definition-local coordinates are written by hand here; scene expectations go
through ``oracle`` (the instance's own full pose, block-system DD2) or an
Exploded twin scene — never through the posed-primitive code under test.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition, _nested_pose

# The snap block (definition-local, origin (0, 0)):
#   L1  line   (60,-80)-(180,-80)      mid (120,-80)
#   V   line   (120,0)-(120,120)       crosses C at (120, 60 -+ sqrt(1200))
#   C   circle centre (100,60) r 40
#   R   rect   x -160..-60, y -40..40  (hollow)
#   A   arc    centre (-100,100) r 30, 0..180 deg
#   N   nested Inner at pos (-110,-100) rot 30 scale 1.2; Inner = circle
#       centre (20,0) r 15 (so the nested insertion point is NOT its centre)
V_X = 120.0
C_C, C_R = (100.0, 60.0), 40.0
INT_DY = math.sqrt(C_R ** 2 - (V_X - C_C[0]) ** 2)       # 34.641...
NEST_REC_POSE = {"pos": [-110.0, -100.0], "rotation": 30.0,
                 "mirrored": False, "scale": 1.2}


def _prim(kind, **kw):
    return {"type": kind, "color": "#ffffff", "lineweight": 1.0, **kw}


def snap_prims():
    return [
        _prim("draw_line", pt1=[60.0, -80.0], pt2=[180.0, -80.0]),
        _prim("draw_line", pt1=[V_X, 0.0], pt2=[V_X, 120.0]),
        _prim("draw_circle", cx=C_C[0], cy=C_C[1], radius=C_R),
        _prim("draw_rectangle", x=-160.0, y=-40.0, w=100.0, h=80.0),
        _prim("arc", cx=-100.0, cy=100.0, radius=30.0,
              start_deg=0.0, span_deg=180.0),
    ]


def register_snap_block(scene, nested: bool = True) -> BlockDefinition:
    """Register Inner (when *nested*) and the snap block; return the outer def."""
    prims = snap_prims()
    if nested:
        inner = BlockDefinition.new(
            name="Inner", library="L", series="S", origin=(0.0, 0.0),
            primitives=[_prim("draw_circle", cx=20.0, cy=0.0, radius=15.0)])
        scene.register_block_definition(inner)
        prims.append({"type": "block_instance", "block_id": inner.id,
                      **NEST_REC_POSE})
    d = BlockDefinition.new(name="Snap", library="L", series="S",
                            origin=(0.0, 0.0), primitives=prims)
    scene.register_block_definition(d)
    return d


def oracle(inst, x: float, y: float) -> QPointF:
    """Scene point of definition-local (x, y) under the instance's full pose."""
    return inst.full_pose_transform().map(QPointF(x, y))


def nested_oracle(inst, x: float, y: float) -> QPointF:
    """Scene point of Inner-local (x, y) inside the nested record N."""
    rec = {"type": "block_instance", **NEST_REC_POSE}
    return inst.full_pose_transform().map(_nested_pose(rec).map(QPointF(x, y)))


def near(p: QPointF, q: QPointF, tol: float = 0.01) -> bool:
    return math.hypot(p.x() - q.x(), p.y() - q.y()) <= tol


# Poses: (pos, rotation, mirrored, scale). All keep the block on screen in
# make_view(scale=1.0) (+-400 x +-300).
POSES = [
    ((40.0, 20.0), 0.0, False, 1.0),
    ((50.0, -30.0), 90.0, True, 1.5),
    ((-40.0, 20.0), 33.0, False, 0.8),
]
POSE_IDS = ["plain", "rot90-mirror-x1.5", "rot33-x0.8"]
