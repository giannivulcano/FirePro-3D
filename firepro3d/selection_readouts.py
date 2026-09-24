"""Selection dimension readouts (2d-geometry.md §8, selection-mode.md §15).

A readout is a transient, painted record — never a QGraphicsItem and never a
child of its primitive. Primitives describe their dimensions via
``dimension_specs() -> list[DimSpec]``; ``SelectionReadoutController`` (added
in Task 10) will turn the live selection into painted, pickable, editable
labels.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PyQt6.QtCore import QPointF


@dataclass(frozen=True)
class DimSpec:
    """One dimension a primitive reports.

    Attributes:
        kind: ``"linear"`` or ``"angular"``.
        key: Stable id within the item (``"length"``, ``"seg:2"``,
            ``"ang:1"``) — survives rebuilds mid-drag.
        field: HUD field label (``"Length"``, ``"R1"``, ``"Angle 2"``).
        prefix: Label prefix (``""``, ``"R"``, ``"R1"``, ``"R2"``).
        value: mm (linear) or degrees (angular).
        field_kind: ``"dimension"`` (length, mm) or ``"span"`` (degrees).
        apply: Pure setter taking one float — no undo (caller owns undo).
        minimum: Accepted values are strictly greater than this.
        maximum: Accepted values are <= this (None = unbounded).
        a, b: Linear endpoints (scene coords).
        away: Linear label goes to the side of a→b away from this point
            (None = prefer screen-up / screen-left).
        center: Angular vertex (scene coords).
        ref_radius: Angular leg length (scene); the reference arc radius is
            a fraction of it and the label hides if the arc would exceed it.
        start_deg, span_deg: Angular sweep, Y-up degrees CCW from +x.
    """
    kind: str
    key: str
    field: str
    prefix: str
    value: float
    field_kind: str
    apply: Callable[[float], None]
    minimum: float = 0.0
    maximum: float | None = None
    a: QPointF | None = None
    b: QPointF | None = None
    away: QPointF | None = None
    center: QPointF | None = None
    ref_radius: float = 0.0
    start_deg: float = 0.0
    span_deg: float = 0.0


def readout_text(spec: DimSpec, scale_manager) -> str:
    """Display string for *spec*: prefix + unit-formatted value."""
    from .scale_manager import ScaleManager
    if spec.field_kind == "span":
        body = ScaleManager.format_span(spec.value)
    elif scale_manager is not None:
        body = scale_manager.format_length(spec.value)
    else:
        body = f"{spec.value:.1f} mm"
    return f"{spec.prefix} {body}" if spec.prefix else body
