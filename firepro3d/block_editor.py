"""Block Editor v2 — standalone authoring tab.

BlockEditorWidget hosts an isolated Model_Space scratchpad + Model_View,
disconnected from the plan scene. BlockEditorManager owns the editor tabs
(add / focus-existing / close), keyed so at most one editor edits a given
definition id. See docs/specs/block-system.md §"Block Editor (v2)".
"""

from __future__ import annotations

import os

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget,
                             QComboBox, QCheckBox, QLabel, QFormLayout, QLineEdit)

from .model_space import Model_Space
from .model_view import Model_View
from .geometry_2d import (
    LineItem, RectangleItem, CircleItem, ArcItem, PolylineItem, RegularPolygonItem,
    EllipseItem, SplineItem,
)
from .text_item import TextItem
from .block_definition import _PRIMITIVE_FACTORY
from . import geometry_import
from .house_dialog import HouseDialog

_CLS_TO_LIST = {
    LineItem: "_draw_lines", RectangleItem: "_draw_rects",
    CircleItem: "_draw_circles", ArcItem: "_draw_arcs",
    EllipseItem: "_draw_ellipses",
    SplineItem: "_draw_splines",
    PolylineItem: "_polylines", RegularPolygonItem: "_draw_polygons",
    TextItem: "_texts",
}


_SAVE_TO_LIB_KEY = "BlockEditor/save_to_library"   # last "Also save" choice


def library_tree_for(project_scene, root: str | None = None) -> dict[str, list[str]]:
    """The Save dialog's Library → Series choices: on-disk folders UNION the
    library/series already used by the project's block definitions."""
    from . import block_library
    tree = {lib: list(ser) for lib, ser in block_library.list_folders(root).items()}
    for d in project_scene._block_definitions.values():
        series = tree.setdefault(d.library, [])
        if d.series not in series:
            series.append(d.series)
    return {lib: sorted(ser) for lib, ser in sorted(tree.items())}


class BlockSaveDialog(HouseDialog):
    """Collect block identity + save options at Save time.

    Library / Series are house dropdowns fed by *library_tree* (Series follows
    the chosen Library); each has a "+" that creates the folder on disk at once
    (under *root*) and selects it. "Also save to library" defaults ON and
    remembers the last choice. When saving to the library would overwrite a
    DIFFERENT block's file, Save offers Overwrite / Rename / Cancel before
    anything is committed (Rename keeps the dialog open on the Name field).

    context: "new" | "seeded" | "edit". Shows a replace-source toggle for
    "seeded" and an "updates N instances" warning for "edit" when N>0.

    Args:
        parent: Qt parent widget.
        theme: Optional theme override.
        library_tree: ``{library: [series, ...]}`` choices.
        root: Block-library root for "+" folder creation + the collision probe
            (None = the configured library).
        collision_id: The id this save would write as (None = a new block).
        context: "new", "seeded", or "edit".
        instance_count: For "edit" context, number of placed instances.
        initial: (name, library, series) to pre-fill.
        validator: Optional callable(name, library, series) -> str|None.
    """

    def __init__(self, parent=None, *, theme=None, library_tree=None, root=None,
                 collision_id=None, context="new", instance_count=0,
                 initial=("", "", ""), validator=None):
        super().__init__(parent, title="Save Block", icon="insert_block_icon.svg",
                         min_width=420, theme=theme)
        from PyQt6.QtCore import QSettings
        from .ui_kit import CreatableSelector, ToggleSwitch
        self.setObjectName("BlockSaveDialog")
        self._validator = validator
        self._context = context
        self._lib_root = root
        self._collision_id = collision_id
        self._overwrite = False
        self._tree = {k: list(v) for k, v in (library_tree or {}).items()}
        # Keep a pre-filled library/series selectable even if not in the tree.
        if initial[1]:
            ser = self._tree.setdefault(initial[1], [])
            if initial[2] and initial[2] not in ser:
                ser.append(initial[2])

        form = QFormLayout()
        form.setVerticalSpacing(14)
        form.setHorizontalSpacing(14)
        self.name_edit = QLineEdit(initial[0])
        self.name_edit.setToolTip("Block name (also its file name in the library)")
        self.library_sel = CreatableSelector(add_tooltip="New library folder")
        self.library_sel.selector.setToolTip("Library (top-level folder)")
        self.series_sel = CreatableSelector(add_tooltip="New series folder in this library")
        self.series_sel.selector.setToolTip("Series (folder inside the library)")
        self.library_combo = self.library_sel.selector
        self.series_combo = self.series_sel.selector
        self.library_combo.currentTextChanged.connect(self._refresh_series)
        self.library_sel.createRequested.connect(self._create_library)
        self.series_sel.createRequested.connect(self._create_series)
        self._pending_series = initial[2]
        self.library_sel.set_items(sorted(self._tree), current=initial[1] or None)
        form.addRow("Name", self.name_edit)
        form.addRow("Library", self.library_sel)
        form.addRow("Series", self.series_sel)

        remembered = QSettings("GV", "FirePro3D").value(_SAVE_TO_LIB_KEY, True)
        if isinstance(remembered, str):
            remembered = remembered.lower() not in ("false", "0")
        self.save_to_library_cb = ToggleSwitch("Also save to library",
                                               checked=bool(remembered))
        self.save_to_library_cb.setToolTip(
            "Also write this block to the on-disk library folder above")
        form.addRow("", self.save_to_library_cb)
        self.replace_source_cb = ToggleSwitch(
            "Replace selected geometry with an instance", checked=True)
        self.replace_source_cb.setToolTip(
            "Swap the source geometry for one placed instance of the new block")
        if context == "seeded":
            form.addRow("", self.replace_source_cb)
        if context == "edit" and instance_count > 0:
            warn = QLabel(f"Saving updates {instance_count} placed instance(s).")
            warn.setWordWrap(True)
            form.addRow("", warn)
        self.error_label = QLabel("")
        self.error_label.setObjectName("fieldError")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        form.addRow("", self.error_label)
        self.body_layout().addLayout(form)
        self.set_footer_buttons(primary=("Save", self._on_save), cancel=True)

    # -- dropdowns ---------------------------------------------------------
    def _refresh_series(self, library: str) -> None:
        cur = self._pending_series or self.series_combo.currentText()
        self._pending_series = ""
        self.series_sel.set_items(self._tree.get(library, []), current=cur or None)

    def _create_library(self, name: str) -> None:
        from . import block_library
        from .themed_message import themed_info
        try:
            path = block_library.create_folder(name, root=self._lib_root)
        except OSError as exc:
            themed_info(self, "New library", f"Could not create the folder:\n{exc}")
            return
        lib = os.path.basename(path)
        self._tree.setdefault(lib, [])
        self.library_sel.set_items(sorted(self._tree), current=lib)

    def _create_series(self, name: str) -> None:
        from . import block_library
        from .themed_message import themed_info
        lib = self.library_combo.currentText().strip()
        if not lib:
            themed_info(self, "New series", "Choose or create a library first.")
            return
        try:
            path = block_library.create_folder(lib, name, root=self._lib_root)
        except OSError as exc:
            themed_info(self, "New series", f"Could not create the folder:\n{exc}")
            return
        ser = os.path.basename(path)
        series = self._tree.setdefault(lib, [])
        if ser not in series:
            series.append(ser)
            series.sort()
        self.series_sel.set_items(series, current=ser)

    # -- values / validation -----------------------------------------------
    def values(self) -> dict:
        """Return the current field values as a dict."""
        return {
            "name": self.name_edit.text().strip(),
            "library": self.library_combo.currentText().strip(),
            "series": self.series_combo.currentText().strip(),
            "save_to_library": self.save_to_library_cb.isChecked(),
            "replace_source": (self._context != "seeded") or self.replace_source_cb.isChecked(),
            "overwrite": self._overwrite,
        }

    def validation_error(self) -> str | None:
        """Return an error string if the form is invalid, else None."""
        v = self.values()
        if not (v["name"] and v["library"] and v["series"]):
            return "Name, Library and Series are all required."
        if self._validator is not None:
            return self._validator(v["name"], v["library"], v["series"])
        return None

    def _show_error(self, text: str) -> None:
        self.error_label.setText(text)
        self.error_label.show()

    def _on_save(self):
        from PyQt6.QtCore import QSettings
        QSettings("GV", "FirePro3D").setValue(
            _SAVE_TO_LIB_KEY, self.save_to_library_cb.isChecked())
        err = self.validation_error()
        if err:
            self._show_error(err)
            return
        self.error_label.hide()
        v = self.values()
        self._overwrite = False
        if v["save_to_library"]:
            from . import block_library
            from .themed_message import themed_choice
            clash = block_library.find_collision(
                self._collision_id or "", v["library"], v["series"], v["name"],
                root=self._lib_root)
            if clash is not None:
                choice = themed_choice(
                    self, "Name already in library",
                    f"A different block \u201c{clash}\u201d is already saved as "
                    f"{v['library']} / {v['series']} / {v['name']}.",
                    [("Cancel", "cancel", None), ("Rename", "rename", None),
                     ("Overwrite", "overwrite", "danger")], kind="warn")
                if choice == "overwrite":
                    self._overwrite = True
                elif choice == "rename":
                    self._show_error(
                        f"\u201c{v['name']}\u201d is taken in {v['library']} / "
                        f"{v['series']} — choose another name.")
                    self.name_edit.setFocus()
                    self.name_edit.selectAll()
                    return
                else:
                    self.reject()
                    return
        self.accept()


class BlockEditorWidget(QWidget):
    """A single editor tab: an isolated Model_Space + Model_View.

    Args:
        project_scene: the real project ``Model_Space`` (commit target; used by
            later sub-tasks for Save). The editor draws on its OWN scene.
        block_id: the definition id when editing in place; None for new/blank.

    Signals:
        saved(BlockEditorWidget, BlockDefinition): emitted after every
            successful commit (the manager retitles + re-keys the tab from it).
    """

    saved = pyqtSignal(object, object)

    def __init__(self, project_scene, *, block_id: str | None = None, parent=None):
        super().__init__(parent)
        self._project_scene = project_scene
        self._edit_block_id = block_id
        self._seed_source_items: list = []   # project-scene items for seeded create
        self._editor_key = None              # set by the manager
        self.editor_scene = Model_Space(scene_role="block_editor")    # isolated scratchpad; no managers injected
        # The blue placement preview-node is a pipe/sprinkler affordance the plan
        # scene suppresses while the crosshair owns the cursor (main._apply_crosshair).
        # The block editor authors only 2D geometry (which has its own ghost), so
        # suppress it here too — otherwise a stray blue dot rode every placement.
        self.editor_scene._suppress_preview_node = True
        self.view = Model_View(self.editor_scene)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        # Editor verbs (Save / Set Origin / Import / Edit Attributes) live in the
        # contextual "Block Editor" ribbon, built by MainWindow when this tab is
        # active — not on a widget strip (see main._build_block_editor_context).
        lay.addWidget(self.view)
        self._dirty = False
        self._origin = None          # QPointF | None ; None => auto bbox_top_left
        self._origin_marker = None   # QGraphicsItem crosshair
        self.editor_scene.sceneModified.connect(self._on_scene_modified)
        self.editor_scene.originPicked.connect(self._on_origin_picked)

    def _on_scene_modified(self):
        self._dirty = True

    def is_dirty(self) -> bool:
        return self._dirty

    def _mark_clean(self):
        self._dirty = False

    # ── Origin-pick mode (BE3b) ──────────────────────────────────────────────

    def begin_set_origin(self):
        """Enter the scene's 'set_origin' mode.

        Reuses the full placement pipeline (OSNAP + ALIGN + live snap marker via
        get_effective_position), so the next click pins a snapped/aligned origin.
        The scene emits ``originPicked`` on click (wired in __init__).
        """
        self.editor_scene.set_mode("set_origin")

    def _on_origin_picked(self, pt):
        """Slot for the editor scene's ``originPicked`` signal."""
        self.set_origin_point(pt)

    # ── Origin point + marker ────────────────────────────────────────────────

    def set_origin_point(self, pt):
        """Pin the block insertion origin (definition-local) + show the marker.

        Args:
            pt: a QPointF in editor-scene coordinates.
        """
        from PyQt6.QtCore import QPointF
        self._origin = QPointF(pt)
        self._ensure_origin_marker()
        self._origin_marker.setPos(self._origin)

    def origin_point(self):
        """Return the pinned origin QPointF, or the current bbox top-left if unset."""
        if self._origin is not None:
            return self._origin
        return geometry_import.bbox_top_left(self.gather_primitives())

    def _ensure_origin_marker(self):
        """Create the persistent, screen-constant origin crosshair once."""
        if self._origin_marker is not None:
            return
        from PyQt6.QtWidgets import QGraphicsPathItem
        from PyQt6.QtGui import QPainterPath, QPen, QColor
        path = QPainterPath()
        r = 8.0  # device px (ItemIgnoresTransformations => screen-constant)
        path.moveTo(-r, 0); path.lineTo(r, 0)
        path.moveTo(0, -r); path.lineTo(0, r)
        path.addEllipse(-r, -r, 2 * r, 2 * r)
        item = QGraphicsPathItem(path)
        pen = QPen(QColor("#ff3b30")); pen.setWidthF(1.5); pen.setCosmetic(True)
        item.setPen(pen)
        item.setFlag(item.GraphicsItemFlag.ItemIgnoresTransformations, True)
        item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, False)
        item.setZValue(10_000)
        item.setData(0, "block_origin_marker")
        self.editor_scene.addItem(item)
        self._origin_marker = item

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
        from PyQt6.QtCore import QPointF
        self.set_origin_point(QPointF(defn.origin[0], defn.origin[1]))
        self._mark_clean()

    def gather_primitives(self):
        """Return the editor scene's construction primitives (stable list order).

        Reads the scene's own tracking lists (populated by both seeding and the
        live drawing tools), so drawn and seeded geometry are both captured, and
        transient preview/ref items are naturally excluded.
        """
        s = self.editor_scene
        items = []
        for attr in ("_draw_lines", "_draw_rects", "_draw_circles",
                     "_draw_arcs", "_draw_ellipses", "_draw_splines", "_polylines", "_draw_polygons",
                     "_texts"):
            items.extend(getattr(s, attr))
        # Reference lines are scaffolding: included in the block ONLY when
        # explicitly printed; a non-printing reference line is dropped (task D).
        items.extend(r for r in getattr(s, "_reference_lines", [])
                     if getattr(r, "printed", False))
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
        self.editor_scene.commit_text_edit()   # inline text edit ends before saving
        items = self.gather_primitives()
        prims = [it.to_dict() for it in items]
        if not prims:
            return None
        origin = self.origin_point()
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
        self.saved.emit(self, defn)
        return defn

    def save(self, parent=None):
        """Open the Save dialog, then commit to the project (+ optional library).

        Args:
            parent: Optional Qt parent for the dialog (falls back to self).

        Returns:
            The committed ``BlockDefinition``, or None if cancelled / no geometry.
        """
        self.editor_scene.commit_text_edit()   # inline text edit ends before saving
        from PyQt6.QtWidgets import QDialog
        if not self.gather_primitives():
            from .themed_message import themed_info
            themed_info(parent or self, "Save Block", "Draw or import geometry first.")
            return None
        proj = self._project_scene
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

        dlg = BlockSaveDialog(parent or self, library_tree=library_tree_for(proj),
                              collision_id=self._edit_block_id,
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
            self._save_to_library(defn, parent or self,
                                  overwrite=v.get("overwrite", False))
        return defn

    # ── Import (BE4) ────────────────────────────────────────────────────────

    def _add_imported_geoms(self, geoms, import_scale):
        """Convert extracted geom dicts to editable primitives in the editor.

        Adds each primitive to the scene + its tracking list, selects the imported
        set, pushes one undo state, and reports a status. Returns (added, skipped).

        Args:
            geoms: List of kind-tagged geometry dicts from an import worker.
            import_scale: Multiplier applied to all coordinates (real mm per
                source unit).

        Returns:
            Tuple ``(added, skipped)`` — counts of accepted and dropped items.
        """
        items, skipped = geometry_import.geom_dicts_to_primitives(
            geoms, import_scale, lineweight=self.editor_scene._geom_color_lw()[1])
        if not items:
            self.editor_scene._show_status(
                f"Import: nothing usable (skipped {skipped})", timeout=4000)
            return 0, skipped
        for it in items:
            self._add_primitive(it)
        # One selectionChanged for the whole batch (per-item select was O(n^2)).
        self.editor_scene.select_items(items)
        self.editor_scene.push_undo_state()
        self.editor_scene._show_status(
            f"Imported {len(items)} primitive(s)" +
            (f", skipped {skipped}" if skipped else ""), timeout=5000)
        return len(items), skipped

    def begin_import(self):
        """Import geometry via the underlay import dialog (ribbon Import verb).

        Reuses ``UnderlayImportDialog`` for the full import UX — file load,
        high-fidelity preview, scale (incl. calibrate), insertion base, and layer
        selection — then bakes its resolved transform and drops the filtered
        geometry into the editor as **native 2D primitives** (not a batched
        underlay). The dialog owns its own async extraction, so no worker is
        needed here.

        Fidelity note: native Arc/Ellipse/Spline import and dialog rotation
        (``ImportParams.rotation``) are both applied via
        ``apply_import_transform``.
        """
        from PyQt6.QtWidgets import QDialog
        from .block_import_dialog import BlockImportDialog
        dlg = BlockImportDialog(self, scale_manager=self.editor_scene.scale_manager)
        try:
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            p = dlg.get_import_params()
        finally:
            dlg.deleteLater()
        self.import_with_params(p)

    def import_with_params(self, p):
        """Place an accepted import's geometry (the dialog-free half of Import).

        The picked **base point** is the grip that places the geometry:

        * ``insert_at_origin`` on — the base point lands on the block origin
          (the pinned origin, else the editor origin).
        * off — the geometry is added base-at-origin, selected, and handed to
          the Move tool with the base point preset, so it rides the cursor
          (OSNAP / ALIGN / HUD) until the placing click.

        Importing into an EMPTY editor with no pinned origin pins the origin
        at the base point (so the marker sits where the base point was picked,
        not at the geometry's bbox corner).

        Args:
            p: ``ImportParams`` from ``BlockImportDialog.get_import_params()``.
        """
        from PyQt6.QtCore import QPointF
        from . import dwg_converter
        was_empty = not self.gather_primitives()
        # Base-shift + scale + rotation: the base point maps to (0, 0). Scale is
        # baked here, so the primitive factory gets 1.0.
        geoms = dwg_converter.apply_import_transform(
            p.geom_list, p.scale, p.base_x, p.base_y, p.rotation)
        target = QPointF(0.0, 0.0)
        if p.insert_at_origin and self._origin is not None:
            target = QPointF(self._origin)
            geoms = dwg_converter.apply_import_transform(
                geoms, 1.0, -target.x(), -target.y())
        if was_empty and self._origin is None:
            self.set_origin_point(QPointF(0.0, 0.0))
        added, _skipped = self._add_imported_geoms(geoms, 1.0)
        if added and not p.insert_at_origin:
            self.editor_scene.begin_move_from(target)

    def _save_to_library(self, defn, parent, *, overwrite: bool = False):
        """Persist *defn* to the on-disk block library.

        The Save dialog already resolved any collision (``overwrite`` carries
        its Overwrite choice); the confirm below only guards a race where the
        slot got taken after the dialog closed.

        Args:
            defn: The ``BlockDefinition`` to persist.
            parent: Qt parent widget for confirmation dialogs.
            overwrite: Clobber a different block holding the same file.
        """
        from . import block_library
        from .themed_message import themed_confirm
        try:
            block_library.save_to_library(defn, overwrite=overwrite)
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
        # Hook set by the app shell (MainWindow) to adopt each freshly-created
        # editor scene into the interaction envelope (Escape/status/mode-sync/
        # property panel). Called with the BlockEditorWidget after its tab lands.
        self.on_open = None

    def _created(self, w: BlockEditorWidget) -> BlockEditorWidget:
        """Wire the save hook, then invoke the shell adoption hook (if any)."""
        w.saved.connect(self._on_saved)   # bound method (harness Invariant 6)
        if self.on_open is not None:
            self.on_open(w)
        return w

    def open_new(self, *, title: str = "New") -> BlockEditorWidget:
        """Open a fresh, independent editor tab (new/blank/clone)."""
        w = BlockEditorWidget(self._project_scene)
        key = ("new", self._new_counter)
        self._new_counter += 1
        w._editor_key = key
        self._open[key] = w
        idx = self._tabs.addTab(w, f"Block: {title}")
        self._tabs.setCurrentIndex(idx)
        return self._created(w)

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
        return self._created(w)

    def _on_saved(self, w: BlockEditorWidget, defn) -> None:
        """Retitle *w*'s tab to the saved name and key it by definition id.

        A new editor starts keyed ``("new", n)``; once saved it IS the editor
        for ``defn.id``, so ``open_for_definition`` must focus it rather than
        open a duplicate.
        """
        old = getattr(w, "_editor_key", None)
        if old != defn.id:
            self._open.pop(old, None)
            w._editor_key = defn.id
            self._open[defn.id] = w
        idx = self._tabs.indexOf(w)
        if idx != -1:
            self._tabs.setTabText(idx, f"Block: {defn.name}")

    def close(self, widget: BlockEditorWidget) -> None:
        """Remove and dispose an editor tab."""
        if hasattr(widget, "editor_scene"):
            widget.editor_scene.commit_text_edit()
        idx = self._tabs.indexOf(widget)
        if idx != -1:
            self._tabs.removeTab(idx)
        self._open.pop(getattr(widget, "_editor_key", None), None)
        widget.deleteLater()

    def forget(self, widget: BlockEditorWidget) -> None:
        """Drop a widget from tracking (called when its tab is closed elsewhere)."""
        self._open.pop(getattr(widget, "_editor_key", None), None)

    def open_editors(self) -> list:
        """Return the currently open editor widgets (stable-ish, dict order).

        Public accessor for callers outside the manager (e.g. main.py's
        ``_text_edit_scenes``) that must not reach into the private ``_open``
        dict directly.
        """
        return list(self._open.values())

