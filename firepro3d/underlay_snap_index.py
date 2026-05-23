"""
underlay_snap_index.py
======================
Grid-based spatial index for lazy snap queries on underlay geometry.

Instead of adding invisible QGraphicsItems to the scene (which bloats
the BSP and slows every repaint), this index stores geometry dicts and
answers spatial queries directly.  The snap engine queries it when the
cursor is near an underlay group.
"""

from __future__ import annotations

_GRID_SIZE = 64  # cells per axis — 64x64 = 4096 cells


class UnderlaySnapIndex:
    """Grid spatial index over underlay geometry dicts.

    Parameters
    ----------
    geom_list : list[dict]
        Transformed geometry dicts (in group-local coordinates).
    hidden_layers : list[str]
        Reference to the Underlay record's ``hidden_layers`` list.
        Mutations to that list (by ``_toggle_underlay_layer``) are
        automatically visible here since we hold the same object.
    """

    __slots__ = (
        "_geom_list", "_hidden_layers", "_cells",
        "_ox", "_oy", "_cw", "_ch", "_nx", "_ny",
    )

    def __init__(self, geom_list: list[dict],
                 hidden_layers: list[str]):
        self._geom_list = geom_list
        self._hidden_layers = hidden_layers

        # Compute bounding rect of all geometry
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")
        for g in geom_list:
            gmin_x, gmin_y, gmax_x, gmax_y = _geom_bounds(g)
            if gmin_x < min_x: min_x = gmin_x
            if gmin_y < min_y: min_y = gmin_y
            if gmax_x > max_x: max_x = gmax_x
            if gmax_y > max_y: max_y = gmax_y

        if min_x > max_x:
            # Empty geometry list
            self._ox = self._oy = 0.0
            self._cw = self._ch = 1.0
            self._nx = self._ny = 1
            self._cells: dict[int, list[int]] = {}
            return

        # Add small padding to avoid edge cases
        pad = max(max_x - min_x, max_y - min_y) * 0.001 + 1.0
        self._ox = min_x - pad
        self._oy = min_y - pad
        w = (max_x - min_x) + 2 * pad
        h = (max_y - min_y) + 2 * pad
        self._nx = min(_GRID_SIZE, max(1, int(w / 100) + 1))
        self._ny = min(_GRID_SIZE, max(1, int(h / 100) + 1))
        self._cw = w / self._nx
        self._ch = h / self._ny

        # Assign each geometry to its overlapping cells
        cells: dict[int, list[int]] = {}
        for idx, g in enumerate(geom_list):
            gmin_x, gmin_y, gmax_x, gmax_y = _geom_bounds(g)
            c0 = max(0, int((gmin_x - self._ox) / self._cw))
            c1 = min(self._nx - 1, int((gmax_x - self._ox) / self._cw))
            r0 = max(0, int((gmin_y - self._oy) / self._ch))
            r1 = min(self._ny - 1, int((gmax_y - self._oy) / self._ch))
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    key = r * self._nx + c
                    cell = cells.get(key)
                    if cell is None:
                        cell = []
                        cells[key] = cell
                    cell.append(idx)
        self._cells = cells

    def query(self, local_rect_x: float, local_rect_y: float,
              local_rect_w: float, local_rect_h: float) -> list[dict]:
        """Return geometry dicts overlapping *local_rect*, excluding hidden layers.

        Parameters are the rect's (x, y, width, height) in group-local
        coordinates.  Returns a deduplicated list of geometry dicts.
        """
        hidden = set(self._hidden_layers) if self._hidden_layers else set()

        x1 = local_rect_x
        y1 = local_rect_y
        x2 = local_rect_x + local_rect_w
        y2 = local_rect_y + local_rect_h

        c0 = max(0, int((x1 - self._ox) / self._cw))
        c1 = min(self._nx - 1, int((x2 - self._ox) / self._cw))
        r0 = max(0, int((y1 - self._oy) / self._ch))
        r1 = min(self._ny - 1, int((y2 - self._oy) / self._ch))

        seen: set[int] = set()
        result: list[dict] = []
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                cell = self._cells.get(r * self._nx + c)
                if cell is None:
                    continue
                for idx in cell:
                    if idx in seen:
                        continue
                    seen.add(idx)
                    g = self._geom_list[idx]
                    layer = g.get("layer", "0")
                    if layer in hidden:
                        continue
                    result.append(g)
        return result


def _geom_bounds(g: dict) -> tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y) for a geometry dict."""
    kind = g.get("kind")
    if kind == "line":
        x1, y1 = g["x1"], g["y1"]
        x2, y2 = g["x2"], g["y2"]
        return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
    if kind == "circle":
        return (g["x"], g["y"], g["x"] + g["w"], g["y"] + g["h"])
    if kind == "arc":
        return (g["rx"], g["ry"], g["rx"] + g["rw"], g["ry"] + g["rh"])
    if kind == "ellipse_full":
        cx, cy = g["pos_cx"] + g["x"], g["pos_cy"] + g["y"]
        return (cx, cy, cx + g["w"], cy + g["h"])
    if kind == "path_points":
        pts = g.get("points", [])
        if not pts:
            return (0, 0, 0, 0)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))
    if kind == "text":
        x, y = g["x"], g["y"]
        size = g.get("size", 6)
        return (x, y - size, x + size * 10, y + size)
    return (0, 0, 0, 0)
