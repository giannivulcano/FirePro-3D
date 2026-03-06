"""
level_manager.py
================
Floor-level system for multi-story building support.

Each drawing item carries a ``level`` string attribute naming the floor
level it belongs to.  Switching the active level hides entities on other
levels, with optional faded display for context.

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
    QAbstractItemView, QLabel, QGraphicsItem, QComboBox, QMenu,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
import theme as th


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

FADE_OPACITY = 0.25  # opacity for faded levels

# Display mode options (stored in Level.display_mode)
DISPLAY_MODES = ["Auto", "Hidden", "Faded", "Visible"]


@dataclass
class Level:
    name:         str
    elevation:    float = 0.0       # ft, relative to project datum
    view_top:     float = 2000.0    # mm above elevation (future use)
    view_bottom:  float = -1000.0   # mm below elevation (future use)
    display_mode: str   = "Auto"    # Auto | Hidden | Faded | Visible

    def to_dict(self) -> dict:
        return {
            "name":         self.name,
            "elevation":    self.elevation,
            "view_top":     self.view_top,
            "view_bottom":  self.view_bottom,
            "display_mode": self.display_mode,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Level":
        return cls(
            name         = d["name"],
            elevation    = d.get("elevation",    0.0),
            view_top     = d.get("view_top",     2000.0),
            view_bottom  = d.get("view_bottom",  -1000.0),
            display_mode = d.get("display_mode", "Auto"),
        )


# Defaults shipped with every new document
DEFAULT_LEVELS: list[Level] = [
    Level("Level 1", elevation=0.0),
    Level("Level 2", elevation=10.0),
    Level("Level 3", elevation=20.0),
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

    # ── Elevation helpers ───────────────────────────────────────────────────

    def update_elevations(self, scene):
        """Recompute z_pos for all nodes: z_pos = level.elevation + z_offset."""
        from node import Node
        lvl_map = {l.name: l for l in self._levels}
        for node in scene.sprinkler_system.nodes:
            lvl = lvl_map.get(getattr(node, "level", "Level 1"))
            level_elev = lvl.elevation if lvl else 0.0
            node.z_pos = level_elev + node.z_offset
            node._properties.get("Elevation Offset", {})["value"] = str(node.z_offset)
            if node.has_sprinkler():
                sp = node.sprinkler._properties.get("Elevation Offset")
                if sp:
                    sp["value"] = str(node.z_offset)

    # ── Apply to scene ────────────────────────────────────────────────────────

    def apply_to_scene(self, scene):
        """Show/hide/fade entities based on active level and display_mode,
        then re-apply layer visibility so both level AND layer filtering
        are respected."""
        active = self._active
        lvl_map = {l.name: l for l in self._levels}

        def _set_level_vis(item):
            lvl_name = getattr(item, "level", "Level 1")
            lvl_def = lvl_map.get(lvl_name)
            mode = lvl_def.display_mode if lvl_def else "Auto"

            # "Hidden" always hides, even if active
            if mode == "Hidden":
                item.setVisible(False)
                item.setOpacity(1.0)
                return

            if lvl_name == active:
                # Active level — fully visible and selectable
                item.setVisible(True)
                item.setOpacity(1.0)
                item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True,
                )
                return

            # Non-active level — check display_mode
            if mode == "Faded":
                item.setVisible(True)
                item.setOpacity(FADE_OPACITY)
                item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False,
                )
            elif mode == "Visible":
                item.setVisible(True)
                item.setOpacity(1.0)
                item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False,
                )
            else:
                # "Auto" when not active — hidden
                item.setVisible(False)
                item.setOpacity(1.0)

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

        # ── Walls ─────────────────────────────────────────────────────────
        for item in getattr(scene, "_walls", []):
            _set_level_vis(item)
            # Also handle openings belonging to this wall
            for op in getattr(item, "openings", []):
                _set_level_vis(op)

        # ── Floor slabs ──────────────────────────────────────────────────
        for item in getattr(scene, "_floor_slabs", []):
            _set_level_vis(item)

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

        # ── Fixup: restore faded opacity for items that survived layer
        #    filtering (ulm.apply_to_scene may have reset opacity) ─────────
        faded_levels = {l.name for l in self._levels
                        if l.display_mode == "Faded" and l.name != active}
        if faded_levels:
            self._reapply_fade(scene, faded_levels)

    def _reapply_fade(self, scene, faded_levels: set[str]):
        """Re-apply FADE_OPACITY to items on faded levels that are still
        visible after user-layer filtering."""
        def _fix(item):
            if not item.isVisible():
                return
            if getattr(item, "level", "Level 1") in faded_levels:
                item.setOpacity(FADE_OPACITY)

        for node in scene.sprinkler_system.nodes:
            _fix(node)
        for pipe in scene.sprinkler_system.pipes:
            _fix(pipe)
        for item in getattr(scene, "_construction_lines", []):
            _fix(item)
        for item in getattr(scene, "_polylines", []):
            _fix(item)
        for item in getattr(scene, "_draw_lines", []):
            _fix(item)
        for item in getattr(scene, "_draw_rects", []):
            _fix(item)
        for item in getattr(scene, "_draw_circles", []):
            _fix(item)
        for item in getattr(scene, "_draw_arcs", []):
            _fix(item)
        for item in getattr(scene, "_gridlines", []):
            _fix(item)
        annotations = getattr(scene, "annotations", None)
        if annotations is not None:
            for dim in getattr(annotations, "dimensions", []):
                _fix(dim)
            for note in getattr(annotations, "notes", []):
                _fix(note)
        for item in getattr(scene, "_hatch_items", []):
            _fix(item)
        ws = getattr(scene, "water_supply_node", None)
        if ws is not None:
            _fix(ws)


# ─────────────────────────────────────────────────────────────────────────────
# Table column indices
# ─────────────────────────────────────────────────────────────────────────────

_COL_NAME    = 0
_COL_ELEV    = 1
_COL_DISPLAY = 2


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
    duplicateLevel     = pyqtSignal(str, str)   # (source_level, new_level)

    def __init__(self, manager: LevelManager, scene=None, parent=None):
        super().__init__(parent)
        self.manager   = manager
        self.scene     = scene
        self._building = False   # suppress signals while populating
        self._build_ui()
        self.populate()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        _t = th.detect()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header — matches ProjectBrowser / ModelBrowser / PropertyManager
        hdr = QLabel("Levels")
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
        add_btn.setToolTip("Add new level")
        add_btn.setStyleSheet(_btn_ss)
        add_btn.clicked.connect(self._add_level)
        del_btn = QPushButton("-")
        del_btn.setFixedSize(24, 24)
        del_btn.setToolTip("Delete selected level")
        del_btn.setStyleSheet(_btn_ss)
        del_btn.clicked.connect(self._delete_level)
        dup_btn = QPushButton("\u29C9")
        dup_btn.setFixedSize(24, 24)
        dup_btn.setToolTip("Duplicate level (copy all entities to new level)")
        dup_btn.setStyleSheet(_btn_ss)
        dup_btn.clicked.connect(self._duplicate_level)
        toolbar.addWidget(add_btn)
        toolbar.addWidget(del_btn)
        toolbar.addWidget(dup_btn)
        layout.addLayout(toolbar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Elevation (ft)", "Display"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            _COL_NAME, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            _COL_ELEV, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.setColumnWidth(_COL_DISPLAY, 100)
        self.table.verticalHeader().setDefaultSectionSize(24)
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
        self.table.setStyleSheet(
            f"QTableWidget {{ background: {_t.bg_raised}; color: {_t.text_primary}; "
            f"border: 1px solid {_t.border_subtle}; }}"
            f"QTableWidget::item:selected {{ background: {_t.accent_primary}; color: #ffffff; }}"
        )
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
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

        # Display mode combo
        combo = QComboBox()
        combo.setFixedHeight(20)
        combo.addItems(DISPLAY_MODES)
        idx = combo.findText(lvl.display_mode)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.currentIndexChanged.connect(
            lambda _idx, r=row: self._on_display_combo_changed(r, _idx)
        )
        self.table.setCellWidget(row, _COL_DISPLAY, combo)

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
            for col in (_COL_NAME, _COL_ELEV):
                it = self.table.item(row, col)
                if it:
                    it.setFont(bold if is_active else normal)
            # Update display combo — always show full options
            combo = self.table.cellWidget(row, _COL_DISPLAY)
            if combo and isinstance(combo, QComboBox):
                combo.blockSignals(True)
                # Restore full options if previously locked to "Active"
                if combo.count() == 1 and combo.itemText(0) == "Active":
                    lvl = self._level_at_row(row)
                    combo.clear()
                    combo.addItems(DISPLAY_MODES)
                    if lvl:
                        idx = combo.findText(lvl.display_mode)
                        if idx >= 0:
                            combo.setCurrentIndex(idx)
                combo.setEnabled(True)
                combo.blockSignals(False)

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
            if self.scene:
                self.manager.update_elevations(self.scene)
            self.levelsChanged.emit()

    def _on_display_combo_changed(self, row: int, idx: int):
        """Handle display mode combo selection."""
        if self._building:
            return
        lvl = self._level_at_row(row)
        if lvl is None or idx < 0 or idx >= len(DISPLAY_MODES):
            return
        lvl.display_mode = DISPLAY_MODES[idx]
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

    def _duplicate_level(self):
        """Duplicate the currently selected level (create new + copy entities)."""
        row = self.table.currentRow()
        lvl = self._level_at_row(row)
        if lvl is None:
            return
        self._duplicate_level_from(lvl)

    def _duplicate_level_from(self, source_lvl: Level):
        """Create a new level and emit signal to copy all entities from source."""
        new_lvl = self.manager.add_level(elevation=source_lvl.elevation)
        self._building = True
        self._append_row(new_lvl)
        self._building = False
        self.duplicateLevel.emit(source_lvl.name, new_lvl.name)
        self.levelsChanged.emit()

    def _on_table_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        lvl = self._level_at_row(row)
        if lvl is None:
            return
        menu = QMenu(self)
        dup_action = menu.addAction("Duplicate Level...")
        dup_action.triggered.connect(lambda: self._duplicate_level_from(lvl))
        menu.exec(self.table.viewport().mapToGlobal(pos))

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
