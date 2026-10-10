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
from .geometry_2d import ReferenceLineItem
from .block_definition import is_scaffold
from . import geometry_import
from .house_dialog import HouseDialog

from . import schematic_scene
from .schematic_scene import _CLS_TO_LIST  # noqa: F401 (moved; re-exported)


def _is_scaffold_item(item) -> bool:
    """Live-item twin of ``block_definition.is_scaffold``: a non-printed
    reference line is scaffolding (D23) — saved, but never block geometry."""
    return isinstance(item, ReferenceLineItem) and not getattr(item, "printed", False)


_SAVE_TO_LIB_KEY = "BlockEditor/save_to_library"   # last "Also save" choice
_SAVE_TEMPLATE_KEY = "BlockEditor/save_schematic_template"   # last "Also save as Template" choice (SV3)

#: Editor tab title prefixes, by definition kind (schematics.md D-S14).
TAB_PREFIXES = ("Block: ", "Schematic: ")
_NO_SERIES = "(none)"   # Save Schematic's blank-Series choice (D-S15)


def tab_title(kind: str, name: str) -> str:
    """``"Block: <name>"`` or ``"Schematic: <name>"`` for an editor tab."""
    return f"{'Schematic' if kind == 'schematic' else 'Block'}: {name}"


def schematic_series_for(project_scene, root: str | None = None) -> list[str]:
    """Series choices for the Save Schematic dialog: the non-blank Series
    already used by the project's schematics UNION the Series folders on
    disk under the templates root (schematics.md D-S15; None = the
    configured ``app_data.schematics_dir()``)."""
    from . import block_library
    from .app_data import schematics_dir
    names = {d.series for d in project_scene._block_definitions.values()
             if d.kind == "schematic" and d.series}
    names.update(block_library.list_folders(
        root if root is not None else schematics_dir()))
    return sorted(names, key=str.lower)


def library_tree_for(project_scene, root: str | None = None) -> dict[str, list[str]]:
    """The Save dialog's Library → Series choices: on-disk folders UNION the
    library/series already used by the project's block definitions."""
    from . import block_library
    tree = {lib: list(ser) for lib, ser in block_library.list_folders(root).items()}
    for d in project_scene._block_definitions.values():
        if d.kind == "schematic":
            continue          # schematics have no Library tier (D-S4)
        series = tree.setdefault(d.library, [])
        if d.series not in series:
            series.append(d.series)
    return {lib: sorted(ser) for lib, ser in sorted(tree.items())}


def save_schematic_template(project_scene, defn, parent, *, root: str | None = None,
                            overwrite: bool = False) -> str | None:
    """Write *defn* (a saved project schematic) to the templates folder
    (schematics.md D-S6 / D-S11c / D-S11d). The one writer behind the editor
    verb and the Project Browser verb; the Save dialog's toggle resolves its
    collision in the dialog and writes through ``_save_to_library`` instead.

    Nested definitions are bundled (``BlockRegistry.bundle_for``). A different
    template already holding ``<name>.fpdb`` in the same Series offers
    Overwrite / Rename / Cancel: Rename asks for a new name, applies it to the
    project copy via ``set_block_metadata`` (one project undo step) and
    retries. A file write is never undoable (D-S17).

    Args:
        project_scene: The project ``Model_Space``.
        defn: The schematic ``BlockDefinition`` (its project copy).
        parent: Qt parent for the prompts.
        root: Templates root; None = ``app_data.schematics_dir()``.
        overwrite: Skip the collision prompt (clobber).

    Returns:
        The written ``.fpdb`` path, or None when cancelled / refused / failed.
    """
    from . import block_library
    from .app_data import schematics_dir
    from .themed_message import themed_choice, themed_info, themed_input_text
    root = root if root is not None else schematics_dir()
    bundled = project_scene.block_registry.bundle_for(defn.id)
    while True:
        try:
            return block_library.save_to_library(defn, root=root, overwrite=overwrite,
                                                 bundled=bundled)
        except block_library.BlockNameCollision as exc:
            where = f"{defn.series} / {defn.name}" if defn.series else defn.name
            choice = themed_choice(
                parent, "Save as Template",
                f"A different schematic “{exc.existing_name}” is already "
                f"saved as {where}.",
                [("Cancel", "cancel", None), ("Rename", "rename", None),
                 ("Overwrite", "overwrite", "danger")], kind="warn")
            if choice == "overwrite":
                overwrite = True
                continue
            if choice != "rename":
                return None
            new_name, ok = themed_input_text(parent, "Rename Schematic", "New name:",
                                             initial=defn.name)
            new_name = (new_name or "").strip()
            if not ok or not new_name or new_name == defn.name:
                return None
            if not project_scene.set_block_metadata(defn.id, new_name, "", defn.series):
                in_series = f" in {defn.series}" if defn.series else ""
                themed_info(parent, "Rename Schematic",
                            f"A schematic named “{new_name}” already exists{in_series}.")
                return None
            # ``set_block_metadata`` renamed the project copy in place: retry.
        except OSError as exc:
            themed_info(parent, "Save as Template", f"Could not save:\n{exc}")
            return None


class BlockSaveDialog(HouseDialog):
    """Collect block identity + save options at Save time.

    Library / Series are house dropdowns fed by *library_tree* (Series follows
    the chosen Library); each has a "+" that creates the folder on disk at once
    (under *root*) and selects it. "Also save to library" defaults ON and
    remembers the last choice. When saving to the library would overwrite a
    DIFFERENT block's file, Save offers Overwrite / Rename / Cancel before
    anything is committed (Rename keeps the dialog open on the Name field).
    A schematic dialog shows "Also save as Template" instead (default OFF,
    remembered under ``BlockEditor/save_schematic_template``; ``root`` is then
    the templates root the collision probe reads — schematics.md D-S14, SV3).

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
        kind: "block" or "schematic" -- a schematic shows Name + Series only
            (no Library, no library toggle; schematics.md D-S14).
        schematic_series: Series choices for a schematic.
    """

    def __init__(self, parent=None, *, theme=None, library_tree=None, root=None,
                 collision_id=None, context="new", instance_count=0,
                 initial=("", "", ""), validator=None, kind="block",
                 schematic_series=None):
        is_schematic = kind == "schematic"
        super().__init__(parent, title="Save Schematic" if is_schematic else "Save Block",
                         icon="insert_block_icon.svg", min_width=420, theme=theme)
        from PyQt6.QtCore import QSettings
        from .ui_kit import CreatableSelector, ToggleSwitch
        self.setObjectName("BlockSaveDialog")
        self._validator = validator
        self._context = context
        self._kind = kind
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
        self.library_sel = CreatableSelector(add_tooltip="New library folder")
        self.series_sel = CreatableSelector(add_tooltip="New series folder in this library")
        self.library_combo = self.library_sel.selector
        self.series_combo = self.series_sel.selector
        self._pending_series = ""
        if is_schematic:
            self.name_edit.setToolTip("Schematic name")
            self.series_sel.selector.setToolTip("Series (optional grouping)")
            items = [_NO_SERIES] + list(schematic_series or [])
            if initial[2] and initial[2] not in items:
                items.append(initial[2])
            self.series_sel.set_items(items, current=initial[2] or _NO_SERIES)
            self.series_sel.createRequested.connect(self._add_schematic_series)
            form.addRow("Name", self.name_edit)
            form.addRow("Series", self.series_sel)
            self.library_sel.hide()
        else:
            self.name_edit.setToolTip("Block name (also its file name in the library)")
            self.library_sel.selector.setToolTip("Library (top-level folder)")
            self.series_sel.selector.setToolTip("Series (folder inside the library)")
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
                                               checked=bool(remembered) and not is_schematic)
        self.save_to_library_cb.setToolTip(
            "Also write this block to the on-disk library folder above")
        self.save_template_cb = None
        if is_schematic:
            # Templates are an explicit push-back (schematics.md D-S6): the
            # toggle defaults OFF and remembers the last choice (SV3, 2026-10-09).
            remembered_t = QSettings("GV", "FirePro3D").value(_SAVE_TEMPLATE_KEY, False)
            if isinstance(remembered_t, str):
                remembered_t = remembered_t.lower() in ("true", "1")
            self.save_template_cb = ToggleSwitch("Also save as Template",
                                                 checked=bool(remembered_t))
            self.save_template_cb.setToolTip(
                "Also write this schematic to the Schematics templates folder "
                "(System Settings > General > Data folder > Schematics)")
            form.addRow("", self.save_template_cb)
        else:
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

    def _add_schematic_series(self, name: str) -> None:
        """Schematic "+": add a Series choice (project-only in SV1 -- the
        schematics folder arrives with SV3, D-S5)."""
        name = name.strip()
        if not name:
            return
        items = [self.series_combo.itemText(i)
                 for i in range(self.series_combo.count())]
        if name not in items:
            items.append(name)
        self.series_sel.set_items(items, current=name)

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
        if self._kind == "schematic":
            ser = self.series_combo.currentText().strip()
            return {"name": self.name_edit.text().strip(), "library": "",
                    "series": "" if ser == _NO_SERIES else ser,
                    "save_to_library": False,
                    "save_template": self.save_template_cb.isChecked(),
                    "replace_source": False, "overwrite": self._overwrite}
        return {
            "name": self.name_edit.text().strip(),
            "library": self.library_combo.currentText().strip(),
            "series": self.series_combo.currentText().strip(),
            "save_to_library": self.save_to_library_cb.isChecked(),
            "save_template": False,
            "replace_source": (self._context != "seeded") or self.replace_source_cb.isChecked(),
            "overwrite": self._overwrite,
        }

    def validation_error(self) -> str | None:
        """Return an error string if the form is invalid, else None."""
        v = self.values()
        if self._kind == "schematic":
            if not v["name"]:
                return "Name is required."
        elif not (v["name"] and v["library"] and v["series"]):
            return "Name, Library and Series are all required."
        if self._validator is not None:
            return self._validator(v["name"], v["library"], v["series"])
        return None

    def _show_error(self, text: str) -> None:
        self.error_label.setText(text)
        self.error_label.show()

    def _on_save(self):
        from PyQt6.QtCore import QSettings
        if self._kind == "schematic":
            QSettings("GV", "FirePro3D").setValue(
                _SAVE_TEMPLATE_KEY, self.save_template_cb.isChecked())
        else:
            QSettings("GV", "FirePro3D").setValue(
                _SAVE_TO_LIB_KEY, self.save_to_library_cb.isChecked())
        err = self.validation_error()
        if err:
            self._show_error(err)
            return
        self.error_label.hide()
        v = self.values()
        self._overwrite = False
        if v["save_to_library"] or v["save_template"]:
            from . import block_library
            from .themed_message import themed_choice
            # Templates probe the schematics root (``root=`` is that root for
            # a schematic dialog); blocks probe the block library root.
            clash = block_library.find_collision(
                self._collision_id or "", v["library"], v["series"], v["name"],
                root=self._lib_root)
            if clash is not None:
                if self._kind == "schematic":
                    noun, where = "schematic", (
                        f"{v['series']} / {v['name']}" if v["series"] else v["name"])
                    title = "Name already a template"
                else:
                    noun, where = "block", f"{v['library']} / {v['series']} / {v['name']}"
                    title = "Name already in library"
                choice = themed_choice(
                    self, title,
                    f"A different {noun} \u201c{clash}\u201d is already saved as {where}.",
                    [("Cancel", "cancel", None), ("Rename", "rename", None),
                     ("Overwrite", "overwrite", "danger")], kind="warn")
                if choice == "overwrite":
                    self._overwrite = True
                elif choice == "rename":
                    self._show_error(
                        f"“{v['name']}” is taken in {where} — choose another name.")
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
        kind: "schematic" makes this a Schematic editor (title, Save Schematic
            dialog, no capability slot).

    Signals:
        saved(BlockEditorWidget, BlockDefinition): emitted after every
            successful commit (the manager retitles + re-keys the tab from it).
    """

    saved = pyqtSignal(object, object)

    def __init__(self, project_scene, *, block_id: str | None = None,
                 kind: str = "block", parent=None):
        super().__init__(parent)
        self.kind = kind     # "block" | "schematic" (schematics.md D-S14)
        self._project_scene = project_scene
        self._seed_source_items: list = []   # project-scene items for seeded create
        self._editor_key = None              # set by the manager
        self.editor_scene = Model_Space(scene_role="block_editor")    # isolated scratchpad; no managers injected
        # ET1 (smoke ruling 2026-10-10): block AND schematic editors preview
        # ends / Drafting linetypes at the project drawing scale -- schematics
        # are built from model-size blocks (MainWindow._seed_editor_units).
        self._edit_block_id = block_id       # mirrored onto the scene (drop cycle host)
        self._dialog_template_path = None    # template the last Save dialog wrote (SV4)
        # The tile frame's preview / panel reach the editor's primitives and
        # its toggle through the scene (hatch D-A32).
        self.editor_scene._tile_editor = self
        # Resolve nested blocks through the PROJECT registry (D4): the editor's
        # own _block_definitions stays private to its undo snapshot.
        self.editor_scene.borrow_block_registry(project_scene.block_registry,
                                                owner=project_scene)
        # The blue placement preview-node is a pipe/sprinkler affordance the plan
        # scene suppresses while the crosshair owns the cursor (main._apply_crosshair).
        # The block editor authors only 2D geometry (which has its own ghost), so
        # suppress it here too — otherwise a stray blue dot rode every placement.
        self.editor_scene._suppress_preview_node = True
        self.view = Model_View(self.editor_scene)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        # Editor verbs (Save / Save As / Import / Edit Attributes) live on the
        # permanent "Block Editor" ribbon tab, enabled by MainWindow while this
        # tab is current — not on a widget strip (see
        # MainWindow._init_block_editor_tab).
        lay.addWidget(self.view)
        self._dirty = False
        # Create Block from a plan selection (D24): the plan-scene point the
        # selection's bbox centre came from. The replaced plan instance is
        # placed there; the definition origin itself is always (0,0) (D4).
        self._seed_base = None       # QPointF | None
        self.editor_scene.sceneModified.connect(self._on_scene_modified)

    @property
    def _edit_block_id(self):
        """The definition id this editor edits (None = unsaved / Save As)."""
        return self.editor_scene._editing_block_id

    @_edit_block_id.setter
    def _edit_block_id(self, block_id) -> None:
        # One home: the scene carries it so a drop onto the editor view can
        # cycle-check against the edited block (nested-blocks D7).
        self.editor_scene._editing_block_id = block_id

    def _on_scene_modified(self):
        self._dirty = True

    def is_dirty(self) -> bool:
        return self._dirty

    def _mark_clean(self):
        self._dirty = False

    # ── Origin (D4: fixed at the editor scene's (0,0)) ───────────────────────

    def origin_point(self):
        """The block insertion origin: always the editor scene's (0,0) (D4).

        The movable origin (Set Origin tool + red marker) and the bbox
        top-left default are retired; users design around the white (0,0)
        cross. See parametric-constraint-system.md D4 / §6.5.
        """
        from PyQt6.QtCore import QPointF
        return QPointF(0.0, 0.0)

    def _translate_all(self, dx: float, dy: float) -> None:
        """Shift every seeded primitive / nested instance in place.

        Used by the D4 origin migration and the D24 bbox-centre base. The SAME
        items are moved (uids stay stable) — never rebuilt.
        """
        for it in self.gather_primitives():
            if hasattr(it, "translate"):
                it.translate(dx, dy)
            else:
                it.manip_translate(dx, dy)     # TextItem (no translate())

    def _rebaseline_undo(self) -> None:
        """Make the current editor state the undo baseline (index 0)."""
        sc = self.editor_scene
        sc._undo_stack = []
        sc._undo_pos = -1
        sc.push_undo_state()
        self._mark_clean()

    def _add_primitive(self, item):
        """Add a construction primitive to the editor scene + its tracking list."""
        schematic_scene.add_primitive(self.editor_scene, item)

    def seed_from_dicts(self, prim_dicts, *, source_items=None):
        """Populate the editor scene with editable copies of primitive dicts.

        Args:
            prim_dicts: list of construction-geometry to_dict dicts.
            source_items: the project-scene items these copies came from (for a
                seeded create's replace-on-save); stored, not modified.
        """
        # One materializer (SV2): the render scenes share it.
        schematic_scene.materialize_primitives(self.editor_scene, prim_dicts)
        if source_items is not None:
            self._seed_source_items = list(source_items)
        # The seeded geometry is the undo baseline (index 0) and cannot be
        # undone away. Without this the stack still held only the scene's empty
        # construction snapshot, so Ctrl+Z after the first edit wiped the whole
        # block. Mirrors the default-grid seed in main.py / scene_io load.
        sc = self.editor_scene
        sc._undo_stack = []
        sc._undo_pos = -1
        sc.push_undo_state()
        self._mark_clean()   # seeding is not a user edit
        # Seeding happens only on a fresh open (edit / clone / Create Block
        # from a selection), so this frames a new tab and never re-zooms a
        # re-focused one (smoke 1).
        self.fit_view_to_block()

    def fit_view_to_block(self) -> None:
        """Frame the view on the block's own geometry (no-op when empty).

        Uses the pen-free bounds of ``gather_primitives()`` (nested blocks via
        ``geometric_rect()``), not ``itemsBoundingRect()``, which would also
        take in the origin cross and helper items.
        """
        rect = geometry_import.geometric_bounds(self.gather_primitives())
        if rect is not None:
            self.view.fit_scene_rect(rect)

    def seed_from_definition(self, defn):
        """Seed from an existing BlockDefinition's primitives (edit or clone).

        Args:
            defn: A ``BlockDefinition`` whose primitives are cloned into the
                editor scene.
        """
        self.seed_from_dicts(list(defn.primitives))
        # D4 / §6.5 migration: a definition with a non-zero origin is moved so
        # its origin lands on (0,0); the next save writes origin (0,0) and the
        # compiled instances render identically (compile applies -origin).
        ox, oy = float(defn.origin[0]), float(defn.origin[1])
        migrated = (ox, oy) != (0.0, 0.0)
        if migrated:
            self._translate_all(-ox, -oy)
        # Constraints load AFTER the migration (uids are stable across it, so
        # the refs still resolve) and BEFORE the re-baseline, so the undo
        # baseline holds them and Ctrl+Z can never undo them away
        # (parametric-constraint-system §6.5, §8).
        self.editor_scene.constraint_ctl.load(defn.constraints)
        # The capability joins the baseline too (hatch D-A32 / LT4-12).
        from .capabilities import kind_of
        k = kind_of(defn)
        cap = (k, getattr(defn, k)) if k else None
        self.editor_scene.set_block_capability(cap, push_undo=False)
        # The (migrated) seeded state is the baseline.
        self._rebaseline_undo()
        if migrated:
            self.fit_view_to_block()
        self._mark_clean()

    def seed_from_selection(self, prim_dicts, *, source_items):
        """Create Block from a plan selection: bbox centre -> (0,0) (D24).

        The copies are translated so the selection's bounding-box centre sits
        on the fixed origin; the plan-scene centre is remembered so a
        replace-on-save places the instance there and nothing moves visually.

        Args:
            prim_dicts: the selection's primitive ``to_dict`` dicts.
            source_items: the plan-scene items (consumed on a replace save).
        """
        from PyQt6.QtCore import QPointF
        self.seed_from_dicts(prim_dicts, source_items=source_items)
        # The base is the centre of the REAL geometry: non-printed reference
        # lines are scaffolding (D23), not block geometry, so they are left out
        # of the bbox (a plan selection carries none today; explicit anyway).
        real = [it for it in self.gather_primitives() if not _is_scaffold_item(it)]
        rect = geometry_import.geometric_bounds(real)
        c = rect.center() if rect is not None else QPointF(0.0, 0.0)
        self._seed_base = QPointF(c)
        if (c.x(), c.y()) != (0.0, 0.0):
            self._translate_all(-c.x(), -c.y())
        self._rebaseline_undo()
        self.fit_view_to_block()

    def toggle_capability(self, kind: str) -> bool:
        """Ribbon / panel "Pattern tile" / "Linetype" / "End type" toggle
        (D-A32, LT4, LT5 Q12).

        On: refused while the block is placed as a symbol or while another
        capability is on; a tile seeds from the content extents, a linetype
        converts strokes to Continuous and seeds its unit (LT4-4 / LT4-6), an
        end type (refused while nested blocks are present) converts strokes
        to Continuous with plain ends and seeds Size Fixed / Trim 0 (LT5 Q8).
        Off: a linetype or an end type is refused while lines use it (LT4-5,
        LT5 Q12). One undo step.

        Args:
            kind: ``"tile"``, ``"repeat"`` or ``"end"``.

        Returns:
            True if the capability changed.

        Raises:
            ValueError: *kind* is not a ``capabilities.CAPABILITY_KINDS`` kind.
        """
        if self.kind == "schematic":
            from .capabilities import SCHEMATIC_CAP_REASON
            self.editor_scene._show_status(SCHEMATIC_CAP_REASON, 5000)
            return False
        from .capabilities import CAPABILITY_KINDS, exclusive_message
        if kind not in CAPABILITY_KINDS:
            raise ValueError(f"unknown capability kind: {kind!r}")
        sc = self.editor_scene
        cur = sc.block_capability
        if cur is not None and cur[0] == kind:
            why = None
            if kind == "repeat":
                why = self._project_scene.linetype_off_refusal(self._edit_block_id)
            elif kind == "end":
                why = self._project_scene.end_off_refusal(self._edit_block_id)
            if why is not None:
                sc._show_status(why, 5000)
                return False
            sc.set_block_capability(None)
            return True
        if cur is not None:
            sc._show_status(exclusive_message(cur[0], kind), 5000)
            return False
        why = self._project_scene.symbol_use_refusal(self._edit_block_id, kind)
        if why is not None:
            sc._show_status(why, 5000)
            return False
        real = [it for it in self.gather_primitives() if not _is_scaffold_item(it)]
        if kind == "tile":
            from .tile_frame import seed_tile
            sc.set_block_capability(("tile", seed_tile(real)))
            return True
        if kind == "end":
            if getattr(sc, "_block_instances", None):
                # LT5 Q8: end content is strokes, fills and text -- no blocks.
                sc._show_status("End types can't contain blocks — explode or "
                                "remove them first", 5000)
                return False
            from .end_authoring import begin_end
            n = begin_end(sc)
            sc.push_undo_state()
            if n:
                sc._show_status(f"{n} line{'s' if n != 1 else ''} set to "
                                f"Continuous with plain ends", 5000)
            return True
        from .linetype_authoring import begin_linetype
        from .linetype_pattern import content_end
        end = content_end([it.to_dict() for it in real if hasattr(it, "to_dict")])
        n = begin_linetype(sc, end)
        sc.push_undo_state()
        if n:
            sc._show_status(f"{n} line{'s' if n != 1 else ''} set to Continuous", 5000)
        return True

    def toggle_pattern_tile(self) -> bool:
        """HF2 name of ``toggle_capability("tile")``."""
        return self.toggle_capability("tile")

    def gather_primitives(self):
        """Return the editor scene's construction primitives (stable list order).

        Reads the scene's own tracking lists (populated by both seeding and the
        live drawing tools), so drawn and seeded geometry are both captured, and
        transient preview/ref items are naturally excluded.
        """
        return schematic_scene.materialized_items(self.editor_scene)

    def commit_block(self, name, library, series, *, replace_source=True,
                     save_to_library=False):
        """Save the editor's geometry to the PROJECT scene (headless core).

        New (``_edit_block_id is None``): registers a new definition. When the
        editor was seeded from a selection and ``replace_source`` is True, the
        source items are consumed and one instance is placed at the seed's
        plan-scene base point (D24; the definition origin is always (0,0), D4).
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
            save_to_library: Unused (library writes happen in the callers:
                ``save`` / ``_save_via_dialog`` → ``_save_to_library``).

        Returns:
            The ``BlockDefinition``, or None if the editor has no geometry.
        """
        self.editor_scene.commit_text_edit()   # inline text edit ends before saving
        items = self.gather_primitives()
        prims = [it.to_nested_dict() if hasattr(it, "to_nested_dict") else it.to_dict()
                 for it in items]
        if all(is_scaffold(p) for p in prims):
            return None   # empty, or scaffolding only (D23: not geometry)
        origin = self.origin_point()
        is_new = self._edit_block_id is None
        do_replace = is_new and replace_source and bool(self._seed_source_items)
        base = self._seed_base
        defn = self._project_scene.commit_block_definition(
            block_id=self._edit_block_id, name=name, library=library, series=series,
            primitives=prims, origin=(origin.x(), origin.y()),
            place_instance=do_replace,
            source_items=self._seed_source_items if do_replace else None,
            place_at=(base.x(), base.y()) if base is not None else None,
            constraints=self.editor_scene.constraint_ctl.to_records(),
            capability=self.editor_scene.block_capability,
            kind=self.kind)
        if defn is None:
            return None
        self._edit_block_id = defn.id
        self._seed_source_items = []   # consumed / no longer a fresh seed
        self._seed_base = None
        self._mark_clean()
        # save_to_library handled in the next sub-task (dialog wiring)
        self.saved.emit(self, defn)
        return defn

    def _saved_definition(self):
        """The project definition this editor edits, or None (never saved)."""
        if self._edit_block_id is None:
            return None
        return self._project_scene.get_block_definition(self._edit_block_id)

    def save(self, parent=None):
        """Save Block (ribbon / Ctrl+S).

        A block never saved before opens the Save dialog (it acts as Save As).
        Afterwards Save is silent: the definition is updated in place (version
        bump, placed instances refresh) and, when the block already has a
        library copy, that copy is rewritten too.

        Args:
            parent: Optional Qt parent for dialogs (falls back to self).

        Returns:
            The committed ``BlockDefinition``, or None if cancelled / no geometry.
        """
        self.editor_scene.commit_text_edit()   # inline text edit ends before saving
        cur = self._saved_definition()
        if cur is None:
            return self._save_via_dialog(parent, save_as=False)
        if not self._has_geometry(parent):
            return None
        from . import block_library
        defn = self.commit_block(cur.name, cur.library, cur.series)
        if defn is None:
            return None
        if self.kind != "schematic" and block_library.source_status(defn) != "project-only":
            self._save_to_library(defn, parent or self)
        n = self._project_scene.instance_count(defn.id)
        m = len(self._project_scene.block_registry.users_of(defn.id))
        parts = []
        if n:
            parts.append(f"{n} placed instance(s)")
        if m:
            parts.append(f"{m} block(s) that use it")
        noun = "schematic" if self.kind == "schematic" else "block"
        self.editor_scene._show_status(
            f"Saved {noun} \u201c{defn.name}\u201d"
            + (f" \u2014 updated {' and '.join(parts)}" if parts else ""),
            timeout=5000)
        return defn

    def save_as(self, parent=None):
        """Save Block As (ribbon / Ctrl+Shift+S): a NEW block from this geometry.

        Opens the Save dialog prefilled with ``"<name> copy"``; the original
        definition and its placed instances are untouched, and this editor
        then edits the new block (the manager retitles + re-keys its tab).
        A never-saved editor behaves exactly like :meth:`save`.

        Args:
            parent: Optional Qt parent for dialogs (falls back to self).

        Returns:
            The new ``BlockDefinition``, or None if cancelled / no geometry.
        """
        self.editor_scene.commit_text_edit()
        if self._saved_definition() is None:
            return self._save_via_dialog(parent, save_as=False)
        return self._save_via_dialog(parent, save_as=True)

    def save_as_template(self, parent=None):
        """Save as Template (ribbon, Schematic tabs only — schematics.md D-S6).

        Saves the project copy first (:meth:`save`: a never-saved schematic
        gets the Save dialog, one project undo step) so the template matches
        what the editor shows, then writes it to the templates folder via
        :func:`save_schematic_template`.

        Args:
            parent: Optional Qt parent for dialogs (falls back to self).

        Returns:
            The written ``.fpdb`` path, or None if cancelled / refused.
        """
        if self.kind != "schematic":
            return None
        self._dialog_template_path = None
        defn = self.save(parent)
        if defn is None:
            return None
        # A first save whose dialog toggle already wrote the template is done:
        # one file write, not two (SV3 seam minor (a), SV4).
        path = self._dialog_template_path or save_schematic_template(
            self._project_scene, defn, parent or self)
        self._dialog_template_path = None
        if path:
            self.editor_scene._show_status(
                f"Saved template “{defn.name}”", timeout=5000)
        return path

    def _has_geometry(self, parent) -> bool:
        if any(not _is_scaffold_item(it) for it in self.gather_primitives()):
            return True   # scaffolding alone is not geometry (D23)
        from .themed_message import themed_info
        themed_info(parent or self,
                    "Save Schematic" if self.kind == "schematic" else "Save Block",
                    "Draw or import geometry first.")
        return False

    def _save_via_dialog(self, parent, *, save_as: bool):
        """Run the Save dialog, then commit to the project (+ optional library).

        Args:
            parent: Optional Qt parent for the dialog (falls back to self).
            save_as: Commit as a NEW definition (Save As) instead of in place.
        """
        from PyQt6.QtWidgets import QDialog
        if not self._has_geometry(parent):
            return None
        proj = self._project_scene
        cur = self._saved_definition()
        if save_as and cur is not None:
            context = "new"
            icount = 0
            initial = (f"{cur.name} copy", cur.library, cur.series)
        elif cur is not None:
            context = "edit"
            icount = proj.instance_count(cur.id)
            initial = (cur.name, cur.library, cur.series)
        elif self._seed_source_items:
            context = "seeded"
            icount = 0
            initial = ("", "", "")
        else:
            context = "new"
            icount = 0
            initial = ("", "", "")
        # The id this save writes as: a Save As writes a brand-new block.
        writes_as = None if save_as else self._edit_block_id

        if self.kind == "schematic":
            def _validator(name, library, series):
                for o in proj._block_definitions.values():
                    if o.id == writes_as or o.kind != "schematic":
                        continue
                    if (o.series, o.name) == (series, name):
                        where = f" in {series}" if series else ""
                        return f"A schematic '{name}' already exists{where}."
                return None
            from .app_data import schematics_dir
            tpl_root = schematics_dir()
            dlg = BlockSaveDialog(parent or self, kind="schematic", root=tpl_root,
                                  schematic_series=schematic_series_for(proj, root=tpl_root),
                                  collision_id=writes_as, context=context,
                                  instance_count=0, initial=initial,
                                  validator=_validator)
        else:
            def _validator(name, library, series):
                for o in proj._block_definitions.values():
                    if o.id == writes_as:
                        continue
                    if (o.library, o.series, o.name) == (library, series, name):
                        return f"A block '{name}' already exists in {library} / {series}."
                return None
            dlg = BlockSaveDialog(parent or self, library_tree=library_tree_for(proj),
                                  collision_id=writes_as,
                                  context=context, instance_count=icount,
                                  initial=initial, validator=_validator)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        v = dlg.values()
        previous_id = self._edit_block_id
        if save_as:
            self._edit_block_id = None          # commit as a NEW definition
        defn = self.commit_block(v["name"], v["library"], v["series"],
                                 replace_source=v["replace_source"] and not save_as)
        if defn is None:
            self._edit_block_id = previous_id
            return None
        if v["save_to_library"]:
            self._save_to_library(defn, parent or self,
                                  overwrite=v.get("overwrite", False))
        elif v.get("save_template"):
            from .app_data import schematics_dir
            # Remembered so a ribbon Save as Template that opened this dialog
            # does not write the same file twice (SV3 seam minor, SV4).
            self._dialog_template_path = self._save_to_library(
                defn, parent or self, overwrite=v.get("overwrite", False),
                root=schematics_dir())
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

        * ``insert_at_origin`` on — the base point lands on the block origin,
          the editor scene's fixed (0,0) (D4, §6.5).
        * off — the geometry is added base-at-origin, selected, and handed to
          the Move tool with the base point preset, so it rides the cursor
          (OSNAP / ALIGN / HUD) until the placing click.

        Args:
            p: ``ImportParams`` from ``BlockImportDialog.get_import_params()``.
        """
        from PyQt6.QtCore import QPointF
        from . import dwg_converter
        # Base-shift + scale + rotation: the base point maps to (0, 0)
        # unconditionally (§6.5). Scale is baked here, so the primitive
        # factory gets 1.0.
        geoms = dwg_converter.apply_import_transform(
            p.geom_list, p.scale, p.base_x, p.base_y, p.rotation)
        added, _skipped = self._add_imported_geoms(geoms, 1.0)
        if added and not p.insert_at_origin:
            self.editor_scene.begin_move_from(QPointF(0.0, 0.0))

    def _save_to_library(self, defn, parent, *, overwrite: bool = False,
                         root: str | None = None):
        """Persist *defn* to the on-disk block library (or, with ``root``,
        the schematic templates folder — schematics.md D-S6).

        The Save dialog already resolved any collision (``overwrite`` carries
        its Overwrite choice); the confirm below only guards a race where the
        slot got taken after the dialog closed.

        Args:
            defn: The ``BlockDefinition`` to persist.
            parent: Qt parent widget for confirmation dialogs.
            overwrite: Clobber a different definition holding the same file.
            root: Library root; None = the block library.

        Returns:
            The written ``.fpdb`` path, or None when the overwrite was declined.
        """
        from . import block_library
        from .themed_message import themed_confirm
        noun = "template" if root is not None else "block"
        bundled = self._project_scene.block_registry.bundle_for(defn.id)
        try:
            return block_library.save_to_library(defn, root=root, overwrite=overwrite,
                                                 bundled=bundled)
        except block_library.BlockNameCollision as e:
            if themed_confirm(parent, f"Overwrite {noun}?",
                              f"A different {noun} '{e.existing_name}' occupies that "
                              f"file. Overwrite it?"):
                return block_library.save_to_library(defn, root=root, overwrite=True,
                                                     bundled=bundled)
        return None


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
        # Rename walker hook (linetypes.md LT2-8): the Display Manager rewrites
        # weight names in open editors' live items through this provider.
        project_scene._editor_scenes_provider = (
            lambda: [w.editor_scene for w in self.open_editors()])

    def _created(self, w: BlockEditorWidget) -> BlockEditorWidget:
        """Wire the save hook, then invoke the shell adoption hook (if any)."""
        w.saved.connect(self._on_saved)   # bound method (harness Invariant 6)
        # Edit Block on a nested instance (right-click / double-click, D10).
        w.editor_scene.blockEditRequested.connect(self.edit_definition)
        if self.on_open is not None:
            self.on_open(w)
        return w

    def edit_definition(self, block_id: str) -> BlockEditorWidget | None:
        """Open *block_id* for editing, seeded from its definition.

        Focuses an already-open editor for the id unchanged (never a
        duplicate tab, never a re-seed); a freshly opened editor is seeded
        from the project definition. ``open_for_definition`` alone opens an
        empty editor (its callers seed), so the nested-block Edit Block
        route (``blockEditRequested``) goes through here.

        Args:
            block_id: The project definition to edit.

        Returns:
            The editor widget, or None when the id does not resolve.
        """
        defn = self._project_scene.get_block_definition(block_id)
        if defn is None:
            return None
        fresh = block_id not in self._open
        w = self.open_for_definition(block_id)
        if fresh:
            w.seed_from_definition(defn)
        return w

    def open_new(self, *, title: str = "New", kind: str = "block") -> BlockEditorWidget:
        """Open a fresh, independent editor tab (new/blank/clone).

        Args:
            title: Tab title suffix.
            kind: ``"schematic"`` opens a Schematic editor (D-S9).
        """
        w = BlockEditorWidget(self._project_scene, kind=kind)
        key = ("new", self._new_counter)
        self._new_counter += 1
        w._editor_key = key
        self._open[key] = w
        idx = self._tabs.addTab(w, tab_title(kind, title))
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
        kind = getattr(defn, "kind", "block")
        w = BlockEditorWidget(self._project_scene, block_id=block_id, kind=kind)
        w._editor_key = block_id
        self._open[block_id] = w
        idx = self._tabs.addTab(w, tab_title(kind, title))
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
            self._tabs.setTabText(idx, tab_title(w.kind, defn.name))

    def editor_for(self, block_id: str) -> BlockEditorWidget | None:
        """The open editor bound to *block_id*, or None."""
        return self._open.get(block_id)

    def retitle_schematics(self) -> None:
        """Re-title open Schematic tabs from the registry names (browser
        Rename and its undo, D-S16/D-S17)."""
        for key, w in self._open.items():
            if w.kind != "schematic" or isinstance(key, tuple):
                continue
            defn = self._project_scene.get_block_definition(key)
            idx = self._tabs.indexOf(w)
            if defn is not None and idx != -1:
                self._tabs.setTabText(idx, tab_title("schematic", defn.name))

    def close(self, widget: BlockEditorWidget) -> None:
        """Remove and dispose an editor tab."""
        if hasattr(widget, "editor_scene"):
            widget.editor_scene.commit_text_edit()
        idx = self._tabs.indexOf(widget)
        if idx != -1:
            self._tabs.removeTab(idx)
        self._open.pop(getattr(widget, "_editor_key", None), None)
        self._detach_registry(widget)
        widget.deleteLater()

    def forget(self, widget: BlockEditorWidget) -> None:
        """Drop a widget from tracking (called when its tab is closed elsewhere)."""
        self._open.pop(getattr(widget, "_editor_key", None), None)
        self._detach_registry(widget)

    def _detach_registry(self, widget: BlockEditorWidget) -> None:
        """Stop the project registry repainting a closed editor's scene.

        The editor scene is Python-owned (no Qt parent), so the registry's
        strong reference would otherwise keep it alive after the tab closes.
        """
        es = getattr(widget, "editor_scene", None)
        if es is not None:
            es.block_registry.detach_scene(es)

    def open_editors(self) -> list:
        """Return the currently open editor widgets (stable-ish, dict order).

        Public accessor for callers outside the manager (e.g. main.py's
        ``_text_edit_scenes``) that must not reach into the private ``_open``
        dict directly.
        """
        return list(self._open.values())

