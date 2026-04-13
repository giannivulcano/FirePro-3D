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
    QAbstractItemView, QMenu, QMessageBox, QFileDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QBrush

from . import theme as th
from .wall import WallSegment
from .floor_slab import FloorSlab
from .wall_opening import DoorOpening, WindowOpening
from .pipe import Pipe
from .node import Node
from .underlay import Underlay
from .underlay_context_menu import UnderlayContextMenu


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

    def refresh(self):
        """Rebuild the tree from current scene data."""
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
            item.setToolTip(0, f"Level: {wall.level}  Layer: {wall.user_layer}")
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
            item.setToolTip(0, f"Level: {slab.level}  Points: {pts}")
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
                if isinstance(op, DoorOpening):
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
                if isinstance(op, WindowOpening):
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
            item.setToolTip(0, f"Level: {pipe.level}  Layer: {pipe.user_layer}")
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
            item.setToolTip(0, f"Level: {node.level}  Layer: {node.user_layer}")
            self._style_hidden(item, node)

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

            for idx, (data, item) in enumerate(underlays):
                filename = os.path.basename(data.path)
                is_missing = (item is None
                              or item.data(0) == "missing_underlay")
                level_label = ("All Levels" if data.level == "*"
                               else data.level)

                # File node
                label = f"{filename}    [{level_label}]"
                if is_missing:
                    label += "  (missing)"
                file_node = QTreeWidgetItem(ul_root, [label])
                file_node.setData(0, _ROLE_UNDERLAY, idx)
                if not data.visible:
                    file_node.setForeground(0, self._GREY)

                # Source-layer children (DXF only)
                if data.type == "dxf" and item is not None and not is_missing:
                    all_layers = item.data(2) or []
                    hidden_set = set(data.hidden_layers)
                    for layer_name in all_layers:
                        count = sum(
                            1 for c in item.childItems()
                            if c.data(1) == layer_name)
                        suffix = "  (hidden)" if layer_name in hidden_set else ""
                        layer_node = QTreeWidgetItem(
                            file_node,
                            [f"{layer_name}  ({count} items){suffix}"])
                        layer_node.setData(0, _ROLE_UNDERLAY, idx)
                        layer_node.setData(0, _ROLE_ENTITY, layer_name)
                        if layer_name in hidden_set:
                            layer_node.setForeground(0, self._GREY)

                # PDF page child
                elif data.type == "pdf" and not is_missing:
                    QTreeWidgetItem(file_node, [f"Page {data.page + 1}"])

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

        # Check for underlay file-node selection (skip layer nodes)
        for tree_item in selected_items:
            ul_idx = tree_item.data(0, _ROLE_UNDERLAY)
            if ul_idx is not None:
                # Layer nodes have _ROLE_ENTITY set to the layer name —
                # don't pan/select for those, only file nodes
                if tree_item.data(0, _ROLE_ENTITY) is None:
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

        menu.exec(self._tree.viewport().mapToGlobal(pos))

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

        # Check if this is a source-layer node
        layer_name = tree_item.data(0, _ROLE_ENTITY)
        if isinstance(layer_name, str):
            self._underlay_layer_context_menu(data, item, layer_name, pos)
            return

        menu = QMenu(self)
        scene = self._scene

        if is_missing:
            act_relink = menu.addAction("Relink\u2026")
            act_relink.triggered.connect(
                lambda: self._relink_underlay(data, item))
            menu.addSeparator()
            act_remove = menu.addAction("Remove")
            act_remove.triggered.connect(
                lambda: self._remove_underlay(data, item))
        else:
            lock_label = "Unlock" if data.locked else "Lock"
            act_lock = menu.addAction(lock_label)
            act_lock.triggered.connect(
                lambda: self._toggle_underlay_lock(data, item))

            vis_label = "Show" if not data.visible else "Hide"
            act_vis = menu.addAction(vis_label)
            act_vis.triggered.connect(
                lambda: self._toggle_underlay_visible(data, item))

            level_menu = menu.addMenu("Change Level")
            lm = getattr(scene, "_level_manager", None)
            levels = lm.levels if lm else []
            for lvl in levels:
                act = level_menu.addAction(lvl.name)
                act.triggered.connect(
                    lambda checked=False, ln=lvl.name:
                        self._set_underlay_level(data, ln))
            level_menu.addSeparator()
            act_all = level_menu.addAction("All Levels")
            act_all.triggered.connect(
                lambda: self._set_underlay_level(data, "*"))

            menu.addSeparator()
            act_scale = menu.addAction("Scale\u2026")
            act_scale.triggered.connect(
                lambda: (UnderlayContextMenu._set_scale(scene, data, item),
                         self.refresh()))
            act_rotate = menu.addAction("Rotate\u2026")
            act_rotate.triggered.connect(
                lambda: (UnderlayContextMenu._set_rotation(scene, data, item),
                         self.refresh()))
            act_opacity = menu.addAction("Opacity\u2026")
            act_opacity.triggered.connect(
                lambda: (UnderlayContextMenu._set_opacity(scene, data, item),
                         self.refresh()))

            menu.addSeparator()
            act_relink = menu.addAction("Relink\u2026")
            act_relink.triggered.connect(
                lambda: self._relink_underlay(data, item))

            act_refresh = menu.addAction("Refresh from Disk")
            act_refresh.triggered.connect(
                lambda: (scene.refresh_underlay(data, item),
                         self.refresh()))

            act_dup = menu.addAction("Duplicate")
            act_dup.triggered.connect(
                lambda: (UnderlayContextMenu._duplicate(scene, data, item),
                         self.refresh()))

            menu.addSeparator()
            act_remove = menu.addAction("Remove")
            act_remove.triggered.connect(
                lambda: self._remove_underlay(data, item))

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _underlay_layer_context_menu(self, data, item, layer_name, pos):
        """Context menu for a DXF source-layer node."""
        menu = QMenu(self)
        is_hidden = layer_name in data.hidden_layers
        label = "Show Layer" if is_hidden else "Hide Layer"
        act = menu.addAction(label)
        act.triggered.connect(
            lambda: self._toggle_underlay_layer(data, item, layer_name))
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

    def _set_underlay_level(self, data, level_name: str):
        data.level = level_name
        lm = getattr(self._scene, "_level_manager", None)
        if lm:
            lm.apply_to_scene(self._scene)
        self._scene.push_undo_state()
        self.refresh()

    def _toggle_underlay_layer(self, data, item, layer_name):
        """Toggle a DXF source layer on/off."""
        if layer_name in data.hidden_layers:
            data.hidden_layers.remove(layer_name)
            show = True
        else:
            data.hidden_layers.append(layer_name)
            show = False
        for child in item.childItems():
            if child.data(1) == layer_name:
                child.setVisible(show)
        self._scene.underlaysChanged.emit()
        self._scene.push_undo_state()
        self.refresh()

    def _relink_underlay(self, data, item):
        """File dialog to relink a missing or changed underlay."""
        if data.type == "dxf":
            filter_str = "DXF Files (*.dxf)"
        else:
            filter_str = "PDF Files (*.pdf)"
        path, _ = QFileDialog.getOpenFileName(
            self, "Relink Underlay", "", filter_str)
        if not path:
            return
        data.path = path
        self._scene.refresh_underlay(data, item)
        self._scene.push_undo_state()
        self.refresh()

    def _remove_underlay(self, data, item):
        """Remove with confirmation dialog."""
        filename = os.path.basename(data.path)
        reply = QMessageBox.question(
            self, "Remove Underlay",
            f"Remove underlay '{filename}'?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._scene.remove_underlay(data, item)
            self.refresh()
