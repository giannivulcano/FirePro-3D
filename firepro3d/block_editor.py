"""Block Editor v2 — standalone authoring tab.

BlockEditorWidget hosts an isolated Model_Space scratchpad + Model_View,
disconnected from the plan scene. BlockEditorManager owns the editor tabs
(add / focus-existing / close), keyed so at most one editor edits a given
definition id. See docs/specs/block-system.md §"Block Editor (v2)".
"""

from __future__ import annotations

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget,
                             QComboBox, QCheckBox, QLabel, QFormLayout, QLineEdit,
                             QToolBar)

from .model_space import Model_Space
from .model_view import Model_View
from .construction_geometry import (
    LineItem, RectangleItem, CircleItem, ArcItem, PolylineItem, RegularPolygonItem,
)
from .block_definition import _PRIMITIVE_FACTORY
from . import geometry_import
from .house_dialog import HouseDialog

_CLS_TO_LIST = {
    LineItem: "_draw_lines", RectangleItem: "_draw_rects",
    CircleItem: "_draw_circles", ArcItem: "_draw_arcs",
    PolylineItem: "_polylines", RegularPolygonItem: "_draw_polygons",
}


class BlockSaveDialog(HouseDialog):
    """Collect block identity + save options at Save time.

    context: "new" | "seeded" | "edit". Shows a replace-source checkbox for
    "seeded" and an "updates N instances" warning for "edit" when N>0.

    Args:
        parent: Qt parent widget.
        theme: Optional theme override.
        libraries: Existing library names for the combo.
        series: Existing series names for the combo.
        context: "new", "seeded", or "edit".
        instance_count: For "edit" context, number of placed instances.
        initial: (name, library, series) to pre-fill.
        validator: Optional callable(name, library, series) -> str|None.
    """

    def __init__(self, parent=None, *, theme=None, libraries=(), series=(),
                 context="new", instance_count=0, initial=("", "", ""),
                 validator=None):
        super().__init__(parent, title="Save Block", icon="insert_block_icon.svg",
                         min_width=400, theme=theme)
        self.setObjectName("BlockSaveDialog")
        self._validator = validator
        self._context = context
        form = QFormLayout()
        form.setVerticalSpacing(14)
        form.setHorizontalSpacing(14)
        self.name_edit = QLineEdit(initial[0])
        self.library_combo = QComboBox()
        self.library_combo.setEditable(True)
        self.library_combo.addItems(list(libraries))
        self.library_combo.setCurrentText(initial[1])
        self.series_combo = QComboBox()
        self.series_combo.setEditable(True)
        self.series_combo.addItems(list(series))
        self.series_combo.setCurrentText(initial[2])
        form.addRow("Name", self.name_edit)
        form.addRow("Library", self.library_combo)
        form.addRow("Series", self.series_combo)
        self.save_to_library_cb = QCheckBox("Also save to library")
        form.addRow("", self.save_to_library_cb)
        self.replace_source_cb = QCheckBox("Replace selected geometry with an instance")
        if context == "seeded":
            self.replace_source_cb.setChecked(True)
            form.addRow("", self.replace_source_cb)
        if context == "edit" and instance_count > 0:
            warn = QLabel(f"Saving updates {instance_count} placed instance(s).")
            warn.setWordWrap(True)
            form.addRow("", warn)
        self.body_layout().addLayout(form)
        self.set_footer_buttons(primary=("Save", self._on_save), cancel=True)

    def values(self) -> dict:
        """Return the current field values as a dict."""
        return {
            "name": self.name_edit.text().strip(),
            "library": self.library_combo.currentText().strip(),
            "series": self.series_combo.currentText().strip(),
            "save_to_library": self.save_to_library_cb.isChecked(),
            "replace_source": (self._context != "seeded") or self.replace_source_cb.isChecked(),
        }

    def validation_error(self) -> str | None:
        """Return an error string if the form is invalid, else None."""
        v = self.values()
        if not (v["name"] and v["library"] and v["series"]):
            return "Name, Library and Series are all required."
        if self._validator is not None:
            return self._validator(v["name"], v["library"], v["series"])
        return None

    def _on_save(self):
        err = self.validation_error()
        if err:
            from .themed_message import themed_info
            themed_info(self, "Save Block", err)
            return
        self.accept()


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
        # editor verb strip (above the canvas)
        self.toolbar = QToolBar()
        self.act_save = self.toolbar.addAction("Save Block")
        self.act_save.triggered.connect(self._on_save_clicked)
        self.act_set_origin = self.toolbar.addAction("Set Origin")
        self.act_set_origin.setEnabled(False)   # enabled in BE3
        self.act_import = self.toolbar.addAction("Import…")
        self.act_import.setEnabled(False)        # enabled in BE4
        lay.addWidget(self.toolbar)
        lay.addWidget(self.view)
        self._dirty = False
        self.editor_scene.sceneModified.connect(self._on_scene_modified)

    def _on_scene_modified(self):
        self._dirty = True

    def _on_save_clicked(self):
        self.save(self)

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

    def save(self, parent=None):
        """Open the Save dialog, then commit to the project (+ optional library).

        Args:
            parent: Optional Qt parent for the dialog (falls back to self).

        Returns:
            The committed ``BlockDefinition``, or None if cancelled / no geometry.
        """
        from PyQt6.QtWidgets import QDialog
        if not self.gather_primitives():
            from .themed_message import themed_info
            themed_info(parent or self, "Save Block", "Draw or import geometry first.")
            return None
        proj = self._project_scene
        defs = list(proj._block_definitions.values())
        libraries = sorted({d.library for d in defs})
        series = sorted({d.series for d in defs})
        if self._edit_block_id is not None:
            context = "edit"
            icount = proj.instance_count(self._edit_block_id)
            cur = proj.get_block_definition(self._edit_block_id)
            initial = (cur.name, cur.library, cur.series) if cur else ("", "", "")
        elif self._seed_source_items:
            context = "seeded"
            icount = 0
            initial = ("", "", "")
        else:
            context = "new"
            icount = 0
            initial = ("", "", "")

        def _validator(name, library, series):
            for o in proj._block_definitions.values():
                if o.id == self._edit_block_id:
                    continue
                if (o.library, o.series, o.name) == (library, series, name):
                    return f"A block '{name}' already exists in {library} / {series}."
            return None

        dlg = BlockSaveDialog(parent or self, libraries=libraries, series=series,
                              context=context, instance_count=icount,
                              initial=initial, validator=_validator)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        v = dlg.values()
        defn = self.commit_block(v["name"], v["library"], v["series"],
                                 replace_source=v["replace_source"])
        if defn is None:
            return None
        if v["save_to_library"]:
            self._save_to_library(defn, parent or self)
        return defn

    def _save_to_library(self, defn, parent):
        """Persist *defn* to the on-disk block library, prompting on collision.

        Args:
            defn: The ``BlockDefinition`` to persist.
            parent: Qt parent widget for confirmation dialogs.
        """
        from . import block_library
        from .themed_message import themed_confirm
        try:
            block_library.save_to_library(defn)
        except block_library.BlockNameCollision as e:
            if themed_confirm(parent, "Overwrite block?",
                              f"A different block '{e.existing_name}' occupies that "
                              f"file. Overwrite it?"):
                block_library.save_to_library(defn, overwrite=True)


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
