"""BlockDefinition — the reusable 2D block definition (flyweight).

A definition owns identity + metadata + captured 2D primitives, and (Task 2)
compiles those primitives once into a shared, origin-relative render-op list
consumed by every BlockInstance. See docs/specs/block-system.md.
"""

from __future__ import annotations

import uuid

from PyQt6.QtGui import QPainterPath, QPen

from .construction_geometry import (
    LineItem, RectangleItem, CircleItem, ArcItem, PolylineItem, RegularPolygonItem,
)

# Primitive-type key -> reconstruction class (same keys as the legacy factory)
_PRIMITIVE_FACTORY = {
    "draw_line": LineItem,
    "draw_rectangle": RectangleItem,
    "draw_circle": CircleItem,
    "arc": ArcItem,
    "polyline": PolylineItem,
    "polygon": RegularPolygonItem,
}


def _local_path(item) -> QPainterPath:
    """Return the primitive's geometry as a QPainterPath in the item's own coords.

    Args:
        item: A construction-geometry primitive (QGraphicsItem subclass).

    Returns:
        A ``QPainterPath`` describing the primitive in its local coordinate frame.
    """
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
        primitives: List of 2D-primitive dicts (construction_geometry to_dict form).
    """

    def __init__(self, *, id: str, version: int, name: str, library: str,
                 series: str, scale_mode: str, origin: tuple[float, float],
                 attributes: list, primitives: list[dict]):
        self.id = id
        self.version = int(version)
        self.name = name
        self.library = library
        self.series = series
        self.scale_mode = scale_mode
        self.origin = (float(origin[0]), float(origin[1]))
        self.attributes = list(attributes)
        self.primitives = list(primitives)
        self._render_ops: list[tuple[QPen, QPainterPath]] | None = None
        self._instances: list = []   # BlockInstance backrefs (Task 4 wires notify)

    @classmethod
    def new(cls, *, name: str, library: str, series: str,
            primitives: list[dict], origin: tuple[float, float]) -> "BlockDefinition":
        """Create a fresh definition with a new uuid and version 1."""
        return cls(id=uuid.uuid4().hex, version=1, name=name, library=library,
                   series=series, scale_mode="real_size", origin=origin,
                   attributes=[], primitives=primitives)

    def set_primitives(self, primitives: list[dict]) -> None:
        """Replace captured primitives, bump version, invalidate + notify instances.

        Args:
            primitives: The new list of 2D-primitive dicts (construction_geometry
                to_dict form) that replaces the definition's geometry.
        """
        self.primitives = list(primitives)
        self.version += 1
        self._render_ops = None
        for inst in list(self._instances):
            inst.on_definition_changed()

    def render_ops(self) -> list[tuple[QPen, QPainterPath]]:
        """Return the cached, shared (pen, path) render-op list (compiled once).

        Returns:
            A list of ``(QPen, QPainterPath)`` tuples in definition-local,
            origin-relative coordinates. The same list identity is returned on
            every call until :meth:`set_primitives` invalidates the cache.
        """
        if self._render_ops is None:
            self._render_ops = self._compile()
        return self._render_ops

    def _compile(self) -> list[tuple[QPen, QPainterPath]]:
        """Compile captured primitive dicts into origin-relative render ops."""
        ox, oy = self.origin
        ops: list[tuple[QPen, QPainterPath]] = []
        for prim in self.primitives:
            cls = _PRIMITIVE_FACTORY.get(prim.get("type"))
            if cls is None:
                continue
            item = cls.from_dict(prim)
            path = item.mapToParent(_local_path(item))   # honor prim pos/rotation
            path.translate(-ox, -oy)                       # origin-relative
            ops.append((QPen(item.pen()), path))
        return ops

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
        )
