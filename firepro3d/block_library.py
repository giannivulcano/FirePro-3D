"""Two-tier user library for block definitions.

Layout: ``<root>/<Library>/<Series>/<name>.fpdb`` (a BlockDefinition.to_dict())
for blocks; ``<root>[/<Series>]/<name>.fpdb`` for schematic templates (empty
tiers skipped -- schematics.md D-S15); plus a per-folder ``index.json`` mapping
filename -> {id, name, version, thumbnail, tile, repeat, end[, kind]}.
Mirrors titleblock_template's atomic-write + tolerant-load + version
divergence, over a folder tree with human-readable filenames. Thumbnails are
reserved (S4). See docs/specs/block-system.md.
"""
from __future__ import annotations

import json
import logging
import os
import re

from .app_data import block_library_dir
from .block_definition import BlockDefinition

_log = logging.getLogger(__name__)
_INDEX = "index.json"
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


def sanitize(name: str) -> str:
    """Filesystem-safe segment: keep [A-Za-z0-9 _.-], collapse the rest to '_'."""
    s = re.sub(r"[^A-Za-z0-9 _.\-]", "_", (name or "").strip())
    return s or "_"


def _segments(library: str, series: str) -> tuple[str, str]:
    """Sanitized folder segments for a (library, series) pair.

    An EMPTY tier stays ``""`` instead of becoming ``"_"``: a schematic
    template has no Library tier (schematics.md D-S15) and an ungrouped one
    no Series either, so its file lives at ``<root>/<Series>/`` or at the
    root itself. Blocks always carry both tiers (validated on save).
    """
    return (sanitize(library) if library else "",
            sanitize(series) if series else "")


def _series_dir(root: str | None, library: str, series: str) -> str:
    return os.path.join(_root(root), *[s for s in _segments(library, series) if s])


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

    Returns:
        The occupying block's human name, or None when the slot is free (or
        already held by *block_id*).
    """
    filename = sanitize(name) + ".fpdb"
    clash = _read_index(_series_dir(root, library, series)).get(filename)
    if clash is not None and clash.get("id") != block_id:
        return clash.get("name", filename)
    return None


def _atomic_write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


def _read_index(series_dir: str) -> dict:
    path = os.path.join(series_dir, _INDEX)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        _log.warning("Unreadable block index %s: %s", path, exc)
        return {}


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
    """Write *definition* to the tree + update the Series index; returns the path.

    Keyed on ``definition.id`` (the frozen identity), not the folder location:

    - **Collision:** if the target ``<name>.fpdb`` is already held by a *different*
      ``id`` and ``overwrite`` is False, raise :class:`BlockNameCollision` without
      touching disk (so the caller can prompt overwrite/cancel).
    - **Re-file:** any stale copy of this same ``id`` living elsewhere in the tree
      (a prior Library/Series/name) is removed, so the block never duplicates.

    Args:
        overwrite: proceed past a cross-``id`` filename collision (clobber the
            other block's ``.fpdb`` + index entry). Confirmed by the caller.
        bundled: ``{id: to_dict}`` of the definitions *definition* nests
            (``BlockRegistry.bundle_for``). Non-empty → the file is written as
            schema 2 with a ``bundled`` map (D11); empty/None → schema 1.

    Writes an optional ``weights`` map of the named line weights the definition
    and its bundle use (linetypes.md LT1-4); absent when none are used. Their
    Model px overrides ride in an optional ``weight_model_px`` (H-MW-a).
    """
    series_dir = _series_dir(root, definition.library, definition.series)
    filename = sanitize(definition.name) + ".fpdb"
    path = os.path.join(series_dir, filename)

    # (a) Cross-id collision check — BEFORE any mutation, so a refused save is inert.
    if not overwrite:
        clash_name = find_collision(definition.id, definition.library,
                                    definition.series, definition.name, root)
        if clash_name is not None:
            raise BlockNameCollision(clash_name, filename)

    # (b) Re-file: drop any stale copy of this id parked at a different location.
    existing = _find_by_id(definition.id, root)
    if existing is not None:
        old_lib, old_series, old_fname, _meta = existing
        if (old_lib, old_series, old_fname) != (*_segments(definition.library,
                                                           definition.series), filename):
            delete_from_library(old_lib, old_series, old_fname, root)

    # (c) Write the .fpdb + refresh the Series index.
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
    index = _read_index(series_dir)
    # ``tile`` / ``repeat`` / ``end`` flag capability blocks (hatch D-A37,
    # linetypes LT3 H3-g, LT5 Q13) so the pattern / linetype / end picker
    # scans needn't parse every file; readers tolerate older entries without
    # them (capability_folder.scan parses the file instead).
    index[filename] = {"id": definition.id, "name": definition.name,
                       "version": definition.version, "thumbnail": None,
                       "tile": bool(definition.tile),
                       "repeat": bool(definition.repeat),
                       "end": bool(definition.end)}
    if definition.kind != "block":    # schematics.md I/O: `kind` only when not a block
        index[filename]["kind"] = definition.kind
    _atomic_write_json(os.path.join(series_dir, _INDEX), index)
    _notify_changed()
    return path


def _iter_index_entries(root: str | None):
    """Yield ``(library, series, filename, meta)`` for every indexed .fpdb in the
    tree (sorted, deterministic). The single tree-walk shared by ``list_library``
    and the by-id lookups — identity is the ``id``, not the folder location.

    Two layouts share one walk: the two-tier block tree
    ``<root>/<Library>/<Series>/index.json`` and the one-tier schematics tree
    ``<root>[/<Series>]/index.json`` (schematics.md D-S15). A folder holding an
    ``index.json`` is a leaf folder: at depth 0 it yields ``("", "")`` entries,
    at depth 1 ``("", <Series>)`` entries and is not descended; a depth-1
    folder without one is a Library and its children are Series."""
    base = _root(root)
    if not os.path.isdir(base):
        return
    for filename, meta in _read_index(base).items():        # ungrouped (root)
        yield "", "", filename, meta
    for first in sorted(os.listdir(base)):
        first_dir = os.path.join(base, first)
        if not os.path.isdir(first_dir):
            continue
        if os.path.isfile(os.path.join(first_dir, _INDEX)):   # one-tier Series
            for filename, meta in _read_index(first_dir).items():
                yield "", first, filename, meta
            continue
        for series in sorted(os.listdir(first_dir)):          # Library / Series
            series_dir = os.path.join(first_dir, series)
            if not os.path.isdir(series_dir):
                continue
            for filename, meta in _read_index(series_dir).items():
                yield first, series, filename, meta


def _find_by_id(block_id: str, root: str | None):
    """Locate a block by its ``id`` anywhere in the tree (not just its def's
    current Library/Series folder). Returns ``(library, series, filename, meta)``
    for the first match, or None. Fixes the 're-filed block reads project-only'
    class where a block's on-disk copy lives in a folder other than its current
    metadata would suggest."""
    for library, series, filename, meta in _iter_index_entries(root):
        if meta.get("id") == block_id:
            return library, series, filename, meta
    return None


def list_library(root: str | None = None) -> list[dict]:
    """List library entries from the per-Series indexes (no full .fpdb parse).

    Each entry: {library, series, filename, id, name, version, thumbnail}.
    """
    return [{"library": library, "series": series, "filename": filename, **meta}
            for library, series, filename, meta in _iter_index_entries(root)]


def entry_path(entry: dict, root: str | None = None) -> str:
    """Absolute ``.fpdb`` path of a :func:`list_library` entry (empty tiers skipped)."""
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
    library, series, filename, _meta = found
    return load_block(library, series, filename, root)


def delete_from_library(library: str, series: str, filename: str,
                        root: str | None = None) -> None:
    """Remove a .fpdb + its index entry (no-op when absent)."""
    series_dir = _series_dir(root, library, series)
    path = os.path.join(series_dir, filename)
    if os.path.isfile(path):
        os.remove(path)
    index = _read_index(series_dir)
    if filename in index:
        del index[filename]
        _atomic_write_json(os.path.join(series_dir, _INDEX), index)
    _notify_changed()
