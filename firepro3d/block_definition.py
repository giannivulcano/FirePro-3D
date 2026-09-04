"""BlockDefinition — the reusable 2D block definition (flyweight).

A definition owns identity + metadata + captured 2D primitives, and (Task 2)
compiles those primitives once into a shared, origin-relative render-op list
consumed by every BlockInstance. See docs/specs/block-system.md.
"""

from __future__ import annotations

import uuid


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

    @classmethod
    def new(cls, *, name: str, library: str, series: str,
            primitives: list[dict], origin: tuple[float, float]) -> "BlockDefinition":
        """Create a fresh definition with a new uuid and version 1."""
        return cls(id=uuid.uuid4().hex, version=1, name=name, library=library,
                   series=series, scale_mode="real_size", origin=origin,
                   attributes=[], primitives=primitives)

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
