"""Overlap-aware paint-order runs for a batched underlay (HF7 D3).

The batch builder groups geometry per layer, which loses stream order. Runs
bring back the part that matters: only a fill and something it overlaps need a
fixed order. Everything else shares a run, so a drawing with thousands of
fill-then-line pairs still compiles to a handful of path items.
"""
from __future__ import annotations

import numpy as np

from .dwg_converter import geom_children
from .underlay_snap_index import _geom_bounds

_NO_BOX = (np.nan, np.nan, np.nan, np.nan)   # overlaps nothing (every compare False)


def fill_class(g: dict) -> str | None:
    """Batch class of a fill: ``mask``, ``tone``, ``solid``; None for lines only."""
    if g.get("mask"):
        return "mask"
    if g.get("tone"):
        return "tone"
    return "solid" if g.get("solid") else None


def paints(g: dict) -> bool:
    """True when a fill record draws anything (a tone/solid/mask or pattern lines).

    A non-solid hatch with an empty or missing pattern draws nothing; it is
    kept only so its boundary snaps.
    """
    return g.get("kind") == "fill" and (fill_class(g) is not None
                                        or bool(g.get("lines")))


def _bounds(g: dict) -> tuple[float, float, float, float]:
    if g.get("kind") != "fill":
        return _geom_bounds(g)
    if not paints(g):
        return _NO_BOX
    boxes = [_geom_bounds(c) for c in geom_children(g)]
    if not boxes:
        return _NO_BOX
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def assign_runs(geoms: list[dict]) -> list[int]:
    """Run index per geom, stream order bottom to top.

    For each fill in stream order: one above the highest earlier overlapping
    stroke, level with an earlier overlapping fill of its layer and class, one
    above any other (a batch holds one layer and class, so level means painted
    together). Every later overlapping geom is raised to at least that run.
    Overlap is by bounding box. O(fills x geoms); HF6 needs a spatial index
    if a PDF page holds tens of thousands of fills.

    A fill that draws nothing (see :func:`paints`) takes no part in ordering.

    Args:
        geoms: Geometry dicts in paint order.

    Returns:
        One run index per geom; all zero when *geoms* holds no painting fill.
    """
    n = len(geoms)
    is_fill = np.fromiter((paints(g) for g in geoms), bool, n)
    if not is_fill.any():
        return [0] * n
    box = np.array([_bounds(g) for g in geoms], dtype=float)
    keys = [(g.get("layer", "0"), fill_class(g)) for g in geoms]
    runs = np.zeros(n, dtype=int)
    for i in np.flatnonzero(is_fill):
        x0, y0, x1, y1 = box[i]
        hit = ((box[:, 0] <= x1) & (box[:, 2] >= x0)
               & (box[:, 1] <= y1) & (box[:, 3] >= y0))
        run = 0
        before = np.flatnonzero(hit[:i])
        if before.size:
            strokes = before[~is_fill[before]]
            if strokes.size:
                run = int(runs[strokes].max()) + 1
            for j in before[is_fill[before]]:
                run = max(run, int(runs[j]) + (0 if keys[j] == keys[i] else 1))
        runs[i] = run
        after = i + 1 + np.flatnonzero(hit[i + 1:])
        runs[after] = np.maximum(runs[after], run)
    return runs.tolist()
