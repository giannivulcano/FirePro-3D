"""Schematic render scenes + the one primitive materializer.

Governing spec: ``docs/specs/schematics.md`` (D-S10, D-S12) and the concept
doc's SD2 / "SV2 delta". The materializer turns a definition's primitive
dicts into live scene items; the Block Editor (seeding) and the render scenes
(``SchematicSceneManager``) are its two callers.
"""
from __future__ import annotations

from PyQt6.QtCore import QRectF

from .block_definition import _PRIMITIVE_FACTORY
from .geometry_2d import (
    ArcItem, CircleItem, EllipseItem, LineItem, PolylineItem, RectangleItem,
    ReferenceLineItem, RegularPolygonItem, SplineItem,
)
from .text_item import TextItem

_CLS_TO_LIST = {
    # Subclass before base (lookup is exact type(item), but keep the guard order).
    ReferenceLineItem: "_reference_lines",
    LineItem: "_draw_lines", RectangleItem: "_draw_rects",
    CircleItem: "_draw_circles", ArcItem: "_draw_arcs",
    EllipseItem: "_draw_ellipses",
    SplineItem: "_draw_splines",
    PolylineItem: "_polylines", RegularPolygonItem: "_draw_polygons",
    TextItem: "_texts",
}

# gather order: drawn primitives + text, then nested blocks, then reference lines
_PRIMITIVE_LISTS = ("_draw_lines", "_draw_rects", "_draw_circles",
                    "_draw_arcs", "_draw_ellipses", "_draw_splines",
                    "_polylines", "_draw_polygons", "_texts")


def add_primitive(scene, item) -> None:
    """Add a construction primitive to *scene* and its tracking list."""
    scene.addItem(item)
    list_attr = _CLS_TO_LIST.get(type(item))
    if list_attr is not None:
        getattr(scene, list_attr).append(item)


def materialize_primitives(scene, prim_dicts) -> None:
    """Build live items in *scene* from definition primitive dicts.

    Nested ``block_instance`` records become real ``BlockInstance``s resolved
    through *scene*'s (borrowed) registry; unknown types are skipped.
    """
    for d in prim_dicts:
        if d.get("type") == "block_instance":
            pos = d.get("pos", [0.0, 0.0])
            scene.place_block_instance(
                d["block_id"], (pos[0], pos[1]), rotation=d.get("rotation", 0.0),
                uid=d.get("uid"), overrides=d.get("overrides"))
            continue
        cls = _PRIMITIVE_FACTORY.get(d.get("type"))
        if cls is None:
            continue
        add_primitive(scene, cls.from_dict(d))


def materialized_items(scene) -> list:
    """The scene's construction primitives in stable order (tracking lists,
    then nested blocks, then reference lines)."""
    items = []
    for attr in _PRIMITIVE_LISTS:
        items.extend(getattr(scene, attr))
    items.extend(getattr(scene, "_block_instances", []))
    items.extend(getattr(scene, "_reference_lines", []))
    return items


def clear_materialized(scene) -> None:
    """Remove every materialized item from *scene* (rebuild-in-place)."""
    for attr in _PRIMITIVE_LISTS + ("_reference_lines",):
        lst = getattr(scene, attr)
        for it in list(lst):
            if it.scene() is scene:
                scene.removeItem(it)
        lst.clear()
    for inst in list(getattr(scene, "_block_instances", [])):
        scene.remove_block_instance(inst)
