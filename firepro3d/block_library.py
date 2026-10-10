"""Two-tier user library for block definitions.

Layout: ``<root>/<Library>/<Series>/<name>.fpdb`` (a BlockDefinition.to_dict())
for blocks; ``<root>[/<Series>]/<name>.fpdb`` for schematic templates (empty
tiers skipped -- schematics.md D-S15). The files on disk ARE the library: the
walk reads each ``.fpdb`` (``capability_folder.read_meta``, cached per mtime),
so a file copied in from outside the app is listed. Folder + filename win over
the stored library / series / name; a block file not in a full
Library/Series folder lists under :data:`UNGROUPED`. The per-folder
``index.json`` is retired (2026-10-10): never written, and a stale one is
removed when the app next writes or deletes in that folder. Mirrors
titleblock_template's atomic-write + tolerant-load + version divergence. See
docs/specs/block-system.md.
"""
from __future__ import annotations

import json
import logging
import os

from . import capability_folder
from .capability_folder import sanitize  # noqa: F401 -- public name, kept here
from .app_data import block_library_dir
from .block_definition import BlockDefinition

_log = logging.getLogger(__name__)
_LEGACY_INDEX = "index.json"   # retired 2026-10-10; removed on the next write
#: Fallback tier for a block ``.fpdb`` not in a full <Library>/<Series> folder.
UNGROUPED = "Ungrouped"
# Load-summary refusal reason for a file that would nest a block in itself.
LOOP_REASON = "a block can't contain itself"
# Place / drag refusal for a tiled (pattern) block (hatch D-A34).
PATTERN_REASON = "Pattern blocks fill regions — they can't be placed"
# Place / drag refusal for a linetype (repeat) block (linetypes.md LT3-2).
LINETYPE_REASON = "Linetype blocks style lines — they can't be placed"
# Place / drag refusal for an end-type block (linetypes.md D-L12, LT5 Q12).
END_REASON = "End type blocks finish lines — they can't be placed"
# Place / drag refusal for a schematic (schematics.md D-S3).
SCHEMATIC_REASON = "Schematics go on sheets as views — they can't be placed"
# Load-summary refusal reason for a same-id file of the other kind: a placed
# block must never silently become a schematic, nor a schematic a block
# (schematics.md D-S3; SV4). ``commit_block_definition`` refuses the same on edit.
KIND_REASON = "a block and a schematic can't replace each other"
_listeners: list = []     # weak refs to zero-arg callables (library changed)


def add_change_listener(callback) -> None:
    """Call *callback()* after any library write (save / delete / new folder).

    Held weakly (bound methods via ``WeakMethod``) so a closed browser never
    leaks or gets called; a listener that raises is logged, not propagated.
    """
    import weakref
    ref = (weakref.WeakMethod(callback) if hasattr(callback, "__self__")
           else weakref.ref(callback))
    _listeners.append(ref)


def _notify_changed() -> None:
    alive = []
    for ref in _listeners:
        cb = ref()
        if cb is None:
            continue
        alive.append(ref)
        try:
            cb()
        except Exception:      # noqa: BLE001 — a dead Qt receiver etc.
            _log.debug("block library listener failed", exc_info=True)
    _listeners[:] = alive


class BlockNameCollision(Exception):
    """Raised by :func:`save_to_library` when the target ``.fpdb`` filename is
    already occupied by a *different* block ``id`` (and ``overwrite`` is False).

    Carries ``existing_name`` (the human name of the block that would be
    clobbered) so the caller can offer an overwrite/cancel prompt.
    """

    def __init__(self, existing_name: str, filename: str):
        super().__init__(
            f"A different block already uses {filename!r} ({existing_name!r})")
        self.existing_name = existing_name
        self.filename = filename


def _root(root: str | None) -> str:
    return root if root is not None else block_library_dir()


def _plain_segment(raw: str) -> bool:
    """True when *raw* can name one folder / file as-is (no separators)."""
    return bool(raw) and raw not in (".", "..") and not any(
        c in raw for c in ("/", "\\", os.sep))


def _segment(parent: str, raw: str, suffix: str = "") -> str:
    """The on-disk name for *raw* under *parent*: an existing entry with the
    exact name is reused (a folder or file the user made in Explorer, e.g.
    ``Pipe & Fittings``), else :func:`sanitize` names a new one."""
    if _plain_segment(raw) and os.path.exists(os.path.join(parent, raw + suffix)):
        return raw + suffix
    return sanitize(raw) + suffix


def _series_dir(root: str | None, library: str, series: str) -> str:
    """Folder for a (library, series) pair. An EMPTY tier is skipped (never a
    ``"_"`` folder): a schematic template has no Library tier (schematics.md
    D-S15) and an ungrouped one no Series either. Blocks always carry both."""
    d = _root(root)
    for raw in (library, series):
        if raw:
            d = os.path.join(d, _segment(d, raw))
    return d


def _target_path(root: str | None, library: str, series: str, name: str) -> str:
    """Where a definition with this identity is saved (see :func:`_segment`)."""
    d = _series_dir(root, library, series)
    return os.path.join(d, _segment(d, name, ".fpdb"))


def _human(on_disk: str, stored: str) -> str:
    """The stored (human) value when *on_disk* is it or its sanitized form --
    ``Pipe _ Fittings`` reads ``Pipe & Fittings`` -- else the on-disk name
    (folder / filename win). Compared as the file system does (case-blind on
    Windows), so a reused ``fire/valves`` folder still reads ``Fire/Valves``."""
    nc = os.path.normcase
    if stored and nc(on_disk) in (nc(stored), nc(sanitize(stored))):
        return stored
    return on_disk


def list_folders(root: str | None = None) -> dict[str, list[str]]:
    """The on-disk Library → Series folder tree (names sorted, files ignored).

    Returns:
        ``{library: [series, ...]}``; ``{}`` when the root does not exist.
    """
    base = _root(root)
    tree: dict[str, list[str]] = {}
    try:
        libs = sorted(e for e in os.listdir(base)
                      if os.path.isdir(os.path.join(base, e)))
    except OSError:
        return {}
    for lib in libs:
        lib_dir = os.path.join(base, lib)
        try:
            tree[lib] = sorted(e for e in os.listdir(lib_dir)
                               if os.path.isdir(os.path.join(lib_dir, e)))
        except OSError:
            tree[lib] = []
    return tree


def create_folder(library: str, series: str | None = None,
                  root: str | None = None) -> str:
    """Create a Library (and optionally Series) folder; returns its path.

    Segments are :func:`sanitize`-d exactly as :func:`save_to_library` names
    them, so a folder made here is the one a later save lands in.
    """
    path = os.path.join(_root(root), *[sanitize(s) for s in (library, series) if s])
    os.makedirs(path, exist_ok=True)
    _notify_changed()
    return path


def find_collision(block_id: str, library: str, series: str, name: str,
                   root: str | None = None) -> str | None:
    """Name of a DIFFERENT block holding ``<name>.fpdb`` in Library/Series.

    The same probe :func:`save_to_library` refuses on (without writing), so a
    caller can resolve Overwrite / Rename / Cancel before committing.

    The occupying file is read itself. A duplicate-id copy (its id owned by
    another file) is not a collision for the block it became (loading it gave
    the project copy a fresh id; its Save writes back over that file) -- but
    it IS one for the original, whose Save would clobber the user's copy.

    Returns:
        The occupying file's block name (its filename stem), or None when the
        slot is free (or already held by *block_id*).
    """
    path = _target_path(root, library, series, name)
    if not os.path.isfile(path):
        return None
    meta = capability_folder.read_meta(path)
    if meta is not None and meta["id"]:
        owner = _find_by_id(meta["id"], root)
        is_owner = owner is None or _same_path(owner[3]["path"], path)
        if meta["id"] == block_id and is_owner:
            return None          # this block's own file
        if meta["id"] != block_id and not is_owner:
            return None          # a copy the project re-id'd on load (AC4)
    return os.path.basename(path)[:-5]


def _atomic_write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _drop_stale_index(folder: str) -> None:
    """Remove a pre-2026-10-10 ``index.json`` from *folder* (no-op if absent)."""
    path = os.path.join(folder, _LEGACY_INDEX)
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            _log.debug("could not remove stale index %s", path, exc_info=True)


def _delete_path(path: str) -> None:
    """Remove one ``.fpdb`` (no-op when absent) and its folder's stale index."""
    if os.path.isfile(path):
        os.remove(path)
    capability_folder.forget(path)
    _drop_stale_index(os.path.dirname(path))


def used_weight_names(records) -> set[str]:
    """Named weights referenced by definition dicts (canonical names, H-g):
    text ``border_weight``, stroke ``style.weight`` (LT2) and nested-record
    Weight overrides (WM2). The ``.fpdb``
    format stays.
    """
    from .paper_display import canonical_weight_name
    from .stroke_style import is_named_weight
    names = set()
    for rec in records:
        for prim in rec.get("primitives", []) or []:
            if prim.get("type") == "text" and prim.get("border_weight"):
                names.add(canonical_weight_name(prim["border_weight"]))
            w = (prim.get("style") or {}).get("weight")
            if is_named_weight(w):
                names.add(canonical_weight_name(w))
            ov = prim.get("overrides")
            if isinstance(ov, dict) and is_named_weight(ov.get("weight")):
                names.add(canonical_weight_name(ov["weight"]))   # WM2 H4
    return names


def read_bundled_weights(path: str) -> dict:
    """The ``weights`` ``{name: mm}`` map of a ``.fpdb`` ({} when absent/unreadable)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return dict(json.load(fh).get("weights") or {})
    except Exception:
        _log.debug("unreadable bundled weights in %s", path, exc_info=True)
        return {}


def read_bundled_weight_model_px(path: str) -> dict:
    """The ``weight_model_px`` ``{name: px}`` map of a ``.fpdb`` (H-MW-a)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return dict(json.load(fh).get("weight_model_px") or {})
    except Exception:
        _log.debug("unreadable bundled weight overrides in %s", path, exc_info=True)
        return {}


def save_to_library(definition: BlockDefinition, root: str | None = None,
                    *, overwrite: bool = False, bundled: dict | None = None) -> str:
    """Write *definition* to the tree; returns the path. No index is written
    (a stale ``index.json`` in the target folder is removed).

    Keyed on ``definition.id`` (the frozen identity), not the folder location:

    - **Collision:** if the target ``<name>.fpdb`` is already held by a *different*
      ``id`` and ``overwrite`` is False, raise :class:`BlockNameCollision` without
      touching disk (so the caller can prompt overwrite/cancel).
    - **Re-file:** the file that owns this ``id`` elsewhere in the tree (a prior
      Library/Series/name, or a loose file) is removed, so the block never
      duplicates.

    Args:
        overwrite: proceed past a cross-``id`` filename collision (clobber the
            other block's ``.fpdb``). Confirmed by the caller.
        bundled: ``{id: to_dict}`` of the definitions *definition* nests
            (``BlockRegistry.bundle_for``). Non-empty → the file is written as
            schema 2 with a ``bundled`` map (D11); empty/None → schema 1.

    Writes an optional ``weights`` map of the named line weights the definition
    and its bundle use (linetypes.md LT1-4); absent when none are used. Their
    Model px overrides ride in an optional ``weight_model_px`` (H-MW-a).
    """
    path = _target_path(root, definition.library, definition.series,
                        definition.name)
    series_dir, filename = os.path.dirname(path), os.path.basename(path)

    # (a) Cross-id collision check — BEFORE any mutation, so a refused save is inert.
    if not overwrite:
        clash_name = find_collision(definition.id, definition.library,
                                    definition.series, definition.name, root)
        if clash_name is not None:
            raise BlockNameCollision(clash_name, filename)

    # (b) Re-file: remove this block's previous file -- ONLY the file it came
    # from (user ruling 2026-10-10): ``definition.source_path`` (set on load /
    # reload / save, session-only) if that file still holds this id; with no
    # known source (e.g. after reopening the project), only an id owner the
    # app wrote where its stored identity says (``consistent``). A user's
    # copy or variant elsewhere is never deleted.
    old = _previous_file(definition, root)
    if old is not None and not _same_path(old, path):
        _delete_path(old)

    # (c) Write the .fpdb (the file IS the listing -- no index).
    rec = definition.to_dict()
    if bundled:
        rec["schema"] = 2
        rec["bundled"] = dict(bundled)
    from .paper_display import project_line_weights
    used = used_weight_names([rec, *(bundled or {}).values()])
    table = {d.name: d for d in project_line_weights()}
    weights = {n: table[n].width_mm for n in sorted(used) if n in table}
    if weights:                       # unknown names are never fabricated
        rec["weights"] = weights
        model = {n: table[n].model_px for n in weights
                 if table[n].model_px is not None}
        if model:                     # MW H-MW-a: overrides of used names only
            rec["weight_model_px"] = model
    _atomic_write_json(path, rec)
    capability_folder.forget(path)
    definition.source_path = path
    _drop_stale_index(series_dir)
    _notify_changed()
    return path


def _previous_file(definition: BlockDefinition, root: str | None) -> str | None:
    """The file a Save of *definition* may re-file (see :func:`save_to_library`)."""
    src = getattr(definition, "source_path", None)
    if src:
        meta = capability_folder.read_meta(src) if os.path.isfile(src) else None
        return src if meta is not None and meta["id"] == definition.id else None
    owner = _find_by_id(definition.id, root)
    if owner is not None and owner[3]["consistent"]:
        return owner[3]["path"]
    return None


def _walk_fpdb(base: str):
    """``(folder names, path)`` for every ``.fpdb`` at depth 0–2 under *base*,
    depth-first with names sorted -- the deterministic order that decides
    which copy of a duplicated id owns it."""
    def files(d):
        try:
            return sorted(e.path for e in os.scandir(d)
                          if e.is_file() and e.name.lower().endswith(".fpdb"))
        except OSError:
            return []

    def subdirs(d):
        try:
            return sorted(e.name for e in os.scandir(d) if e.is_dir())
        except OSError:
            return []

    for p in files(base):
        yield (), p
    for first in subdirs(base):
        d1 = os.path.join(base, first)
        for p in files(d1):
            yield (first,), p
        for second in subdirs(d1):
            for p in files(os.path.join(d1, second)):
                yield (first, second), p


def _tiers(meta: dict, dirs: tuple) -> tuple[str, str]:
    """``(library, series)`` of a file under *dirs* (folder wins; a folder
    that is the stored value's sanitized form reads as the stored value).
    Schematics are one-tier (schematics.md D-S15: root = ungrouped, one
    folder = Series; one filed two deep reads like a block); blocks are
    two-tier, a file short of a full Library/Series folder listing under
    :data:`UNGROUPED`."""
    lib, ser = meta["library"], meta["series"]
    if meta["kind"] == "schematic" and len(dirs) < 2:
        return ("", _human(dirs[0], ser)) if dirs else ("", "")
    if len(dirs) == 0:
        return UNGROUPED, UNGROUPED
    if len(dirs) == 1:
        return _human(dirs[0], lib), UNGROUPED
    return _human(dirs[0], lib), _human(dirs[1], ser)


def _iter_entries(root: str | None):
    """Yield ``(library, series, filename, meta)`` for every readable ``.fpdb``
    on disk -- the single walk behind ``list_library`` and the by-id lookups
    (identity is the ``id``, not the folder location).

    *meta* is ``capability_folder.read_meta`` plus ``name`` (the filename
    stem -- filename wins -- or the stored name when the stem is its
    sanitized form), ``path``, ``consistent`` (the file sits where its stored
    identity would be saved: the app wrote it there) and ``duplicate``.
    When several files hold one id (a file copied to make a variant), the
    owner is the first consistent one, else the first whose filename still
    matches its stored name, else the first in walk order; the others are
    ``duplicate``. Unreadable files and files without an id are skipped."""
    base = _root(root)
    if not os.path.isdir(base):
        return
    found = []
    for dirs, path in _walk_fpdb(base):
        meta = capability_folder.read_meta(path)
        if meta is None or not meta["id"]:
            continue
        library, series = _tiers(meta, dirs)
        name = _human(os.path.basename(path)[:-5], meta["name"])
        consistent = (library, series, name) == (
            meta["library"], meta["series"], meta["name"])
        found.append((library, series, name, consistent, path, meta))
    owner: dict = {}
    for *_x, consistent, path, meta in found:   # the app-written file first
        if consistent:
            owner.setdefault(meta["id"], path)
    for *_x, path, meta in found:               # then a name-matching one
        if capability_folder.owns_name(path, meta):
            owner.setdefault(meta["id"], path)
    for *_x, path, meta in found:               # else the first in walk order
        owner.setdefault(meta["id"], path)
    for library, series, name, consistent, path, meta in found:
        yield library, series, os.path.basename(path), {
            **meta, "library": library, "series": series, "name": name,
            "path": path, "consistent": consistent,
            "duplicate": owner[meta["id"]] != path}


def _find_by_id(block_id: str, root: str | None):
    """Locate the file that owns *block_id* anywhere in the tree (not just its
    def's current Library/Series folder). Returns ``(library, series, filename,
    meta)`` -- ``meta["path"]`` is the file -- or None. A duplicate-id copy
    never answers (the owner does). Fixes the 're-filed block reads
    project-only' class where a block's on-disk copy lives in a folder other
    than its current metadata would suggest."""
    for library, series, filename, meta in _iter_entries(root):
        if meta["id"] == block_id and not meta["duplicate"]:
            return library, series, filename, meta
    return None


def is_copy(path: str, block_id: str, root: str | None = None) -> bool:
    """True when *path* holds *block_id* but another file owns that id -- a
    copied file, which loads as its own block under a fresh id."""
    owner = _find_by_id(block_id, root)
    return owner is not None and not _same_path(owner[3]["path"], path)


def human_folders(root: str | None = None,
                  entries: list[dict] | None = None) -> dict[str, list[str]]:
    """:func:`list_folders` with each folder named as its blocks read it --
    a ``Pipe _ Fittings`` folder holding "Pipe & Fittings" blocks is listed
    as "Pipe & Fittings", so a browser shows one node, not a sanitized twin.

    Args:
        entries: An already-read :func:`list_library` result (None reads it).
    """
    base = _root(root)
    if entries is None:
        entries = list_library(root)
    lib_name: dict = {}
    ser_name: dict = {}
    for e in entries:
        if e.get("kind") == "schematic":
            continue
        parts = os.path.relpath(os.path.dirname(e["path"]), base).split(os.sep)
        if parts and parts[0] not in ("", "."):
            lib_name.setdefault(parts[0], e["library"])
        if len(parts) == 2:
            ser_name.setdefault(tuple(parts), e["series"])
    out: dict[str, list[str]] = {}
    for lib, series in list_folders(root).items():
        names = out.setdefault(lib_name.get(lib, lib), [])
        names.extend(ser_name.get((lib, s), s) for s in series)
    return {k: sorted(set(v)) for k, v in out.items()}


def list_library(root: str | None = None) -> list[dict]:
    """List every ``.fpdb`` on disk (each parsed once per mtime, cached).

    Each entry: {library, series, filename, path, id, name, version, kind,
    tile, repeat, end, duplicate} -- library / series from the folder, name
    from the filename.
    """
    return [{"library": library, "series": series, "filename": filename, **meta}
            for library, series, filename, meta in _iter_entries(root)]


def entry_path(entry: dict, root: str | None = None) -> str:
    """Absolute ``.fpdb`` path of a :func:`list_library` entry."""
    if entry.get("path"):
        return entry["path"]
    return os.path.join(_root(root),
                        *[s for s in (entry["library"], entry["series"]) if s],
                        entry["filename"])


def load_block(library: str, series: str, filename: str,
               root: str | None = None) -> BlockDefinition | None:
    """Load one .fpdb into a BlockDefinition; None if missing/corrupt."""
    path = os.path.join(_series_dir(root, library, series), filename)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return BlockDefinition.from_dict(json.load(fh))
    except Exception as exc:
        _log.warning("Unreadable block .fpdb %s: %s", path, exc)
        return None


def load_block_file(path: str) -> BlockDefinition | None:
    """Load a BlockDefinition from an arbitrary .fpdb path (a .fpdb IS a
    ``to_dict()`` JSON). None if missing/unreadable/corrupt (logged). Used by
    the browse-anywhere 'Load from Library' file dialog, which is not restricted
    to the library tree."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return BlockDefinition.from_dict(json.load(fh))
    except Exception as exc:
        _log.warning("Unreadable block .fpdb %s: %s", path, exc)
        return None


def load_failure_message(name: str, summary: dict, *, noun: str = "block") -> str:
    """The user message for a library block that failed to load.

    Shared by the Blocks-browser double-click, the canvas drop and the New
    Schematic picker so all read the same.

    Args:
        name: The block's display name.
        summary: ``Model_Space.load_blocks_from_files`` result ({} if no load
            was attempted).
        noun: ``"block"`` or ``"schematic"`` — the kind named in the
            name-clash reason (schematics.md D-S11d, ratified 2026-10-09).

    Returns:
        ``Could not load “name”: <why>.``
    """
    refused = summary.get("refused") or []
    if any(LOOP_REASON in r for r in refused):
        why = LOOP_REASON
    elif any(KIND_REASON in r for r in refused):
        why = KIND_REASON
    elif refused:
        why = f"a different {noun} already uses this name in the project"
    else:
        why = "the file could not be read"
    return f"Could not load “{name}”: {why}."


def load_block_file_with_bundle(path: str):
    """Load a ``.fpdb`` plus the nested definitions it bundles.

    Schema-1 files carry no bundle (empty list); schema-2 files carry a
    ``bundled`` ``{id: to_dict}`` map of every transitively nested
    definition (D11).

    Args:
        path: The ``.fpdb`` file path.

    Returns:
        ``(definition, [bundled definitions])``, or None if unreadable.
    """
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        defn = BlockDefinition.from_dict(data)
        bundled = [BlockDefinition.from_dict(v)
                   for v in (data.get("bundled") or {}).values()]
        return defn, bundled
    except Exception as exc:
        _log.warning("Unreadable block .fpdb %s: %s", path, exc)
        return None


def source_status(definition: BlockDefinition, root: str | None = None) -> str:
    """Return 'project-only' | 'library' | 'modified' for an embedded def.

    Resolves the library copy by ``id`` across the whole tree, so a block whose
    metadata (Library/Series/name) has drifted from its on-disk location still
    reads correctly instead of falsely 'project-only'.
    """
    found = _find_by_id(definition.id, root)
    if found is None:
        return "project-only"
    _lib, _series, _fname, meta = found
    return "library" if meta.get("version") == definition.version else "modified"


def reload_from_library(definition: BlockDefinition,
                        root: str | None = None) -> BlockDefinition | None:
    """Return the library copy of *definition* (by id), or None if absent.

    Locates the copy by ``id`` anywhere in the tree (not just the def's current
    Library/Series folder)."""
    found = _find_by_id(definition.id, root)
    if found is None:
        return None
    return load_block_file(found[3]["path"])


def delete_from_library(library: str, series: str, filename: str,
                        root: str | None = None) -> None:
    """Remove a .fpdb (no-op when absent) and its folder's stale
    ``index.json``, if any (the index is retired, 2026-10-10)."""
    _delete_path(os.path.join(_series_dir(root, library, series), filename))
    _notify_changed()
