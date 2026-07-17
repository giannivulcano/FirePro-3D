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


class WrapResizeTextCommand(QUndoCommand):
    """Undo/redo a corner-grip wrap-resize gesture.

    Carries both x-position and wrap_width_mm so a left-corner drag (which
    moves the anchor while pinning the right edge) is restored atomically.
    A right-corner drag is the x-unchanged case: pass the same x for old and
    new.

    Args:
        scene: The PaperScene that owns the annotation.
        data: The TextAnnotationData being resized.
        old_state: ``(old_x, old_wrap_width_mm)`` — state before the gesture.
        new_state: ``(new_x, new_wrap_width_mm)`` — state after the gesture.
    """
    def __init__(self, scene, data, old_state, new_state):
        super().__init__("Resize Text"); self._scene, self._data = scene, data
        self._old, self._new = old_state, new_state
    def _set(self, state):
        x, w = state
        def op():
            self._data.x = x
            self._data.wrap_width_mm = w
            it = _find_text_item(self._scene, self._data)
            if it is not None:
                it.setPos(x, self._data.y)
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
