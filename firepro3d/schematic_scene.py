"""Schematic render scenes + the one primitive materializer.

Governing spec: ``docs/specs/schematics.md`` (D-S10, D-S12) and the concept
doc's SD2 / "SV2 delta". The materializer turns a definition's primitive
dicts into live scene items; the Block Editor (seeding) and the render scenes
(``SchematicSceneManager``) are its two callers.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import QRectF

from .block_definition import _PRIMITIVE_FACTORY, is_scaffold_item
from .geometry_2d import (
    ArcItem, CircleItem, EllipseItem, LineItem, PolylineItem, RectangleItem,
    RegularPolygonItem, SplineItem,
)
from .filled_region import FilledRegionItem
from .text_item import TextItem

log = logging.getLogger("FirePro3D")

_CLS_TO_LIST = {
    # Reference shapes stay in their class's list (design RG1).
    LineItem: "_draw_lines", RectangleItem: "_draw_rects",
    CircleItem: "_draw_circles", ArcItem: "_draw_arcs",
    EllipseItem: "_draw_ellipses",
    SplineItem: "_draw_splines",
    PolylineItem: "_polylines", RegularPolygonItem: "_draw_polygons",
    FilledRegionItem: "_filled_regions",
    TextItem: "_texts",
}

# gather order: drawn primitives + text (reference shapes included), then nested blocks
_PRIMITIVE_LISTS = ("_draw_lines", "_draw_rects", "_draw_circles",
                    "_draw_arcs", "_draw_ellipses", "_draw_splines",
                    "_polylines", "_draw_polygons", "_filled_regions", "_texts")


def add_primitive(scene, item) -> None:
    """Add a construction primitive to *scene* and its tracking list."""
    scene.addItem(item)
    list_attr = _CLS_TO_LIST.get(type(item))
    if list_attr is not None:
        getattr(scene, list_attr).append(item)
    if getattr(item, "reference", False):            # RG18: the category colour
        from .display_manager import refresh_category_display
        refresh_category_display(item)


def materialize_primitives(scene, prim_dicts) -> None:
    """Build live items in *scene* from definition primitive dicts.

    Nested ``block_instance`` records become real ``BlockInstance``s resolved
    through *scene*'s (borrowed) registry; unknown types are skipped.
    """
    for d in prim_dicts:
        if d.get("type") == "block_instance":
            from .block_instance import BlockInstance
            pos = d.get("pos", [0.0, 0.0])
            # A nested record never carries a host; a None return (unresolved host) is
            # simply not placed -- same as this loop skipping an unknown type.
            scene.place_block_instance(d["block_id"], (pos[0], pos[1]),
                                       uid=d.get("uid"), **BlockInstance.place_kwargs(d))
            continue
        cls = _PRIMITIVE_FACTORY.get(d.get("type"))
        if cls is None:
            continue
        add_primitive(scene, cls.from_dict(d))


def materialized_items(scene) -> list:
    """The scene's construction primitives in stable order (tracking lists,
    then nested blocks)."""
    items = []
    for attr in _PRIMITIVE_LISTS:
        items.extend(getattr(scene, attr))
    items.extend(getattr(scene, "_block_instances", []))
    return items


def _with_leaders(rect: QRectF, items: list) -> QRectF:
    """*rect* grown to hold every text leader's elbow and tip, so a note reaching
    past the drawing is not cropped at the viewport (notes design N17)."""
    from .text_item import TextItem
    pts = [p for it in items if isinstance(it, TextItem) and it.data.leader
           for p in it.grip_points()[TextItem.LEADER_KNEE_GRIP:]]
    if not pts:
        return rect
    left = min([rect.left()] + [p.x() for p in pts])
    top = min([rect.top()] + [p.y() for p in pts])
    right = max([rect.right()] + [p.x() for p in pts])
    bottom = max([rect.bottom()] + [p.y() for p in pts])
    return QRectF(left, top, right - left, bottom - top)


def clear_materialized(scene) -> None:
    """Remove every materialized item from *scene* (rebuild-in-place)."""
    for attr in _PRIMITIVE_LISTS:
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

PRINTED_SAVE_VERSION = 12  # files below it hold schematics from before Printed text (N13)
_TEXT_TYPE = "text"        # block_definition._PRIMITIVE_FACTORY key of TextItem
_SCALE_DECIMALS = 3        # a fitted NTS scale: paper_space.float_to_scale_str's label precision


def _first_viewport(project, block_id):
    """The first viewport of schematic *block_id* in sheet order, or None."""
    for sheet in getattr(project, "_sheets", ()):
        for data in sheet.sheet_views:
            if data.source_view_type == "schematic" and data.source_view_name == block_id:
                return data
    return None


def _viewport_scale(mgr, block_id, data) -> "float | None":
    """Paper mm per model mm of *data*: its true scale, else its NTS fit, the
    ``SheetViewport.paint`` rule over the live extent. None with no extent."""
    if data.scale > 0.0:
        return data.scale
    mgr.scene_for(block_id)
    extent = mgr.extent(block_id)
    if extent is None or extent.isEmpty() or data.w <= 0.0 or data.h <= 0.0:
        return None
    return min(data.w / extent.width(), data.h / extent.height())


def migrate_old_schematics(project, version) -> None:
    """Turn every schematic of a file below ``PRINTED_SAVE_VERSION`` Printed (N13).

    Runs once per file: a saved file carries the new version, so Real size chosen
    afterwards stays. Text keeps the size its first viewport printed: N = 1 / S
    leaves the N15 paint factor at 1 there. With no text, or no sheet, nothing has
    a printed size to keep, so the schematic starts at the project scale as a new
    one does (N12). Stored heights are untouched.

    Args:
        project: The loaded ``Model_Space``, its definitions and sheets in place.
        version: The file's ``version``; a non-numeric one counts as oldest.
    """
    try:
        if int(version) >= PRINTED_SAVE_VERSION:
            return
    except (TypeError, ValueError):
        pass
    old = [d for d in project._block_definitions.values()
           if d.kind == "schematic" and d.text_sizing is None]
    if not old:
        return
    from .annotative import _drawing_scale
    default = _drawing_scale(project)
    mgr = SchematicSceneManager(project)
    try:
        for defn in old:
            data = _first_viewport(project, defn.id)
            has_text = any(p.get("type") == _TEXT_TYPE for p in defn.primitives)
            s = None
            if data is not None and has_text:
                try:
                    s = _viewport_scale(mgr, defn.id, data)
                except Exception:      # a schematic that cannot build never stops an open
                    log.exception("Schematic %s: viewport scale unavailable", defn.name)
            defn.text_sizing = "printed"
            defn.text_scale = (round(1.0 / s, _SCALE_DECIMALS) if s else 0.0) or default
    finally:
        mgr.close()


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

    @property
    def scenes(self) -> list:
        """Every live render scene (public read-only view; one per placed schematic)."""
        return list(self._scenes.values())

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

    def schematic_names(self) -> list:
        """Display names of every schematic in the project, sorted
        case-insensitively (``ViewResolver.available_views`` "Schematics")."""
        return sorted((d.name for d in self._project._block_definitions.values()
                       if d.kind == "schematic"), key=str.lower)

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
            sc.opaque_blocks = True                # block stacking D3: a schematic
            sc.scale_manager.drawing_scale = 1.0   # ET1 Q2: schematic = real size
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
        sc.text_print_scale = d.text_print_scale   # N15: read by the paper pass
        return sc

    def text_scale(self, block_id) -> float:
        """The schematic's drawing scale N when Printed, else 1 (N17)."""
        d = self._schematic(block_id)
        return (d.text_print_scale or 1.0) if d is not None else 1.0

    def extent(self, block_id) -> "QRectF | None":
        """Padded pen-free bounds of the built scene (None if not built).

        Recomputed each call so a nested block's edit re-fits the viewport.
        """
        sc = self._scenes.get(block_id)
        if sc is None:
            return None
        from .geometry_import import geometric_bounds
        items = [it for it in materialized_items(sc)
                 if not is_scaffold_item(it)]                    # D23 / RG11
        rect = geometric_bounds(items)
        if rect is None:
            return QRectF(_DEFAULT_EXTENT)
        rect = _with_leaders(rect, items)
        pad = max(_EXTENT_PAD_MIN_MM,
                  _EXTENT_PAD_FRAC * max(rect.width(), rect.height()))
        return rect.adjusted(-pad, -pad, pad, pad)

    def dispose(self, block_id) -> None:
        """Drop *block_id*'s render scene and detach it from the registry."""
        sc = self._scenes.pop(block_id, None)
        self._keys.pop(block_id, None)
        if sc is not None:
            sc.block_registry.detach_scene(sc)

    def close(self) -> None:
        """Drop every render scene and stop listening: the manager is done with."""
        self.dispose_all()
        self._project.blockDefinitionsChanged.disconnect(self._on_definitions_changed)

    def dispose_all(self) -> None:
        """Drop every render scene (project load / new file / teardown)."""
        for bid in list(self._scenes):
            self.dispose(bid)

    def _on_definitions_changed(self) -> None:
        for bid in list(self._scenes):
            if self._schematic(bid) is None:
                self.dispose(bid)
