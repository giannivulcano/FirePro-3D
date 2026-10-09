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


def make_end(name, prims, trim=0.0, screen="scale"):
    """An end-type block (``end`` capability, origin = attach point);
    *screen* "fixed" = On screen Fixed size (ET1 Q6)."""
    end = {"trim": trim}
    if screen == "fixed":
        end["screen"] = "fixed"
    return BlockDefinition.new(name=name, library="L", series="End Types",
                               primitives=prims, origin=(0.0, 0.0), end=end)


def arrow(length=3.0, half=0.75, trim=None, screen="scale", name="Arrow"):
    """Filled closed triangle: tip at the attach point, base at x = -length;
    trim defaults to the length (the stroke stops at the base)."""
    return make_end(name, [_poly([(0.0, 0.0), (-length, -half), (-length, half)])],
                    trim=length if trim is None else trim, screen=screen)


def half_arrow(length=3.0, h=1.5, name="Half"):
    """Asymmetric one-sided barb on -Y only (mirror test, E5)."""
    return make_end(name, [_poly([(0.0, 0.0), (-length, 0.0), (-length, -h)])])


def _disc(radius):
    c = CircleItem(QPointF(0.0, 0.0), radius)
    c.fill_type = "solid"
    c.fill_opacity = 1.0
    return c.to_dict()


def dot(radius=0.5, name="Dot"):
    """Fixed filled disc (printed mm)."""
    return make_end(name, [_disc(radius)])


def tick(h=1.0, name="Tick"):
    """A stroke-only end: one vertical Line through the attach point."""
    return make_end(name, [LineItem(QPointF(0.0, -h), QPointF(0.0, h)).to_dict()])


def set_ends(item, start=None, finish=None, mirrored=False, scale=None):
    """Stamp explicit end refs (an id or "none") on a style record; *scale*
    (ET1 Q5) is written on each stamped end when given."""
    for key, ref in (("start", start), ("finish", finish)):
        if ref is not None:
            rec = {"end": ref, "visible": True}
            if mirrored:
                rec["mirrored"] = True
            if scale is not None:
                rec["scale"] = scale
            item.style[key] = rec


# ── Group D helpers (R2: one LT5 helper module) ─────────────────────────────

def v_end(name="Arrow", screen="scale", trim=0.0, length=3.0, half=1.0,
          library="L", series="End Types"):
    """An end block: an open V arrowhead pointing +X with its tip on the
    origin (two Lines (0,0)->(-length, +-half)); *screen* / *trim* set the
    ``end`` record (LT5 Q5: origin = attach point, +X = outward)."""
    prims = [LineItem(QPointF(0.0, 0.0), QPointF(-length, -half)).to_dict(),
             LineItem(QPointF(0.0, 0.0), QPointF(-length, half)).to_dict()]
    end = {"trim": trim}
    if screen == "fixed":
        end["screen"] = "fixed"
    return BlockDefinition.new(name=name, library=library, series=series,
                               primitives=prims, origin=(0.0, 0.0), end=end)


def end_id(ms, **kw):
    """Register a :func:`v_end` block on *ms*; return its id."""
    d = v_end(**kw)
    ms.register_block_definition(d)
    return d.id


def scene_line(ms, p1=(0.0, 0.0), p2=(30.0, 0.0), **style):
    """A LineItem in *ms*'s undo-snapshot draw list (+ a baseline step);
    *style* keys overwrite the style record (e.g. ``finish={...}``)."""
    ln = LineItem(QPointF(*p1), QPointF(*p2))
    for k, v in style.items():
        ln.style[k] = v
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    ms.push_undo_state()
    return ln
