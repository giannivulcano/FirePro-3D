"""Hatch pattern registry: built-in tile blocks, legacy aliases, picker source.

hatch-and-fill.md D-A28 / D-A29, concept HD4a. A pattern is a Block definition
with a ``tile``. Built-ins are code-level, read-only definitions with frozen
ids (HF8 replaces their content with shipped System > Hatches blocks; this
table stays the never-vanish fallback). Pure data at import time —
``geometry_2d`` imports this module — the built-in definitions are built
lazily so there is no import cycle through ``block_definition``.
"""
from __future__ import annotations

import json
import logging
import math
import os

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

#: Picker label for a stored ref that resolves to no offered tile (D-A36): shown
#: as the current value, never applied (``ref_from_value`` keeps the stored ref).
MISSING_PATTERN_LABEL = "<missing pattern>"

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


def picker_exclude(scene) -> frozenset:
    """Tile ids a picker in *scene* must not offer: in a Block Editor, the
    edited block and every tile that would nest it (a cycle the save refuses).

    Args:
        scene: The scene the picked fill lives in (or None).

    Returns:
        The excluded block ids (empty outside a Block Editor).
    """
    host = getattr(scene, "_editing_block_id", None) if scene is not None else None
    reg = getattr(scene, "block_registry", None) if scene is not None else None
    if host is None or reg is None:
        return frozenset()
    return frozenset({host} | {b for b in reg.ids() if reg.would_cycle(host, b)})


_log = logging.getLogger(__name__)
_LIB_CACHE: dict = {}        # abs folder -> (stamp, [(name, id, path)])
_PARSE_CACHE: dict = {}      # (.fpdb path, mtime_ns) -> (is_tile, id, name) | None
_LOGGED: set = set()         # paths already logged as unreadable (log once)


def _log_once(path: str, exc) -> None:
    if path not in _LOGGED:
        _LOGGED.add(path)
        _log.warning("Hatch pattern library: unreadable %s: %s", path, exc)


def _scan_dirs(folder: str) -> list[str]:
    """*folder*, its subfolders and their subfolders (a Series, a Library or a
    Library root all work as the patterns folder), sorted for determinism."""
    dirs, level = [folder], [folder]
    for _depth in range(2):
        nxt = []
        for d in level:
            try:
                subs = sorted(e.path for e in os.scandir(d) if e.is_dir())
            except OSError:
                continue
            nxt.extend(subs)
        dirs.extend(nxt)
        level = nxt
    return dirs


def _dir_stamp(dirs: list[str]) -> tuple:
    """Cache key: every index.json / .fpdb path in *dirs* with its mtime."""
    stamp = []
    for d in dirs:
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name)
        except OSError:
            continue
        for e in entries:
            low = e.name.lower()
            if e.is_file() and (low == "index.json" or low.endswith(".fpdb")):
                try:
                    stamp.append((e.path, e.stat().st_mtime_ns))
                except OSError:
                    continue
    return tuple(stamp)


def _parse_fpdb(path: str, mtime_ns: int):
    """``(is_tile, id, name)`` read from the .fpdb itself (index lacked
    ``tile``), cached per (path, mtime); None if unreadable."""
    key = (path, mtime_ns)
    if key in _PARSE_CACHE:
        return _PARSE_CACHE[key]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        res = (bool(data.get("tile")), data.get("id") or "", data.get("name") or "")
    except Exception as exc:          # noqa: BLE001 — skip silently, log once
        _log_once(path, exc)
        res = None
    _PARSE_CACHE[key] = res
    return res


def library_patterns(folder: str | None = None) -> list[tuple[str, str, str]]:
    """Pattern blocks in the Hatch patterns folder (D-A37).

    Scans *folder* (default ``app_data.hatch_patterns_dir()``) plus two levels
    of subfolders. Each Series ``index.json`` entry's ``tile`` flag decides;
    an older entry without the flag (or a ``.fpdb`` with no entry) is parsed
    once. Cached on the folder + every index.json/.fpdb mtime, so a newly
    saved pattern appears without a restart. Unreadable files are skipped
    (logged once). Never called from paint paths.

    Args:
        folder: Folder to scan; None = the configured Hatch patterns folder.

    Returns:
        ``[(name, block_id, .fpdb path)]`` sorted by name; first id wins.
    """
    if folder is None:
        from .app_data import hatch_patterns_dir
        folder = hatch_patterns_dir()
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        return []
    dirs = _scan_dirs(folder)
    stamp = _dir_stamp(dirs)
    hit = _LIB_CACHE.get(folder)
    if hit is not None and hit[0] == stamp:
        return list(hit[1])
    mtimes = dict(stamp)
    out, seen = [], set()
    for d in dirs:
        idx_path = os.path.join(d, "index.json")
        index: dict = {}
        if os.path.isfile(idx_path):
            try:
                with open(idx_path, "r", encoding="utf-8") as fh:
                    index = json.load(fh)
                if not isinstance(index, dict):
                    raise ValueError("index is not a mapping")
            except Exception as exc:  # noqa: BLE001
                _log_once(idx_path, exc)
                index = {}
        try:
            names = sorted(e.name for e in os.scandir(d)
                           if e.is_file() and e.name.lower().endswith(".fpdb"))
        except OSError:
            continue
        for fname in names:
            path = os.path.join(d, fname)
            meta = index.get(fname)
            if isinstance(meta, dict) and "tile" in meta and meta.get("id"):
                is_tile = bool(meta["tile"])
                bid, name = meta["id"], meta.get("name") or fname[:-5]
            else:
                parsed = _parse_fpdb(path, mtimes.get(path, 0))
                if parsed is None:
                    continue
                is_tile, bid, name = parsed
                name = name or fname[:-5]
            if is_tile and bid and bid not in seen:
                seen.add(bid)
                out.append((name, bid, path))
    out.sort(key=lambda x: x[0].lower())
    _LIB_CACHE[folder] = (stamp, out)
    return list(out)


def _unique(name: str, used: set, tag: str) -> str:
    label, k = name, 1
    while label in used:
        k += 1
        label = f"{name} ({tag})" if k == 2 else f"{name} ({tag} {k - 1})"
    used.add(label)
    return label


def tile_choices(registry=None, exclude=(),
                 include_library=True) -> list[tuple[str, str]]:
    """``[(label, ref)]``: built-ins in fixed order, then the project's valid
    tiled blocks by name, then the Hatch patterns folder's pattern blocks not
    already in the project (D-A37). The single source for every pattern picker.

    Labels are unique: a project tile whose name collides with an earlier label
    gets `` (project)`` appended (then `` (project 2)`` ...), a library one
    `` (library)``, so every ref is reachable through ``ref_from_value``.

    Args:
        registry: Project block registry, or None (built-ins only — e.g. the
            global category defaults, which can't reference a project block).
        exclude: Tile ids to leave out (``picker_exclude``).
        include_library: Append the library patterns (only with a registry:
            picking one loads it into that project — ``ensure_pattern_available``).
    """
    out = list(((n, i) for i, n in _BUILTIN_NAMES))
    if registry is not None:
        project = []
        for bid in registry.ids():
            if bid in exclude:
                continue
            d = registry.get(bid)
            if d is not None and d.tile and tile_is_valid(d):
                project.append((d.name or bid, bid))
        used = {n for n, _ in out}
        for name, bid in sorted(project, key=lambda x: x[0].lower()):
            out.append((_unique(name, used, "project"), bid))
        if include_library:
            for name, bid, _path in library_patterns():
                if bid in exclude or bid in BUILTIN_IDS or registry.get(bid) is not None:
                    continue
                out.append((_unique(name, used, "library"), bid))
    return out


def ensure_pattern_available(ref: str | None, scene) -> bool:
    """Load a library pattern into the project before its id is stored (D-A37).

    A built-in, a pattern already in the project registry, or a ref that is no
    library pattern (kept as-is per D-A36) needs nothing. A library-only
    pattern is loaded into the PROJECT scene (a Block Editor scene's
    ``_block_registry_owner``) as one undoable batch via
    ``blocks_browser.ensure_block_loaded``. UI paths only — never paint.

    Args:
        ref: The picked pattern ref (id or legacy name).
        scene: The scene the picked fill lives in (plan or Block Editor).

    Returns:
        False only when *ref* is a library pattern that failed to load (the
        caller must not store it); True otherwise.
    """
    ref = canonical_ref(ref)
    if not ref or ref in BUILTIN_IDS or scene is None:
        return True
    project = getattr(scene, "_block_registry_owner", None) or scene
    reg = getattr(project, "block_registry", None)
    if reg is None or reg.get(ref) is not None:
        return True
    for name, bid, path in library_patterns():
        if bid == ref:
            from .blocks_browser import ensure_block_loaded
            return ensure_block_loaded(project, bid, path, name)
    return True


def display_name(ref: str | None, registry=None, exclude=()) -> str:
    """Picker label for *ref* (falls back to the raw ref for an unknown one)."""
    ref = canonical_ref(ref)
    for name, r in tile_choices(registry, exclude):
        if r == ref:
            return name
    d = resolve_tile(ref, registry)
    return d.name if d is not None else (ref or "")


def ref_from_value(value: str, registry=None, exclude=()) -> str:
    """A picker label or a stored ref → the ref to store (D-A29: ids)."""
    for name, ref in tile_choices(registry, exclude):
        if value == name:
            return ref
    return canonical_ref(value)
