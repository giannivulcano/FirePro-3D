"""DXF SOLID / HATCH readers: entities to ``fill`` geom records (HF7 D1, D2).

Output is plain JSON-safe dicts in scene coordinates (Y negated), like the rest
of the extraction pipeline. ``loops`` is always flat and oriented by nesting
depth (even positive, odd negative), which the underlay's winding batch relies
on. ``exact_loops`` is added in curve-preserving mode, for Block Editor regions.
"""
from __future__ import annotations

import itertools
import math

from ezdxf import path as ezpath
from ezdxf import reorder
from ezdxf.render import hatching
from ezdxf.upright import upright

from .constants import HATCH_IMPORT_MAX_LINES
from .pdf_import_worker import _subpath_geoms

_FLATTEN_DIVISOR = 2000.0   # flatten tolerance = loop bbox diagonal / this
_PATH_TEXTBOX = 8           # DXF boundary path flag: a text box, not an edge
_WHITE = "#ffffff"


def in_draw_order(layout) -> list:
    """The layout's entities in paint order (bottom first).

    The redraw table applies when present. With no table the layout's own order
    stands: ``reorder.ascending`` would sort by handle, which can reorder a
    lines-only file for nothing.
    """
    table = list(layout.get_redraw_order())
    return list(reorder.ascending(layout, table)) if table else list(layout)


def _record(layer, color, *, solid, loops, exact_loops=None, lines=(), tone=False,
            pattern=None) -> dict:
    rec = {"kind": "fill", "layer": layer, "color": color, "solid": solid,
           "mask": bool(solid and str(color).lower() == _WHITE), "tone": tone,
           "loops": loops, "lines": list(lines), "pattern": pattern}
    if exact_loops is not None:
        rec["exact_loops"] = exact_loops
    return rec


def _child(layer, color, points, *, straight=False) -> dict:
    g = {"kind": "path_points", "layer": layer, "color": color,
         "points": points, "closed": True}
    if straight:
        g["straight"] = True
    return g


def read_solid(entity, layer: str, color: str) -> dict | None:
    """A SOLID as one closed straight loop; None under 3 distinct corners."""
    pts: list[tuple[float, float]] = []
    for v in entity.wcs_vertices():
        p = (v.x, -v.y)
        if not pts or p != pts[-1]:
            pts.append(p)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    if len(pts) < 3:
        return None
    return _record(layer, color, solid=True,
                   loops=[[_child(layer, color, _oriented(pts, 0), straight=True)]])


def _signed_area(pts) -> float:
    return sum(a[0] * b[1] - b[0] * a[1]
               for a, b in zip(pts, [*pts[1:], pts[0]])) / 2


def _oriented(pts: list, depth: int) -> list:
    """*pts* with positive area at an even depth, negative at an odd one."""
    return pts if (_signed_area(pts) > 0) == (depth % 2 == 0) else list(reversed(pts))


def _inside(pt, poly) -> bool:
    x, y = pt
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, [*poly[1:], poly[0]]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def _depths(polys: list[list]) -> list[int]:
    """Nesting depth of each loop, from geometry.

    Hatch path flags do not hold this: real files mark outer loops 0 and flag
    islands EXTERNAL. The test point is the first edge's midpoint, so a corner
    shared with another loop does not decide it.
    """
    out = []
    for i, poly in enumerate(polys):
        (ax, ay), (bx, by) = poly[0], poly[1]
        mid = ((ax + bx) / 2, (ay + by) / 2)
        out.append(sum(1 for j, q in enumerate(polys) if j != i and _inside(mid, q)))
    return out


def _flat(p) -> list[tuple[float, float]]:
    """Path *p* flattened at a tolerance relative to its size (scene coords)."""
    vs = p.control_vertices()
    xs, ys = [v.x for v in vs], [v.y for v in vs]
    diag = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    if diag <= 0:
        return []
    pts = [(v.x, -v.y) for v in p.flattening(diag / _FLATTEN_DIVISOR)]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    return pts


def _segs(p) -> list[tuple]:
    """Path *p* as the ``("l", a, b)`` / ``("c", a, c1, c2, b)`` runs
    ``pdf_import_worker._subpath_geoms`` reads (scene coords)."""
    xy = lambda v: (v.x, -v.y)         # noqa: E731
    out, cur = [], p.start
    for cmd in p.commands():
        if cmd.type == ezpath.Command.LINE_TO:
            out.append(("l", xy(cur), xy(cmd.end)))
        elif cmd.type == ezpath.Command.CURVE3_TO:
            c1 = cur + (cmd.ctrl - cur) * (2 / 3)
            c2 = cmd.end + (cmd.ctrl - cmd.end) * (2 / 3)
            out.append(("c", xy(cur), xy(c1), xy(c2), xy(cmd.end)))
        elif cmd.type == ezpath.Command.CURVE4_TO:
            out.append(("c", xy(cur), xy(cmd.ctrl1), xy(cmd.ctrl2), xy(cmd.end)))
        cur = cmd.end
    return out


def _exact_loop(p, layer, color) -> list[dict]:
    children = _subpath_geoms(_segs(p), True, layer)
    for c in children:
        c["color"] = color
    return children


def _keep(depth: int, style: int) -> bool:
    """Hatch style filter: 0 normal, 1 outer (two levels), 2 ignore (outermost)."""
    if style == 2:
        return depth == 0
    if style == 1:
        return depth <= 1
    return True


def _pattern(entity) -> dict | None:
    pat = entity.pattern
    if entity.dxf.solid_fill or pat is None or not pat.lines:
        return None
    fams = [{"angle": -ln.angle,
             "base": [ln.base_point.x, -ln.base_point.y],
             "offset": [ln.offset.x, -ln.offset.y],
             "dashes": list(ln.dash_length_items)} for ln in pat.lines]
    return {"name": entity.dxf.pattern_name or "", "families": fams}


def _pattern_lines(entity) -> tuple[list[list[float]], bool]:
    """``(lines, tone)``: the clipped pattern lines, or a tone past the cap."""
    try:
        gen = hatching.hatch_entity(entity, jiggle_origin=False)
        pairs = list(itertools.islice(gen, HATCH_IMPORT_MAX_LINES + 1))
    except hatching.DenseHatchingLinesError:
        return [], True
    if len(pairs) > HATCH_IMPORT_MAX_LINES:
        return [], True
    return [[a.x, -a.y, b.x, -b.y] for a, b in pairs], False


def read_hatch(entity, layer: str, color: str, *, exact: bool = False) -> dict | None:
    """A HATCH as one fill record; None when no usable loop remains."""
    if entity.dxf.extrusion.z < 0:
        upright(entity)
    ocs, elevation = entity.ocs(), entity.dxf.elevation.z
    paths, polys = [], []
    for bp in entity.paths:
        if int(bp.path_type_flags) & _PATH_TEXTBOX:
            continue
        whole = ezpath.from_hatch_boundary_path(bp, ocs, elevation)
        for sub in whole.sub_paths():
            pts = _flat(sub)
            if len(pts) >= 3:
                paths.append(sub)
                polys.append(pts)
    if not polys:
        return None
    depths = _depths(polys)
    style = int(entity.dxf.hatch_style)
    kept = [i for i, d in enumerate(depths) if _keep(d, style)]
    loops = [[_child(layer, color, _oriented(polys[i], depths[i]))] for i in kept]
    exact_loops = ([_exact_loop(paths[i], layer, color) for i in kept] if exact else None)
    solid = bool(entity.dxf.solid_fill)
    pattern = _pattern(entity)
    lines, tone = ([], False) if pattern is None else _pattern_lines(entity)
    return _record(layer, color, solid=solid, loops=loops, exact_loops=exact_loops,
                   lines=lines, tone=tone, pattern=pattern)
