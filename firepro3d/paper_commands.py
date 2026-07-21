"""QUndoCommand subclasses for paper-space undo/redo.

Each targets a PaperScene and keys on PERSISTENT data identity
(SheetViewData / TextAnnotationData), never live item pointers — items are
destroyed/recreated on every PaperScene._setup()/paper-size change. No import
from main.py (keeps each command unit-testable in isolation).
"""
from __future__ import annotations
from PyQt6.QtGui import QUndoCommand


def _find_text_item(scene, data):
    for it in scene.get_annotations():
        if it.data is data:
            return it
    return None


class AddTextAnnotationCommand(QUndoCommand):
    def __init__(self, scene, data):
        super().__init__("Add Text"); self._scene, self._data = scene, data
    def redo(self): self._scene._apply(lambda: self._scene._do_add_annotation(self._data))
    def undo(self): self._scene._apply(lambda: self._scene._do_remove_annotation_by_data(self._data))


class DeleteTextAnnotationCommand(QUndoCommand):
    def __init__(self, scene, data):
        super().__init__("Delete Text"); self._scene, self._data = scene, data
    def redo(self): self._scene._apply(lambda: self._scene._do_remove_annotation_by_data(self._data))
    def undo(self): self._scene._apply(lambda: self._scene._do_add_annotation(self._data))


class MoveTextAnnotationCommand(QUndoCommand):
    def __init__(self, scene, data, old_xy, new_xy):
        super().__init__("Move Text"); self._scene, self._data = scene, data
        self._old, self._new = old_xy, new_xy
    def _set(self, xy):
        def op():
            self._data.x, self._data.y = xy
            it = _find_text_item(self._scene, self._data)
            if it is not None: it.setPos(xy[0], xy[1])
        self._scene._apply(op)
    def redo(self): self._set(self._new)
    def undo(self): self._set(self._old)


class ResizeTextBoxCommand(QUndoCommand):
    """Undo/redo an 8-handle box resize gesture.

    Carries x, y, wrap_width_mm, and box_height_mm so that any combination of
    left/right/top/bottom handle drags (which may move the anchor and/or change
    size) is restored atomically.

    Args:
        scene: The PaperScene that owns the annotation.
        data: The TextAnnotationData being resized.
        old_state: ``(old_x, old_y, old_wrap_width_mm, old_box_height_mm)``
                   — state before the gesture.
        new_state: ``(new_x, new_y, new_wrap_width_mm, new_box_height_mm)``
                   — state after the gesture.
    """
    def __init__(self, scene, data, old_state, new_state):
        super().__init__("Resize Text Box"); self._scene, self._data = scene, data
        self._old, self._new = old_state, new_state
    def _set(self, state):
        x, y, w, bh = state
        def op():
            self._data.x = x
            self._data.y = y
            self._data.wrap_width_mm = w
            self._data.box_height_mm = bh
            it = _find_text_item(self._scene, self._data)
            if it is not None:
                it.setPos(x, y)
                it.prepareGeometryChange()
                it._apply_format()
        self._scene._apply(op)
    def redo(self): self._set(self._new)
    def undo(self): self._set(self._old)


class EditTextCommand(QUndoCommand):
    def __init__(self, scene, data, old_text, new_text):
        super().__init__("Edit Text"); self._scene, self._data = scene, data
        self._old, self._new = old_text, new_text
    def _set(self, text):
        def op():
            self._data.text = text
            it = _find_text_item(self._scene, self._data)
            if it is not None: it.setPlainText(text); it._apply_format()
        self._scene._apply(op)
    def redo(self): self._set(self._new)
    def undo(self): self._set(self._old)


class FormatTextCommand(QUndoCommand):
    """old_fields / new_fields: dicts of TextAnnotationData attributes."""
    def __init__(self, scene, data, old_fields, new_fields):
        super().__init__("Format Text"); self._scene, self._data = scene, data
        self._old, self._new = old_fields, new_fields
    def _set(self, fields):
        def op():
            for k, v in fields.items(): setattr(self._data, k, v)
            it = _find_text_item(self._scene, self._data)
            if it is not None:
                it.setPlainText(self._data.text); it.prepareGeometryChange(); it._apply_format()
        self._scene._apply(op)
    def redo(self): self._set(self._new)
    def undo(self): self._set(self._old)


def _find_viewport(scene, data):
    for vp in scene.get_viewports():
        if vp.data is data: return vp
    return None


class AddViewportCommand(QUndoCommand):
    def __init__(self, scene, data):
        super().__init__("Add Viewport"); self._scene, self._data = scene, data
    def redo(self): self._scene._apply(lambda: self._scene._do_add_viewport(self._data))
    def undo(self): self._scene._apply(lambda: self._scene._do_remove_viewport_by_data(self._data))


class RemoveViewportCommand(QUndoCommand):
    def __init__(self, scene, data):
        super().__init__("Delete Viewport"); self._scene, self._data = scene, data
    def redo(self): self._scene._apply(lambda: self._scene._do_remove_viewport_by_data(self._data))
    def undo(self): self._scene._apply(lambda: self._scene._do_add_viewport(self._data))


class ViewportGeometryCommand(QUndoCommand):
    def __init__(self, scene, data, old_geom, new_geom):
        super().__init__("Move/Resize Viewport"); self._scene, self._data = scene, data
        self._old, self._new = old_geom, new_geom        # (x, y, w, h)
    def _set(self, g):
        def op():
            self._data.x, self._data.y, self._data.w, self._data.h = g
            self._scene._resync_viewport(self._data)
        self._scene._apply(op)
    def redo(self): self._set(self._new)
    def undo(self): self._set(self._old)


class ChangeViewportPropertiesCommand(QUndoCommand):
    def __init__(self, scene, data, old_fields, new_fields):
        super().__init__("Edit Viewport"); self._scene, self._data = scene, data
        self._old, self._new = old_fields, new_fields
    def _set(self, fields):
        def op():
            for k, v in fields.items(): setattr(self._data, k, v)
            self._scene._resync_viewport(self._data)
        self._scene._apply(op)
    def redo(self): self._set(self._new)
    def undo(self): self._set(self._old)


class SetSheetFieldCommand(QUndoCommand):
    """Set one per-sheet title block field value.

    Pushes through the paper undo stack so field edits are undoable and the
    §17.7 dirty-flag relay (indexChanged → sheetModified) fires automatically.

    Args:
        scene: The PaperScene that owns the sheet.
        sheet: The Sheet whose title_block_fields entry is being changed.
        key: The field key (e.g. "Title", "Drawing No").
        new_value: The new string value to store.
    """

    def __init__(self, scene, sheet, key: str, new_value: str):
        super().__init__(f"Title Block {key}")
        self._scene, self._sheet, self._key = scene, sheet, key
        self._new = new_value
        self._old = sheet.title_block_fields.get(key, "")
        self._had_old = key in sheet.title_block_fields

    def redo(self):
        self._sheet.title_block_fields[self._key] = self._new
        self._scene._refresh_titleblock()

    def undo(self):
        if self._had_old:
            self._sheet.title_block_fields[self._key] = self._old
        else:
            self._sheet.title_block_fields.pop(self._key, None)
        self._scene._refresh_titleblock()


class EditRevisionsCommand(QUndoCommand):
    """Replace the sheet's revision list wholesale (one command per dialog OK).

    Stores a deep copy of both old and new revision lists so undo/redo never
    share mutable references with the live sheet data.

    Args:
        scene: The PaperScene that owns the sheet.
        sheet: The Sheet whose revisions list is being replaced.
        new_revisions: The replacement revision list (list of dicts with
            "no", "description", "date" keys).
    """

    def __init__(self, scene, sheet, new_revisions: list):
        super().__init__("Edit Revisions")
        self._scene, self._sheet = scene, sheet
        self._new = [dict(r) for r in new_revisions]
        self._old = [dict(r) for r in sheet.revisions]

    def redo(self):
        self._sheet.revisions = [dict(r) for r in self._new]
        self._scene._refresh_titleblock()

    def undo(self):
        self._sheet.revisions = [dict(r) for r in self._old]
        self._scene._refresh_titleblock()
