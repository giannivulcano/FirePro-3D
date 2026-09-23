"""TextEditController — the model-surface inline text-edit session.

A plain object composed on ``Model_Space`` (decomposition pattern, like
``GeometryDrawingController``).  It owns the edit-session lifecycle — begin,
the single commit funnel, abandon — plus the undo and empty-text rules, and
(Task 5) the scene mouse gate.  The editing marker itself stays on the scene
(``scene._editing_item``, set by ``TextItem.begin_edit``) because the view and
the paper scene read it through ``text_item.editing_text_item``.

Governing spec: docs/specs/text-annotation-system.md § Inline edit (model surface).
"""
from __future__ import annotations

from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QGraphicsItem

from .text_item import TextItem, editing_text_item


class TextEditController:
    def __init__(self, scene):
        self._scene = scene

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def can_edit(self, item) -> bool:
        """Only top-level, visible, selectable, tracked TextItems are editable."""
        s = self._scene
        return (isinstance(item, TextItem)
                and item.scene() is s
                and item.parentItem() is None
                and item.isVisible()
                and bool(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
                and item in s._texts)

    def begin(self, item: TextItem, *, is_new: bool = False, scene_pos=None) -> None:
        """Start an edit session on *item* (commits any other live session).

        Args:
            item: The TextItem to edit.
            is_new: True when the session was started by placement (an empty
                commit then discards the item without an undo step).
            scene_pos: Scene point to place the caret at; ``None`` = end of text.
        """
        current = editing_text_item(self._scene)
        if current is not None and current is not item:
            self.commit()
        item._edit_before = item.to_dict()
        item._edit_is_new = is_new
        item.begin_edit()
        if scene_pos is not None:
            self.set_cursor_at(item, scene_pos, keep_anchor=False)
        else:
            c = item.textCursor()
            c.movePosition(QTextCursor.MoveOperation.End)
            item.setTextCursor(c)
        item._start_caret_blink()

    def commit(self) -> bool:
        """End the live session (idempotent).  Returns True if one was ended.

        Undo rule: one snapshot per session, pushed only when ``to_dict()``
        changed (or the session was a placement).  Empty rule: a new placement
        committed empty is discarded with no snapshot; an existing box emptied
        is deleted with one snapshot.
        """
        s = self._scene
        item = editing_text_item(s)
        if item is None:
            return False
        item._stop_caret_blink()
        before, is_new = item._edit_before, item._edit_is_new
        item._edit_before, item._edit_is_new = None, False
        item.commit_edit()                 # writes _data.text, clears the marker
        item.clearFocus()
        if item.is_effectively_empty():
            s._remove_item_from_lists(item)
            if not is_new:
                s.push_undo_state()
            s.requestPropertyUpdate.emit(None)
            return True
        if is_new or item.to_dict() != before:
            s.push_undo_state()
        s.requestPropertyUpdate.emit(item)
        return True

    def abandon(self, item: TextItem) -> None:
        """End *item*'s session WITHOUT committing (it is being deleted)."""
        from PyQt6.QtCore import Qt
        item._stop_caret_blink()
        item._editing = False
        item._edit_before, item._edit_is_new = None, False
        if getattr(self._scene, "_editing_item", None) is item:
            self._scene._editing_item = None
        item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        item.clearFocus()

    # ── Cursor placement (shared by begin + the Task-5 mouse gate) ─────────

    def set_cursor_at(self, item: TextItem, scene_pos, *, keep_anchor: bool) -> None:
        """Move *item*'s text cursor to the character nearest *scene_pos*."""
        local = item.mapFromScene(scene_pos)       # composed rotation override
        pos = item.cursor_position_at(local)
        c = item.textCursor()
        c.setPosition(pos, QTextCursor.MoveMode.KeepAnchor if keep_anchor
                      else QTextCursor.MoveMode.MoveAnchor)
        item.setTextCursor(c)
        item._reset_caret_phase()
