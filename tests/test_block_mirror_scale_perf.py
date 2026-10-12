"""Mirror / scale keeps the flyweight and the paint cost (design DD4, AC8).

1000 mirrored x2 instances of one definition share ONE variant op list, and
painting them stays within a relative bar of painting 1000 un-posed instances
(relative, never an absolute ms bar -- absolute bars fail under load).
"""
import time

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QStyleOptionGraphicsItem

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _scene_def():
    ms = Model_Space()
    d = BlockDefinition.new(name="P", library="L", series="S", origin=(0.0, 0.0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict(),
                                        LineItem(QPointF(0, 0), QPointF(0, -40)).to_dict()])
    ms.register_block_definition(d)
    return ms, d


def test_mirrored_scaled_instances_share_one_variant_list(qapp):
    ms, d = _scene_def()
    insts = [ms.place_block_instance(d.id, (i * 10.0, 0.0), mirrored=True, scale=2.0)
             for i in range(1000)]
    ops = [i.render_ops() for i in insts]
    assert all(o is ops[0] for o in ops)
    assert insts[0].render_ops() is d.render_ops_variant(True, 2.0)


def _paint_all(insts):
    img = QImage(64, 64, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    opt = QStyleOptionGraphicsItem()
    t0 = time.perf_counter()
    for i in insts:
        i.paint(p, opt, None)
    dt = time.perf_counter() - t0
    p.end()
    return dt


@pytest.mark.perf
def test_posed_paint_stays_within_a_relative_bar_of_unposed(qapp):
    ms, d = _scene_def()
    posed = [ms.place_block_instance(d.id, (i * 10.0, 0.0), mirrored=True, scale=2.0)
             for i in range(1000)]
    plain = [ms.place_block_instance(d.id, (i * 10.0, 50.0)) for i in range(1000)]
    _paint_all(posed), _paint_all(plain)              # warm caches (variant, posed path)
    best_posed = min(_paint_all(posed) for _ in range(3))
    best_plain = min(_paint_all(plain) for _ in range(3))
    assert best_posed <= 1.5 * best_plain + 0.05
