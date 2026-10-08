"""LT5 shared test helpers: hand-made end-type blocks (the authoring UI is
Group D). Origin = attach point, +X = outward (Q5); scene Y-down, so -Y is
"above" the axis on screen."""
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import CircleItem, LineItem, PolylineItem


def _poly(points, closed=True, fill=True):
    pl = PolylineItem(QPointF(*points[0]))
    for p in points[1:]:
        pl.append_point(QPointF(*p))
    if closed:
        pl.close()
    if fill:
        pl.fill_type = "solid"
        pl.fill_opacity = 1.0          # an authored end fill is opaque
    return pl.to_dict()


def make_end(name, prims, size="fixed", trim=0.0):
    """An end-type block (``end`` capability, origin = attach point)."""
    return BlockDefinition.new(name=name, library="L", series="End Types",
                               primitives=prims, origin=(0.0, 0.0),
                               end={"size": size, "trim": trim})


def arrow(length=3.0, half=0.75, trim=None, size="fixed", name="Arrow"):
    """Filled closed triangle: tip at the attach point, base at x = -length;
    trim defaults to the length (the stroke stops at the base)."""
    return make_end(name, [_poly([(0.0, 0.0), (-length, -half), (-length, half)])],
                    size=size, trim=length if trim is None else trim)


def half_arrow(length=3.0, h=1.5, name="Half"):
    """Asymmetric one-sided barb on -Y only (mirror test, E5)."""
    return make_end(name, [_poly([(0.0, 0.0), (-length, 0.0), (-length, -h)])])


def _disc(radius):
    c = CircleItem(QPointF(0.0, 0.0), radius)
    c.fill_type = "solid"
    c.fill_opacity = 1.0
    return c.to_dict()


def round_end(radius=0.5, name="Round"):
    """Weight-relative filled disc: radius 0.5 = half the line's weight."""
    return make_end(name, [_disc(radius)], size="weight_relative")


def dot(radius=0.5, name="Dot"):
    """Fixed filled disc (printed mm)."""
    return make_end(name, [_disc(radius)])


def tick(h=1.0, name="Tick"):
    """A stroke-only end: one vertical Line through the attach point."""
    return make_end(name, [LineItem(QPointF(0.0, -h), QPointF(0.0, h)).to_dict()])


def set_ends(item, start=None, finish=None, mirrored=False):
    """Stamp explicit end refs (an id or "none") on a style record."""
    for key, ref in (("start", start), ("finish", finish)):
        if ref is not None:
            rec = {"end": ref, "visible": True}
            if mirrored:
                rec["mirrored"] = True
            item.style[key] = rec
