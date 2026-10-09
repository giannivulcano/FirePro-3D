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


_DEFAULT_EXTENT = QRectF(0, 0, 1000, 1000)   # the plan / elevation empty rule
_EXTENT_PAD_FRAC = 0.02    # per side, of the larger extent dimension
_EXTENT_PAD_MIN_MM = 1.0   # so edge strokes are never half-clipped


def _is_scaffold(item) -> bool:
    """A non-printed reference line is scaffolding (D23) -- never extent."""
    return isinstance(item, ReferenceLineItem) and not getattr(item, "printed", False)


class SchematicSceneManager:
    """One off-screen render scene per placed schematic (concept SD2).

    Each scene is a ``Model_Space(scene_role="block_editor")`` borrowing the
    project registry, materialized from the definition and rebuilt **in
    place** when the definition changes (cache key: the definition object
    (identity) + version -- project undo restores new definition objects). Rebuilds happen only in
    :meth:`scene_for` (called from ``ViewResolver.resolve``, never mid-paint).
    Render scenes outlive every ``PaperScene``, including export temp scenes.

    Args:
        project_scene: The project ``Model_Space`` whose registry holds the
            schematic definitions.
    """

    def __init__(self, project_scene):
        self._project = project_scene
        self._scenes: dict = {}
        self._keys: dict = {}
        project_scene.blockDefinitionsChanged.connect(self._on_definitions_changed)

    def _schematic(self, block_id):
        d = self._project.get_block_definition(block_id)
        return d if d is not None and d.kind == "schematic" else None

    def display_name(self, block_id) -> "str | None":
        """The schematic's current name, or None when it is not one."""
        d = self._schematic(block_id)
        return d.name if d is not None else None

    def live_ids(self) -> set:
        """Ids that currently own a render scene."""
        return set(self._scenes)

    def scene_for(self, block_id):
        """The render scene for *block_id*, built / rebuilt as needed.

        Returns:
            The ``Model_Space``, or None (and any old scene disposed) when
            *block_id* is not a schematic in the project.
        """
        d = self._schematic(block_id)
        if d is None:
            self.dispose(block_id)
            return None
        sc = self._scenes.get(block_id)
        if sc is None:
            from .model_space import Model_Space
            sc = Model_Space(scene_role="block_editor")
            sc._hatch_paper_scale = None           # explicit: the paper override pass sets/clears it per viewport render
            sc._suppress_preview_node = True
            sc.borrow_block_registry(self._project.block_registry,
                                     owner=self._project)
            self._scenes[block_id] = sc
        cached = self._keys.get(block_id)
        if cached is None or cached[0] is not d or cached[1] != d.version:
            clear_materialized(sc)
            materialize_primitives(sc, d.primitives)
            self._keys[block_id] = (d, d.version)
        return sc

    def extent(self, block_id) -> "QRectF | None":
        """Padded pen-free bounds of the built scene (None if not built).

        Recomputed each call so a nested block's edit re-fits the viewport.
        """
        sc = self._scenes.get(block_id)
        if sc is None:
            return None
        from .geometry_import import geometric_bounds
        rect = geometric_bounds([it for it in materialized_items(sc)
                                 if not _is_scaffold(it)])
        if rect is None:
            return QRectF(_DEFAULT_EXTENT)
        pad = max(_EXTENT_PAD_MIN_MM,
                  _EXTENT_PAD_FRAC * max(rect.width(), rect.height()))
        return rect.adjusted(-pad, -pad, pad, pad)

    def dispose(self, block_id) -> None:
        """Drop *block_id*'s render scene and detach it from the registry."""
        sc = self._scenes.pop(block_id, None)
        self._keys.pop(block_id, None)
        if sc is not None:
            sc.block_registry.detach_scene(sc)

    def dispose_all(self) -> None:
        """Drop every render scene (project load / new file / teardown)."""
        for bid in list(self._scenes):
            self.dispose(bid)

    def _on_definitions_changed(self) -> None:
        for bid in list(self._scenes):
            if self._schematic(bid) is None:
                self.dispose(bid)
