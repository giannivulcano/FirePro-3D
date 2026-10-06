"""Shared LT3 test helpers: hand-made linetype blocks (no authoring UI in LT3)."""
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem


def make_linetype(name="Hidden", dashes=((0.0, 6.0),), dots=(), length=9.0,
                  size="drafting", weight=None, screen="scale"):
    """A repeat block: axis Lines [start, start+len] are dashes, zero-length
    axis Lines are dots (LT3-3). *weight* sets every dash's style weight;
    *screen* "fixed" makes it a Fixed on-screen linetype (LTS-1)."""
    prims = []
    for st, ln in dashes:
        it = LineItem(QPointF(st, 0.0), QPointF(st + ln, 0.0))
        if weight:
            it.style["weight"] = weight
        prims.append(it.to_dict())
    for x in dots:
        prims.append(LineItem(QPointF(x, 0.0), QPointF(x, 0.0)).to_dict())
    rep = {"length": length, "size": size}
    if screen == "fixed":
        rep["screen"] = "fixed"
    return BlockDefinition.new(name=name, library="L", series="Linetypes",
                               primitives=prims, origin=(0.0, 0.0),
                               repeat=rep)


def hidden(ms, **kw):
    """Register a Hidden (6 dash / 3 gap) linetype on *ms*; return its id."""
    d = make_linetype(**kw)
    ms.register_block_definition(d)
    return d.id
