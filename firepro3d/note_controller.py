"""Notes: view-owned text notes (design 2026-11-04-text-leader-annotations).

Module helpers keep a note's owning view in step with view renames and deletes.
``NoteController`` (placement, the edit overlay) lives below them.
"""
from __future__ import annotations

from PyQt6 import sip
from PyQt6.QtCore import QPointF, Qt

from . import text_leader as _tl


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


class NoteController:
    """Note placement and the canvas edit overlay (design D8, D13).

    A Note's text is the ``Text`` attribute of a placed block, so it has no
    ``TextItem`` of its own to type into. Editing puts a transient ``TextItem``
    over the note and runs ``TextEditController`` on it unchanged; commit writes
    the attribute back. The overlay is deliberately NOT in ``scene._texts``: that
    list feeds the undo snapshot, the file save and every text path, none of which
    may ever see it.
    """

    def __init__(self, scene):
        self._scene = scene
        self._host = None        # the instance under edit
        self._overlay = None     # its transient TextItem

    @property
    def overlay(self):
        """The live edit overlay, or None."""
        return self._overlay

    @property
    def host(self):
        """The note instance under edit, or None."""
        return self._host

    # -- placement -----------------------------------------------------------

    def place(self, rect) -> None:
        """Place a note whose box is *rect* (scene mm, two-corner drag) and open
        its editor. The box is stored in printed mm, so it follows the drawing
        scale (D14)."""
        from .constants import MIN_NOTE_BOX_MM
        from .system_blocks import NOTE_BLOCK_ID
        s = self._scene
        if s.ensure_system_block(NOTE_BLOCK_ID) is None:
            s._show_status("The Note block is missing from the System library")
            return
        note = {"view": s.active_view_key, "wrap_width_mm": MIN_NOTE_BOX_MM,
                "box_height_mm": MIN_NOTE_BOX_MM}
        from .block_instance import BlockInstance
        inst = s.place_block_instance(                 # fresh placement, through the one
            NOTE_BLOCK_ID, (rect.x(), rect.y()),       # field-carrying choke point (DD7)
            **BlockInstance.place_kwargs({"note": note}))
        if inst is None:
            return
        k = inst.note_k()
        inst.note["wrap_width_mm"] = max(rect.width() / k, MIN_NOTE_BOX_MM)
        inst.note["box_height_mm"] = max(rect.height() / k, MIN_NOTE_BOX_MM)
        inst.note_changed()
        s._end_placement_switch(inst)
        self.begin(inst, is_new=True)

    # -- edit overlay ----------------------------------------------------------

    def begin(self, inst, *, is_new: bool = False, scene_pos=None) -> None:
        """Open the editor on *inst*: a transient ``TextItem`` carries the Text
        attribute over the note, in the note's own style (the definition's text
        primitive), box and leader, at the note's scene size."""
        from .text_item import TextItem
        s = self._scene
        g = inst._note_geometry()
        if g is None:
            return
        if self._overlay is not None:
            s._text_edit_ctl.commit()
        item, xf = g
        prim = next(b.prim for b in inst.definition().bound_prims())
        k = inst.note_k()
        px, py = float(prim.get("x", 0.0)), float(prim.get("y", 0.0))
        mirrored = inst.block_mirrored()
        # A mirrored pose flips the box about the insertion point, so its scene
        # top-left (the overlay's unmirrored anchor) is the far end of the box
        # along the prim's x: xf already carries the mirror.
        origin = xf.map(QPointF(px + (_tl._box_mm(item).width() if mirrored else 0.0), py))
        rec = dict(prim, text=str(inst.attributes.get("Text", "")),
                   x=origin.x(), y=origin.y(),
                   wrap_width_mm=inst.note["wrap_width_mm"] * k,
                   box_height_mm=inst.note["box_height_mm"] * k,
                   height_mm=float(prim.get("height_mm", 3.0)) * k,
                   cell_padding_mm=float(prim.get("cell_padding_mm", 1.0)) * k,
                   angle=0.0)
        rec.pop("uid", None)
        lead = inst.note.get("leader")
        if lead:
            rec["leader"] = dict(lead, shoulder_mm=lead["shoulder_mm"] * k)
            if mirrored:
                # The ops draw the leader through the variant mirror; the overlay
                # is unmirrored, so mirror the record: L <-> R, and the attach
                # runs the other way along a top / bottom edge.
                ld = rec["leader"]
                if ld["edge"] in ("L", "R"):
                    ld["edge"] = "R" if ld["edge"] == "L" else "L"
                else:
                    ld["t"] = 1.0 - float(ld["t"])
        ov = TextItem.from_dict(rec)
        s.addItem(ov)
        turn = float(prim.get("angle", 0.0)) + inst.block_rotation()
        if turn:
            ov.set_angle(turn, origin)     # a block turns about its insertion point, a
                                           # text about its centre unless given a pivot
        ov._note_host = inst
        self._host, self._overlay = inst, ov
        inst.setVisible(False)
        s._text_edit_ctl.begin(ov, is_new=is_new, scene_pos=scene_pos)

    def finish(self, item) -> str:
        """End the overlay *item*: write its text back to the host and remove it.
        Runs before any undo push, so no snapshot sees the overlay.

        Returns:
            ``"kept"``; ``"emptied"`` when the note was deleted for empty text;
            ``"gone"`` when the host no longer exists (nothing is written).
        """
        s = self._scene
        inst, text = self._host, item.data.text
        self._host = self._overlay = None
        if item.scene() is s:
            s.removeItem(item)
        if inst is None or sip.isdeleted(inst) or inst not in s._block_instances:
            return "gone"
        if inst.note.get("view") == s.active_view_key:
            inst.setVisible(True)
        if not text.strip():
            s.remove_block_instance(inst)
            return "emptied"
        inst.set_attributes(dict(inst.attributes, Text=text))
        inst.setSelected(True)
        return "kept"

    def discard_overlay(self, *, delete_new: bool = True) -> None:
        """Drop a live overlay without writing anything (host deleted, scene
        rebuilt by undo, project reset): nothing may crash and nothing is kept.
        A new note still being typed is deleted with it (placement pushed no
        step); *delete_new* False when the caller is itself removing the host."""
        item, inst = self._overlay, self._host
        self._host = self._overlay = None
        if item is None or sip.isdeleted(item):
            return
        s = self._scene
        was_new = bool(item._edit_is_new)
        item._stop_caret_blink()
        item._editing = False
        item._edit_before, item._edit_is_new = None, False
        if getattr(s, "_editing_item", None) is item:
            s._editing_item = None
        item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        item.clearFocus()
        if item.scene() is s:
            s.removeItem(item)
        if inst is None or sip.isdeleted(inst) or inst not in s._block_instances:
            return
        if was_new and delete_new:
            s.remove_block_instance(inst)
        elif inst.note.get("view") == s.active_view_key:
            inst.setVisible(True)

    def handle_double_click(self, scene_pos) -> bool:
        """Double-click on a note opens its editor (D13). True = consumed."""
        s = self._scene
        for it in s.items(scene_pos):
            if getattr(it, "note", None) and it.isVisible() and it in s._block_instances:
                m = s._live_manip()
                if m is not None and m.isVisible() and m.handles_at(scene_pos):
                    return False          # a manipulator handle owns the click
                s.clearSelection()
                it.setSelected(True)
                self.begin(it, scene_pos=scene_pos)
                return True
        return False
