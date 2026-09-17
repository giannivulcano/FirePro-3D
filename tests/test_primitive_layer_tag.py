"""Slice 1 guard — reference-graphic unification: primitive dicts carry a `layer` tag.

The unified import pipeline (R1) must preserve per-source-layer identity onto the
native primitives, so a reference definition can batch-compile per layer. These
guards lock:

  * ``geom_dicts_to_primitives`` threads the source ``layer`` onto every primitive
    kind (it was dropped before this slice).
  * The ``layer`` tag round-trips through ``to_dict``/``from_dict`` on every
    ``Geometry2DMixin`` primitive.
  * An untagged primitive defaults to ``""`` and OMITS ``layer`` from ``to_dict``
    (backward-compat: authored-block/serialization dicts are unchanged).

See docs/specs/reference-graphic-model.md → Implementation → "Layer-tagged primitives".
"""

from __future__ import annotations

from firepro3d.geometry_import import geom_dicts_to_primitives
from firepro3d.geometry_2d import (
    LineItem, CircleItem, PolylineItem, ArcItem, EllipseItem, SplineItem,
)


# One representative geom dict per supported import kind, each tagged with a layer.
_TAGGED_GEOMS = [
    {"kind": "line", "layer": "WALLS", "color": "#ffffff",
     "x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 0.0},
    {"kind": "circle", "layer": "COLS", "color": "#ffffff",
     "x": 0.0, "y": 0.0, "w": 4.0, "h": 4.0},
    {"kind": "path_points", "layer": "GRID", "color": "#ffffff",
     "points": [(0.0, 0.0), (1.0, 1.0), (2.0, 0.0)], "closed": False},
    {"kind": "arc", "layer": "ARCS", "color": "#ffffff",
     "rx": 0.0, "ry": 0.0, "rw": 4.0, "rh": 4.0, "start": 0.0, "span": 90.0},
    {"kind": "ellipse_full", "layer": "ELLIP", "color": "#ffffff",
     "pos_cx": 0.0, "pos_cy": 0.0, "w": 6.0, "h": 4.0, "rotation": 0.0},
    {"kind": "spline", "layer": "SPLN", "color": "#ffffff",
     "control_points": [(0.0, 0.0), (1.0, 2.0), (3.0, 0.0)], "degree": 2},
]


def test_import_threads_layer_onto_every_kind(qapp):
    """Every primitive built from a tagged geom dict carries its source layer."""
    items, skipped = geom_dicts_to_primitives(_TAGGED_GEOMS)
    assert skipped == 0
    assert len(items) == len(_TAGGED_GEOMS)
    got = [it.layer for it in items]
    assert got == ["WALLS", "COLS", "GRID", "ARCS", "ELLIP", "SPLN"]


def test_import_untagged_geom_defaults_layer_empty(qapp):
    """A geom dict with no ``layer`` key yields a primitive with ``layer == ''``."""
    items, _ = geom_dicts_to_primitives(
        [{"kind": "line", "color": "#ffffff",
          "x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 1.0}])
    assert len(items) == 1
    assert items[0].layer == ""


def test_layer_roundtrips_through_to_from_dict(qapp):
    """A ``layer`` set on any primitive survives a to_dict -> from_dict round-trip."""
    from PyQt6.QtCore import QPointF
    samples = [
        LineItem(QPointF(0, 0), QPointF(1, 1)),
        CircleItem(QPointF(0, 0), 2.0),
        PolylineItem(QPointF(0, 0)),
        ArcItem(QPointF(0, 0), 2.0, 0.0, 90.0),
        EllipseItem(QPointF(0, 0), 3.0, 2.0, 0.0),
        SplineItem([QPointF(0, 0), QPointF(1, 1), QPointF(2, 0)], 2),
    ]
    for it in samples:
        it.layer = "REF_LAYER"
        d = it.to_dict()
        assert d.get("layer") == "REF_LAYER", type(it).__name__
        restored = type(it).from_dict(d)
        assert restored.layer == "REF_LAYER", type(it).__name__


def test_untagged_primitive_omits_layer_from_dict(qapp):
    """An untagged primitive keeps ``layer`` OUT of to_dict (backward-compat)."""
    from PyQt6.QtCore import QPointF
    it = LineItem(QPointF(0, 0), QPointF(1, 1))
    assert it.layer == ""
    assert "layer" not in it.to_dict()
