"""Notes: view-owned text notes (design 2026-11-04-text-leader-annotations).

Module helpers keep a note's owning view in step with view renames and deletes.
``NoteController`` (placement, the edit overlay) lives below them.
"""
from __future__ import annotations


def notes_of(scene, view_key: str) -> list:
    """The Note instances of *scene* owned by *view_key* (``plan:Plan: L1``)."""
    return [i for i in getattr(scene, "_block_instances", [])
            if (getattr(i, "note", None) or {}).get("view") == view_key]


def rekey_notes(scene, old: str, new: str) -> None:
    """Move every note owned by view *old* to view *new* (a view rename, D10)."""
    for inst in notes_of(scene, old):
        inst.note["view"] = new


def remove_notes(scene, view_key: str) -> None:
    """Delete every note owned by *view_key* (a view delete, D10).

    No undo push of its own: the caller's one step carries the removal.
    """
    for inst in notes_of(scene, view_key):
        scene.remove_block_instance(inst)
