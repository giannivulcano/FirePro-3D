"""Fill geom records to Block Editor items and an import report (HF7 D4, D7)."""
from __future__ import annotations

from PyQt6.QtCore import QPointF

from . import fill_types, hatch_tile
from .constants import HATCH_IMPORT_MAX_EDIT_LINES, IMPORTED_SOLID_TYPE, TOKEN_AUTO
from .dwg_converter import fill_line_geoms
from .fill_layers import BackgroundLayer, FillLayers, PatternLayer
from .filled_region import FilledRegionItem
from .geometry_2d import LineItem
from .geometry_import import geom_dicts_to_primitives

_LIBRARY, _SERIES = "Imported", "Patterns"
_LINES_AND_BOUNDARY = "lines and boundary"
_BOUNDARY_ONLY = "boundary only"
_DEPTH_LOW, _DEPTH_SPAN = -0.9, 0.8     # the free band between regions and shapes


def _is_auto(color) -> bool:
    return not color or color == TOKEN_AUTO


def _region(g: dict, lineweight: float) -> FilledRegionItem | None:
    """A region from the fill's exact loops (flat loops when absent).

    The region fills even-odd, so the loops' winding does not matter.
    """
    loops = []
    for loop in g.get("exact_loops") or g.get("loops", ()):
        pieces, _ = geom_dicts_to_primitives(loop, 1.0, lineweight=lineweight)
        if pieces:
            loops.append(pieces)
    if not loops:
        return None
    region = FilledRegionItem.from_pieces(loops)
    region.layer = g.get("layer", "")
    return region


def _pattern_name(g: dict) -> str:
    name = (g["pattern"].get("name") or "").strip()
    return "Hatch" if not name or name.startswith("_") else name


def _free_block_name(scene, base: str) -> str:
    names = {d.name for d in scene._block_definitions.values()}
    if base not in names:
        return base
    n = 2
    while f"{base} {n}" in names:
        n += 1
    return f"{base} {n}"


def _stored_key(defn) -> str | None:
    t = defn.tile
    if not t or t["w"] <= 0 or t["h"] <= 0:
        return None
    try:
        segs = [(*p["pt1"], *p["pt2"]) for p in defn.primitives]
    except KeyError:
        return None                     # a user-edited block with other primitives
    return hatch_tile.key_of(segs, t["w"], t["h"])


def _find_or_commit(scene, tile, name: str, lineweight: float, seen: dict):
    """The project block for *tile*; a new one is part of the undo baseline."""
    if tile.key in seen:
        return seen[tile.key]
    for defn in scene._block_definitions.values():
        if defn.library == _LIBRARY and _stored_key(defn) == tile.key:
            seen[tile.key] = defn
            return defn
    prims = [LineItem(QPointF(x1, y1), QPointF(x2, y2), TOKEN_AUTO, lineweight).to_dict()
             for x1, y1, x2, y2 in tile.segments]
    defn = scene.commit_block_outside_history(
        block_id=None, name=_free_block_name(scene, f"{name} (imported)"),
        library=_LIBRARY, series=_SERIES, primitives=prims, origin=(0.0, 0.0),
        capability=("tile", {"w": tile.w, "h": tile.h, "row_shift": 0.0, "size": "model"}),
        place_instance=False)
    seen[tile.key] = defn
    return defn


def _solid_region(g, lineweight, table):
    region = _region(g, lineweight)
    if region is None:
        return None
    t = table.ensure_named(IMPORTED_SOLID_TYPE, FillLayers(BackgroundLayer(TOKEN_AUTO, 1.0)))
    region.set_fill_type(t.id)
    region.outline = False
    color = g.get("color")
    if not _is_auto(color):
        region.fill_layers = FillLayers(BackgroundLayer(color, 1.0))
    return region


def _pattern_region(g, tile, lineweight, table, scene, seen):
    region = _region(g, lineweight)
    if region is None:
        return None
    name = _pattern_name(g)
    defn = _find_or_commit(scene, tile, name, lineweight, seen)
    if defn is None:
        return None
    t = table.ensure_look(f"{name} (imported)",
                          FillLayers(None, PatternLayer(defn.id, TOKEN_AUTO, 1.0, 1.0)))
    region.set_fill_type(t.id)
    region.outline = False
    scale = tile.w / defn.tile["w"]
    color = g.get("color")
    region.fill_layers = FillLayers(None, PatternLayer(
        defn.id, TOKEN_AUTO if _is_auto(color) else color, 1.0, scale))
    return region


def _boundary_shapes(g, lineweight) -> list:
    items = []
    for loop in g.get("exact_loops") or g.get("loops", ()):
        got, _ = geom_dicts_to_primitives(loop, 1.0, lineweight=lineweight)
        items.extend(got)
    return items


def _unconverted(g, lineweight) -> tuple[list, str]:
    lines = fill_line_geoms(g)
    if g.get("tone") or len(lines) > HATCH_IMPORT_MAX_EDIT_LINES:
        return _boundary_shapes(g, lineweight), _BOUNDARY_ONLY
    drawn, _ = geom_dicts_to_primitives(lines, 1.0, lineweight=lineweight)
    return [*drawn, *_boundary_shapes(g, lineweight)], _LINES_AND_BOUNDARY


def _families_key(families) -> tuple:
    """A hashable form of a family list (the same pattern is the same list)."""
    return tuple((f["angle"], tuple(f["base"]), tuple(f["offset"]), tuple(f["dashes"]))
                 for f in families)


def build_items(geoms, *, lineweight, project_scene):
    """Editor items for *geoms*, in paint order.

    Args:
        geoms: Transformed geom dicts holding at least one fill.
        lineweight: Weight of produced strokes.
        project_scene: Scene that owns the pattern blocks.

    Returns:
        ``(items, skipped, report)``. ``report`` rows are
        ``(pattern name, count, outcome)``, only for what did not convert.
    """
    table = fill_types.project_table()
    seen: dict = {}
    tiles: dict = {}            # family list -> Tile | None (convert is the slow step)
    items: list = []
    counts: dict = {}
    skipped = 0
    for g in geoms:
        if g.get("kind") != "fill":
            got, s = geom_dicts_to_primitives([g], 1.0, lineweight=lineweight)
            items.extend(got)
            skipped += s
            continue
        if g.get("solid"):
            region = _solid_region(g, lineweight, table)
            if region is None:
                skipped += 1
            else:
                items.append(region)
            continue
        if not g.get("pattern"):
            skipped += 1
            continue
        tile = None
        if not g.get("tone"):
            fk = _families_key(g["pattern"]["families"])
            if fk not in tiles:
                tiles[fk] = hatch_tile.convert(g["pattern"]["families"])
            tile = tiles[fk]
        region = (_pattern_region(g, tile, lineweight, table, project_scene, seen)
                  if tile is not None else None)
        if region is not None:
            items.append(region)
            continue
        got, outcome = _unconverted(g, lineweight)
        items.extend(got)
        key = (_pattern_name(g), outcome)
        counts[key] = counts.get(key, 0) + 1
    n = len(items)
    for i, it in enumerate(items):
        if hasattr(it, "set_draw_z"):
            it.set_draw_z(_DEPTH_LOW + _DEPTH_SPAN * (i + 1) / (n + 1))
    return items, skipped, [(name, c, outcome) for (name, outcome), c in counts.items()]
