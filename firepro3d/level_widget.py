"""
level_widget.py
===============
UI widget for the floor-level table panel.

Separated from ``level_manager.py`` so the data model (``LevelManager``)
has no dependency on Qt widgets.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QMessageBox,
    QAbstractItemView, QLabel, QComboBox, QMenu,
    QStyledItemDelegate,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from .dimension_edit import DimensionEdit
from . import theme as th

from .constants import DEFAULT_LEVEL
from .level_manager import Level, LevelManager, DISPLAY_MODES


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
        val = index.data(Qt.ItemDataRole.UserRole)
        if val is not None:
            editor.set_value_mm(float(val))

    def setModelData(self, editor, model, index):
        mm = editor.value_mm()
        model.setData(index, mm, Qt.ItemDataRole.UserRole)
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
    activeLevelChanged(str)  — emitted when the view level changes
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
        self._building = False
        self._build_ui()
        self.populate()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        _t = th.detect()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

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

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Name", "Elevation", "Display"])
        self.table.horizontalHeader().setSectionResizeMode(
            _COL_NAME, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            _COL_ELEV, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(_COL_DISPLAY, 100)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.SelectedClicked)
        self.table.setStyleSheet(
            f"QTableWidget {{ background: {_t.bg_raised}; color: {_t.text_primary}; "
            f"border: 1px solid {_t.border_subtle}; }}"
            f"QTableWidget::item:selected {{ background: {_t.accent_primary}; color: #ffffff; }}"
        )
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        self.table.itemChanged.connect(self._on_item_changed)
        self._elev_delegate = _ElevationDelegate(
            lambda: getattr(self.scene, "scale_manager", None) if self.scene else None,
            parent=self.table)
        self.table.setItemDelegateForColumn(_COL_ELEV, self._elev_delegate)
        layout.addWidget(self.table)

    # ── Populate ──────────────────────────────────────────────────────────────

    def populate(self):
        self._building = True
        self.table.setRowCount(0)
        for lvl in self.manager.levels:
            self._append_row(lvl)
        self._refresh_active_combo()
        self._building = False
        self._highlight_active()

    def _fmt_elev(self, elev_mm: float) -> str:
        sm = getattr(self.scene, "scale_manager", None) if self.scene else None
        if sm:
            return sm.format_length(elev_mm)
        return f"{elev_mm:.2f}"

    def _append_row(self, lvl: Level):
        row = self.table.rowCount()
        self.table.insertRow(row)
        name_it = QTableWidgetItem(lvl.name)
        name_it.setData(Qt.ItemDataRole.UserRole, lvl.name)
        self.table.setItem(row, _COL_NAME, name_it)
        elev_it = QTableWidgetItem(self._fmt_elev(lvl.elevation))
        elev_it.setData(Qt.ItemDataRole.UserRole, lvl.elevation)
        self.table.setItem(row, _COL_ELEV, elev_it)
        combo = QComboBox()
        combo.setFixedHeight(20)
        combo.addItems(DISPLAY_MODES)
        idx = combo.findText(lvl.display_mode)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.currentIndexChanged.connect(
            lambda _idx, r=row: self._on_display_combo_changed(r, _idx))
        self.table.setCellWidget(row, _COL_DISPLAY, combo)

    # ── Active-level highlight ────────────────────────────────────────────────

    def _highlight_active(self):
        active = getattr(self.scene, "active_level", DEFAULT_LEVEL) if self.scene else DEFAULT_LEVEL
        bold = QFont(); bold.setBold(True)
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
            combo = self.table.cellWidget(row, _COL_DISPLAY)
            if combo and isinstance(combo, QComboBox):
                combo.blockSignals(True)
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
            old_name = item.data(Qt.ItemDataRole.UserRole) or lvl.name
            if new_name and new_name != lvl.name:
                ok = self.manager.rename_level(
                    lvl.name, new_name, self._all_scene_items())
                if not ok:
                    self._building = True
                    item.setText(lvl.name)
                    self._building = False
                else:
                    item.setData(Qt.ItemDataRole.UserRole, new_name)
                    self._highlight_active()
                    self._refresh_active_combo()
                    self.levelsChanged.emit()
                    current = getattr(self.scene, "active_level", DEFAULT_LEVEL) if self.scene else DEFAULT_LEVEL
                    if current == old_name or current == new_name:
                        self.activeLevelChanged.emit(new_name)

        elif col == _COL_ELEV:
            user_val = item.data(Qt.ItemDataRole.UserRole)
            if user_val is not None:
                try:
                    new_elev = float(user_val)
                except (ValueError, TypeError):
                    return
            else:
                sm = getattr(self.scene, "scale_manager", None) if self.scene else None
                text = item.text().strip()
                parsed_mm = None
                if sm:
                    from .scale_manager import ScaleManager
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
            lvl.elevation = new_elev
            self._building = True
            item.setText(self._fmt_elev(new_elev))
            item.setData(Qt.ItemDataRole.UserRole, new_elev)
            self._building = False
            if self.scene:
                self.manager.update_elevations(self.scene)
            self.levelsChanged.emit()

    def _on_display_combo_changed(self, row: int, idx: int):
        if self._building:
            return
        lvl = self._level_at_row(row)
        if lvl is None or idx < 0 or idx >= len(DISPLAY_MODES):
            return
        lvl.display_mode = DISPLAY_MODES[idx]
        self.levelsChanged.emit()

    def _on_active_combo_changed(self, idx: int):
        if self._building or idx < 0:
            return
        name = self._active_combo.itemData(idx)
        current = getattr(self.scene, "active_level", DEFAULT_LEVEL) if self.scene else DEFAULT_LEVEL
        if name and name != current:
            self._highlight_active()
            self.activeLevelChanged.emit(name)

    def _refresh_active_combo(self):
        self._active_combo.blockSignals(True)
        self._active_combo.clear()
        current = getattr(self.scene, "active_level", DEFAULT_LEVEL) if self.scene else DEFAULT_LEVEL
        active_idx = 0
        for i, lvl in enumerate(self.manager.levels):
            self._active_combo.addItem(
                f"{lvl.name}  ({self._fmt_elev(lvl.elevation)})", lvl.name)
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
            QMessageBox.information(self, "Level",
                                    "The last remaining level cannot be deleted.")
            return
        reply = QMessageBox.question(
            self, "Delete Level",
            f"Delete level '{lvl.name}'?\n"
            "Items on this level will be moved to the first remaining level.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
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
        row = self.table.currentRow()
        lvl = self._level_at_row(row)
        if lvl is None:
            return
        self._duplicate_level_from(lvl)

    def _duplicate_level_from(self, source_lvl: Level):
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
        canonical = it.data(Qt.ItemDataRole.UserRole)
        if canonical:
            lvl = self.manager.get(canonical)
            if lvl is not None:
                return lvl
        return self.manager.get(it.text())

    def _all_scene_items(self) -> list:
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
