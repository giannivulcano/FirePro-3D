"""Two-layer shape fill: a background and a pattern (UP1 design D1).

The one home of the ``fill`` record: its shape, the legacy reading and the
defaults. No other module parses a ``fill`` dict -- readers call
:func:`from_record` (every load path: ``.fpdb``, project-bundled definitions,
undo snapshots), writers :func:`to_record`.

New record::

    {"background": {"color", "opacity"},
     "pattern":    {"ref", "color", "opacity", "scale"}}

an absent layer's key omitted. A legacy record (has a ``type`` key) is read
same-look (R11): ``solid`` -> background, ``hatch`` -> pattern (its colour =
the legacy colour, scale 1.0), ``none`` -> empty. Opacity is a fraction 0..1.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .constants import FILL_LEGACY_COLOUR, FILL_LEGACY_OPACITY, TOKEN_AUTO


@dataclass(frozen=True)
class BackgroundLayer:
    """Solid background: colour (HF1 value) + opacity fraction."""
    color: str
    opacity: float = 1.0


@dataclass(frozen=True)
class PatternLayer:
    """Tiled pattern: tile ref + colour + opacity fraction + scale."""
    ref: str
    color: str = TOKEN_AUTO
    opacity: float = 1.0
    scale: float = 1.0


@dataclass(frozen=True)
class FillLayers:
    """A shape's fill: either layer may be None (off)."""
    background: BackgroundLayer | None = None
    pattern: PatternLayer | None = None

    @property
    def is_empty(self) -> bool:
        return self.background is None and self.pattern is None


class _NoLayer:
    """Picker result for "layer off" (distinct from None = cancelled)."""
    __slots__ = ()

    def __repr__(self) -> str:
        return "NO_LAYER"


NO_LAYER = _NoLayer()
EMPTY = FillLayers()


def alpha(opacity: float) -> int:
    """0-255 alpha of an opacity fraction (the legacy rounding)."""
    return int(round(opacity * 255))


def _opacity(value, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(v):
        return default
    return max(0.0, min(1.0, v))


def _scale(value) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 1.0
    return v if math.isfinite(v) and v > 0.0 else 1.0


def _canonical(ref):
    from .hatch_patterns import canonical_ref     # lazy: hatch_patterns reads us
    return canonical_ref(ref)


def _default_ref() -> str:
    from .hatch_patterns import DEFAULT_TILE_REF
    return DEFAULT_TILE_REF


def _background(d) -> BackgroundLayer | None:
    if not isinstance(d, dict):
        return None
    col = d.get("color")
    if not isinstance(col, str) or col == "":
        return None
    return BackgroundLayer(col, _opacity(d.get("opacity", 1.0), 1.0))


def _pattern(d) -> PatternLayer | None:
    if not isinstance(d, dict):
        return None
    ref = d.get("ref")
    if not isinstance(ref, str) or not ref:
        return None
    col = d.get("color")
    col = col if isinstance(col, str) and col else TOKEN_AUTO
    return PatternLayer(_canonical(ref), col, _opacity(d.get("opacity", 1.0), 1.0),
                        _scale(d.get("scale", 1.0)))


def _from_legacy(rec: dict) -> FillLayers:
    kind = rec.get("type")
    col = rec.get("color")
    if col == "":
        return EMPTY                      # HF1 No Fill: the item path never drew it
    if not isinstance(col, str):
        col = FILL_LEGACY_COLOUR
    op = _opacity(rec.get("opacity", FILL_LEGACY_OPACITY), FILL_LEGACY_OPACITY)
    if kind == "solid":
        return FillLayers(background=BackgroundLayer(col, op))
    if kind == "hatch":
        pat = rec.get("pattern")
        ref = _canonical(pat) if isinstance(pat, str) and pat else _default_ref()
        return FillLayers(pattern=PatternLayer(ref, col, op, 1.0))
    return EMPTY


def from_record(rec) -> FillLayers:
    """Layers of a stored ``fill`` record (new or legacy); never raises."""
    if not isinstance(rec, dict):
        return EMPTY
    if "type" in rec:
        return _from_legacy(rec)
    return FillLayers(_background(rec.get("background")), _pattern(rec.get("pattern")))


def to_record(layers: FillLayers | None) -> dict | None:
    """The ``fill`` record of *layers*, or None when empty (write no key)."""
    if layers is None or layers.is_empty:
        return None
    out: dict = {}
    bg = layers.background
    if bg is not None:
        out["background"] = {"color": bg.color, "opacity": bg.opacity}
    pat = layers.pattern
    if pat is not None:
        out["pattern"] = {"ref": pat.ref, "color": pat.color,
                          "opacity": pat.opacity, "scale": pat.scale}
    return out


def pattern_ref(rec) -> str | None:
    """Canonical pattern ref of a record of either shape (reference collectors)."""
    pat = from_record(rec).pattern
    return pat.ref if pat is not None else None
