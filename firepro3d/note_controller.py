"""Notes: view-owned text notes (design 2026-11-04-text-leader-annotations).

Module helpers keep a note's owning view in step with view renames and deletes.
``NoteController`` (placement, the edit overlay) lives below them.
"""
from __future__ import annotations

from PyQt6 import sip
from PyQt6.QtCore import QPointF, Qt

from . import text_leader as _tl

# The Text panel rows a Note carries, in panel order. Content and Wrap stay out:
# the text is typed on the canvas and the box is authored by its corners.
_STYLE_ROWS = ("Format", "Font", "Height", "Padding", "Style", "Alignment", "V Align",
               "Font Color", "Frame", "Line Type", "Border Weight", "Corner",
               "Corner Radius", "Fill", "Fill Color", "Fill Opacity")
# Every key those rows commit under (the Style row commits per button).
STYLE_KEYS = frozenset(_STYLE_ROWS) | {"Bold", "Italic", "Underline"}
_STYLE_FIELDS = ("font_family", "height_mm", "cell_padding_mm", "bold", "italic", "underline",
                 "align", "valign", "color", "border", "border_line_type", "border_weight",
                 "border_corner", "border_corner_radius_mm", "fill_color", "fill_opacity")


def _style_item(prim: dict, style: "dict | None"):
    """A free ``TextItem`` of a Note's text primitive under *style*: it owns the
    rows and their parsing, so a Note cannot drift from the Text primitive."""
    from .text_item import TextItem
    rec = dict(prim, text="")
    rec.update(style or {})
    rec.pop("uid", None)
    rec.pop("leader", None)
    item = TextItem.from_dict(rec)
    item._printed_height = True        # a Note's box and text are in printed mm (D14)
    return item


def style_rows(prim: dict, style: "dict | None") -> dict:
    """The Format / Frame / Fill rows of a Note's text primitive under *style*."""
    props = _style_item(prim, style).get_properties()
    return {k: props[k] for k in _STYLE_ROWS if k in props}


def style_after(prim: dict, style: "dict | None", key: str, value) -> dict:
    """*style* after one row commit: only the fields that differ from *prim*, so
    every field a note leaves alone still follows the Note block (D8)."""
    item = _style_item(prim, style)
    item._set_property_model(key, value)
    base = _style_item(prim, None).data
    return {f: getattr(item.data, f) for f in _STYLE_FIELDS
            if getattr(item.data, f) != getattr(base, f)}


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
    doomed = notes_of(scene, view_key)
    ctl = getattr(scene, "constraint_ctl", None)
    if ctl is not None and doomed:
        ctl.on_items_removed(doomed)      # section 8: cascade-delete, inside the caller's step
    for inst in doomed:
        scene.remove_block_instance(inst)


def rekey_history(scene, old: str, new: str) -> None:
    """Re-key every note record of every undo / redo state from *old* to *new*.

    For a DETAIL rename only: a detail has no undo step, so a snapshot taken
    before the rename would restore notes under a name that no longer exists
    (permanently hidden). Rewrites history in place and pushes nothing. A level
    rename is undoable, so its snapshots keep the old key and must not be passed
    here.
    """
    for state in getattr(scene, "_undo_stack", ()):
        for rec in state.get("blocks", ()):
            note = rec.get("note")
            if note and note.get("view") == old:
                note["view"] = new


def drop_history(scene, view_key: str) -> None:
    """Remove every note record owned by *view_key* from every undo / redo state.

    For a DETAIL delete only (not undoable): an undo past it would otherwise
    bring back notes keyed to a view that no longer exists. Pushes nothing. A
    level delete is undoable and restores its notes, so it never calls this.
    """
    for state in getattr(scene, "_undo_stack", ()):
        blocks = state.get("blocks")
        if blocks:
            dead = {r.get("uid") for r in blocks
                    if (r.get("note") or {}).get("view") == view_key}
            state["blocks"] = [r for r in blocks if r.get("uid") not in dead]
            if dead and state.get("constraints"):      # no constraint may name a dropped note
                state["constraints"] = [
                    c for c in state["constraints"]
                    if not any(isinstance(r, dict) and r.get("uid") in dead
                               for r in c.get("refs", ()))]


class NoteTemplate:
    """Property-panel target while the Note tool is armed: the rows of the Text
    primitive, stamped on the next note. Duck-typed (``get_properties`` /
    ``set_property``) like the other pre-placement templates; it changes nothing
    in the model, so it never asks for an undo step.
    """

    def __init__(self, scene):
        self._scene = scene
        self.style: dict = {}
        self.leader: "dict | None" = None      # ``{end, weight}`` while Leader is on

    def _prim(self) -> "dict | None":
        from .system_blocks import NOTE_BLOCK_ID
        d = self._scene.ensure_system_block(NOTE_BLOCK_ID)
        bps = d.bound_prims() if d is not None else []
        return bps[0].prim if bps else None

    def get_properties(self) -> dict:
        prim = self._prim()
        if prim is None:
            return {}
        from .hatch_patterns import picker_exclude
        props = style_rows(prim, self.style)
        props.update(_tl.panel_rows(
            self.leader, getattr(self._scene, "block_registry", None),
            picker_exclude(self._scene),
            fallback_weight=str(self.style.get("border_weight")
                                or prim.get("border_weight", ""))))
        return props

    def set_property(self, key: str, value) -> None:
        prim = self._prim()
        if prim is None:
            return
        if key == "Leader":
            self.leader = {"end": _tl.DEFAULT_END_ID, "weight": ""} if value else None
        elif key in ("Leader End", "Leader Weight"):
            if self.leader is not None:
                from .hatch_patterns import picker_exclude
                _tl.set_panel_row(self.leader, key, value,
                                  getattr(self._scene, "block_registry", None),
                                  picker_exclude(self._scene))
        elif key in STYLE_KEYS:
            self.style = style_after(prim, self.style, key, value)


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
        self.template = NoteTemplate(scene)

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
        if self.template.style:
            note["style"] = dict(self.template.style)
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
        lead = self.template.leader
        if lead is not None:
            from .capabilities import ensure_end_available
            chg = inst._note_leader_change("Leader", True)
            if chg[0] and ensure_end_available(lead["end"], s, outside_history=True):
                inst.note["leader"] = dict(chg[0], **lead)
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
        prim = dict(inst._note_prim(), **(inst.note.get("style") or {}))
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
                   border_corner_radius_mm=float(prim.get("border_corner_radius_mm", 0.0)) * k,
                   angle=0.0)
        rec.pop("uid", None)
        rec.pop("leader", None)         # prim-frame record of the definition: the note's own below
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
