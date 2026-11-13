"""Stable element uids (SB5 hosting foundation, design section 1).

Every model element (concept F7, SB5 Q1) carries ``self._uid``: a uuid4 hex
string minted in its constructor, written by ``to_dict`` / the network codec on
both serialization paths (``.fpd`` save and the undo snapshot), re-applied on
load and undo restore, and never adopted by a copy (paste strips it). The
plan scene keeps a uid index (``Model_Space.element_by_uid``); the helpers
here re-index an item that is already in such a scene so the index (and its
duplicate repair, Q6) sees the saved uid.
"""
from __future__ import annotations

import uuid

UID_KEY = "uid"
SPRINKLER_UID_KEY = "sprinkler_uid"   # a node record's sibling key (the sprinkler_phase pattern)


def new_uid() -> str:
    """A fresh element uid (uuid4 hex, 32 characters)."""
    return uuid.uuid4().hex


def uid_to_dict(item, d: dict, key: str = UID_KEY) -> dict:
    """Write *item*'s uid into record *d* under *key*.

    Args:
        item: An element carrying ``_uid``.
        d: The record being built (mutated).
        key: The record key (``"uid"``; a node writes its head's under
            ``SPRINKLER_UID_KEY``).

    Returns:
        *d*.
    """
    d[key] = item._uid
    return d


def uid_from_dict(item, data, key: str = UID_KEY) -> None:
    """Re-apply a saved uid to *item* (load / undo restore).

    A record without a usable uid (a legacy file, design Q5) leaves the uid the
    constructor minted. An item already in a scene that keeps a uid index is
    re-indexed through ``scene._uid_reindex`` so duplicate repair sees it.

    Args:
        item: The rebuilt element (a QGraphicsItem carrying ``_uid``).
        data: Its record (any non-dict is ignored).
        key: The record key holding the uid.
    """
    uid = data.get(key) if isinstance(data, dict) else None
    if not isinstance(uid, str) or not uid:
        return
    sc = item.scene()
    reindex = getattr(sc, "_uid_reindex", None) if sc is not None else None
    if reindex is not None:
        reindex(item, uid)
    else:
        item._uid = uid


def transfer_uid(scene, old, new) -> None:
    """Hand *old*'s uid to its in-place replacement *new* (pipe split, Q4).

    Call after *old* has left *scene*, so the index sees no collision.

    Args:
        scene: The scene holding *new*.
        old: The replaced element (already removed).
        new: The element that takes over its identity and dependents.
    """
    uid = old._uid
    reindex = getattr(scene, "_uid_reindex", None)
    if reindex is not None and new.scene() is scene:
        reindex(new, uid)
    else:
        new._uid = uid


def without_uid(rec: dict, *keys: str) -> dict:
    """A shallow copy of *rec* without its uid keys, so an element built from
    it mints its own uid (copies never adopt a record's uid, design section 3).

    Args:
        rec: A ``to_dict`` / codec / clipboard record.
        *keys: The keys to drop; default ``"uid"``.

    Returns:
        The copy.
    """
    drop = set(keys) or {UID_KEY}
    return {k: v for k, v in rec.items() if k not in drop}
