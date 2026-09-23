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

import time

from PyQt6 import sip
from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication, QGraphicsItem, QGraphicsScene

from .manip_handle import GripHandle
from .text_item import TextItem, editing_text_item


class TextEditController:
    """Owns the model-surface inline text-edit session lifecycle.

    A plain object composed on ``Model_Space`` (decomposition pattern, like
    ``GeometryDrawingController``) — begin, the single commit funnel, abandon
    — plus the undo and empty-text rules, and (Task 5) the scene mouse gate.
    The editing marker itself stays on the scene (``scene._editing_item``, set
    by ``TextItem.begin_edit``) because the view and the paper scene read it
    through ``text_item.editing_text_item``.

    Governing spec: docs/specs/text-annotation-system.md § Inline edit (model
    surface).
    """

    def __init__(self, scene):
        """Initialize the controller.

        Args:
            scene: The ``Model_Space`` this controller is composed on.
        """
        self._scene = scene
        self._mouse_selecting = False     # press inside the box, drag extends
        self._swallow_release = False     # release that belongs to a gate click
        self._last_dbl_t = None           # monotonic time of the last word-select
        self._last_dbl_screen = None      # screen pos of that word-select (triple gate)

    def _reset_gesture_state(self) -> None:
        """Forget every in-flight mouse-gesture flag (press / release pairing
        and the triple-click window) — a session boundary or a fresh press."""
        self._mouse_selecting = False
        self._swallow_release = False
        self._last_dbl_t = None
        self._last_dbl_screen = None

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

        Re-entrant: if *item* is already the live session, this only
        repositions the caret — ``_edit_before``/``_edit_is_new`` are left
        untouched so the undo/empty rules still see the session's true start
        (e.g. a second click on the same freshly-placed, still-empty box must
        not turn off its ``is_new`` discard-without-a-step behaviour).

        Args:
            item: The TextItem to edit.
            is_new: True when the session was started by placement (an empty
                commit then discards the item without an undo step).  Ignored
                when *item* is already the live session.
            scene_pos: Scene point to place the caret at; ``None`` = end of text.
        """
        self._reset_gesture_state()
        current = editing_text_item(self._scene)
        if current is item:
            if scene_pos is not None:
                self.set_cursor_at(item, scene_pos, keep_anchor=False)
            else:
                item._reset_caret_phase()
            return
        if current is not None:
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

    def commit(self) -> "str | None":
        """End the live session (idempotent).

        Undo rule: one snapshot per session, pushed only when ``to_dict()``
        changed (or the session was a placement).  Empty rule: a new placement
        committed empty is discarded with no snapshot; an existing box emptied
        is deleted with one snapshot.

        Returns:
            str | None: ``None`` when there was no live session (nothing
            happened); ``"discarded"`` when a new, still-empty placement was
            removed WITHOUT pushing an undo snapshot (callers that commit-first
            before an undo/redo step must not also step the stack, since
            nothing was ever pushed for this item); ``"committed"`` for every
            other outcome (a snapshot was pushed, or an existing box's no-op
            edit ended with nothing to push).  Both non-``None`` values are
            truthy, matching the previous "was a session ended" bool.
        """
        self._reset_gesture_state()        # a lost release must not leak a flag
        s = self._scene
        item = editing_text_item(s)
        if item is None:
            return None
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
                return "committed"
            s.requestPropertyUpdate.emit(None)
            return "discarded"
        if is_new or item.to_dict() != before:
            s.push_undo_state()
        s.requestPropertyUpdate.emit(item)
        return "committed"

    def abandon(self, item: TextItem) -> None:
        """End *item*'s session WITHOUT committing (it is being deleted)."""
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

    # ── Mouse gate (runs ahead of manipulator / HALO / per-mode dispatch) ──
    #
    # Called from Model_Space's mouse handlers right after their input-mode
    # guard.  Each ``handle_*`` returns True when the text editor consumed the
    # event (the scene handler then returns without any further dispatch).

    def _inside(self, item: TextItem, scene_pos) -> bool:
        """True when *scene_pos* lies inside *item*'s (rotated) box."""
        return item._box_rect_local().contains(item.mapFromScene(scene_pos))

    def _in_content(self, item: TextItem, scene_pos) -> bool:
        """True when *scene_pos* lies on *item*'s painted text (line rects)."""
        local = item.mapFromScene(scene_pos)
        return any(r.contains(local) for r in item.content_rects_local())

    def _handle_wins(self, item: TextItem, scene_pos) -> bool:
        """Does a press at *scene_pos* on *item* (the live session, or the
        double-click entry candidate) belong to a manipulator handle rather
        than the text?

        Text wins over handles (user decision, spec Q7): *item*'s own centre
        move grip is never a handle here, and any other handle (resize /
        rotate) wins only when the press is NOT on the painted text content.
        """
        m = self._scene._live_manip()
        if m is None or not m.isVisible():
            return False
        hits = [h for h in m.handles_at(scene_pos)
                if not (isinstance(h, GripHandle) and h.item is item
                        and h.index == item.MOVE_GRIP_INDEX)]
        if not hits:
            return False
        return not self._in_content(item, scene_pos)

    def item_at(self, scene_pos):
        """Topmost editable TextItem whose rotated box contains *scene_pos*."""
        for it in self._scene.items(scene_pos):
            if (isinstance(it, TextItem) and self.can_edit(it)
                    and self._inside(it, scene_pos)):
                return it
        return None

    def _is_triple(self, screen_pos) -> bool:
        """True when a press follows a word-select within the double-click
        interval AND within the drag distance (screen px) of it — the third
        click of a triple-click, not a quick click elsewhere."""
        if self._last_dbl_t is None or self._last_dbl_screen is None:
            return False
        elapsed_ms = (time.monotonic() - self._last_dbl_t) * 1000.0
        if elapsed_ms > QApplication.doubleClickInterval():
            return False
        moved = (QPointF(screen_pos) - QPointF(self._last_dbl_screen)).manhattanLength()
        return moved <= QApplication.startDragDistance()

    def _select_unit(self, item: TextItem, scene_pos, unit) -> None:
        """Select the word / line under *scene_pos* in *item*."""
        self.set_cursor_at(item, scene_pos, keep_anchor=False)
        c = item.textCursor()
        c.select(unit)
        item.setTextCursor(c)
        item._reset_caret_phase()

    def _refocus(self, item: TextItem) -> None:
        """Hand keyboard focus back to *item* if it is still the live session."""
        if editing_text_item(self._scene) is item:
            item.setFocus(Qt.FocusReason.OtherFocusReason)

    def _deferred_refocus(self, item: TextItem) -> None:
        """Queued refocus target — guards a deleted / moved item first."""
        if sip.isdeleted(item) or item.scene() is not self._scene:
            return
        self._refocus(item)

    def handle_press(self, event) -> bool:
        """Left press while editing.

        Handle press → the manipulator gesture runs (keyboard handed back
        after Qt's click-focus lands); press inside the box → caret / Shift
        extend / triple-click line select; press outside → commit, then the
        normal press handling runs (select / HALO / tool).

        Every press first drops the press/release pairing flags, so a gesture
        whose release was lost (session ended mid-drag) cannot leak into this
        one.  The triple-click window survives (it is what this press tests).

        Args:
            event: The scene mouse-press event.

        Returns:
            bool: True when the text editor consumed the press.
        """
        self._mouse_selecting = False
        self._swallow_release = False
        item = editing_text_item(self._scene)
        if item is None:
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            # Right-click outside the box commits (mirrors the left-press
            # outside-commit rule below); inside, the session stays live so
            # the native context menu can open (handle_context_menu).  Middle
            # button (pan) never reaches here — Model_View intercepts it for
            # panning before the event is forwarded to the scene.
            if (event.button() == Qt.MouseButton.RightButton
                    and not self._inside(item, event.scenePos())):
                self.commit()
            return False
        pos = event.scenePos()
        if self._handle_wins(item, pos):
            # Manipulator resize/rotate runs; hand the keyboard back after Qt's
            # click-focus has landed (it lands before our handlers).
            QTimer.singleShot(0, lambda it=item: self._deferred_refocus(it))
            return False
        if self._inside(item, pos):
            triple = self._is_triple(event.screenPos())
            self._last_dbl_t = self._last_dbl_screen = None
            if triple:
                self._select_unit(item, pos, QTextCursor.SelectionType.LineUnderCursor)
                self._swallow_release = True
            else:
                shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                self.set_cursor_at(item, pos, keep_anchor=shift)
                self._mouse_selecting = True
            event.accept()
            return True
        self.commit()                       # outside press: commit, then normal handling
        return False

    def handle_move(self, event) -> bool:
        """Drag after an inside press extends the text selection.

        Only while the left button is held during a live session; the
        status-bar X/Y readout (``cursorMoved``) stays live while consumed.

        Args:
            event: The scene mouse-move event.

        Returns:
            bool: True when the move extended the text selection (consumed).
        """
        if not self._mouse_selecting:
            return False
        item = editing_text_item(self._scene)
        if item is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return False
        s = self._scene
        s.cursorMoved.emit(s._format_cursor_readout(event.scenePos()))
        self.set_cursor_at(item, event.scenePos(), keep_anchor=True)
        event.accept()
        return True

    def handle_release(self, event) -> bool:
        """Swallow the left release that belongs to a gate-consumed press.

        Args:
            event: The scene mouse-release event.

        Returns:
            bool: True when the release was the tail of a gate-consumed
            press / double-click (consumed); False otherwise.
        """
        if not (self._mouse_selecting or self._swallow_release):
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._mouse_selecting = False
        self._swallow_release = False
        event.accept()
        return True

    def handle_double_click(self, event) -> bool:
        """Double-click: word-select while editing; else enter edit on the
        editable TextItem under the cursor (select mode only).

        Text wins over handles (``_handle_wins``) on both paths.

        Args:
            event: The scene mouse-double-click event.

        Returns:
            bool: True when the text editor consumed the double-click.
        """
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        s = self._scene
        item = editing_text_item(s)
        if item is None and s.mode not in (None, "select"):
            return False                    # a placement tool owns the clicks
        pos = event.scenePos()
        if item is not None:
            if self._handle_wins(item, pos):
                return False
            if self._inside(item, pos):
                self._mouse_selecting = False
                self._select_unit(item, pos, QTextCursor.SelectionType.WordUnderCursor)
                self._last_dbl_t = time.monotonic()
                self._last_dbl_screen = QPointF(event.screenPos())
                self._swallow_release = True
                event.accept()
                return True
            return False
        target = self.item_at(pos)
        if target is None:
            return False
        # Entry: text wins too (spec Q7) — the candidate's centre grip never
        # blocks entry; other handles only outside its painted text.
        if self._handle_wins(target, pos):
            return False
        s.clearSelection()
        target.setSelected(True)
        self.begin(target, scene_pos=pos)
        self._swallow_release = True
        event.accept()
        return True

    def handle_context_menu(self, event) -> bool:
        """Right-click inside the editing box → the native text menu.

        Delivered through ``QGraphicsScene``'s base item dispatch (NOT a direct
        ``item.contextMenuEvent(event)`` call): PyQt6's
        ``QGraphicsSceneContextMenuEvent`` exposes no ``setPos``, and only the
        base dispatch stamps the item-local ``pos()`` the text control needs.
        The manipulator/handles above the item ignore context menus, and so do
        non-editing TextItems while a session is live, so the event
        propagates down to the editing TextItem.

        Args:
            event: The scene context-menu event.

        Returns:
            bool: True when the press was inside the editing box (handled).
        """
        item = editing_text_item(self._scene)
        if item is None or not self._inside(item, event.scenePos()):
            return False
        QGraphicsScene.contextMenuEvent(self._scene, event)
        event.accept()
        return True
