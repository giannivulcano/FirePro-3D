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
    QStyledItemDelegate,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from dimension_edit import DimensionEdit
import theme as th


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

FADE_OPACITY = 0.25  # opacity for faded levels

from constants import DEFAULT_LEVEL, DEFAULT_CEILING_OFFSET_MM
# Display mode options (stored in Level.display_mode)
DISPLAY_MODES = ["Auto", "Hidden", "Faded", "Visible"]


@dataclass
class Level:
    name:         str
    elevation:    float = 0.0       # mm, relative to project datum
    view_top:     float = 2000.0    # mm above elevation (future use)
    view_bottom:  float = -1000.0   # mm below elevation (future use)
    display_mode: str   = "Auto"    # Auto | Hidden | Faded | Visible

    def to_dict(self) -> dict:
        return {
            "name":         self.name,
            "elevation_mm": self.elevation,
            "view_top":     self.view_top,
            "view_bottom":  self.view_bottom,
            "display_mode": self.display_mode,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Level":
        # Prefer new mm key; fall back to legacy ft key converted to mm
        if "elevation_mm" in d:
            elev = d["elevation_mm"]
        else:
            elev = d.get("elevation", 0.0) * 304.8
        return cls(
            name         = d["name"],
            elevation    = elev,
            view_top     = d.get("view_top",     2000.0),
            view_bottom  = d.get("view_bottom",  -1000.0),
            display_mode = d.get("display_mode", "Auto"),
        )


# Defaults shipped with every new document
DEFAULT_LEVELS: list[Level] = [
    Level(DEFAULT_LEVEL, elevation=0.0),
    Level("Level 2", elevation=3048.0),
    Level("Level 3", elevation=6096.0),
]


# ─────────────────────────────────────────────────────────────────────────────
# Manager (pure data, no Qt)
# ─────────────────────────────────────────────────────────────────────────────

class LevelManager:
    """Manages the ordered list of floor levels.

    The "active level" concept is now purely view-driven: whichever
    Plan tab is currently displayed defines the active level.  The
    manager no longer stores active-level state; callers pass the
    level name explicitly to ``apply_for_level()``.
    """

    def __init__(self):
        self._levels: list[Level] = [
            Level(**vars(l)) for l in DEFAULT_LEVELS
        ]

    # ── Level list API ────────────────────────────────────────────────────────

    @property
    def levels(self) -> list[Level]:
        return list(self._levels)

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

    def rename_level(self, old_name: str, new_name: str, items) -> bool:
        """Rename a level and update all items that referenced the old name."""
        if not new_name or (self.get(new_name) is not None
                           and new_name != old_name):
            return False
        lvl = self.get(old_name)
        if lvl is None:
            return False
        lvl.name = new_name
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

    def reset(self):
        """Reset to default levels (used on new file)."""
        self._levels = [Level(**vars(l)) for l in DEFAULT_LEVELS]

    # ── Elevation helpers ───────────────────────────────────────────────────

    def update_elevations(self, scene):
        """Recompute z_pos for all nodes using ceiling_level + ceiling_offset."""
        from node import Node
        lvl_map = {l.name: l for l in self._levels}
        for node in scene.sprinkler_system.nodes:
            # 3D elevation = ceiling level elevation (mm) + ceiling offset (mm)
            ceil_lvl = lvl_map.get(getattr(node, "ceiling_level", DEFAULT_LEVEL))
            ceil_elev = ceil_lvl.elevation if ceil_lvl else 0.0
            node.z_pos = ceil_elev + getattr(node, "ceiling_offset", DEFAULT_CEILING_OFFSET_MM)

    # ── Apply to scene ────────────────────────────────────────────────────────

    def apply_to_scene(self, scene, active_level: str | None = None):
        """Show/hide/fade entities based on *active_level* and display_mode,
        then re-apply layer visibility so both level AND layer filtering
        are respected.

        *active_level* is the level of the current plan view.  If ``None``,
        falls back to ``scene.active_level``.
        """
        active = active_level or getattr(scene, "active_level", DEFAULT_LEVEL)
        lvl_map = {l.name: l for l in self._levels}

        def _set_level_vis(item):
            lvl_name = getattr(item, "level", DEFAULT_LEVEL)
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

        # ── Gridlines (always visible on all levels) ─────────────────────
        for item in getattr(scene, "_gridlines", []):
            item.setVisible(True)
            item.setOpacity(1.0)
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

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

        # ── Roofs ────────────────────────────────────────────────────────
        for item in getattr(scene, "_roofs", []):
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
            if getattr(item, "level", DEFAULT_LEVEL) in faded_levels:
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
# Elevation cell delegate (DimensionEdit editor)
# ─────────────────────────────────────────────────────────────────────────────

class _ElevationDelegate(QStyledItemDelegate):
    """Provides a DimensionEdit widget when editing elevation cells."""

    def __init__(self, get_scale_manager, parent=None):
        super().__init__(parent)
        self._get_sm = get_scale_manager  # callable → ScaleManager | None

    def createEditor(self, parent, option, index):
        sm = self._get_sm()
        editor = DimensionEdit(sm, initial_mm=0.0, parent=parent)
        return editor

    def setEditorData(self, editor, index):
        # Read elevation stored in Qt.ItemDataRole.UserRole
        val = index.data(Qt.ItemDataRole.UserRole)
        if val is not None:
            editor.set_value_mm(float(val))

    def setModelData(self, editor, model, index):
        mm = editor.value_mm()
        model.setData(index, mm, Qt.ItemDataRole.UserRole)
        # Format for display
        sm = self._get_sm()
        if sm:
            model.setData(index, sm.format_length(mm), Qt.ItemDataRole.DisplayRole)
        else:
            model.setData(index, f"{mm:.1f} mm", Qt.ItemDataRole.DisplayRole)


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

        # View level dropdown — switches to the corresponding plan tab
        active_row = QHBoxLayout()
        active_row.setContentsMargins(0, 0, 0, 0)
        active_lbl = QLabel("View Level:")
        active_lbl.setStyleSheet(f"color: {_t.text_primary}; font-size: 11px;")
        active_row.addWidget(active_lbl)
        self._active_combo = QComboBox()
        self._active_combo.setStyleSheet(
            f"QComboBox {{ background: {_t.bg_raised}; color: {_t.text_primary}; "
            f"border: 1px solid {_t.border_subtle}; border-radius: 2px; }}"
        )
        self._active_combo.currentIndexChanged.connect(self._on_active_combo_changed)
        active_row.addWidget(self._active_combo, stretch=1)
        layout.addLayout(active_row)

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
        add_btn = QPushButton("+ Add")
        add_btn.setFixedHeight(24)
        add_btn.setToolTip("Add new level")
        add_btn.setStyleSheet(_btn_ss)
        add_btn.clicked.connect(self._add_level)
        del_btn = QPushButton("− Delete")
        del_btn.setFixedHeight(24)
        del_btn.setToolTip("Delete selected level")
        del_btn.setStyleSheet(_btn_ss)
        del_btn.clicked.connect(self._delete_level)
        dup_btn = QPushButton("⧉ Duplicate")
        dup_btn.setFixedHeight(24)
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
            ["Name", "Elevation", "Display"]
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
        # Note: active level is now controlled by the dropdown combo above,
        # not by table row selection.
        # DimensionEdit delegate for elevation column
        self._elev_delegate = _ElevationDelegate(
            lambda: getattr(self.scene, "scale_manager", None) if self.scene else None,
            parent=self.table,
        )
        self.table.setItemDelegateForColumn(_COL_ELEV, self._elev_delegate)
        layout.addWidget(self.table)

    # ── Populate ──────────────────────────────────────────────────────────────

    def populate(self):
        """Rebuild the table and view-level combo from manager.levels."""
        self._building = True
        self.table.setRowCount(0)
        for lvl in self.manager.levels:
            self._append_row(lvl)
        self._refresh_active_combo()
        self._building = False
        self._highlight_active()

    def _fmt_elev(self, elev_mm: float) -> str:
        """Format a level elevation using the scene's ScaleManager."""
        sm = getattr(self.scene, "scale_manager", None) if self.scene else None
        if sm:
            return sm.format_length(elev_mm)
        return f"{elev_mm:.2f}"

    def _append_row(self, lvl: Level):
        row = self.table.rowCount()
        self.table.insertRow(row)

        # Name (store canonical name in UserRole for reliable lookup)
        name_it = QTableWidgetItem(lvl.name)
        name_it.setData(Qt.ItemDataRole.UserRole, lvl.name)
        self.table.setItem(row, _COL_NAME, name_it)

        # Elevation (store mm value in UserRole for the delegate)
        elev_it = QTableWidgetItem(self._fmt_elev(lvl.elevation))
        elev_it.setData(Qt.ItemDataRole.UserRole, lvl.elevation)
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
        active = getattr(self.scene, "active_level", DEFAULT_LEVEL) if self.scene else DEFAULT_LEVEL
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
            print(f"[LEVEL] name edit: lvl.name={lvl.name!r}, new_name={new_name!r}")
            if new_name and new_name != lvl.name:
                ok = self.manager.rename_level(
                    lvl.name, new_name, self._all_scene_items()
                )
                if not ok:
                    self._building = True
                    item.setText(lvl.name)
                    self._building = False
                else:
                    # Update canonical name in UserRole to match new name
                    item.setData(Qt.ItemDataRole.UserRole, new_name)
                    self._highlight_active()
                    self._refresh_active_combo()
                    self.levelsChanged.emit()
                    current = getattr(self.scene, "active_level", DEFAULT_LEVEL) if self.scene else DEFAULT_LEVEL
                    if current == old_name or current == new_name:
                        self.activeLevelChanged.emit(new_name)

        elif col == _COL_ELEV:
            # Check if the DimensionEdit delegate set the value via UserRole
            user_val = item.data(Qt.ItemDataRole.UserRole)
            if user_val is not None:
                try:
                    new_elev = float(user_val)
                except (ValueError, TypeError):
                    return
            else:
                # Fallback: parse dimension text (manual edit without delegate)
                sm = getattr(self.scene, "scale_manager", None) if self.scene else None
                text = item.text().strip()
                parsed_mm = None
                if sm:
                    from scale_manager import ScaleManager
                    fallback = sm.bare_number_unit()
                    parsed_mm = ScaleManager.parse_dimension(text, fallback)
                if parsed_mm is not None:
                    new_elev = parsed_mm
                else:
                    try:
                        new_elev = float(text)
                    except (ValueError, TypeError):
                        self._building = True
                        item.setText(self._fmt_elev(lvl.elevation))
                        self._building = False
                        return
            print(f"[LEVEL] setting {lvl.name} elevation: {lvl.elevation} -> {new_elev}")
            lvl.elevation = new_elev
            # Reformat the cell to the canonical display
            self._building = True
            item.setText(self._fmt_elev(new_elev))
            item.setData(Qt.ItemDataRole.UserRole, new_elev)
            self._building = False
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
        """Legacy table selection handler — no longer sets active level."""
        pass

    def _on_active_combo_changed(self, idx: int):
        """Handle active-level dropdown selection."""
        if self._building or idx < 0:
            return
        name = self._active_combo.itemData(idx)
        current = getattr(self.scene, "active_level", DEFAULT_LEVEL) if self.scene else DEFAULT_LEVEL
        if name and name != current:
            self._highlight_active()
            self.activeLevelChanged.emit(name)

    def _refresh_active_combo(self):
        """Rebuild the view-level combo after add/delete/rename."""
        self._active_combo.blockSignals(True)
        self._active_combo.clear()
        current = getattr(self.scene, "active_level", DEFAULT_LEVEL) if self.scene else DEFAULT_LEVEL
        active_idx = 0
        for i, lvl in enumerate(self.manager.levels):
            self._active_combo.addItem(
                f"{lvl.name}  ({self._fmt_elev(lvl.elevation)})", lvl.name
            )
            if lvl.name == current:
                active_idx = i
        self._active_combo.setCurrentIndex(active_idx)
        self._active_combo.blockSignals(False)

    # ── Buttons ───────────────────────────────────────────────────────────────

    def _add_level(self):
        lvl = self.manager.add_level()
        self._building = True
        self._append_row(lvl)
        self._building = False
        self._refresh_active_combo()
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
        # If the deleted level was active, switch to the first level
        current = getattr(self.scene, "active_level", DEFAULT_LEVEL) if self.scene else DEFAULT_LEVEL
        if self.manager.get(current) is None:
            fallback_name = self.manager.levels[0].name if self.manager.levels else DEFAULT_LEVEL
            self.activeLevelChanged.emit(fallback_name)

    def _assign_selection(self):
        if self.scene is None:
            return
        active = getattr(self.scene, "active_level", DEFAULT_LEVEL)
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
        # Use UserRole (canonical name) for reliable lookup — display text
        # may already reflect an in-progress edit that hasn't been committed.
        canonical = it.data(Qt.ItemDataRole.UserRole)
        if canonical:
            lvl = self.manager.get(canonical)
            if lvl is not None:
                return lvl
        # Fallback to display text
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
        items += getattr(self.scene, "_roofs", [])
        ann = getattr(self.scene, "annotations", None)
        if ann:
            items += getattr(ann, "dimensions", [])
            items += getattr(ann, "notes", [])
        ws = getattr(self.scene, "water_supply_node", None)
        if ws is not None:
            items.append(ws)
        return items
