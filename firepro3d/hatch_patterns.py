"""Hatch pattern registry: frozen pattern ids, legacy aliases, picker source.

hatch-and-fill.md D-A29 / D-A37 / D-A39, concept HD4a. A pattern is a Block
definition with a ``tile``. **Blocks only (D-A39):** there is no code-level
pattern table. The five standard patterns (Diagonal, Cross Hatch, Horizontal,
Concrete, Brick) ship as real ``.fpdb`` blocks under
``firepro3d/system_blocks/Hatches`` (frozen ids below), are copied into the
Hatch patterns folder once (``seed_hatch_folder``) and are loaded into a
project from that folder on new / open (``ensure_project_patterns``). A ref
resolves through the project block registry only; one that can't resolve
draws the tone (D-A36). Pure data at import time — ``geometry_2d`` imports
this module — so Qt / block imports stay inside the functions.
"""
from __future__ import annotations

import json
import logging
import os
import shutil

# Frozen ids of the shipped patterns (D-A39: ordinary block ids — the files
# live in firepro3d/system_blocks/Hatches; the ids predate the shipped files).
BUILTIN_DIAGONAL = "builtin-hatch-diagonal"
BUILTIN_CROSS_HATCH = "builtin-hatch-cross-hatch"
BUILTIN_HORIZONTAL = "builtin-hatch-horizontal"
BUILTIN_CONCRETE = "builtin-hatch-concrete"
BUILTIN_BRICK = "builtin-hatch-brick"

#: Legacy pattern names (QSettings, DM overrides, old files) → frozen id (D-A29).
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

#: QSettings key: the Hatch patterns folders already seeded (D-A39 "once").
HATCH_SEEDED_KEY = "paths/hatch_seeded"

_INDEX = "index.json"


def canonical_ref(ref: str | None) -> str | None:
    """A legacy name mapped to its frozen id; any other ref unchanged."""
    if not ref:
        return ref
    return LEGACY_ALIAS.get(ref, ref)


def shipped_patterns_dir() -> str:
    """The app's read-only folder of shipped pattern ``.fpdb`` files (D-A39)."""
    from .assets import system_blocks_path
    return system_blocks_path("Hatches")


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def shipped_pattern_files() -> list[tuple[str, str]]:
    """``[(block id, .fpdb path)]`` of the shipped patterns, sorted by file name."""
    folder = shipped_patterns_dir()
    out = []
    try:
        names = sorted(n for n in os.listdir(folder) if n.lower().endswith(".fpdb"))
    except OSError:
        return out
    for n in names:
        path = os.path.join(folder, n)
        try:
            bid = _read_json(path).get("id")
        except Exception as exc:          # noqa: BLE001 — a broken ship file
            _log_once(path, exc)
            continue
        if bid:
            out.append((bid, path))
    return out


def _seeded_folders() -> list[str]:
    from PyQt6.QtCore import QSettings
    raw = QSettings("GV", "FirePro3D").value(HATCH_SEEDED_KEY, [])
    if isinstance(raw, str):
        raw = [raw] if raw else []
    return [os.path.normcase(os.path.abspath(p)) for p in (raw or []) if p]


def _mark_seeded(folder: str) -> None:
    from PyQt6.QtCore import QSettings
    s = QSettings("GV", "FirePro3D")
    seen = _seeded_folders()
    key = os.path.normcase(os.path.abspath(folder))
    if key not in seen:
        seen.append(key)
    s.setValue(HATCH_SEEDED_KEY, seen)
    s.sync()


def _folder_ids(folder: str) -> set[str]:
    """Every block id held by an ``.fpdb`` in *folder* (+ two subfolder levels),
    read from the files themselves (an index can be stale or missing)."""
    ids = set()
    for d in _scan_dirs(folder):
        try:
            names = [e.path for e in os.scandir(d)
                     if e.is_file() and e.name.lower().endswith(".fpdb")]
        except OSError:
            continue
        for path in names:
            try:
                bid = _read_json(path).get("id")
            except Exception:             # noqa: BLE001 — unreadable: not ours
                continue
            if bid:
                ids.add(bid)
    return ids


def seed_hatch_folder(folder: str | None = None) -> list[str]:
    """Copy the shipped patterns into the Hatch patterns folder, once (D-A39).

    Runs once per folder (recorded under ``HATCH_SEEDED_KEY``): a shipped
    pattern the user later deletes is not re-seeded. A shipped pattern whose id
    is already held by any ``.fpdb`` in the folder (the user's edited copy,
    whatever its file name) is skipped — never overwritten. A copy that would
    clash with a different block's file name is skipped too. The folder's
    ``index.json`` gains an entry (with the ``tile`` flag) per copied file.

    Args:
        folder: Target folder; None = ``app_data.hatch_patterns_dir()``.

    Returns:
        The block ids copied (empty when the folder was already seeded).
    """
    if folder is None:
        from .app_data import hatch_patterns_dir
        folder = hatch_patterns_dir()
    folder = os.path.abspath(folder)
    if os.path.normcase(folder) in _seeded_folders():
        return []
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError as exc:
        _log.warning("Hatch patterns folder %s not writable: %s", folder, exc)
        return []
    have = _folder_ids(folder)
    idx_path = os.path.join(folder, _INDEX)
    index: dict = {}
    if os.path.isfile(idx_path):
        try:
            index = _read_json(idx_path)
            if not isinstance(index, dict):
                index = {}
        except Exception as exc:          # noqa: BLE001
            _log_once(idx_path, exc)
            index = {}
    copied = []
    for bid, src in shipped_pattern_files():
        if bid in have:
            continue
        fname = os.path.basename(src)
        dst = os.path.join(folder, fname)
        if os.path.exists(dst):
            continue                      # a different block owns the name
        try:
            shutil.copyfile(src, dst)
            data = _read_json(src)
        except (OSError, ValueError) as exc:
            _log.warning("Hatch pattern seed %s failed: %s", fname, exc)
            continue
        index[fname] = {"id": bid, "name": data.get("name") or fname[:-5],
                        "version": data.get("version", 1), "thumbnail": None,
                        "tile": bool(data.get("tile"))}
        copied.append(bid)
    if copied:
        tmp = idx_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(index, fh, indent=2)
            os.replace(tmp, idx_path)
        except OSError as exc:
            _log.warning("Hatch pattern index %s not written: %s", idx_path, exc)
        from . import block_library
        block_library._notify_changed()   # an open Blocks browser refreshes
    _mark_seeded(folder)
    return copied


def tile_is_valid(defn) -> bool:
    """A usable tile: positive W×H and at least one compiled op (edge: empty tile)."""
    t = getattr(defn, "tile", None)
    return bool(t) and t["w"] > 0 and t["h"] > 0 and bool(defn.render_ops())


def resolve_tile(ref: str | None, registry=None):
    """Tile definition for *ref*: alias → the project registry; else None.

    Blocks only (D-A39): there is no code-level fallback — an unloaded ref
    resolves to None and the renderer draws the tone (D-A36).
    """
    ref = canonical_ref(ref)
    if not ref or registry is None:
        return None
    d = registry.get(ref)
    if d is not None and d.tile:
        return d
    return None


_PREVIEW_CACHE: dict = {}    # (.fpdb path, mtime_ns) -> BlockDefinition | None


def _file_tile(path: str):
    """A pattern definition read from *path* for previews (cached per mtime)."""
    try:
        key = (path, os.stat(path).st_mtime_ns)
    except OSError:
        return None
    if key not in _PREVIEW_CACHE:
        from .block_library import load_block_file
        d = load_block_file(path)
        _PREVIEW_CACHE[key] = d if d is not None and d.tile else None
    return _PREVIEW_CACHE[key]


def preview_tile(ref: str | None, registry=None):
    """Tile definition for a picker / badge swatch (never the renderer).

    The project registry first; else the Hatch patterns folder's copy (a
    library pattern a picker offers before it is loaded); else the shipped
    file. Swatches only — canvas / sheet / PDF rendering resolves through
    :func:`resolve_tile` (blocks loaded in the project, D-A39).
    """
    d = resolve_tile(ref, registry)
    if d is not None:
        return d
    ref = canonical_ref(ref)
    if not ref:
        return None
    for _name, bid, path in library_patterns():
        if bid == ref:
            d = _file_tile(path)
            if d is not None:
                return d
    for bid, path in shipped_pattern_files():
        if bid == ref:
            return _file_tile(path)
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
    """``[(label, ref)]``: the project's valid tiled blocks by name, then the
    Hatch patterns folder's pattern blocks not already in the project (D-A37).
    Blocks only (D-A39) — the single source for every pattern picker.

    Labels are unique: a name colliding with an earlier label gets
    `` (project)`` / `` (library)`` appended (then `` (project 2)`` ...), so
    every ref is reachable through ``ref_from_value``.

    Args:
        registry: Project block registry, or None (folder patterns only — the
            global Display Manager category defaults, which can't reference a
            project-only block).
        exclude: Tile ids to leave out (``picker_exclude``).
        include_library: Append the folder patterns (picking one loads it into
            the project — ``ensure_pattern_available``).
    """
    out: list[tuple[str, str]] = []
    used: set = set()
    if registry is not None:
        project = []
        for bid in registry.ids():
            if bid in exclude:
                continue
            d = registry.get(bid)
            if d is not None and d.tile and tile_is_valid(d):
                project.append((d.name or bid, bid))
        for name, bid in sorted(project, key=lambda x: x[0].lower()):
            out.append((_unique(name, used, "project"), bid))
    if include_library:
        for name, bid, _path in library_patterns():
            if bid in exclude or (registry is not None
                                  and registry.get(bid) is not None):
                continue
            out.append((_unique(name, used, "library"), bid))
    return out


def ensure_pattern_available(ref: str | None, scene) -> bool:
    """Load a library pattern into the project before its id is stored (D-A37).

    A pattern already in the project registry, or a ref that is no library
    pattern (kept as-is per D-A36) needs nothing. A library-only pattern is
    loaded into the PROJECT scene (a Block Editor scene's
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
    if not ref or scene is None:
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


def _fill_ref(primitive) -> str | None:
    f = primitive.get("fill") if isinstance(primitive, dict) else None
    if isinstance(f, dict) and f.get("type") == "hatch":
        return canonical_ref(f.get("pattern"))
    return None


def project_pattern_refs(scene) -> set[str]:
    """Every pattern ref a project uses or will draw with (D-A39).

    Collected (canonical ids): 2D items' hatch ``fill_pattern``; every block
    definition's primitive hatch fills; each item's Display Manager section
    pattern (``_display_section_pattern`` + a per-instance
    ``_display_overrides`` value); every Display Manager category
    ``section_pattern`` (QSettings / factory, via the DM reader); and
    ``DEFAULT_TILE_REF`` — the pattern walls / floors / roofs fall back to.

    Args:
        scene: The project ``Model_Space``.

    Returns:
        The set of canonical refs (loaded or not).
    """
    refs: set = {DEFAULT_TILE_REF}
    for item in scene.items():
        if getattr(item, "fill_type", None) == "hatch":
            refs.add(canonical_ref(getattr(item, "fill_pattern", None)))
        refs.add(canonical_ref(getattr(item, "_display_section_pattern", None)))
        ov = getattr(item, "_display_overrides", None)
        if isinstance(ov, dict):
            refs.add(canonical_ref(ov.get("section_pattern")))
    store = getattr(scene, "_block_definitions", None) or {}
    for defn in list(store.values()):
        for p in getattr(defn, "primitives", ()) or ():
            refs.add(_fill_ref(p))
    try:
        from .display_manager import _CATEGORIES, _read_category_from_settings
        for cat in _CATEGORIES:
            if cat.get("section_pattern") is None:
                continue
            refs.add(canonical_ref(
                _read_category_from_settings(cat["key"]).get("section_pattern")))
    except Exception:                     # noqa: BLE001 — DM unavailable headless
        _log.debug("Display Manager categories unreadable", exc_info=True)
    refs.discard(None)
    refs.discard("")
    return {r for r in refs if isinstance(r, str)}


def load_patterns_outside_history(scene, refs) -> list[str]:
    """Load the folder patterns among *refs* the project lacks — no undo step.

    The loaded definitions join every existing undo snapshot (the baseline),
    so Ctrl+Z can never unload them (D-A39). Refs not in the Hatch patterns
    folder are left alone (they draw the tone, D-A36).

    Args:
        scene: The project ``Model_Space`` (a Block Editor scene's
            ``_block_registry_owner`` is used when given an editor scene).
        refs: Pattern refs (ids or legacy names).

    Returns:
        The block ids that became project definitions.
    """
    project = getattr(scene, "_block_registry_owner", None) or scene
    store = getattr(project, "_block_definitions", None)
    if store is None or not hasattr(project, "load_blocks_outside_history"):
        return []
    want = {canonical_ref(r) for r in refs if r} - set(store)
    if not want:
        return []
    paths = [path for _name, bid, path in library_patterns() if bid in want]
    if not paths:
        return []
    return project.load_blocks_outside_history(paths)


def ensure_project_patterns(scene) -> list[str]:
    """Load every pattern the project references from the folder (D-A39).

    Call on project new (before the undo baseline reset) and after project
    open (after the display settings are applied). Repeats until nothing new
    loads, so a pattern whose own fills use another pattern is followed.

    Args:
        scene: The project ``Model_Space``.

    Returns:
        The block ids loaded.
    """
    loaded: list = []
    for _round in range(8):               # nested pattern-in-pattern depth cap
        got = load_patterns_outside_history(scene, project_pattern_refs(scene))
        if not got:
            break
        loaded.extend(got)
    return loaded


def display_name(ref: str | None, registry=None, exclude=()) -> str:
    """Picker label for *ref* (falls back to the raw ref for an unknown one)."""
    ref = canonical_ref(ref)
    for name, r in tile_choices(registry, exclude):
        if r == ref:
            return name
    d = preview_tile(ref, registry)
    return d.name if d is not None else (ref or "")


def ref_from_value(value: str, registry=None, exclude=()) -> str:
    """A picker label or a stored ref → the ref to store (D-A29: ids)."""
    for name, ref in tile_choices(registry, exclude):
        if value == name:
            return ref
    return canonical_ref(value)
