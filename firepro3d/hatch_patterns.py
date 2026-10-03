"""Hatch pattern registry: built-in tile blocks, legacy aliases, picker source.

hatch-and-fill.md D-A28 / D-A29, concept HD4a. A pattern is a Block definition
with a ``tile``. Built-ins are code-level, read-only definitions with frozen
ids (HF8 replaces their content with shipped System > Hatches blocks; this
table stays the never-vanish fallback). Pure data at import time —
``geometry_2d`` imports this module — the built-in definitions are built
lazily so there is no import cycle through ``block_definition``.
"""
from __future__ import annotations

import math

BUILTIN_DIAGONAL = "builtin-hatch-diagonal"
BUILTIN_CROSS_HATCH = "builtin-hatch-cross-hatch"
BUILTIN_HORIZONTAL = "builtin-hatch-horizontal"
BUILTIN_CONCRETE = "builtin-hatch-concrete"
BUILTIN_BRICK = "builtin-hatch-brick"

#: Legacy pattern names (QSettings, DM overrides, old files) → built-in id.
LEGACY_ALIAS: dict[str, str] = {
    "diagonal": BUILTIN_DIAGONAL,
    "cross_hatch": BUILTIN_CROSS_HATCH,
    "horizontal": BUILTIN_HORIZONTAL,
    "concrete": BUILTIN_CONCRETE,
}

DEFAULT_TILE_REF = BUILTIN_DIAGONAL

_SPACING_MM = 3.0   # printed perpendicular spacing of the Drafting test set (D-A28)

# Picker order + display names (D-A28).
_BUILTIN_NAMES: list[tuple[str, str]] = [
    (BUILTIN_DIAGONAL, "Diagonal"),
    (BUILTIN_CROSS_HATCH, "Cross Hatch"),
    (BUILTIN_HORIZONTAL, "Horizontal"),
    (BUILTIN_CONCRETE, "Concrete"),
    (BUILTIN_BRICK, "Brick"),
]
BUILTIN_IDS = frozenset(i for i, _ in _BUILTIN_NAMES)

_BUILTINS: dict | None = None


def canonical_ref(ref: str | None) -> str | None:
    """A legacy name mapped to its built-in id; any other ref unchanged."""
    if not ref:
        return ref
    return LEGACY_ALIAS.get(ref, ref)


def is_builtin_ref(ref: str | None) -> bool:
    """True if *ref* (id or legacy name) names a built-in tile."""
    return canonical_ref(ref) in BUILTIN_IDS


def _line(x1, y1, x2, y2) -> dict:
    from PyQt6.QtCore import QPointF
    from .geometry_2d import LineItem
    return LineItem(QPointF(x1, y1), QPointF(x2, y2)).to_dict()


def _dot(x, y, r=0.2) -> dict:
    from PyQt6.QtCore import QPointF
    from .geometry_2d import CircleItem
    return CircleItem(QPointF(x, y), r).to_dict()


def _tri(pts) -> list[dict]:
    (a, b, c) = pts
    return [_line(*a, *b), _line(*b, *c), _line(*c, *a)]


def _builtin_specs() -> list[tuple[str, dict, list[dict]]]:
    """(id, tile, primitives). Tile frame = (0,0)→(w,−h): scene y-down, so −h
    is screen-up (D-A32). The diagonal rises to the right on screen (45° Y-up)."""
    d = _SPACING_MM * math.sqrt(2.0)
    s = _SPACING_MM
    drafting = lambda w, h, shift=0.0: {"w": w, "h": h, "row_shift": shift,
                                        "size": "drafting"}
    concrete = (_tri([(1.0, -1.0), (2.0, -1.2), (1.4, -2.0)])
                + _tri([(4.0, -3.5), (5.0, -3.8), (4.3, -4.6)])
                + [_dot(3.0, -1.5), _dot(1.5, -4.5), _dot(5.0, -1.0), _dot(2.6, -5.2)])
    return [
        (BUILTIN_DIAGONAL, drafting(d, d), [_line(0, 0, d, -d)]),
        (BUILTIN_CROSS_HATCH, drafting(d, d), [_line(0, 0, d, -d), _line(0, -d, d, 0)]),
        (BUILTIN_HORIZONTAL, drafting(s, s), [_line(0, 0, s, 0)]),
        (BUILTIN_CONCRETE, drafting(6.0, 6.0), concrete),
        (BUILTIN_BRICK, {"w": 225.0, "h": 75.0, "row_shift": 112.5, "size": "model"},
         [_line(0, 0, 225.0, 0), _line(0, 0, 0, -75.0)]),
    ]


def builtin_tiles() -> dict:
    """``{frozen id: BlockDefinition}`` of the built-in tiles (built once)."""
    global _BUILTINS
    if _BUILTINS is None:
        from .block_definition import BlockDefinition
        names = dict(_BUILTIN_NAMES)
        _BUILTINS = {
            bid: BlockDefinition(id=bid, version=1, name=names[bid],
                                 library="System", series="Hatches",
                                 scale_mode="real_size", origin=(0.0, 0.0),
                                 attributes=[], primitives=prims, tile=tile)
            for bid, tile, prims in _builtin_specs()
        }
    return _BUILTINS


def tile_is_valid(defn) -> bool:
    """A usable tile: positive W×H and at least one compiled op (edge: empty tile)."""
    t = getattr(defn, "tile", None)
    return bool(t) and t["w"] > 0 and t["h"] > 0 and bool(defn.render_ops())


def resolve_tile(ref: str | None, registry=None):
    """Tile definition for *ref*: alias → built-ins → project registry; else None."""
    ref = canonical_ref(ref)
    if not ref:
        return None
    b = builtin_tiles().get(ref)
    if b is not None:
        return b
    if registry is not None:
        d = registry.get(ref)
        if d is not None and d.tile:
            return d
    return None


def tile_choices(registry=None) -> list[tuple[str, str]]:
    """``[(label, ref)]``: built-ins in fixed order, then the project's valid
    tiled blocks by name. The single source for every pattern picker.

    Labels are unique: a project tile whose name collides with an earlier label
    gets `` (project)`` appended (then `` (project 2)`` ...), so every ref is
    reachable through ``ref_from_value``.
    """
    out = list(((n, i) for i, n in _BUILTIN_NAMES))
    if registry is not None:
        project = []
        for bid in registry.ids():
            d = registry.get(bid)
            if d is not None and d.tile and tile_is_valid(d):
                project.append((d.name or bid, bid))
        used = {n for n, _ in out}
        for name, bid in sorted(project, key=lambda x: x[0].lower()):
            label, k = name, 1
            while label in used:
                k += 1
                label = (f"{name} (project)" if k == 2
                         else f"{name} (project {k - 1})")
            used.add(label)
            out.append((label, bid))
    return out


def display_name(ref: str | None, registry=None) -> str:
    """Picker label for *ref* (falls back to the raw ref for an unknown one)."""
    ref = canonical_ref(ref)
    for name, r in tile_choices(registry):
        if r == ref:
            return name
    d = resolve_tile(ref, registry)
    return d.name if d is not None else (ref or "")


def ref_from_value(value: str, registry=None) -> str:
    """A picker label or a stored ref → the ref to store (D-A29: ids)."""
    for name, ref in tile_choices(registry):
        if value == name:
            return ref
    return canonical_ref(value)


# Transitional (removed in HF2 Task 5): legacy importers still read these names.
PATTERN_NAMES: list[str] = list(LEGACY_ALIAS)


def is_svg(name: str) -> bool:
    """Transitional (removed in HF2 Task 4): SVG patterns no longer exist."""
    return False


def draw_svg_hatch(*args, **kwargs) -> None:
    """Transitional (removed in HF2 Task 4): never reached (``is_svg`` is False)."""


def make_hatch_brush(name: str, tile_size: int = 24, color=None,
                     line_width: float = 1.0):
    """Transitional (removed in HF2 Task 4): Qt brush for the legacy paint path.

    Keeps ``displayable_item._apply_hatch_pattern`` / the DM swatch from raising
    ImportError (a native abort inside paint) until the tile renderer lands.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QBrush, QColor
    styles = {BUILTIN_DIAGONAL: Qt.BrushStyle.BDiagPattern,
              BUILTIN_CROSS_HATCH: Qt.BrushStyle.DiagCrossPattern,
              BUILTIN_HORIZONTAL: Qt.BrushStyle.HorPattern}
    style = styles.get(canonical_ref(name), Qt.BrushStyle.BDiagPattern)
    return QBrush(color or QColor(100, 100, 100), style)
