"""Block Editor v2 — standalone authoring tab.

BlockEditorWidget hosts an isolated Model_Space scratchpad + Model_View,
disconnected from the plan scene. BlockEditorManager owns the editor tabs
(add / focus-existing / close), keyed so at most one editor edits a given
definition id. See docs/specs/block-system.md §"Block Editor (v2)".
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget

from .model_space import Model_Space
from .model_view import Model_View


class BlockEditorWidget(QWidget):
    """A single editor tab: an isolated Model_Space + Model_View.

    Args:
        project_scene: the real project ``Model_Space`` (commit target; used by
            later sub-tasks for Save). The editor draws on its OWN scene.
        block_id: the definition id when editing in place; None for new/blank.
    """

    def __init__(self, project_scene, *, block_id: str | None = None, parent=None):
        super().__init__(parent)
        self._project_scene = project_scene
        self._edit_block_id = block_id
        self._seed_source_items: list = []   # project-scene items for seeded create
        self._editor_key = None              # set by the manager
        self.editor_scene = Model_Space()    # isolated scratchpad; no managers injected
        self.view = Model_View(self.editor_scene)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view)


class BlockEditorManager:
    """Owns Block Editor tabs on a QTabWidget (add / focus / close).

    Keyed so that ``open_for_definition`` focuses an already-open editor for the
    same definition id instead of opening a duplicate. New/blank editors get a
    unique key and are always independent.
    """

    def __init__(self, tab_widget: QTabWidget, project_scene):
        self._tabs = tab_widget
        self._project_scene = project_scene
        self._open: dict = {}          # key -> BlockEditorWidget
        self._new_counter = 0

    def open_new(self, *, title: str = "New") -> BlockEditorWidget:
        """Open a fresh, independent editor tab (new/blank/clone)."""
        w = BlockEditorWidget(self._project_scene)
        key = ("new", self._new_counter)
        self._new_counter += 1
        w._editor_key = key
        self._open[key] = w
        idx = self._tabs.addTab(w, f"Block: {title}")
        self._tabs.setCurrentIndex(idx)
        return w

    def open_for_definition(self, block_id: str) -> BlockEditorWidget:
        """Open an editor for *block_id*, focusing an existing one if open."""
        existing = self._open.get(block_id)
        if existing is not None:
            self._tabs.setCurrentWidget(existing)
            return existing
        defn = self._project_scene.get_block_definition(block_id)
        title = defn.name if defn is not None else block_id
        w = BlockEditorWidget(self._project_scene, block_id=block_id)
        w._editor_key = block_id
        self._open[block_id] = w
        idx = self._tabs.addTab(w, f"Block: {title}")
        self._tabs.setCurrentIndex(idx)
        return w

    def close(self, widget: BlockEditorWidget) -> None:
        """Remove and dispose an editor tab."""
        idx = self._tabs.indexOf(widget)
        if idx != -1:
            self._tabs.removeTab(idx)
        self._open.pop(getattr(widget, "_editor_key", None), None)
        widget.deleteLater()

    def forget(self, widget: BlockEditorWidget) -> None:
        """Drop a widget from tracking (called when its tab is closed elsewhere)."""
        self._open.pop(getattr(widget, "_editor_key", None), None)
