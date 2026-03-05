"""
level_manager.py
================
Floor-level system for multi-story building support.

Each drawing item carries a ``level`` string attribute naming the floor
level it belongs to.  Switching the active level hides entities on other
levels.

Classes
-------
Level           — dataclass for one level's properties
LevelManager    — ordered list of levels + active-level tracking
LevelWidget     — QWidget dock panel (table UI + add/delete buttons)
"""

from __future__ import annotations

from dataclasses import dataclass
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QMessageBox,
    QAbstractItemView, QFrame, QLabel, QGraphicsItem,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Level:
    name:         str
    elevation:    float = 0.0       # mm, relative to project datum
    view_top:     float = 2000.0    # mm above elevation (future use)
    view_bottom:  float = -1000.0   # mm below elevation (future use)

    def to_dict(self) -> dict:
        return {
            "name":        self.name,
            "elevation":   self.elevation,
            "view_top":    self.view_top,
            "view_bottom": self.view_bottom,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Level":
        return cls(
            name        = d["name"],
            elevation   = d.get("elevation",   0.0),
            view_top    = d.get("view_top",    2000.0),
            view_bottom = d.get("view_bottom", -1000.0),
        )


# Defaults shipped with every new document
DEFAULT_LEVELS: list[Level] = [
    Level("Level 1", elevation=0.0),
]


# ─────────────────────────────────────────────────────────────────────────────
# Manager (pure data, no Qt)
# ─────────────────────────────────────────────────────────────────────────────

class LevelManager:
    """Manages the ordered list of floor levels and the active level."""

    def __init__(self):
        self._levels: list[Level] = [
            Level(**vars(l)) for l in DEFAULT_LEVELS
        ]
        self._active: str = "Level 1"

    # ── Level list API ────────────────────────────────────────────────────────

    @property
    def levels(self) -> list[Level]:
        return list(self._levels)

    @property
    def active_level(self) -> str:
        return self._active

    @active_level.setter
    def active_level(self, name: str):
        if self.get(name) is not None:
            self._active = name

    def get(self, name: str) -> Level | None:
        for lvl in self._levels:
            if lvl.name == name:
                return lvl
        return None

    def add_level(self, name: str | None = None,
                  elevation: float = 0.0) -> Level:
        if name is None or self.get(name) is not None:
            i = 1
            while self.get(f"Level {i}") is not None:
                i += 1
            name = f"Level {i}"
        lvl = Level(name, elevation=elevation)
        self._levels.append(lvl)
        return lvl

    def remove_level(self, name: str):
        """Delete a level.  The last remaining level cannot be deleted."""
        if len(self._levels) <= 1:
            return
        self._levels = [l for l in self._levels if l.name != name]
        if self._active == name:
            self._active = self._levels[0].name

    def rename_level(self, old_name: str, new_name: str, items) -> bool:
        """Rename a level and update all items that referenced the old name."""
        if not new_name or (self.get(new_name) is not None
                           and new_name != old_name):
            return False
        lvl = self.get(old_name)
        if lvl is None:
            return False
        lvl.name = new_name
        if self._active == old_name:
            self._active = new_name
        for item in items:
            if getattr(item, "level", None) == old_name:
                item.level = new_name
        return True

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_list(self) -> list[dict]:
        return [l.to_dict() for l in self._levels]

    def from_list(self, data: list[dict]):
        self._levels = [Level.from_dict(d) for d in data]
        # Ensure at least one level exists
        if not self._levels:
            self._levels = [Level(**vars(l)) for l in DEFAULT_LEVELS]
        # Reset active to first level if current active no longer exists
        if self.get(self._active) is None:
            self._active = self._levels[0].name

    def reset(self):
        """Reset to default levels (used on new file)."""
        self._levels = [Level(**vars(l)) for l in DEFAULT_LEVELS]
        self._active = "Level 1"

    # ── Apply to scene ────────────────────────────────────────────────────────

    def apply_to_scene(self, scene):
        """Show/hide entities based on active level, then re-apply layer
        visibility so that both level AND layer filtering are respected."""
        active = self._active

        def _set_level_vis(item):
            lvl_name = getattr(item, "level", "Level 1")
            vis = (lvl_name == active)
            item.setVisible(vis)
            if not vis:
                item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False,
                )

        # ── Sprinkler system ──────────────────────────────────────────────
        for node in scene.sprinkler_system.nodes:
            _set_level_vis(node)

        for pipe in scene.sprinkler_system.pipes:
            _set_level_vis(pipe)

        # ── Construction / draw geometry ──────────────────────────────────
        for item in getattr(scene, "_construction_lines", []):
            _set_level_vis(item)

        for item in getattr(scene, "_polylines", []):
            _set_level_vis(item)

        for item in getattr(scene, "_draw_lines", []):
            _set_level_vis(item)

        for item in getattr(scene, "_draw_rects", []):
            _set_level_vis(item)

        for item in getattr(scene, "_draw_circles", []):
            _set_level_vis(item)

        for item in getattr(scene, "_draw_arcs", []):
            _set_level_vis(item)

        # ── Gridlines ─────────────────────────────────────────────────────
        for item in getattr(scene, "_gridlines", []):
            _set_level_vis(item)

        # ── Annotations ───────────────────────────────────────────────────
        annotations = getattr(scene, "annotations", None)
        if annotations is not None:
            for dim in getattr(annotations, "dimensions", []):
                _set_level_vis(dim)
            for note in getattr(annotations, "notes", []):
                _set_level_vis(note)

        # ── Hatches ───────────────────────────────────────────────────────
        for item in getattr(scene, "_hatch_items", []):
            _set_level_vis(item)

        # ── Water supply ──────────────────────────────────────────────────
        ws = getattr(scene, "water_supply_node", None)
        if ws is not None:
            _set_level_vis(ws)

        # ── Re-apply user-layer visibility on top ─────────────────────────
        ulm = getattr(scene, "_user_layer_manager", None)
        if ulm is not None:
            ulm.apply_to_scene(scene)


# ─────────────────────────────────────────────────────────────────────────────
# Table column indices
# ─────────────────────────────────────────────────────────────────────────────

_COL_NAME  = 0
_COL_ELEV  = 1


# ─────────────────────────────────────────────────────────────────────────────
# Widget
# ─────────────────────────────────────────────────────────────────────────────

class LevelWidget(QWidget):
    """
    Dock panel showing the floor level table.

    Signals
    -------
    activeLevelChanged(str)  — emitted when the active level changes
    levelsChanged()          — emitted after any structural change so the
                               scene can be refreshed
    """

    activeLevelChanged = pyqtSignal(str)
    levelsChanged      = pyqtSignal()

    def __init__(self, manager: LevelManager, scene=None, parent=None):
        super().__init__(parent)
        self.manager   = manager
        self.scene     = scene
        self._building = False   # suppress signals while populating
        self._build_ui()
        self.populate()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header row
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("<b>Levels</b>"))
        hdr.addStretch()
        add_btn = QPushButton("+")
        add_btn.setFixedSize(24, 24)
        add_btn.setToolTip("Add new level")
        add_btn.clicked.connect(self._add_level)
        del_btn = QPushButton("-")
        del_btn.setFixedSize(24, 24)
        del_btn.setToolTip("Delete selected level")
        del_btn.clicked.connect(self._delete_level)
        hdr.addWidget(add_btn)
        hdr.addWidget(del_btn)
        layout.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Name", "Elevation (mm)"])
        self.table.horizontalHeader().setSectionResizeMode(
            _COL_NAME, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            _COL_ELEV, QHeaderView.ResizeMode.Stretch
        )
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table)

        # Assign button
        assign_btn = QPushButton("Assign Selection -> Active Level")
        assign_btn.setToolTip(
            "Move selected scene items onto the active level"
        )
        assign_btn.clicked.connect(self._assign_selection)
        layout.addWidget(assign_btn)

    # ── Populate ──────────────────────────────────────────────────────────────

    def populate(self):
        """Rebuild the table from manager.levels."""
        self._building = True
        self.table.setRowCount(0)
        for lvl in self.manager.levels:
            self._append_row(lvl)
        self._building = False
        self._highlight_active()

    def _append_row(self, lvl: Level):
        row = self.table.rowCount()
        self.table.insertRow(row)

        # Name
        name_it = QTableWidgetItem(lvl.name)
        self.table.setItem(row, _COL_NAME, name_it)

        # Elevation
        elev_it = QTableWidgetItem(str(lvl.elevation))
        self.table.setItem(row, _COL_ELEV, elev_it)

    # ── Active-level highlight ────────────────────────────────────────────────

    def _highlight_active(self):
        active = self.manager.active_level
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
        lvl = self._level_at_row(row)
        if lvl is None:
            return

        if col == _COL_NAME:
            new_name = item.text().strip()
            if new_name and new_name != lvl.name:
                ok = self.manager.rename_level(
                    lvl.name, new_name, self._all_scene_items()
                )
                if not ok:
                    self._building = True
                    item.setText(lvl.name)
                    self._building = False
                else:
                    self._highlight_active()
                    self.levelsChanged.emit()
                    if self.manager.active_level == new_name:
                        self.activeLevelChanged.emit(new_name)

        elif col == _COL_ELEV:
            try:
                new_elev = float(item.text())
            except (ValueError, TypeError):
                self._building = True
                item.setText(str(lvl.elevation))
                self._building = False
                return
            lvl.elevation = new_elev
            self.levelsChanged.emit()

    def _on_selection_changed(self):
        rows = self.table.selectedItems()
        if not rows:
            return
        lvl = self._level_at_row(rows[0].row())
        if lvl:
            self.manager.active_level = lvl.name
            self._highlight_active()
            self.activeLevelChanged.emit(lvl.name)

    # ── Buttons ───────────────────────────────────────────────────────────────

    def _add_level(self):
        lvl = self.manager.add_level()
        self._building = True
        self._append_row(lvl)
        self._building = False
        self.levelsChanged.emit()

    def _delete_level(self):
        row = self.table.currentRow()
        lvl = self._level_at_row(row)
        if lvl is None:
            return
        if len(self.manager.levels) <= 1:
            QMessageBox.information(
                self, "Level",
                "The last remaining level cannot be deleted."
            )
            return
        reply = QMessageBox.question(
            self, "Delete Level",
            f"Delete level '{lvl.name}'?\n"
            "Items on this level will be moved to the first remaining level.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        # Reassign entities to first remaining level (that isn't being deleted)
        fallback = None
        for l in self.manager.levels:
            if l.name != lvl.name:
                fallback = l.name
                break
        if fallback:
            for item in self._all_scene_items():
                if getattr(item, "level", None) == lvl.name:
                    item.level = fallback
        self.manager.remove_level(lvl.name)
        self.populate()
        self.levelsChanged.emit()
        self.activeLevelChanged.emit(self.manager.active_level)

    def _assign_selection(self):
        if self.scene is None:
            return
        active = self.manager.active_level
        for item in self.scene.selectedItems():
            if hasattr(item, "level"):
                item.level = active
        self.levelsChanged.emit()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _level_at_row(self, row: int) -> Level | None:
        it = self.table.item(row, _COL_NAME)
        if it is None:
            return None
        return self.manager.get(it.text())

    def _all_scene_items(self) -> list:
        """Return all scene items that may carry a level attribute."""
        if self.scene is None:
            return []
        items = (list(self.scene.sprinkler_system.nodes) +
                 list(self.scene.sprinkler_system.pipes))
        items += getattr(self.scene, "_construction_lines", [])
        items += getattr(self.scene, "_polylines", [])
        items += getattr(self.scene, "_draw_lines", [])
        items += getattr(self.scene, "_draw_rects", [])
        items += getattr(self.scene, "_draw_circles", [])
        items += getattr(self.scene, "_draw_arcs", [])
        items += getattr(self.scene, "_gridlines", [])
        items += getattr(self.scene, "_hatch_items", [])
        ann = getattr(self.scene, "annotations", None)
        if ann:
            items += getattr(ann, "dimensions", [])
            items += getattr(ann, "notes", [])
        ws = getattr(self.scene, "water_supply_node", None)
        if ws is not None:
            items.append(ws)
        return items
