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
    QAbstractItemView, QLabel, QComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QFont
import theme as th
from constants import DEFAULT_USER_LAYER


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
    UserLayer(DEFAULT_USER_LAYER,      "#ffffff", 0.35, True,  False, True),
    UserLayer("Underlay",     "#aaaaaa", 0.18, True,  False, False),
    UserLayer("Annotations",  "#cccccc", 0.25, True,  False, True),
    UserLayer("Gridlines",    "#888888", 0.25, True,  False, True),
]


# Named lineweight options:  (display label, mm value, cosmetic screen px)
LINEWEIGHT_OPTIONS: list[tuple[str, float, float]] = [
    ("Very Thin (0.18 mm)", 0.18, 1.0),
    ("Thin (0.25 mm)",      0.25, 1.5),
    ("Medium (0.35 mm)",    0.35, 2.0),
    ("Thick (0.50 mm)",     0.50, 3.0),
    ("Very Thick (0.70 mm)", 0.70, 4.0),
]

def lw_mm_to_cosmetic_px(mm: float) -> float:
    """Map a layer lineweight (mm) to the nearest named cosmetic px value."""
    best_px = 2.0
    best_dist = 999.0
    for _, lw_mm, px in LINEWEIGHT_OPTIONS:
        d = abs(mm - lw_mm)
        if d < best_dist:
            best_dist = d
            best_px = px
    return best_px

def lw_mm_to_label(mm: float) -> str:
    """Return the display label for the closest named lineweight."""
    best_label = LINEWEIGHT_OPTIONS[2][0]  # Medium fallback
    best_dist = 999.0
    for label, lw_mm, _ in LINEWEIGHT_OPTIONS:
        d = abs(mm - lw_mm)
        if d < best_dist:
            best_dist = d
            best_label = label
    return best_label


# ─────────────────────────────────────────────────────────────────────────────
# Manager (pure data, no Qt)
# ─────────────────────────────────────────────────────────────────────────────

class UserLayerManager:
    """Manages the ordered list of user layers and the active layer."""

    def __init__(self):
        self._layers: list[UserLayer] = [
            UserLayer(**vars(l)) for l in DEFAULT_LAYERS
        ]
        self._active: str = DEFAULT_USER_LAYER

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
        """Delete a layer.  The first layer cannot be deleted."""
        if name == self._layers[0].name:
            return
        self._layers = [l for l in self._layers if l.name != name]
        if self._active == name:
            self._active = self._layers[0].name

    def rename_layer(self, old_name: str, new_name: str, items) -> bool:
        """Rename a layer and update all items that referenced the old name."""
        if old_name == self._layers[0].name:
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
        """Show/hide, lock/unlock, and re-colour drawing items by layer."""
        from PyQt6.QtWidgets import QGraphicsItem
        from PyQt6.QtGui import QPen, QColor as _QColor

        # Build lookup: layer name → UserLayer
        lyr_map = {l.name: l for l in self._layers}

        def _apply_item(item, lyr_name: str):
            """Apply visibility, lock, colour and lineweight to a geometry item.
            Only HIDE items when the layer is hidden — never un-hide items
            that were already hidden by the level manager."""
            ldef = lyr_map.get(lyr_name)
            if ldef is None:
                return
            if not ldef.visible:
                item.setVisible(False)
            if not ldef.visible or ldef.locked:
                item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False,
                )
            # Apply layer colour + lineweight to items that have a pen
            if callable(getattr(item, "pen", None)) and callable(getattr(item, "setPen", None)):
                pen = QPen(item.pen())
                pen.setColor(_QColor(ldef.color))
                # Apply lineweight: cosmetic pens use screen px, non-cosmetic use mm
                if pen.isCosmetic():
                    pen.setWidthF(lw_mm_to_cosmetic_px(ldef.lineweight))
                else:
                    pen.setWidthF(ldef.lineweight)
                item.setPen(pen)

        # ── Sprinkler system (nodes + pipes — visibility/lock only) ───────────
        for node in scene.sprinkler_system.nodes:
            lyr = getattr(node, "user_layer", "0")
            ldef = lyr_map.get(lyr)
            if ldef:
                if not ldef.visible:
                    node.setVisible(False)
                if not ldef.visible or ldef.locked:
                    node.setFlag(
                        QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False,
                    )

        for pipe in scene.sprinkler_system.pipes:
            lyr = getattr(pipe, "user_layer", "0")
            ldef = lyr_map.get(lyr)
            if ldef:
                if not ldef.visible:
                    pipe.setVisible(False)
                if not ldef.visible or ldef.locked:
                    pipe.setFlag(
                        QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False,
                    )

        # ── Construction / draw geometry (colour + lineweight applied) ────────
        for item in getattr(scene, "_construction_lines", []):
            _apply_item(item, getattr(item, "user_layer", "0"))

        for item in getattr(scene, "_polylines", []):
            _apply_item(item, getattr(item, "user_layer", "0"))

        for item in getattr(scene, "_draw_lines", []):
            _apply_item(item, getattr(item, "user_layer", "0"))

        for item in getattr(scene, "_draw_rects", []):
            _apply_item(item, getattr(item, "user_layer", "0"))

        for item in getattr(scene, "_draw_circles", []):
            _apply_item(item, getattr(item, "user_layer", "0"))

        for item in getattr(scene, "_draw_arcs", []):
            _apply_item(item, getattr(item, "user_layer", "0"))

        # ── Annotations (dimensions, notes, hatches) ─────────────────────────
        annotations = getattr(scene, "annotations", None)
        if annotations is not None:
            for dim in getattr(annotations, "dimensions", []):
                lyr_name = getattr(dim, "user_layer", DEFAULT_USER_LAYER)
                ldef = lyr_map.get(lyr_name)
                if ldef is None:
                    continue
                if not ldef.visible:
                    dim.setVisible(False)
                if not ldef.visible or ldef.locked:
                    dim.setFlag(
                        QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False,
                    )
                # Apply colour to dim pen and child items
                c = _QColor(ldef.color)
                dim._dim_pen.setColor(c)
                dim.setPen(dim._dim_pen)
                dim.label.setDefaultTextColor(c)
                for child in (dim.tick1, dim.tick2, dim.witness1, dim.witness2):
                    if child:
                        child.setPen(dim._dim_pen)
            for note in getattr(annotations, "notes", []):
                lyr_name = getattr(note, "user_layer", DEFAULT_USER_LAYER)
                ldef = lyr_map.get(lyr_name)
                if ldef is None:
                    continue
                if not ldef.visible:
                    note.setVisible(False)
                if not ldef.visible or ldef.locked:
                    note.setFlag(
                        QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False,
                    )
                note.setDefaultTextColor(_QColor(ldef.color))

        for item in getattr(scene, "_hatch_items", []):
            lyr_name = getattr(item, "user_layer", DEFAULT_USER_LAYER)
            ldef = lyr_map.get(lyr_name)
            if ldef is None:
                continue
            if not ldef.visible:
                item.setVisible(False)
            if not ldef.visible or ldef.locked:
                item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False,
                )
            item._colour = ldef.color
            item.update()


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
        _t = th.detect()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header — matches ProjectBrowser / ModelBrowser / PropertyManager
        hdr = QLabel("User Layers")
        hdr.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        f = QFont()
        f.setBold(True)
        f.setPointSize(9)
        hdr.setFont(f)
        hdr.setStyleSheet(
            f"color: {_t.text_primary}; "
            f"background: {_t.bg_raised}; "
            f"padding: 4px; "
            f"border-radius: 3px;"
        )
        layout.addWidget(hdr)

        # Toolbar row
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.addStretch()
        _btn_ss = (
            f"QPushButton {{ background: {_t.bg_raised}; "
            f"border: 1px solid {_t.border_subtle}; "
            f"border-radius: 2px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {_t.btn_hover}; }}"
        )
        add_btn = QPushButton("+")
        add_btn.setFixedSize(24, 24)
        add_btn.setToolTip("Add new layer")
        add_btn.setStyleSheet(_btn_ss)
        add_btn.clicked.connect(self._add_layer)
        del_btn = QPushButton("\u2715")
        del_btn.setFixedSize(24, 24)
        del_btn.setToolTip("Delete selected layer")
        del_btn.setStyleSheet(_btn_ss)
        del_btn.clicked.connect(self._delete_layer)
        toolbar.addWidget(add_btn)
        toolbar.addWidget(del_btn)
        layout.addLayout(toolbar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["👁", "🔒", "Color", "Name", "LW"])
        self.table.horizontalHeader().setSectionResizeMode(
            _COL_NAME, QHeaderView.ResizeMode.Stretch
        )
        for col in (_COL_VIS, _COL_LOCK, _COL_COLOR):
            self.table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        self.table.setColumnWidth(_COL_LW, 150)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.table.setStyleSheet(
            f"QTableWidget {{ background: {_t.bg_raised}; color: {_t.text_primary}; "
            f"border: 1px solid {_t.border_subtle}; }}"
            f"QTableWidget::item:selected {{ background: {_t.accent_primary}; color: #ffffff; }}"
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

        # Lineweight — QComboBox with named options
        lw_combo = QComboBox()
        lw_combo.setFixedHeight(20)
        for label, mm, _px in LINEWEIGHT_OPTIONS:
            lw_combo.addItem(label, mm)
        # Select the closest match
        best_idx = 0
        best_dist = 999.0
        for i, (_, mm, _px) in enumerate(LINEWEIGHT_OPTIONS):
            d = abs(lyr.lineweight - mm)
            if d < best_dist:
                best_dist = d
                best_idx = i
        lw_combo.setCurrentIndex(best_idx)
        lw_combo.currentIndexChanged.connect(
            lambda idx, r=row: self._on_lw_combo_changed(r, idx)
        )
        self.table.setCellWidget(row, _COL_LW, lw_combo)

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
                    # Sync scene active_user_layer if the renamed layer was active
                    if self.manager.active_layer == new_name:
                        self.activeLayerChanged.emit(new_name)

    def _on_lw_combo_changed(self, row: int, idx: int):
        """Handle lineweight combo selection in a table row."""
        if self._building:
            return
        lyr = self._layer_at_row(row)
        if lyr is None or idx < 0 or idx >= len(LINEWEIGHT_OPTIONS):
            return
        _, mm, _ = LINEWEIGHT_OPTIONS[idx]
        lyr.lineweight = mm
        self._apply_and_emit()

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
                item.user_layer = self.manager._layers[0].name
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
