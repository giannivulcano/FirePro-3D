"""
dynamic_input.py
================
Dynamic Input: the on-canvas HUD that both reports the live geometry of an
in-progress placement and accepts typed values to drive it precisely.

Schemas are organised by **geometric primitive**, not entity type — pipe,
wall, gridline, polyline and the line tool are all *a line from an anchor*,
so one Line schema serves five clients.

This module knows nothing about ``QGraphicsScene``.  A schema turns typed
values into the same point a mouse click would have produced; ``Model_Space``
hands that point to the existing click-commit path.  Dynamic input is an
alternative *point source*, not an alternative *commit path*.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable

from PyQt6.QtCore import QPointF


class FieldKind(Enum):
    """How a field is formatted, parsed and validated.

    Three kinds map to three ``DimensionEdit`` configurations — not three
    widgets.
    """
    DIMENSION = auto()
    ANGLE = auto()
    COUNT = auto()


@dataclass(frozen=True)
class FieldSpec:
    """Declarative description of one HUD field.

    Attributes:
        name: Key used in the values dict passed to a resolver.
        label: Short caption shown beside the editor in the HUD.
        kind: Formatting/parsing configuration for the editor.
        minimum: Follows ``DimensionEdit`` semantics — accepted values must
            be strictly greater than it, so ``0.0`` rejects zero and
            negatives.  ``None`` where negatives are legal (angles,
            displacement components).
    """
    name: str
    label: str
    kind: FieldKind
    minimum: float | None = None


@dataclass(frozen=True)
class Schema:
    """A field set plus the pure functions converting typed values to geometry.

    Attributes:
        name: Registry key.
        fields: Ordered field specs; order is the HUD's tab order.
        resolve: ``resolve(anchor, values)`` returns a ``QPointF`` for
            placement schemas and a plain dict for transform schemas.
        seed: The inverse of *resolve* for placement schemas, and ``None``
            for transforms — their seeds come from scene state rather than a
            cursor position.
        returns_point: Whether *resolve* yields a ``QPointF`` (placement) or a
            dict (transform).  Declared rather than inferred from ``seed``:
            "has an inverse" and "resolves to a point" are independent
            properties that merely coincide across today's six schemas.
            Callers branch on this to pick an applier, so a future schema that
            seeds from scene state yet resolves to a point must not be able to
            route itself to the wrong one.
    """
    name: str
    fields: tuple[FieldSpec, ...]
    resolve: Callable
    seed: Callable | None = None
    returns_point: bool = True

    @property
    def is_placement(self) -> bool:
        """True when this schema resolves to a point rather than a transform."""
        return self.returns_point


# ── Line ──────────────────────────────────────────────────────────────────
# Angles are Y-up (0° = right, 90° = up); scene Y is down, hence the negation.

def resolve_line(anchor: QPointF, values: dict) -> QPointF:
    """Return the endpoint *Length* away from *anchor* at *Angle*."""
    rad = math.radians(values["Angle"])
    length = values["Length"]
    return QPointF(anchor.x() + length * math.cos(rad),
                   anchor.y() - length * math.sin(rad))


def seed_line(anchor: QPointF, point: QPointF) -> dict:
    """Return the Length/Angle that ``resolve_line`` maps back to *point*."""
    dx = point.x() - anchor.x()
    dy = point.y() - anchor.y()
    return {"Length": math.hypot(dx, dy),
            "Angle": math.degrees(math.atan2(-dy, dx))}


# ── Rectangle ─────────────────────────────────────────────────────────────

def resolve_rectangle(anchor: QPointF, values: dict) -> QPointF:
    """Return the opposite-corner point *X*/*Y* away from *anchor*.

    Resolving to a corner rather than a size keeps this a point source, and
    signed extents let one point serve both rectangle modes: corner-to-corner
    builds ``QRectF(anchor, point).normalized()`` — where the sign chooses
    which quadrant the rectangle occupies — while from-centre re-applies
    ``abs()`` to derive half-extents and so ignores the sign.  Feeding this an
    unsigned *X*/*Y* would silently rebuild every corner-mode rectangle in the
    up-right quadrant.
    """
    return QPointF(anchor.x() + values["X"], anchor.y() - values["Y"])


def seed_rectangle(anchor: QPointF, point: QPointF) -> dict:
    """Return the signed X/Y extents from *anchor* to *point*, Y-up.

    The sign is kept so ``resolve_rectangle`` round-trips *point* exactly:
    in corner mode the drag direction is the geometry, not just a visual cue.
    Folding to a magnitude is left to the from-centre commit path, which
    ``abs()``es anyway.
    """
    return {"X": point.x() - anchor.x(),
            "Y": -(point.y() - anchor.y())}


# ── Circle ────────────────────────────────────────────────────────────────

def resolve_circle(anchor: QPointF, values: dict) -> QPointF:
    """Return any point *Radius* away from the centre *anchor*.

    Direction is arbitrary — the click path takes the hypot of the point
    against the centre, so only the distance survives.
    """
    return QPointF(anchor.x() + values["Radius"], anchor.y())


def seed_circle(anchor: QPointF, point: QPointF) -> dict:
    """Return the radius implied by *point* on a circle centred at *anchor*."""
    return {"Radius": math.hypot(point.x() - anchor.x(),
                                 point.y() - anchor.y())}


# ── Transforms ────────────────────────────────────────────────────────────
# Transforms modify existing geometry rather than producing a new point, so
# these return dicts the caller applies directly.

def resolve_displacement(anchor, values: dict) -> dict:
    """Return the move/copy offset for typed *dX*/*dY* (Y-up input)."""
    return {"offset": QPointF(values["dX"], -values["dY"])}


def resolve_distance(anchor, values: dict) -> dict:
    """Return the scalar distance for offset-style operations."""
    return {"distance": values["Distance"]}


def resolve_spacing_count(anchor, values: dict) -> dict:
    """Return spacing plus an integer count, floored at one.

    The editor yields a float, so the count is rounded and clamped: an array
    of zero items is never a useful commit.
    """
    return {"spacing": values["Spacing"],
            "count": max(1, int(round(values["Count"])))}


SCHEMAS: dict[str, Schema] = {
    "line": Schema(
        name="line",
        fields=(
            FieldSpec("Length", "L", FieldKind.DIMENSION, minimum=0.0),
            FieldSpec("Angle", "A", FieldKind.ANGLE),
        ),
        resolve=resolve_line,
        seed=seed_line,
    ),
    "rectangle": Schema(
        name="rectangle",
        fields=(
            # Signed, like displacement dX/dY: a left/down drag seeds a
            # negative extent, and in corner mode that sign is the geometry.
            # A 0.0 minimum would reject the seed the schema just produced.
            FieldSpec("X", "X", FieldKind.DIMENSION),
            FieldSpec("Y", "Y", FieldKind.DIMENSION),
        ),
        resolve=resolve_rectangle,
        seed=seed_rectangle,
    ),
    "circle": Schema(
        name="circle",
        fields=(
            FieldSpec("Radius", "R", FieldKind.DIMENSION, minimum=0.0),
        ),
        resolve=resolve_circle,
        seed=seed_circle,
    ),
    "displacement": Schema(
        name="displacement",
        fields=(
            FieldSpec("dX", "dX", FieldKind.DIMENSION),
            FieldSpec("dY", "dY", FieldKind.DIMENSION),
        ),
        resolve=resolve_displacement,
        returns_point=False,
    ),
    "distance": Schema(
        name="distance",
        fields=(
            FieldSpec("Distance", "Dist", FieldKind.DIMENSION, minimum=0.0),
        ),
        resolve=resolve_distance,
        returns_point=False,
    ),
    "spacing_count": Schema(
        name="spacing_count",
        fields=(
            FieldSpec("Spacing", "Sp", FieldKind.DIMENSION, minimum=0.0),
            FieldSpec("Count", "N", FieldKind.COUNT, minimum=0.0),
        ),
        resolve=resolve_spacing_count,
        returns_point=False,
    ),
}
