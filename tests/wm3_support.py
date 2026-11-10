"""WM3 shared helpers: the composite "Sprinkler" test block (design G1).

Every component a placement Colour must reach, each authored in its own
colour and laid out so ``test_lt1_block_paper._render_model`` (scene
-400..400 mm onto 400 px, 0.5 px / mm, black ground, no antialiasing) shows
it in its own image box:

    circle    stroke  y=-200            red         row 100
    cross     stroke  y=0               Automatic   row 200
    deflector stroke  y=+200            blue        row 300
    end       stroke  (0,-300)-(200,-300) + Arrow end block   row 50
    text      "H" with a box border, a box fill (textfill) and a leader at (-300,-140)
    bound     "@[Tag]" bound text with a box border at (100,-140)
    fill      rectangle (100,60)-(300,140), solid background
    hatch     rectangle (-300,60)-(-100,140), shipped Horizontal pattern
    dots      stroke (-300,300)-(300,300) in a linetype with a dot symbol
"""
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor

from firepro3d import hatch_patterns as hp
from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition
from firepro3d.fill_layers import BackgroundLayer, FillLayers, PatternLayer
from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.text_item import TextAnnotationData, TextItem
from tests.lt3_support import make_linetype
from tests.lt5_support import arrow
from tests.wm2_support import nested_record, scene_with

#: The override colour the guards pick ("existing = grey", design G1). No
#: authored component uses it; canvas rendering is aliased, so every pixel of
#: a recoloured op is exactly this colour.
OVR = "#808080"

#: component -> authored colour (the raw source every "As Authored" assert cites)
AUTHORED = {"circle": "#ff0000", "cross": "token:auto", "deflector": "#0000ff",
            "end": "#ff8000", "text": "#ff00ff", "bound": "#ff0080",
            "fill": "#ffff00", "hatch": "#00ffff", "dots": "#8080ff",
            "textfill": "#406080"}      # the "H" text's box fill (keeps its colour, R3)

#: component -> image box (x0, y0, x1, y1), exclusive ends, in _render_model px
BOXES = {"circle": (300, 97, 340, 104), "cross": (300, 197, 340, 204),
         "deflector": (300, 297, 340, 304), "end": (200, 40, 320, 60),
         "text": (40, 120, 120, 160), "bound": (240, 120, 340, 160),
         "fill": (255, 235, 345, 265), "hatch": (55, 235, 145, 265),
         "dots": (60, 345, 340, 356)}

#: the scene's origin cross (theme-drawn, never part of the block)
ORIGIN_BOX = (185, 185, 216, 216)

#: the "H" text's leader (text_leader record): right edge -> tip at model (-170, -110)
LEADER = {"edge": "R", "t": 0.5, "shoulder_mm": 10.0, "tip_x": -170.0,
          "tip_y": -110.0, "end": "none", "weight": ""}


def _line(p1, p2, colour, **style):
    ln = LineItem(QPointF(*p1), QPointF(*p2))
    ln.style["colour"] = colour
    for k, v in style.items():
        ln.style[k] = v
    return ln.to_dict()


def _text(text, x, colour, leader=None, fill=""):
    return TextItem(TextAnnotationData(text=text, x=x, y=-140.0, height_mm=60.0,
                                       color=colour, border=True, fill_color=fill,
                                       leader=dict(leader) if leader else None)).to_dict()


def composite_defs(colour=None, name="Sprinkler", leader=True):
    """``(end, linetype, definition)`` of the composite block; *colour* set
    authors every component in that one colour EXCEPT the "H" text's box
    fill, which keeps ``AUTHORED["textfill"]`` (ruling R3) -- the "twin" a
    recoloured placement must match pixel for pixel. *leader* False drops
    the "H" leader (Explode re-seats a leader 1 px off -- pre-existing)."""
    c = {k: (v if k == "textfill" else (colour or v)) for k, v in AUTHORED.items()}
    end = arrow(length=0.4, half=0.15)
    lt = make_linetype(name="DotLT", dashes=((0.0, 40.0),), dots=(60.0,),
                       length=80.0, size="model")
    prims = [
        _line((-1500, -200), (1500, -200), c["circle"]),
        _line((-1500, 0), (1500, 0), c["cross"]),
        _line((-1500, 200), (1500, 200), c["deflector"]),
        _line((0, -300), (200, -300), c["end"],
              finish={"end": end.id, "visible": True}),
        _line((-300, 300), (300, 300), c["dots"], linetype=lt.id),
        _text("H", -300.0, c["text"], LEADER if leader else None, c["textfill"]),
        _text("@[Tag]", 100.0, c["bound"]),
    ]
    fill = RectangleItem(QPointF(100, 60), QPointF(300, 140))
    fill.style["colour"] = c["fill"]
    fill.fill_layers = FillLayers(background=BackgroundLayer(c["fill"], 1.0))
    hatch = RectangleItem(QPointF(-300, 60), QPointF(-100, 140))
    hatch.style["colour"] = c["hatch"]
    hatch.fill_layers = FillLayers(pattern=PatternLayer(hp.BUILTIN_HORIZONTAL,
                                                        c["hatch"], 1.0, 0.1))
    prims += [fill.to_dict(), hatch.to_dict()]
    d = BlockDefinition.new(name=name, library="L", series="S",
                            primitives=prims, origin=(0.0, 0.0))
    d.attributes = [normalise_attr({"key": "Tag", "default": "B"})]
    return end, lt, d


def composite_scene(shipped_hatches, overrides=None, colour=None, host_rec_ov=None):
    """A Model_Space with one placement of the composite block (or, with
    *host_rec_ov* not None, of a Host whose one nested record carries that
    override). Returns ``(ms, inst)`` -- hold *ms* for the test's lifetime."""
    end, lt, d = composite_defs(colour)
    defs = [end, lt, d]
    place = d.id
    if host_rec_ov is not None:
        host = BlockDefinition.new(name="Host", library="L", series="S",
                                   primitives=[nested_record(d.id, host_rec_ov)],
                                   origin=(0.0, 0.0))
        defs.append(host)
        place = host.id
    ms, inst = scene_with(defs, place, overrides)
    shipped_hatches(ms)
    inst.update()
    return ms, inst


def box_colours(img, box):
    """Distinct non-black colour names inside *box* (VC2: every pixel)."""
    x0, y0, x1, y1 = box
    return {QColor(img.pixel(x, y)).name() for x in range(x0, x1)
            for y in range(y0, y1)} - {"#000000"}


def lit_outside_origin(img):
    """Distinct non-black colour names over the whole image minus the origin cross."""
    ox0, oy0, ox1, oy1 = ORIGIN_BOX
    return {QColor(img.pixel(x, y)).name() for x in range(img.width())
            for y in range(img.height())
            if not (ox0 <= x < ox1 and oy0 <= y < oy1)} - {"#000000"}


def pdf_colours(pdf):
    """``(strokes, fills)``: Counters of the rounded RGB stroke / fill colour
    of every drawing strictly inside the sheet viewport box
    (``test_lt1_block_paper`` geometry) -- the block's ops and nothing else
    (VC2: every drawing counted)."""
    from collections import Counter
    import fitz
    from tests.test_lt1_block_paper import _VP_W, _VP_X, _VP_Y
    pt = 25.4 / 72.0
    strokes, fills = Counter(), Counter()
    doc = fitz.open(str(pdf))
    try:
        for dr in doc[0].get_drawings():
            r = dr["rect"]
            x0, y0, x1, y1 = (v * pt for v in (r.x0, r.y0, r.x1, r.y1))
            if not (_VP_X + 1 < x0 and x1 < _VP_X + _VP_W - 1
                    and _VP_Y + 1 < y0 and y1 < _VP_Y + _VP_W - 1):
                continue
            kind = dr.get("type") or ""
            if "s" in kind:
                strokes[tuple(round(v, 3) for v in dr["color"])] += 1
            if "f" in kind:
                fills[tuple(round(v, 3) for v in dr["fill"])] += 1
        return strokes, fills
    finally:
        doc.close()


def rgb(hexv):
    """A ``#rrggbb`` as the rounded 0..1 tuple PyMuPDF reports."""
    c = QColor(hexv)
    return (round(c.redF(), 3), round(c.greenF(), 3), round(c.blueF(), 3))
