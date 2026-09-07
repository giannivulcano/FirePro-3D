"""
model_browser.py
================
Model Browser dock widget for FirePro 3D.

Displays all model entities (walls, floors, doors, windows) in a
categorised tree view with auto-generated names.  Click to select
an entity in the 2D scene, double-click to zoom-to-fit.
"""

from __future__ import annotations

import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel, QSizePolicy,
    QAbstractItemView, QMenu,
)
from .themed_message import themed_confirm
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent
from PyQt6.QtGui import QFont, QColor, QBrush

from . import theme as th
from .wall import WallSegment
from .floor_slab import FloorSlab
from .pipe import Pipe
from .node import Node


_ROLE_ENTITY = Qt.ItemDataRole.UserRole  # stores Python id() of the entity
_ROLE_UNDERLAY = Qt.ItemDataRole.UserRole + 1  # stores index into scene.underlays


class ModelBrowser(QWidget):
    """Tree-view browser listing all model entities by category."""

    entitySelected = pyqtSignal(object)  # emits the QGraphicsItem (or None)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = None
        self._syncing = False  # guard against selection-change recursion

        _t = th.detect()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header
        hdr = QLabel("Model Browser")
        hdr.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        f = QFont()
        f.setBold(True)
        f.setPointSize(9)
        hdr.setFont(f)
        hdr.setStyleSheet(
            f"color: {_t.text_primary}; "
            f"background: {_t.bg_raised}; "
            f"padding: 4px; border-radius: 3px;"
        )
        layout.addWidget(hdr)

        # Tree widget
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(16)
        self._tree.setStyleSheet(
            f"QTreeWidget {{ background: {_t.bg_raised}; color: {_t.text_primary}; "
            f"border: 1px solid {_t.border_subtle}; }}"
            f"QTreeWidget::item:selected {{ background: {_t.accent_primary}; color: #ffffff; }}"
            f"QTreeWidget::item:hover   {{ background: {_t.bg_base}; }}"
        )
        self._tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.itemChanged.connect(self._on_tree_item_changed)
        # Delete key on the tree deletes the selected entities (spec §4.3).
        self._tree.installEventFilter(self)
        layout.addWidget(self._tree)

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        # Debounce timer for refresh
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(200)
        self._refresh_timer.timeout.connect(self._do_refresh)

    # ── Public API ────────────────────────────────────────────────────────

    def set_scene(self, scene):
        """Connect to a Model_Space scene."""
        self._scene = scene
        if scene is not None and hasattr(scene, "sceneModified"):
            scene.sceneModified.connect(self.schedule_refresh)
            scene.underlaysChanged.connect(self.schedule_refresh)
        self.refresh()

    def sync_from_scene(self):
        """Highlight tree items matching the current scene selection.

        Called when selection changes in the 2D scene or 3D view so the
        model browser stays in sync.
        """
        if self._syncing or self._scene is None:
            return
        self._syncing = True
        try:
            selected = self._scene.selectedItems()
            sel_ids = {id(item) for item in selected}

            self._tree.blockSignals(True)
            self._tree.clearSelection()

            # Walk tree and select matching items
            def _walk(parent_item):
                for i in range(parent_item.childCount()):
                    child = parent_item.child(i)
                    entity_id = child.data(0, _ROLE_ENTITY)
                    if entity_id is not None and entity_id in sel_ids:
                        child.setSelected(True)
                    _walk(child)

            root = self._tree.invisibleRootItem()
            _walk(root)
            self._tree.blockSignals(False)
        except RuntimeError:
            pass  # scene C++ object deleted during shutdown
        finally:
            self._syncing = False

    def schedule_refresh(self):
        """Schedule a debounced refresh."""
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    # ── Internals ─────────────────────────────────────────────────────────

    def _do_refresh(self):
        self.refresh()

    def _save_expansion(self) -> set[str]:
        """Return text of all expanded tree items."""
        expanded = set()
        for i in range(self._tree.topLevelItemCount()):
            self._walk_expansion(self._tree.topLevelItem(i), expanded)
        return expanded

    def _walk_expansion(self, item, expanded: set, prefix: str = ""):
        key = prefix + item.text(0)
        if item.isExpanded():
            expanded.add(key)
        for j in range(item.childCount()):
            self._walk_expansion(item.child(j), expanded, key + "/")

    def _restore_expansion(self, expanded: set):
        """Re-expand tree items whose text path matches."""
        for i in range(self._tree.topLevelItemCount()):
            self._walk_restore(self._tree.topLevelItem(i), expanded)

    def _walk_restore(self, item, expanded: set, prefix: str = ""):
        key = prefix + item.text(0)
        if key in expanded:
            item.setExpanded(True)
        for j in range(item.childCount()):
            self._walk_restore(item.child(j), expanded, key + "/")

    def refresh(self):
        """Rebuild the tree from current scene data."""
        self._syncing = True
        try:
            expanded = self._save_expansion()
            self._tree.clear()
            if self._scene is None:
                return

            f_bold = QFont()
            f_bold.setBold(True)

            # -- Walls --
            walls = getattr(self._scene, "_walls", [])
            walls_root = QTreeWidgetItem(self._tree, [f"Walls ({len(walls)})"])
            walls_root.setFont(0, f_bold)
            walls_root.setExpanded(True)
            for wall in walls:
                label = wall.name if wall.name else "Wall"
                item = QTreeWidgetItem(walls_root, [label])
                item.setData(0, _ROLE_ENTITY, id(wall))
                item.setToolTip(0, f"Level: {wall.level}")
                self._style_hidden(item, wall)

            # -- Floors --
            slabs = getattr(self._scene, "_floor_slabs", [])
            floors_root = QTreeWidgetItem(self._tree, [f"Floors ({len(slabs)})"])
            floors_root.setFont(0, f_bold)
            floors_root.setExpanded(True)
            for slab in slabs:
                label = slab.name if slab.name else "Floor"
                item = QTreeWidgetItem(floors_root, [label])
                item.setData(0, _ROLE_ENTITY, id(slab))
                pts = len(slab.points) if hasattr(slab, "points") else 0
                item.setToolTip(0, f"Points: {pts}")
                self._style_hidden(item, slab)

            # -- Roofs --
            roofs = getattr(self._scene, "_roofs", [])
            roofs_root = QTreeWidgetItem(self._tree, [f"Roofs ({len(roofs)})"])
            roofs_root.setFont(0, f_bold)
            roofs_root.setExpanded(True)
            for roof in roofs:
                label = roof.name if roof.name else "Roof"
                item = QTreeWidgetItem(roofs_root, [label])
                item.setData(0, _ROLE_ENTITY, id(roof))
                pts = len(roof.points) if hasattr(roof, "points") else 0
                item.setToolTip(0, f"Level: {roof.level}  Type: {getattr(roof, '_roof_type', 'flat')}  Points: {pts}")
                self._style_hidden(item, roof)

            # -- Rooms --
            rooms = getattr(self._scene, "_rooms", [])
            rooms_root = QTreeWidgetItem(self._tree, [f"Rooms ({len(rooms)})"])
            rooms_root.setFont(0, f_bold)
            rooms_root.setExpanded(True)
            for room in rooms:
                label = room.name if room.name else "Room"
                item = QTreeWidgetItem(rooms_root, [label])
                item.setData(0, _ROLE_ENTITY, id(room))
                item.setToolTip(0, f"Level: {room.level}  Tag: {getattr(room, '_tag', '')}")
                self._style_hidden(item, room)

            # -- Doors --
            doors: list = []
            for wall in walls:
                for op in getattr(wall, "openings", []):
                    if getattr(op, "_type", "door") == "door":
                        doors.append(op)
            doors_root = QTreeWidgetItem(self._tree, [f"Doors ({len(doors)})"])
            doors_root.setFont(0, f_bold)
            for i, door in enumerate(doors, 1):
                item = QTreeWidgetItem(doors_root, [f"Door {i}"])
                item.setData(0, _ROLE_ENTITY, id(door))
                self._style_hidden(item, door)

            # -- Windows --
            windows: list = []
            for wall in walls:
                for op in getattr(wall, "openings", []):
                    if getattr(op, "_type", "") == "window":
                        windows.append(op)
            windows_root = QTreeWidgetItem(self._tree, [f"Windows ({len(windows)})"])
            windows_root.setFont(0, f_bold)
            for i, win in enumerate(windows, 1):
                item = QTreeWidgetItem(windows_root, [f"Window {i}"])
                item.setData(0, _ROLE_ENTITY, id(win))
                self._style_hidden(item, win)

            # -- Pipes --
            pipes = list(getattr(self._scene, "sprinkler_system", None).pipes) \
                if getattr(self._scene, "sprinkler_system", None) else []
            pipes_root = QTreeWidgetItem(self._tree, [f"Pipes ({len(pipes)})"])
            pipes_root.setFont(0, f_bold)
            pipes_root.setExpanded(True)
            for i, pipe in enumerate(pipes, 1):
                dia = pipe._properties.get("Diameter", {}).get("value", "?")
                label = f"Pipe {i}  ({dia})"
                item = QTreeWidgetItem(pipes_root, [label])
                item.setData(0, _ROLE_ENTITY, id(pipe))
                item.setToolTip(0, f"Level: {pipe.level}")
                self._style_hidden(item, pipe)

            # -- Sprinklers --
            sprinkler_nodes = [n for n in
                (getattr(self._scene, "sprinkler_system", None).nodes
                 if getattr(self._scene, "sprinkler_system", None) else [])
                if n.has_sprinkler()]
            sprinklers_root = QTreeWidgetItem(
                self._tree, [f"Sprinklers ({len(sprinkler_nodes)})"])
            sprinklers_root.setFont(0, f_bold)
            sprinklers_root.setExpanded(True)
            for i, node in enumerate(sprinkler_nodes, 1):
                spr = node.sprinkler
                mfr = spr._properties.get("Manufacturer", {}).get("value", "")
                orient = spr._properties.get("Orientation", {}).get("value", "")
                label = f"Sprinkler {i}  ({mfr} {orient})"
                item = QTreeWidgetItem(sprinklers_root, [label])
                item.setData(0, _ROLE_ENTITY, id(node))
                item.setToolTip(0, f"Level: {node.level}")
                self._style_hidden(item, node)

            # -- Fittings --
            all_nodes = list(
                getattr(self._scene, "sprinkler_system", None).nodes
            ) if getattr(self._scene, "sprinkler_system", None) else []
            # Build pipe index for labeling
            pipe_list = list(
                getattr(self._scene, "sprinkler_system", None).pipes
            ) if getattr(self._scene, "sprinkler_system", None) else []
            pipe_idx = {id(p): i for i, p in enumerate(pipe_list, 1)}
            fitting_nodes = [
                n for n in all_nodes
                if n.fitting and n.fitting.type != "no fitting"
            ]
            fittings_root = QTreeWidgetItem(
                self._tree, [f"Fittings ({len(fitting_nodes)})"])
            fittings_root.setFont(0, f_bold)
            for node in fitting_nodes:
                fit = node.fitting
                # Build label: type @ connected pipe indices
                pipe_refs = ", ".join(
                    f"Pipe {pipe_idx.get(id(p), '?')}"
                    for p in node.pipes
                )
                type_name = fit.type.replace("_", " ").title()
                label = f"{type_name} @ {pipe_refs}" if pipe_refs else type_name
                item = QTreeWidgetItem(fittings_root, [label])
                item.setData(0, _ROLE_ENTITY, id(node))
                item.setToolTip(
                    0, f"Level: {node.level}  Type: {fit.type}")
                self._style_hidden(item, fit)

            # -- Gridlines --
            gridlines = getattr(self._scene, "_gridlines", [])
            if gridlines:
                gl_root = QTreeWidgetItem(self._tree, [f"Gridlines ({len(gridlines)})"])
                gl_root.setFont(0, f_bold)
                for gl in gridlines:
                    lbl = getattr(gl, "_label_text", "?")
                    item = QTreeWidgetItem(gl_root, [f"Grid {lbl}"])
                    item.setData(0, _ROLE_ENTITY, id(gl))
                    self._style_hidden(item, gl)

            # -- Design Areas --
            design_areas = getattr(self._scene, "design_areas", [])
            if design_areas:
                da_root = QTreeWidgetItem(self._tree, [f"Design Areas ({len(design_areas)})"])
                da_root.setFont(0, f_bold)
                for i, da in enumerate(design_areas, 1):
                    name = da._properties.get("System Name", {}).get("value", f"Area {i}")
                    item = QTreeWidgetItem(da_root, [name])
                    item.setData(0, _ROLE_ENTITY, id(da))
                    self._style_hidden(item, da)

            # -- Water Supply --
            ws = getattr(self._scene, "water_supply_node", None)
            if ws is not None:
                ws_root = QTreeWidgetItem(self._tree, ["Water Supply (1)"])
                ws_root.setFont(0, f_bold)
                item = QTreeWidgetItem(ws_root, ["Water Supply"])
                item.setData(0, _ROLE_ENTITY, id(ws))
                self._style_hidden(item, ws)

            # -- Underlays ─────────────────────────────────────────────────
            underlays = getattr(self._scene, "underlays", [])
            if underlays:
                ul_root = QTreeWidgetItem(
                    self._tree, [f"Underlays ({len(underlays)})"])
                ul_root.setFont(0, f_bold)
                ul_root.setExpanded(True)

                from .underlay_manager_model import _record_name
                for idx, (data, item) in enumerate(underlays):
                    filename = _record_name(data)
                    is_missing = (item is None
                                  or item.data(0) == "missing_underlay")
                    level_label = (
                        "All Levels" if data.levels == ["*"]
                        else ", ".join(data.levels) or "—"
                    )

                    # File node
                    label = f"{filename}    [{level_label}]"
                    if is_missing:
                        label += "  (missing)"
                    file_node = QTreeWidgetItem(ul_root, [label])
                    file_node.setData(0, _ROLE_UNDERLAY, idx)
                    if not is_missing:
                        file_node.setFlags(
                            file_node.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        # Simple two-state checkbox — layer-level visibility is
                        # managed in the Underlay Manager, not the browser.
                        file_node.setCheckState(
                            0, Qt.CheckState.Checked if data.visible
                            else Qt.CheckState.Unchecked)
                    if not data.visible:
                        file_node.setForeground(0, self._GREY)

                    # PDF page child (navigation-only; DXF layer nodes removed)
                    if data.type == "pdf" and not is_missing:
                        QTreeWidgetItem(file_node, [f"Page {data.page + 1}"])
            self._restore_expansion(expanded)
        finally:
            self._syncing = False

    # ── Helpers ─────────────────────────────────────────────────────────

    _GREY = QBrush(QColor("#888888"))

    @staticmethod
    def _style_hidden(tree_item: QTreeWidgetItem, entity):
        """Grey out the tree item if the entity is manually hidden."""
        if getattr(entity, "_display_overrides", {}).get("visible") is False:
            tree_item.setForeground(0, ModelBrowser._GREY)

    # ── Entity lookup ─────────────────────────────────────────────────────

    def _find_entity_by_id(self, entity_id: int):
        """Look up a scene entity by its Python id()."""
        if self._scene is None:
            return None
        for wall in getattr(self._scene, "_walls", []):
            if id(wall) == entity_id:
                return wall
            for op in getattr(wall, "openings", []):
                if id(op) == entity_id:
                    return op
        for slab in getattr(self._scene, "_floor_slabs", []):
            if id(slab) == entity_id:
                return slab
        for roof in getattr(self._scene, "_roofs", []):
            if id(roof) == entity_id:
                return roof
        ss = getattr(self._scene, "sprinkler_system", None)
        if ss:
            for pipe in ss.pipes:
                if id(pipe) == entity_id:
                    return pipe
            for node in ss.nodes:
                if id(node) == entity_id:
                    return node
        for gl in getattr(self._scene, "_gridlines", []):
            if id(gl) == entity_id:
                return gl
        for room in getattr(self._scene, "_rooms", []):
            if id(room) == entity_id:
                return room
        for da in getattr(self._scene, "design_areas", []):
            if id(da) == entity_id:
                return da
        ws = getattr(self._scene, "water_supply_node", None)
        if ws and id(ws) == entity_id:
            return ws
        return None

    # ── Click handlers ────────────────────────────────────────────────────

    def _on_selection_changed(self):
        """Handle tree selection changes."""
        if self._syncing:
            return
        selected_items = self._tree.selectedItems()

        # Check for underlay file-node selection
        for tree_item in selected_items:
            ul_idx = tree_item.data(0, _ROLE_UNDERLAY)
            if ul_idx is not None:
                self._on_underlay_selected(ul_idx)
                return

        # Existing entity selection logic
        entities = []
        for tree_item in selected_items:
            entity_id = tree_item.data(0, _ROLE_ENTITY)
            if entity_id is not None:
                entity = self._find_entity_by_id(entity_id)
                if entity is not None:
                    entities.append(entity)
        if not entities:
            return
        self._syncing = True
        try:
            self._scene.clearSelection()
            for entity in entities:
                entity.setSelected(True)
        finally:
            self._syncing = False
        if len(entities) == 1:
            self.entitySelected.emit(entities[0])
        else:
            self.entitySelected.emit(entities)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Double-click: select + zoom to fit the entity."""
        entity_id = item.data(0, _ROLE_ENTITY)
        if entity_id is not None:
            entity = self._find_entity_by_id(entity_id)
            if entity is not None:
                self._scene.clearSelection()
                entity.setSelected(True)
                self.entitySelected.emit(entity)
                # Zoom to fit in the first view
                views = self._scene.views()
                if views:
                    br = entity.boundingRect()
                    views[0].fitInView(
                        entity.mapToScene(br).boundingRect().adjusted(-50, -50, 50, 50),
                        Qt.AspectRatioMode.KeepAspectRatio,
                    )

    def _on_context_menu(self, pos):
        """Right-click context menu on tree items."""
        if self._scene is None:
            return

        tree_item = self._tree.itemAt(pos)
        if tree_item is not None:
            ul_idx = tree_item.data(0, _ROLE_UNDERLAY)
            if ul_idx is not None:
                self._underlay_context_menu(tree_item, ul_idx, pos)
                return

        # Gather entities from selected tree items
        entities = []
        for tree_item in self._tree.selectedItems():
            eid = tree_item.data(0, _ROLE_ENTITY)
            if eid is not None:
                entity = self._find_entity_by_id(eid)
                if entity is not None:
                    entities.append(entity)
        if not entities:
            return

        menu = QMenu(self)

        # Check if any selected entities are currently hidden
        any_hidden = any(
            getattr(e, "_display_overrides", {}).get("visible") is False
            for e in entities
        )
        any_visible = any(
            getattr(e, "_display_overrides", {}).get("visible") is not False
            for e in entities
        )

        if any_visible:
            act_hide = menu.addAction("Hide")
            act_hide.triggered.connect(
                lambda: (self._scene._hide_items(entities), self.refresh()))

        if any_hidden:
            act_show = menu.addAction("Show")
            act_show.triggered.connect(
                lambda: (self._scene._show_items(entities), self.refresh()))

        menu.addSeparator()
        act_show_all = menu.addAction("Show All Hidden")
        act_show_all.triggered.connect(
            lambda: (self._scene._show_all_hidden(), self.refresh()))

        menu.addSeparator()
        act_delete = menu.addAction("Delete")
        act_delete.triggered.connect(self._delete_selected_entities)

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    # ── Deletion (spec §4.3) ───────────────────────────────────────────────

    def eventFilter(self, obj, event):
        """Delete key on the tree deletes the selected entities."""
        if (obj is self._tree
                and event.type() == QEvent.Type.KeyPress
                and event.key() == Qt.Key.Key_Delete):
            self._delete_selected_entities()
            return True
        return super().eventFilter(obj, event)

    def _delete_selected_entities(self):
        """Delete the selected entity rows via the scene's canonical path.

        Underlay file/layer rows are excluded (their removal is a separate,
        non-undoable path). The browser does not re-implement deletion: it
        selects the resolved entities in the scene and delegates to
        ``delete_selected_items()``, which owns the entity-graph bookkeeping
        and the single undo push (spec §4.3).
        """
        if self._scene is None:
            return
        entities = []
        for tree_item in self._tree.selectedItems():
            if tree_item.data(0, _ROLE_UNDERLAY) is not None:
                continue  # underlay rows are not entity-deletable
            eid = tree_item.data(0, _ROLE_ENTITY)
            if eid is not None:
                entity = self._find_entity_by_id(eid)
                if entity is not None:
                    entities.append(entity)
        if not entities:
            return
        self._syncing = True
        try:
            self._scene.clearSelection()
            for entity in entities:
                entity.setSelected(True)
        finally:
            self._syncing = False
        self._scene.delete_selected_items()
        self.refresh()

    # ── Checkbox handler ───────────────────────────────────────────────

    def _on_tree_item_changed(self, tree_item: QTreeWidgetItem, column: int):
        """Handle checkbox state changes on underlay file nodes (show/hide)."""
        if self._syncing:
            return
        ul_idx = tree_item.data(0, _ROLE_UNDERLAY)
        if ul_idx is None:
            return
        underlays = getattr(self._scene, "underlays", [])
        if ul_idx < 0 or ul_idx >= len(underlays):
            return
        data, item = underlays[ul_idx]
        if item is None:
            return

        # File node only (layer child nodes no longer exist in the browser)
        new_state = tree_item.checkState(0)
        if new_state == Qt.CheckState.Checked and not data.visible:
            self._toggle_underlay_visible(data, item)
        elif new_state == Qt.CheckState.Unchecked and data.visible:
            self._toggle_underlay_visible(data, item)

    # ── Underlay handlers ────────────────────────────────────────────────

    def _on_underlay_selected(self, idx: int):
        """Handle click on an underlay file node — pan to it and populate
        property panel (even for locked underlays)."""
        underlays = getattr(self._scene, "underlays", [])
        if idx < 0 or idx >= len(underlays):
            return
        data, item = underlays[idx]

        if item is not None:
            # Pan view to the underlay
            views = self._scene.views()
            if views:
                br = item.boundingRect()
                scene_rect = item.mapToScene(br).boundingRect()
                views[0].centerOn(scene_rect.center())

            # Select in scene if not locked
            self._syncing = True
            try:
                self._scene.clearSelection()
                if not data.locked:
                    item.setSelected(True)
            finally:
                self._syncing = False

        # Populate property panel (always, even when item is None)
        self.entitySelected.emit(data)

    def _underlay_context_menu(self, tree_item, ul_idx: int, pos):
        """Build and show context menu for an underlay tree node."""
        underlays = getattr(self._scene, "underlays", [])
        if ul_idx < 0 or ul_idx >= len(underlays):
            return
        data, item = underlays[ul_idx]
        is_missing = (item is None
                      or item.data(0) == "missing_underlay")

        menu = QMenu(self)

        if is_missing:
            # Missing underlay: only Remove is available
            act_remove = menu.addAction("Remove")
            act_remove.triggered.connect(
                lambda: self._remove_underlay(data, item))
        else:
            # Navigation-only actions (no editing \u2014 editing is in Underlay Manager)
            lock_label = "Unlock" if data.locked else "Lock"
            act_lock = menu.addAction(lock_label)
            act_lock.triggered.connect(
                lambda: self._toggle_underlay_lock(data, item))

            vis_label = "Show" if not data.visible else "Hide"
            act_vis = menu.addAction(vis_label)
            act_vis.triggered.connect(
                lambda: self._toggle_underlay_visible(data, item))

            menu.addSeparator()
            act_remove = menu.addAction("Remove")
            act_remove.triggered.connect(
                lambda: self._remove_underlay(data, item))

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    # ── Underlay action helpers ──────────────────────────────────────────

    def _toggle_underlay_lock(self, data, item):
        from PyQt6.QtWidgets import QGraphicsItem
        data.locked = not data.locked
        if data.locked:
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        else:
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self._scene.push_undo_state()
        self.refresh()

    def _toggle_underlay_visible(self, data, item):
        data.visible = not data.visible
        lm = getattr(self._scene, "_level_manager", None)
        if lm:
            lm.apply_to_scene(self._scene)
        elif item is not None:
            item.setVisible(data.visible)
        self._scene.push_undo_state()
        self.refresh()

    def _remove_underlay(self, data, item):
        """Remove with confirmation dialog."""
        from .underlay_manager_model import _record_name
        filename = _record_name(data)
        if themed_confirm(
            self, "Remove Underlay",
            f"Remove underlay '{filename}'?\nThis cannot be undone.",
        ):
            self._scene.remove_underlay(data, item)
            self.refresh()
