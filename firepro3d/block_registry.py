"""BlockRegistry — the single choke point for block definitions (nested blocks).

Owned by the project ``Model_Space``; Block Editor scenes borrow it read-only
for resolution (their own undo restore wipes their private dict, so the
project store is never aliased into them). Dependencies are derived by id from
definition contents — undo restore recreates definition objects, so object
back-references cannot carry them. See
docs/superpowers/specs/2026-09-29-nested-blocks-design.md (D3).
"""

from __future__ import annotations

from .hatch_patterns import canonical_ref
from .stroke_style import is_linetype_ref

NESTED_TYPE = "block_instance"


def nested_ids(defn) -> set[str]:
    """Block ids a definition nests directly.

    Args:
        defn: A ``BlockDefinition``.

    Returns:
        The set of ``block_id`` values of its ``block_instance`` records.
    """
    return {p.get("block_id") for p in defn.primitives
            if p.get("type") == NESTED_TYPE and p.get("block_id")}


def prim_refs(primitives) -> set[str]:
    """Block ids a primitive list depends on: nested records + pattern refs +
    linetype refs (LT3-2).

    Every pattern ref is a real dependency (hatch D-A39 — the shipped patterns
    are ordinary blocks): bundled with the host, cycle-checked, counted as a
    user. Legacy names are mapped to their frozen ids. A styled primitive's
    ``style.linetype`` block id is one too (linetypes.md H3-h); the
    ``continuous`` / ``by_block`` keywords are not.
    """
    out = set()
    for p in primitives:
        if p.get("type") == NESTED_TYPE and p.get("block_id"):
            out.add(p["block_id"])
        f = p.get("fill")
        if isinstance(f, dict) and f.get("type") == "hatch":
            ref = canonical_ref(f.get("pattern"))
            if ref:
                out.add(ref)
        st = p.get("style")
        if isinstance(st, dict) and is_linetype_ref(st.get("linetype")):
            out.add(st["linetype"])
    return out


def linetype_users_in(scene, block_id: str) -> list:
    """The scene's live styled primitives whose ``style.linetype`` is
    *block_id* (LT3-2 / LT3-10); empty for a scene without geometry tools."""
    tools = getattr(scene, "_tools", None)
    if tools is None:
        return []
    out = []
    for item in tools._all_geometry_items():
        st = getattr(item, "style", None)
        if isinstance(st, dict) and st.get("linetype") == block_id:
            out.append(item)
    return out


def referenced_ids(defn) -> set[str]:
    """Every block id *defn* depends on (nested + pattern + linetype; hatch HD4a, LT LD5, LT3-2)."""
    return prim_refs(defn.primitives)


class BlockRegistry:
    """Resolution, dependency, cycle and invalidation service over a store.

    Args:
        store: The ``{id: BlockDefinition}`` dict this registry fronts (the
            project scene's ``_block_definitions``). Writers that bypass the
            registry (undo restore, project load) are tolerated: ``get``
            injects the resolver lazily.
    """

    def __init__(self, store: dict):
        self._store = store
        self._scenes: list = []

    # ── store ────────────────────────────────────────────────────────────
    def get(self, block_id: str):
        """Resolve *block_id*; injects this registry as the definition's resolver.

        Args:
            block_id: Definition id.

        Returns:
            The ``BlockDefinition`` or ``None``.
        """
        d = self._store.get(block_id)
        if d is not None and d._resolve is None:
            d._resolve = self.get
        return d

    def add(self, defn) -> None:
        """Insert or replace *defn* and invalidate everything that nests it.

        Args:
            defn: The ``BlockDefinition`` to store.
        """
        old = self._store.get(defn.id)
        self._store[defn.id] = defn
        defn._resolve = self.get
        # A replaced linetype may become a non-linetype (missing for its raw
        # users): capture the OLD repeat before it is gone (LT3-10).
        self.invalidate(defn.id,
                        was_linetype=bool(getattr(old, "repeat", None)))

    def ids(self) -> list[str]:
        """Every definition id in the store."""
        return list(self._store)

    # ── scenes whose instances repaint on invalidate ─────────────────────
    def attach_scene(self, scene) -> None:
        """Register *scene* so its instances repaint on :meth:`invalidate`."""
        if scene not in self._scenes:
            self._scenes.append(scene)

    def detach_scene(self, scene) -> None:
        """Stop repainting *scene*'s instances on :meth:`invalidate`."""
        if scene in self._scenes:
            self._scenes.remove(scene)

    # ── dependency graph (by id) ─────────────────────────────────────────
    def closure(self, block_id: str, extra: dict | None = None) -> set[str]:
        """Every id reachable from *block_id* through nested records and pattern references.

        Args:
            block_id: Start definition id (not included unless on a cycle).
            extra: Optional ``{id: BlockDefinition}`` consulted before the
                store (a library file's bundle during a load check).

        Returns:
            The set of reachable definition ids.
        """
        seen: set[str] = set()
        stack = [block_id]
        while stack:
            cur = stack.pop()
            d = (extra or {}).get(cur) or self._store.get(cur)
            if d is None:
                continue
            for child in referenced_ids(d):
                if child not in seen:
                    seen.add(child)
                    stack.append(child)
        return seen

    def bundle_for(self, block_id: str) -> dict:
        """Serialized copies of every definition *block_id* nests (transitively).

        The ``bundled`` map a schema-2 ``.fpdb`` carries (D11).

        Args:
            block_id: The definition being saved to the library.

        Returns:
            ``{id: definition.to_dict()}``; empty when nothing is nested.
        """
        return {i: self._store[i].to_dict() for i in sorted(self.closure(block_id))
                if i in self._store and i != block_id}

    def merged_with_file(self, bundled, defn) -> dict:
        """The store as it would read after loading a library file (D11).

        The single merge rule shared by the load's cycle check and the
        drag-time preview: bundled copies only fill ids the project lacks
        (the project copy wins), while the file's own definition wins for
        its id (it is what gets embedded or swapped in).

        Args:
            bundled: The file's bundled ``BlockDefinition`` list.
            defn: The file's own ``BlockDefinition``.

        Returns:
            ``{id: BlockDefinition}`` to pass as ``extra`` to :meth:`closure`
            / :meth:`would_cycle`.
        """
        return {**{d.id: d for d in bundled}, **self._store, defn.id: defn}

    def users_of(self, block_id: str) -> set[str]:
        """Definitions that use *block_id* (nested record or pattern reference), directly or transitively.

        Args:
            block_id: The nested definition id.

        Returns:
            Ids of every definition whose closure contains *block_id*.
        """
        return set(self._inverse_closures().get(block_id, ())) - {block_id}

    def users_map(self) -> dict[str, set[str]]:
        """``{id: users_of(id)}`` for every stored definition, in one pass.

        Each definition's closure is computed once (memoised over the nesting
        DAG) and then inverted — the Block Manager's "Used in" column reads
        this instead of calling :meth:`users_of` per row.

        Returns:
            Stored id → ids of the definitions nesting it (direct or indirect).
        """
        inv = self._inverse_closures()
        return {i: set(inv.get(i, ())) - {i} for i in self._store}

    def _inverse_closures(self) -> dict[str, set[str]]:
        """``{nested id: {stored ids whose closure contains it}}`` (one pass)."""
        memo: dict[str, set[str]] = {}
        active: set[str] = set()
        cyclic = False

        def walk(i: str) -> set[str]:
            nonlocal cyclic
            if i in memo:
                return memo[i]
            d = self._store.get(i)
            if d is None:
                return set()
            if i in active:                  # a cycle: memo would be partial
                cyclic = True
                return set()
            active.add(i)
            out: set[str] = set()
            for child in referenced_ids(d):
                out.add(child)
                out |= walk(child)
            active.discard(i)
            memo[i] = out
            return out

        for i in self._store:                # recursion depth = nesting depth
            walk(i)
        if cyclic:                           # never expected; stay exact anyway
            memo = {i: self.closure(i) for i in self._store}
        inv: dict[str, set[str]] = {}
        for i, reach in memo.items():
            for j in reach:
                inv.setdefault(j, set()).add(i)
        return inv

    def would_cycle(self, host_id, candidate_id, extra: dict | None = None) -> bool:
        """True if nesting *candidate_id* inside *host_id* forms a cycle.

        An unsaved host (``host_id is None``) can never be nested, so it is
        never part of a cycle.

        Args:
            host_id: The definition being edited (``None`` if unsaved).
            candidate_id: The definition to nest inside it.
            extra: Optional bundle consulted before the store (see
                :meth:`closure`).
        """
        if host_id is None:
            return False
        return candidate_id == host_id or host_id in self.closure(candidate_id, extra)

    def missing_nested(self) -> dict[str, set[str]]:
        """``{missing_id: {user ids}}`` for nested records with no definition."""
        out: dict[str, set[str]] = {}
        for i, d in self._store.items():
            for child in nested_ids(d):
                if child not in self._store:
                    out.setdefault(child, set()).add(i)
        return out

    # ── invalidation ─────────────────────────────────────────────────────
    def invalidate(self, block_id: str, *, already=(),
                   was_linetype: bool = False) -> None:
        """Drop compile caches of *block_id* + its users; repaint their instances.

        Args:
            block_id: The definition whose contents changed.
            already: Instances the caller has just repainted (e.g. the
                backrefs ``BlockDefinition.set_primitives`` notified) — skipped
                so each live instance repaints exactly once.
            was_linetype: The definition *block_id* replaced was a linetype
                (``add``), so raw users may flip even if the new one is not.
        """
        skip = {id(i) for i in already}
        affected = {block_id} | self.users_of(block_id)
        for i in affected:
            d = self._store.get(i)
            if d is not None:
                d.invalidate_cache()
        from PyQt6 import sip
        # Only a linetype -- old or new -- (or a vanished id) can flip a raw
        # stroke's missing state; skip the scan for ordinary symbol edits.
        d0 = self._store.get(block_id)
        lt_scan = (was_linetype or d0 is None
                   or bool(getattr(d0, "repeat", None)))
        for sc in list(self._scenes):
            if sip.isdeleted(sc):
                self._scenes.remove(sc)
                continue
            for inst in list(getattr(sc, "_block_instances", [])):
                if inst.block_id in affected and id(inst) not in skip:
                    inst.on_definition_changed()
            # Raw primitives styled with *block_id* as their linetype: their
            # missing-glyph bounds pad may flip with this change (LT3-10).
            for item in (linetype_users_in(sc, block_id) if lt_scan else ()):
                item.prepareGeometryChange()
                item.update()
