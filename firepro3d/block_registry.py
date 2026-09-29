"""BlockRegistry — the single choke point for block definitions (nested blocks).

Owned by the project ``Model_Space``; Block Editor scenes borrow it read-only
for resolution (their own undo restore wipes their private dict, so the
project store is never aliased into them). Dependencies are derived by id from
definition contents — undo restore recreates definition objects, so object
back-references cannot carry them. See
docs/superpowers/specs/2026-09-29-nested-blocks-design.md (D3).
"""

from __future__ import annotations

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
        self._store[defn.id] = defn
        defn._resolve = self.get
        self.invalidate(defn.id)

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
        """Every id reachable from *block_id* through nested records.

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
            for child in nested_ids(d):
                if child not in seen:
                    seen.add(child)
                    stack.append(child)
        return seen

    def users_of(self, block_id: str) -> set[str]:
        """Definitions that nest *block_id* directly or transitively.

        Args:
            block_id: The nested definition id.

        Returns:
            Ids of every definition whose closure contains *block_id*.
        """
        return {i for i in self._store if i != block_id
                and block_id in self.closure(i)}

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
    def invalidate(self, block_id: str, *, already=()) -> None:
        """Drop compile caches of *block_id* + its users; repaint their instances.

        Args:
            block_id: The definition whose contents changed.
            already: Instances the caller has just repainted (e.g. the
                backrefs ``BlockDefinition.set_primitives`` notified) — skipped
                so each live instance repaints exactly once.
        """
        skip = {id(i) for i in already}
        affected = {block_id} | self.users_of(block_id)
        for i in affected:
            d = self._store.get(i)
            if d is not None:
                d.invalidate_cache()
        from PyQt6 import sip
        for sc in list(self._scenes):
            if sip.isdeleted(sc):
                self._scenes.remove(sc)
                continue
            for inst in list(getattr(sc, "_block_instances", [])):
                if inst.block_id in affected and id(inst) not in skip:
                    inst.on_definition_changed()
