"""BlockDefinition — the reusable 2D block definition (flyweight).

A definition owns identity + metadata + captured 2D primitives, and (Task 2)
compiles those primitives once into a shared, origin-relative render-op list
consumed by every BlockInstance. See docs/specs/block-system.md.
"""

from __future__ import annotations

import uuid

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen

from .geometry_2d import (
    LineItem, RectangleItem, CircleItem, ArcItem, PolylineItem, RegularPolygonItem,
    EllipseItem, SplineItem,
)
from .text_item import TextItem

# Primitive-type key -> reconstruction class (same keys as the legacy factory)
_PRIMITIVE_FACTORY = {
    "draw_line": LineItem,
    "draw_rectangle": RectangleItem,
    "draw_circle": CircleItem,
    "arc": ArcItem,
    "polyline": PolylineItem,
    "polygon": RegularPolygonItem,
    "draw_ellipse": EllipseItem,
    "draw_spline": SplineItem,
    "text": TextItem,
}


def _local_path(item) -> QPainterPath:
    """Return the primitive's geometry as a QPainterPath in the item's own coords.

    Args:
        item: A construction-geometry primitive (QGraphicsItem subclass).

    Returns:
        A ``QPainterPath`` describing the primitive in its local coordinate frame.
    """
    # TextItem contributes filled glyph outlines (bake-at-rest rotation already
    # applied inside render_outline_path — see its docstring).
    if hasattr(item, "render_outline_path"):
        return item.render_outline_path()
    from PyQt6.QtWidgets import (
        QGraphicsLineItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem,
    )
    path = QPainterPath()
    if isinstance(item, QGraphicsLineItem):
        ln = item.line()
        path.moveTo(ln.p1())
        path.lineTo(ln.p2())
    elif isinstance(item, QGraphicsEllipseItem):
        path.addEllipse(item.rect())
    elif isinstance(item, QGraphicsRectItem):
        path.addRect(item.rect())
    elif isinstance(item, QGraphicsPathItem):
        path = QPainterPath(item.path())
    return path


class BlockDefinition:
    """A named, reusable 2D block definition.

    Attributes:
        id: Stable uuid4 hex identity (registry key + instance reference + library link).
        version: Monotonic revision, bumped on each edit; drives library divergence.
        name/library/series: Human-readable metadata (2-tier library taxonomy).
        scale_mode: v1 sole value "real_size" ("annotative" reserved for v2).
        origin: Definition-local insertion origin, in scene millimetres.
        attributes: Reserved slot list; no UI in v1.
        primitives: List of 2D-primitive dicts (geometry_2d to_dict form).
    """

    def __init__(self, *, id: str, version: int, name: str, library: str,
                 series: str, scale_mode: str, origin: tuple[float, float],
                 attributes: list, primitives: list[dict],
                 render_mode: str = "default", geoms: list[dict] | None = None):
        self.id = id
        self.version = int(version)
        self.name = name
        self.library = library
        self.series = series
        self.scale_mode = scale_mode
        self.origin = (float(origin[0]), float(origin[1]))
        self.attributes = list(attributes)
        self.primitives = list(primitives)
        # Reference definitions (render_mode="reference") own the curve-preserving,
        # layer-tagged import geom-dict list. This is the geometry data model for
        # imported references — rendered by the batched underlay builder (which
        # also handles text) and persisted via the underlay cache, NOT via
        # to_dict (keeps .fpd lean). Empty for authored blocks.
        self.geoms: list[dict] = list(geoms) if geoms else []
        # Render mode (reference-graphic unification, constraint #1):
        #   "default"   — one render op per primitive (authored blocks).
        #   "reference" — one render op per distinct source `layer` tag; the
        #                 batched-per-layer compile that keeps a 437k-geom DXF
        #                 interactive. See docs/specs/reference-graphic-model.md.
        self.render_mode = render_mode or "default"
        self._render_ops: list[tuple[QPen, QBrush, QPainterPath]] | None = None
        self._instances: list = []   # BlockInstance backrefs (Task 4 wires notify)

    @classmethod
    def new(cls, *, name: str, library: str, series: str,
            primitives: list[dict], origin: tuple[float, float],
            render_mode: str = "default") -> "BlockDefinition":
        """Create a fresh definition with a new uuid and version 1."""
        return cls(id=uuid.uuid4().hex, version=1, name=name, library=library,
                   series=series, scale_mode="real_size", origin=origin,
                   attributes=[], primitives=primitives, render_mode=render_mode)

    @classmethod
    def reference_from_geoms(cls, geoms: list[dict], *, name: str = "",
                             library: str = "", series: str = "") -> "BlockDefinition":
        """Build a reference definition from imported geom dicts (R1).

        The single import front-end (DXF/DWG/PDF) hands its curve-preserving,
        layer-tagged geom dicts here. Geometry lives in ``geoms`` (rendered by the
        batched underlay builder); ``primitives`` stays empty. Raster imports have
        no geoms and produce a valid empty reference. See
        docs/specs/reference-graphic-model.md.

        Args:
            geoms: import geom dicts (worker output; ``_preserve_curves`` path for
                curve fidelity, each carrying a ``layer`` tag).
            name/library/series: definition metadata.

        Returns:
            A ``BlockDefinition`` with ``render_mode="reference"`` and ``geoms`` set.
        """
        d = cls.new(name=name, library=library, series=series, primitives=[],
                    origin=(0.0, 0.0), render_mode="reference")
        d.geoms = list(geoms) if geoms else []
        return d

    def set_primitives(self, primitives: list[dict]) -> None:
        """Replace captured primitives, bump version, invalidate + notify instances.

        Args:
            primitives: The new list of 2D-primitive dicts (geometry_2d
                to_dict form) that replaces the definition's geometry.
        """
        self.primitives = list(primitives)
        self.version += 1
        self._render_ops = None
        for inst in list(self._instances):
            inst.on_definition_changed()

    def render_ops(self) -> list[tuple[QPen, QBrush, QPainterPath]]:
        """Return the cached, shared (pen, brush, path) render-op list.

        Returns:
            A list of ``(QPen, QBrush, QPainterPath)`` tuples in definition-local,
            origin-relative coordinates. Stroked geometry carries a ``NoBrush``;
            text carries a ``NoPen`` + a solid colour brush (filled glyph
            outlines). The same list identity is returned on every call until
            :meth:`set_primitives` invalidates the cache.
        """
        if self._render_ops is None:
            self._render_ops = self._compile()
        return self._render_ops

    def _compile(self) -> list[tuple[QPen, QBrush, QPainterPath]]:
        """Compile captured primitive dicts into origin-relative render ops.

        In ``reference`` mode the ops are batched per source layer (one op per
        distinct ``layer`` tag) — the binding perf constraint that keeps a
        large imported reference interactive. In ``default`` mode each primitive
        gets its own op (authored blocks, unchanged).
        """
        if self.render_mode == "reference":
            return self._compile_reference()
        ox, oy = self.origin
        ops: list[tuple[QPen, QBrush, QPainterPath]] = []
        for prim in self.primitives:
            cls = _PRIMITIVE_FACTORY.get(prim.get("type"))
            if cls is None:
                continue
            item = cls.from_dict(prim)
            # _local_path returns the glyph outline for text (rotation baked);
            # mapToParent applies the item's pos (data.x/y) in both cases.
            path = item.mapToParent(_local_path(item))   # honor prim pos/rotation
            path.translate(-ox, -oy)                       # origin-relative
            if hasattr(item, "render_outline_path"):
                # Text primitive: fill the glyph outline (no stroke). pen() does
                # not exist on TextItem; the fill colour is the authored colour.
                pen = QPen(Qt.PenStyle.NoPen)
                brush = QBrush(QColor(item.data.color))
            else:
                pen = QPen(item.pen())
                brush = QBrush(Qt.BrushStyle.NoBrush)
            ops.append((pen, brush, path))
        return ops

    def _compile_reference(self) -> list[tuple[QPen, QBrush, QPainterPath]]:
        """Batched compile: accumulate each layer's geometry into one path.

        Groups by ``layer`` tag, unioning each layer's geometry into a single
        cosmetic ``QPainterPath`` (subpaths kept separate via ``addPath``). The
        result is one ``(QPen, QBrush, QPainterPath)`` per distinct *geometry*
        layer — ``len(render_ops) == n_distinct_layers``, never ``n_primitives``.
        Per-layer colour/weight is applied downstream by the reference bundle's
        display pass, so the compile pen is a cosmetic default.

        A geom-backed reference (imported) compiles from ``geoms``; text geoms
        carry no geometry_2d primitive and are excluded here (the batched
        underlay builder renders them). An authored reference (rare) falls back
        to ``primitives``.
        """
        ox, oy = self.origin
        by_layer: dict[str, QPainterPath] = {}
        pens: dict[str, QPen] = {}
        for item, layer in self._reference_items():
            path = item.mapToParent(_local_path(item))
            path.translate(-ox, -oy)                       # origin-relative
            if layer not in by_layer:
                by_layer[layer] = QPainterPath()
                pen = QPen(item.pen())
                pen.setCosmetic(True)
                pens[layer] = pen
            by_layer[layer].addPath(path)
        # Reference geometry is stroked (text is excluded here — see docstring),
        # so every op carries a NoBrush for a consistent 3-tuple shape.
        no_brush = QBrush(Qt.BrushStyle.NoBrush)
        return [(pens[layer], no_brush, by_layer[layer]) for layer in by_layer]

    def _reference_items(self):
        """Yield ``(primitive_item, layer)`` for the reference compile.

        Geom-backed definitions (imported references) compile from ``geoms`` via
        the shared ``geom_dicts_to_primitives`` converter (curve-preserving,
        layer-tagged); otherwise fall back to ``primitives`` (geometry_2d dicts).
        """
        if self.geoms:
            from .geometry_import import geom_dicts_to_primitives
            items, _ = geom_dicts_to_primitives(self.geoms)
            for it in items:
                yield it, getattr(it, "layer", "")
        else:
            for prim in self.primitives:
                cls = _PRIMITIVE_FACTORY.get(prim.get("type"))
                if cls is None:
                    continue
                yield cls.from_dict(prim), prim.get("layer", "")

    def to_dict(self) -> dict:
        return {
            "schema": 1,
            "id": self.id,
            "version": self.version,
            "name": self.name,
            "library": self.library,
            "series": self.series,
            "scale_mode": self.scale_mode,
            "origin": [self.origin[0], self.origin[1]],
            "attributes": list(self.attributes),
            "primitives": list(self.primitives),
            "render_mode": self.render_mode,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BlockDefinition":
        origin = data.get("origin", [0.0, 0.0])
        return cls(
            id=data["id"], version=data.get("version", 1),
            name=data.get("name", ""), library=data.get("library", ""),
            series=data.get("series", ""),
            scale_mode=data.get("scale_mode", "real_size"),
            origin=(origin[0], origin[1]),
            attributes=data.get("attributes", []),
            primitives=data.get("primitives", []),
            render_mode=data.get("render_mode", "default"),
        )
