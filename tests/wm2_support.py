"""WM2 shared helpers: the spec's "Sprinkler" test block as three
horizontal lines (one per component) the canvas / PDF probes can tell apart
by position. Model y -200 / 0 / +200 -> render rows 100 / 200 / 300
(``test_lt1_block_paper._render_model``: scene -400..400 mm onto 400 px)."""
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.test_lt1_block_paper import _HALF_LEN

#: component -> (model y, authored weight)
SPRINKLER = {"circle": (-200.0, "Thickest"),
             "cross": (0.0, "Thinnest"),
             "deflector": (200.0, "Thin")}
ROWS = {"circle": 100, "cross": 200, "deflector": 300}
COL = 320                                       # clear of the origin cross


def sprinkler_def(weights=None, linetype="continuous", name="Sprinkler"):
    """The three-line Sprinkler definition (per-component weight overrides)."""
    prims = []
    for comp, (y, w) in SPRINKLER.items():
        ln = LineItem(QPointF(-_HALF_LEN, y), QPointF(_HALF_LEN, y))
        ln.style["weight"] = (weights or {}).get(comp, w)
        ln.style["linetype"] = linetype
        prims.append(ln.to_dict())
    return BlockDefinition.new(name=name, library="L", series="S",
                               primitives=prims, origin=(0.0, 0.0))


def scene_with(defs, place_id, overrides=None):
    """A Model_Space holding *defs* with one placement of *place_id*."""
    ms = Model_Space()
    for d in defs:
        ms.register_block_definition(d)
    inst = ms.place_block_instance(place_id, (0.0, 0.0), level=ms.active_level,
                                   overrides=overrides)
    return ms, inst


def nested_record(block_id, overrides=None):
    """A D2 nested ``block_instance`` record (optional override)."""
    rec = {"type": "block_instance", "block_id": block_id,
           "pos": [0, 0], "rotation": 0.0}
    if overrides:
        rec["overrides"] = dict(overrides)
    return rec
