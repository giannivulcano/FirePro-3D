"""LT5 A3 -- ``RenderOp.ends``: open strokes carry their end records (Q2).

Compiled through the real ``BlockDefinition._compile`` from real primitive
dicts; nested records through ``_nested_ops`` (``mapped`` +
``apply_overrides``), as the plan canvas and PDF receive them.
"""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform

from firepro3d import stroke_style as ss
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import (ArcItem, CircleItem, EllipseItem, LineItem,
                                   PolylineItem, RectangleItem,
                                   RegularPolygonItem, SplineItem)
from firepro3d.model_space import Model_Space
from firepro3d.render_op import STROKE, apply_overrides

_S = {"end": "end-s", "visible": True}
_F = {"end": "none", "visible": False, "mirrored": True}


def _poly(closed=False, coincident=False):
    p = PolylineItem(QPointF(0, 0))
    for q in ((100, 0), (100, -100)):
        p.append_point(QPointF(*q))
    if coincident:
        p.append_point(QPointF(0, 0))     # end on the start, flag still off
    if closed:
        p.append_point(QPointF(0, -100))
        p.close()
    return p


_CP = [QPointF(0, 0), QPointF(50, -60), QPointF(100, 0), QPointF(150, -40)]

# (factory, open?) -- the item's own closed predicate decides (Q2).
ITEMS = {
    "line": (lambda: LineItem(QPointF(0, 0), QPointF(100, 0)), True),
    "polyline_open": (_poly, True),
    "polyline_coincident_open": (lambda: _poly(coincident=True), True),
    "polyline_closed": (lambda: _poly(closed=True), False),
    "arc_open": (lambda: ArcItem(QPointF(0, 0), 50.0, 0.0, 90.0), True),
    "arc_full": (lambda: ArcItem(QPointF(0, 0), 50.0, 0.0, 360.0), False),
    "spline_open": (lambda: SplineItem(list(_CP)), True),
    "spline_periodic": (lambda: SplineItem(list(_CP), closed=True), False),
    "rect": (lambda: RectangleItem(QPointF(0, 0), QPointF(100, -50)), False),
    "circle": (lambda: CircleItem(QPointF(0, 0), 50.0), False),
    "ellipse": (lambda: EllipseItem(QPointF(0, 0), 80.0, 40.0), False),
    "polygon": (lambda: RegularPolygonItem(QPointF(0, 0), sides=6,
                                           radius_mm=50.0), False),
}


def _def(items, name="B"):
    prims = []
    for it in items:
        it.style["start"], it.style["finish"] = dict(_S), dict(_F)
        prims.append(it.to_dict())
    return BlockDefinition.new(name=name, library="L", series="S",
                               primitives=prims, origin=(0.0, 0.0))


@pytest.mark.parametrize("name", list(ITEMS))
def test_compile_captures_ends_for_open_strokes_only(qapp, name):
    factory, is_open = ITEMS[name]
    item = factory()
    assert ss.open_stroke(item) is is_open
    (op,) = [o for o in _def([item]).render_ops() if o.kind == STROKE]
    if is_open:
        assert op.ends == (_S, _F)
    else:
        assert op.ends is None


def test_ends_survive_a_load_round_trip(qapp):
    d = _def([ITEMS["arc_open"][0]()])
    d2 = BlockDefinition.from_dict(d.to_dict())
    (op,) = d2.render_ops()
    assert op.ends == (_S, _F)


def test_unstyled_and_text_ops_carry_no_ends(qapp):
    from firepro3d.geometry_2d import ReferenceLineItem
    ref = ReferenceLineItem(QPointF(0, 0), QPointF(10, 0))
    ref.printed = True
    d = BlockDefinition.new(name="R", library="L", series="S",
                            primitives=[ref.to_dict()], origin=(0.0, 0.0))
    assert all(op.ends is None for op in d.render_ops())


def test_mapped_and_overrides_carry_ends():
    d = _def([ITEMS["line"][0]()])
    (op,) = d.render_ops()
    moved = op.mapped(QTransform.fromTranslate(5.0, 7.0))
    assert moved.ends is op.ends and moved.pieces != op.pieces
    (ov,) = apply_overrides([op], weight="Heavy", linetype="continuous")
    assert ov.weight == "Heavy" and ov.ends is op.ends


def test_nested_record_ops_keep_their_ends(qapp):
    ms = Model_Space()
    inner = _def([ITEMS["polyline_open"][0](), ITEMS["rect"][0]()], "Inner")
    nested = {"type": "block_instance", "block_id": inner.id,
              "pos": [200.0, 0.0], "rotation": 30.0,
              "overrides": {"weight": "Heavy"}}
    outer = BlockDefinition.new(name="Outer", library="L", series="S",
                                primitives=[nested], origin=(0.0, 0.0))
    for d in (inner, outer):
        ms.register_block_definition(d)
    ops = [o for o in outer.render_ops() if o.kind == STROKE]
    assert [o.weight for o in ops] == ["Heavy", "Heavy"]     # override applied
    assert [o.ends for o in ops] == [(_S, _F), None]
