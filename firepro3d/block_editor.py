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
from .construction_geometry import (
    LineItem, RectangleItem, CircleItem, ArcItem, PolylineItem, RegularPolygonItem,
)
from .block_definition import _PRIMITIVE_FACTORY
from . import geometry_import

_CLS_TO_LIST = {
    LineItem: "_draw_lines", RectangleItem: "_draw_rects",
    CircleItem: "_draw_circles", ArcItem: "_draw_arcs",
    PolylineItem: "_polylines", RegularPolygonItem: "_draw_polygons",
}


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
        self._dirty = False
        self.editor_scene.sceneModified.connect(self._on_scene_modified)

    def _on_scene_modified(self):
        self._dirty = True

    def is_dirty(self) -> bool:
        return self._dirty

    def _mark_clean(self):
        self._dirty = False

    def _add_primitive(self, item):
        """Add a construction primitive to the editor scene + its tracking list."""
        self.editor_scene.addItem(item)
        list_attr = _CLS_TO_LIST.get(type(item))
        if list_attr is not None:
            getattr(self.editor_scene, list_attr).append(item)

    def seed_from_dicts(self, prim_dicts, *, source_items=None):
        """Populate the editor scene with editable copies of primitive dicts.

        Args:
            prim_dicts: list of construction-geometry to_dict dicts.
            source_items: the project-scene items these copies came from (for a
                seeded create's replace-on-save); stored, not modified.
        """
        for d in prim_dicts:
            cls = _PRIMITIVE_FACTORY.get(d.get("type"))
            if cls is None:
                continue
            self._add_primitive(cls.from_dict(d))
        if source_items is not None:
            self._seed_source_items = list(source_items)
        self._mark_clean()   # seeding is not a user edit

    def seed_from_definition(self, defn):
        """Seed from an existing BlockDefinition's primitives (edit or clone).

        Args:
            defn: A ``BlockDefinition`` whose primitives are cloned into the
                editor scene.
        """
        self.seed_from_dicts(list(defn.primitives))

    def gather_primitives(self):
        """Return the editor scene's construction primitives (stable list order).

        Reads the scene's own tracking lists (populated by both seeding and the
        live drawing tools), so drawn and seeded geometry are both captured, and
        transient preview/ref items are naturally excluded.
        """
        s = self.editor_scene
        items = []
        for attr in ("_draw_lines", "_draw_rects", "_draw_circles",
                     "_draw_arcs", "_polylines", "_draw_polygons"):
            items.extend(getattr(s, attr))
        return items

    def commit_block(self, name, library, series, *, replace_source=True,
                     save_to_library=False):
        """Save the editor's geometry to the PROJECT scene (headless core).

        New (``_edit_block_id is None``): registers a new definition. When the
        editor was seeded from a selection and ``replace_source`` is True, the
        source items are consumed and one instance is placed at the origin.
        Edit-in-place: updates the existing definition (version bump + repaint),
        no placement. Returns the BlockDefinition, or None if there is no
        geometry. After a successful new commit, ``_edit_block_id`` is set so a
        subsequent Save edits in place.

        Args:
            name: Human-readable block name.
            library: Library taxonomy tier-1.
            series: Library taxonomy tier-2.
            replace_source: When True and source items were set via
                ``seed_from_dicts``, consume those items and place one instance.
            save_to_library: Reserved for the next sub-task (dialog wiring).

        Returns:
            The ``BlockDefinition``, or None if the editor has no geometry.
        """
        items = self.gather_primitives()
        prims = [it.to_dict() for it in items]
        if not prims:
            return None
        origin = geometry_import.bbox_top_left(items)
        is_new = self._edit_block_id is None
        do_replace = is_new and replace_source and bool(self._seed_source_items)
        defn = self._project_scene.commit_block_definition(
            block_id=self._edit_block_id, name=name, library=library, series=series,
            primitives=prims, origin=(origin.x(), origin.y()),
            place_instance=do_replace,
            source_items=self._seed_source_items if do_replace else None)
        if defn is None:
            return None
        self._edit_block_id = defn.id
        self._seed_source_items = []   # consumed / no longer a fresh seed
        self._mark_clean()
        # save_to_library handled in the next sub-task (dialog wiring)
        return defn


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
