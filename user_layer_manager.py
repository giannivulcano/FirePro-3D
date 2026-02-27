"""
user_layer_manager.py
=====================
Sprint 4A — User-defined layer system.

Each drawing item (Pipe, Node, Sprinkler) carries a ``user_layer`` string
attribute naming the layer it lives on.

Classes
-------
UserLayer        — dataclass for one layer's properties
UserLayerManager — ordered list of layers + active-layer tracking
UserLayerWidget  — QWidget dock panel (table UI + add/delete/assign buttons)
"""

from __future__ import annotations

from dataclasses import dataclass
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QColorDialog, QMessageBox,
    QAbstractItemView, QFrame, QLabel,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QFont


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class UserLayer:
    name:       str
    color:      str   = "#000000"   # hex colour — easy for JSON
    lineweight: float = 0.35        # mm paper lineweight
    visible:    bool  = True
    locked:     bool  = False
    plot:       bool  = True

    def to_dict(self) -> dict:
        return {
            "name":       self.name,
            "color":      self.color,
            "lineweight": self.lineweight,
            "visible":    self.visible,
            "locked":     self.locked,
            "plot":       self.plot,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UserLayer":
        return cls(
            name       = d["name"],
            color      = d.get("color",      "#000000"),
            lineweight = d.get("lineweight",  0.35),
            visible    = d.get("visible",     True),
            locked     = d.get("locked",      False),
            plot       = d.get("plot",        True),
        )


# Defaults shipped with every new document
DEFAULT_LAYERS: list[UserLayer] = [
    UserLayer("0",            "#000000", 0.35, True,  False, True),
    UserLayer("Sprinklers",   "#cc0000", 0.50, True,  False, True),
    UserLayer("Branch Lines", "#0055cc", 0.35, True,  False, True),
    UserLayer("Mains",        "#001f7a", 0.70, True,  False, True),
    UserLayer("Fittings",     "#007700", 0.35, True,  False, True),
    UserLayer("Valves",       "#880088", 0.35, True,  False, True),
    UserLayer("Annotations",  "#333333", 0.25, True,  False, True),
    UserLayer("Underlay",     "#aaaaaa", 0.18, True,  False, False),
]


# ─────────────────────────────────────────────────────────────────────────────
# Manager (pure data, no Qt)
# ─────────────────────────────────────────────────────────────────────────────

class UserLayerManager:
    """Manages the ordered list of user layers and the active layer."""

    def __init__(self):
        self._layers: list[UserLayer] = [
            UserLayer(**vars(l)) for l in DEFAULT_LAYERS
        ]
        self._active: str = "0"

    # ── Layer list API ───────────────────────────────────────────────────────

    @property
    def layers(self) -> list[UserLayer]:
        return list(self._layers)

    @property
    def active_layer(self) -> str:
        return self._active

    @active_layer.setter
    def active_layer(self, name: str):
        if self.get(name) is not None:
            self._active = name

    def get(self, name: str) -> UserLayer | None:
        for lyr in self._layers:
            if lyr.name == name:
                return lyr
        return None

    def add_layer(self, name: str | None = None) -> UserLayer:
        if name is None or self.get(name) is not None:
            i = 1
            while self.get(f"Layer {i}") is not None:
                i += 1
            name = f"Layer {i}"
        lyr = UserLayer(name)
        self._layers.append(lyr)
        return lyr

    def remove_layer(self, name: str):
        """Delete a layer.  Layer '0' cannot be deleted."""
        if name == "0":
            return
        self._layers = [l for l in self._layers if l.name != name]
        if self._active == name:
            self._active = "0"

    def rename_layer(self, old_name: str, new_name: str, items) -> bool:
        """Rename a layer and update all items that referenced the old name."""
        if old_name == "0":
            return False
        if not new_name or (self.get(new_name) is not None and new_name != old_name):
            return False
        lyr = self.get(old_name)
        if lyr is None:
            return False
        lyr.name = new_name
        if self._active == old_name:
            self._active = new_name
        for item in items:
            if getattr(item, "user_layer", None) == old_name:
                item.user_layer = new_name
        return True

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_list(self) -> list[dict]:
        return [l.to_dict() for l in self._layers]

    def from_list(self, data: list[dict]):
        self._layers = [UserLayer.from_dict(d) for d in data]
        if not self.get("0"):
            self._layers.insert(0, UserLayer("0"))

    # ── Apply to scene ───────────────────────────────────────────────────────

    def apply_to_scene(self, scene):
        """Show/hide and lock/unlock drawing items according to their layer."""
        from PyQt6.QtWidgets import QGraphicsItem
        visibility = {l.name: l.visible for l in self._layers}
        locked     = {l.name: l.locked  for l in self._layers}

        for node in scene.sprinkler_system.nodes:
            lyr = getattr(node, "user_layer", "0")
            vis = visibility.get(lyr, True)
            node.setVisible(vis)
            node.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,
                vis and not locked.get(lyr, False),
            )

        for pipe in scene.sprinkler_system.pipes:
            lyr = getattr(pipe, "user_layer", "0")
            vis = visibility.get(lyr, True)
            pipe.setVisible(vis)
            pipe.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,
                vis and not locked.get(lyr, False),
            )


# ─────────────────────────────────────────────────────────────────────────────
# Table column indices
# ─────────────────────────────────────────────────────────────────────────────

_COL_VIS   = 0
_COL_LOCK  = 1
_COL_COLOR = 2
_COL_NAME  = 3
_COL_LW    = 4


# ─────────────────────────────────────────────────────────────────────────────
# Widget
# ─────────────────────────────────────────────────────────────────────────────

class UserLayerWidget(QWidget):
    """
    Dock panel showing the user layer table.

    Signals
    -------
    activeLayerChanged(str)  — emitted when the active layer changes
    layersChanged()          — emitted after any structural change so the
                               scene can be refreshed
    """

    activeLayerChanged = pyqtSignal(str)
    layersChanged      = pyqtSignal()

    def __init__(self, manager: UserLayerManager, scene=None, parent=None):
        super().__init__(parent)
        self.manager   = manager
        self.scene     = scene
        self._building = False   # suppress signals while populating
        self._build_ui()
        self.populate()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header row
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("<b>User Layers</b>"))
        hdr.addStretch()
        add_btn = QPushButton("＋")
        add_btn.setFixedSize(24, 24)
        add_btn.setToolTip("Add new layer")
        add_btn.clicked.connect(self._add_layer)
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(24, 24)
        del_btn.setToolTip("Delete selected layer")
        del_btn.clicked.connect(self._delete_layer)
        hdr.addWidget(add_btn)
        hdr.addWidget(del_btn)
        layout.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["👁", "🔒", "Color", "Name", "LW"])
        self.table.horizontalHeader().setSectionResizeMode(
            _COL_NAME, QHeaderView.ResizeMode.Stretch
        )
        for col in (_COL_VIS, _COL_LOCK, _COL_COLOR, _COL_LW):
            self.table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table)

        # Assign button
        assign_btn = QPushButton("Assign Selection → Active Layer")
        assign_btn.setToolTip("Move selected scene items onto the active layer")
        assign_btn.clicked.connect(self._assign_selection)
        layout.addWidget(assign_btn)

    # ── Populate ─────────────────────────────────────────────────────────────

    def populate(self):
        """Rebuild the table from manager.layers (preserves selection row)."""
        self._building = True
        self.table.setRowCount(0)
        for lyr in self.manager.layers:
            self._append_row(lyr)
        self._building = False
        self._highlight_active()

    def _append_row(self, lyr: UserLayer):
        row = self.table.rowCount()
        self.table.insertRow(row)

        # Visibility checkbox
        vis = QTableWidgetItem()
        vis.setFlags(Qt.ItemFlag.ItemIsEnabled |
                     Qt.ItemFlag.ItemIsUserCheckable |
                     Qt.ItemFlag.ItemIsSelectable)
        vis.setCheckState(
            Qt.CheckState.Checked if lyr.visible else Qt.CheckState.Unchecked
        )
        vis.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, _COL_VIS, vis)

        # Lock checkbox
        lock = QTableWidgetItem()
        lock.setFlags(Qt.ItemFlag.ItemIsEnabled |
                      Qt.ItemFlag.ItemIsUserCheckable |
                      Qt.ItemFlag.ItemIsSelectable)
        lock.setCheckState(
            Qt.CheckState.Checked if lyr.locked else Qt.CheckState.Unchecked
        )
        lock.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, _COL_LOCK, lock)

        # Color swatch (double-click to edit)
        color_it = QTableWidgetItem("  ")
        color_it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        color_it.setBackground(QBrush(QColor(lyr.color)))
        self.table.setItem(row, _COL_COLOR, color_it)

        # Name (editable unless "0")
        name_it = QTableWidgetItem(lyr.name)
        if lyr.name == "0":
            name_it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.table.setItem(row, _COL_NAME, name_it)

        # Lineweight
        lw_it = QTableWidgetItem(f"{lyr.lineweight:.2f}")
        self.table.setItem(row, _COL_LW, lw_it)

    # ── Active-layer highlight ────────────────────────────────────────────────

    def _highlight_active(self):
        active = self.manager.active_layer
        bold   = QFont(); bold.setBold(True)
        normal = QFont()
        for row in range(self.table.rowCount()):
            name_it = self.table.item(row, _COL_NAME)
            if name_it is None:
                continue
            is_active = name_it.text() == active
            for col in range(self.table.columnCount()):
                it = self.table.item(row, col)
                if it:
                    it.setFont(bold if is_active else normal)

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._building:
            return
        row = item.row()
        col = item.column()
        lyr = self._layer_at_row(row)
        if lyr is None:
            return

        if col == _COL_VIS:
            lyr.visible = (item.checkState() == Qt.CheckState.Checked)
            self._apply_and_emit()

        elif col == _COL_LOCK:
            lyr.locked = (item.checkState() == Qt.CheckState.Checked)
            self._apply_and_emit()

        elif col == _COL_NAME:
            new_name = item.text().strip()
            if new_name and new_name != lyr.name:
                ok = self.manager.rename_layer(lyr.name, new_name,
                                               self._all_scene_items())
                if not ok:
                    self._building = True
                    item.setText(lyr.name)
                    self._building = False
                else:
                    self._highlight_active()
                    self.layersChanged.emit()

        elif col == _COL_LW:
            try:
                lw = float(item.text())
                lyr.lineweight = max(0.0, lw)
            except ValueError:
                self._building = True
                item.setText(f"{lyr.lineweight:.2f}")
                self._building = False

    def _on_double_click(self, row: int, col: int):
        if col != _COL_COLOR:
            return
        lyr = self._layer_at_row(row)
        if lyr is None:
            return
        color = QColorDialog.getColor(QColor(lyr.color), self, "Layer Colour")
        if color.isValid():
            lyr.color = color.name()
            self._building = True
            it = self.table.item(row, _COL_COLOR)
            if it:
                it.setBackground(QBrush(color))
            self._building = False
            self.layersChanged.emit()

    def _on_selection_changed(self):
        rows = self.table.selectedItems()
        if not rows:
            return
        lyr = self._layer_at_row(rows[0].row())
        if lyr:
            self.manager.active_layer = lyr.name
            self._highlight_active()
            self.activeLayerChanged.emit(lyr.name)

    # ── Buttons ───────────────────────────────────────────────────────────────

    def _add_layer(self):
        lyr = self.manager.add_layer()
        self._building = True
        self._append_row(lyr)
        self._building = False
        self.layersChanged.emit()

    def _delete_layer(self):
        row = self.table.currentRow()
        lyr = self._layer_at_row(row)
        if lyr is None:
            return
        if lyr.name == "0":
            QMessageBox.information(self, "Layer 0",
                                    "Layer '0' cannot be deleted.")
            return
        reply = QMessageBox.question(
            self, "Delete Layer",
            f"Delete layer '{lyr.name}'?\n"
            "Items on this layer will be moved to layer '0'.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        for item in self._all_scene_items():
            if getattr(item, "user_layer", None) == lyr.name:
                item.user_layer = "0"
        self.manager.remove_layer(lyr.name)
        self.populate()
        self.layersChanged.emit()

    def _assign_selection(self):
        if self.scene is None:
            return
        active = self.manager.active_layer
        for item in self.scene.selectedItems():
            if hasattr(item, "user_layer"):
                item.user_layer = active
        self.layersChanged.emit()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _layer_at_row(self, row: int) -> UserLayer | None:
        it = self.table.item(row, _COL_NAME)
        if it is None:
            return None
        return self.manager.get(it.text())

    def _all_scene_items(self) -> list:
        if self.scene is None:
            return []
        return (list(self.scene.sprinkler_system.nodes) +
                list(self.scene.sprinkler_system.pipes))

    def _apply_and_emit(self):
        if self.scene:
            self.manager.apply_to_scene(self.scene)
        self.layersChanged.emit()
