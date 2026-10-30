"""
level_widget.py
===============
The Level Manager table + action row (view-relationships section 12).

Separated from ``level_manager.py`` so the data model (``LevelManager``)
has no dependency on Qt widgets.  Rows map to levels through the Name
item's UserRole (the canonical name), never the row index: the VIEW sorts
on a header click while ``manager.levels`` stays lowest-elevation-first.
``main.py`` keeps one hidden instance as the signal hub; ``LevelDialog``
shows a second one on the same manager and chains into the hub.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMenu,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from .themed_message import themed_confirm
from .dimension_edit import DimensionDelegate
from .icons import themed_icon
from . import theme as th
from .theme import M
from .ui_kit import SortHeader, glyph_button
from .constants import DEFAULT_LEVEL
from .level_manager import Level, LevelManager


# ─────────────────────────────────────────────────────────────────────────────
# Table column indices
# ─────────────────────────────────────────────────────────────────────────────

_COL_NAME    = 0
_COL_NUM     = 1
_COL_ELEV    = 2
_ROLE_ORDER  = Qt.ItemDataRole.UserRole + 2   # manager list index: the view-sort tie-break

_TIP_ADD             = "Add level"
_TIP_DELETE          = "Delete level(s)"
_TIP_DELETE_ALL      = "At least one level must remain"
_TIP_DUPLICATE       = "Duplicate level"
_TIP_DUPLICATE_NEEDS_ONE = "Select a single level to duplicate"


class _LevelItem(QTableWidgetItem):
    """Sorts by the column's real value — Name case-insensitively, Number as an int,
    Elevation by its UserRole mm — and breaks ties by manager order (P4 probe
    2026-10-30: a ``__lt__`` override drives both ``sortItems`` and header sorts)."""

    def _key(self):
        col = self.column()
        if col == _COL_ELEV:
            try:
                return float(self.data(Qt.ItemDataRole.UserRole))
            except (TypeError, ValueError):
                return 0.0
        if col == _COL_NUM:
            try:
                return int(self.text())
            except ValueError:
                return 0
        return self.text().lower()

    def __lt__(self, other):
        return ((self._key(), self.data(_ROLE_ORDER) or 0)
                < (other._key(), other.data(_ROLE_ORDER) or 0))


class _LevelTable(QTableWidget):
    """QTableWidget that turns a Delete key press outside a cell edit into a signal
    (the modal dialog is its own window, so MainWindow's Delete shortcut is inactive)."""

    deleteRequested = pyqtSignal()

    def keyPressEvent(self, event):
        if (event.key() == Qt.Key.Key_Delete
                and self.state() != QAbstractItemView.State.EditingState):
            self.deleteRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# Widget
# ─────────────────────────────────────────────────────────────────────────────

class LevelWidget(QWidget):
    """
    The level table (Name / Number / Elevation) + the `+` / `−` / duplicate glyph row.

    Signals
    -------
    activeLevelChanged(str)   — the active level should change (a rename of the
                                active level, or its delete fallback)
    levelsChanged()           — emitted after any structural change so the
                                scene / browser / sections can be refreshed
    duplicateLevel(src, new)  — copy the entities of *src* to *new*
    levelRenamed(old, new)    — emitted BEFORE levelsChanged (main retitles the tab)
    levelsRemoved(list)       — deleted names, emitted BEFORE levelsChanged
    """

    activeLevelChanged = pyqtSignal(str)
    levelsChanged      = pyqtSignal()
    duplicateLevel     = pyqtSignal(str, str)   # (source_level, new_level)
    levelRenamed       = pyqtSignal(str, str)   # (old_name, new_name)
    levelsRemoved      = pyqtSignal(list)       # [deleted names]

    def __init__(self, manager: LevelManager, scene=None, parent=None):
        super().__init__(parent)
        self.manager   = manager
        self.scene     = scene
        self._building = False
        self._build_ui()
        self.populate()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(M.LEVEL_TOOLBAR_TOP)

        self.table = _LevelTable(objectName="levelTable")     # build_dialog_qss #levelTable
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Name", "Number", "Elevation"])
        self.table.setHorizontalHeader(SortHeader(self.table))
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_NUM, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_COL_ELEV, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(_COL_NUM, M.LEVEL_COL_NUMBER_W)
        self.table.setColumnWidth(_COL_ELEV, M.LEVEL_COL_ELEV_W)
        self.table.verticalHeader().setDefaultSectionSize(M.LEVEL_ROW_H)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.SelectedClicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemSelectionChanged.connect(self._sync_buttons)
        self.table.deleteRequested.connect(self._delete_level)
        self._elev_delegate = DimensionDelegate(
            lambda: getattr(self.scene, "scale_manager", None) if self.scene else None,
            parent=self.table)
        self.table.setItemDelegateForColumn(_COL_ELEV, self._elev_delegate)
        # View sort (section 12.4): default Elevation ascending == the manager order.
        # Enable AFTER setHorizontalHeader (it wires that header's signal) and only
        # through SortHeader.set_view_sorting — table.setSortingEnabled(True) re-shows
        # the native arrow from C++ (probe (i)).
        hdr.set_view_sorting(self.table, True)
        self.table.sortByColumn(_COL_ELEV, Qt.SortOrder.AscendingOrder)
        layout.addWidget(self.table, 1)

        theme_name = "dark" if th.detect() is th.DARK else "light"
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(M.GLYPH_BTN_GAP)
        self.add_btn = glyph_button("+", _TIP_ADD, self._add_level)
        self.del_btn = glyph_button("\u2212", _TIP_DELETE, self._delete_level)
        self.dup_btn = glyph_button(None, _TIP_DUPLICATE, self._duplicate_level,
                                    icon=themed_icon("duplicate_icon.svg", theme_name))
        for b in (self.add_btn, self.del_btn, self.dup_btn):
            row.addWidget(b)
        row.addStretch(1)
        layout.addLayout(row)

    # ── Populate ──────────────────────────────────────────────────────────────

    def populate(self):
        self._building = True
        hdr = self.table.horizontalHeader()
        col, order = hdr.sortIndicatorSection(), hdr.sortIndicatorOrder()
        hdr.set_view_sorting(self.table, False)   # P4 probe: filling with sorting ON reorders ties mid-fill
        self.table.setRowCount(0)
        for i, lvl in enumerate(self.manager.levels):
            self._append_row(lvl, i)
        hdr.set_view_sorting(self.table, True)    # re-hides the native arrow on every refill (probe (i))
        self.table.sortItems(col, order)      # the session's view sort survives a refill
        self._building = False
        self._highlight_active()
        self._sync_buttons()

    def _fmt_elev(self, elev_mm: float) -> str:
        sm = getattr(self.scene, "scale_manager", None) if self.scene else None
        if sm:
            return sm.format_length(elev_mm)
        return f"{elev_mm:.2f}"

    def _append_row(self, lvl: Level, order: int):
        row = self.table.rowCount()
        self.table.insertRow(row)
        name_it = _LevelItem(lvl.name)
        name_it.setData(Qt.ItemDataRole.UserRole, lvl.name)
        num_it = _LevelItem(str(lvl.number))
        elev_it = _LevelItem(self._fmt_elev(lvl.elevation))
        elev_it.setData(Qt.ItemDataRole.UserRole, lvl.elevation)
        for col, it in ((_COL_NAME, name_it), (_COL_NUM, num_it), (_COL_ELEV, elev_it)):
            it.setData(_ROLE_ORDER, order)
            self.table.setItem(row, col, it)

    def _refresh_order_roles(self):
        """After an elevation edit the manager re-sorted: re-seat the tie-break index."""
        index = {l.name: i for i, l in enumerate(self.manager.levels)}
        was = self._building
        self._building = True
        # Snapshot the items first: with the view sort live, each setData re-sorts its
        # row, so a row-index loop could skip a row that moved under it.
        rows = [(self._level_at_row(row),
                 [self.table.item(row, col) for col in (_COL_NAME, _COL_NUM, _COL_ELEV)])
                for row in range(self.table.rowCount())]
        try:
            for lvl, items in rows:
                if lvl is None:
                    continue
                for it in items:
                    if it is not None:
                        it.setData(_ROLE_ORDER, index[lvl.name])
        finally:
            self._building = was

    def _resort_view(self):
        hdr = self.table.horizontalHeader()
        self.table.sortItems(hdr.sortIndicatorSection(), hdr.sortIndicatorOrder())

    # ── Active-level highlight ────────────────────────────────────────────────

    def _highlight_active(self):
        active = getattr(self.scene, "active_level", DEFAULT_LEVEL) if self.scene else DEFAULT_LEVEL
        bold = QFont(); bold.setBold(True)
        normal = QFont()
        was_building = self._building
        self._building = True          # setFont fires itemChanged: not an edit
        try:
            for row in range(self.table.rowCount()):
                name_it = self.table.item(row, _COL_NAME)
                if name_it is None:
                    continue
                is_active = name_it.text() == active
                for col in (_COL_NAME, _COL_NUM, _COL_ELEV):
                    it = self.table.item(row, col)
                    if it:
                        it.setFont(bold if is_active else normal)
        finally:
            self._building = was_building

    # ── Selection ─────────────────────────────────────────────────────────────

    def _selected_levels(self) -> list[Level]:
        rows = sorted({ix.row() for ix in self.table.selectionModel().selectedRows()})
        if not rows and self.table.currentRow() >= 0:
            rows = [self.table.currentRow()]
        out = []
        for r in rows:
            lvl = self._level_at_row(r)
            if lvl is not None:
                out.append(lvl)
        return out

    def _select_level(self, name: str):
        for row in range(self.table.rowCount()):
            it = self.table.item(row, _COL_NAME)
            if it is not None and it.data(Qt.ItemDataRole.UserRole) == name:
                self.table.setCurrentCell(row, _COL_NAME)     # selects the row (SelectRows)
                return

    def _sync_buttons(self):
        """Section 12.4: Delete is disabled (with the reason as tooltip) when the selection
        covers every level; Duplicate needs exactly one row."""
        sel = self._selected_levels()
        all_selected = bool(sel) and len(sel) >= len(self.manager.levels)
        self.del_btn.setEnabled(bool(sel) and not all_selected)
        self.del_btn.setToolTip(_TIP_DELETE_ALL if all_selected else _TIP_DELETE)
        self.dup_btn.setEnabled(len(sel) == 1)
        self.dup_btn.setToolTip(_TIP_DUPLICATE if len(sel) == 1 else _TIP_DUPLICATE_NEEDS_ONE)

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
                    lvl.name, new_name, self._all_scene_items(),
                    scene=self.scene)
                if not ok:
                    self._building = True
                    item.setText(lvl.name)
                    self._building = False
                else:
                    self._building = True
                    item.setData(Qt.ItemDataRole.UserRole, new_name)
                    self._building = False
                    self._remap_underlay_views(old_name, new_name)
                    pvm = self._plan_views()
                    if pvm is not None:
                        pvm.rename_level(old_name, new_name)   # section 12.4: the PlanView moves with the name
                    self._resort_view()
                    self.levelRenamed.emit(old_name, new_name)
                    self.levelsChanged.emit()
                    current = getattr(self.scene, "active_level", DEFAULT_LEVEL) if self.scene else DEFAULT_LEVEL
                    if current == old_name or current == new_name:
                        self.activeLevelChanged.emit(new_name)
                    self._highlight_active()            # after main moved the active level
                    self._push_level_step()

        elif col == _COL_NUM:
            try:
                new_num = int(item.text().strip())
            except ValueError:
                self._building = True
                item.setText(str(lvl.number))
                self._building = False
                return
            if new_num != lvl.number:
                lvl.number = new_num
                self._resort_view()
                self.levelsChanged.emit()
                self._push_level_step()

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
            changed = new_elev != lvl.elevation
            lvl.elevation = new_elev
            self.manager.resort()                     # the store stays lowest first
            self._building = True
            item.setText(self._fmt_elev(new_elev))
            item.setData(Qt.ItemDataRole.UserRole, new_elev)
            self._building = False
            self._refresh_order_roles()
            self._resort_view()
            if self.scene:
                self.manager.update_elevations(self.scene)
            self.levelsChanged.emit()
            if changed:
                self._push_level_step()

    def _push_level_step(self) -> None:
        """One undo step per Level-manager edit (SB2b M15).

        Push-after-change: the snapshot holds the settled state.  ``populate``
        never calls this (it is the undo restore's refresh).
        """
        if self.scene is not None and hasattr(self.scene, "push_undo_state"):
            self.scene.push_undo_state()

    def _remap_underlay_views(self, old_name: str, new_name: str):
        """§16.7: propagate a level rename into underlay records.

        Underlays are stored as records (not scene items), so
        ``LevelManager.rename_level`` — which only rewrites ``item.level``
        for QGraphicsItems — never reaches them.  ``record.levels`` must
        follow the rename so a level-specific underlay does not orphan and
        get hidden by the §7.2 visibility pass (``lvl_map.get`` would miss
        the stale name).
        """
        scene = self.scene
        underlays = getattr(scene, "underlays", None) if scene else None
        if not underlays:
            return
        for record, _item in underlays:
            record.levels = [new_name if n == old_name else n
                             for n in record.levels]

    # ── Actions (buttons, Delete key, context menu) ───────────────────────────

    def _add_level(self):
        """Section 12.4 Add: above the top level, next free name, Number = next."""
        lvl = self.manager.add_level(elevation=self.manager.next_elevation_above_top())
        self.populate()
        self._select_level(lvl.name)
        self.levelsChanged.emit()
        self._push_level_step()

    def _delete_level(self):
        """Section 12.4 Delete: the selected rows (one or more); items move to the nearest
        remaining level below; the plan views are dropped; one undo step."""
        doomed = self._selected_levels()
        if not doomed or len(doomed) >= len(self.manager.levels):
            return                                   # disabled state: the tooltip says why
        names = [l.name for l in doomed]
        if len(names) == 1:
            title, what = "Delete Level", f"Delete level '{names[0]}'?"
        else:
            title, what = "Delete Levels", f"Delete {len(names)} levels ({', '.join(names)})?"
        if not themed_confirm(
                self, title,
                f"{what}\nItems on deleted levels move to the nearest remaining level below."):
            return
        # Read the active level BEFORE levelsRemoved: main closes the deleted tabs on that
        # signal, and closing the current tab re-targets scene.active_level to a neighbour.
        current = getattr(self.scene, "active_level", DEFAULT_LEVEL) if self.scene else DEFAULT_LEVEL
        targets = self.manager.remove_levels(names, self._all_scene_items(), scene=self.scene)
        if not targets:
            return
        for record, _item in (getattr(self.scene, "underlays", []) if self.scene else []):
            record.levels = [n for n in record.levels if n not in targets]
        pvm = self._plan_views()
        if pvm is not None:
            for n in names:
                pvm.remove_level(n)                  # section 12.4: the PlanView is dropped
        self.populate()
        self.levelsRemoved.emit(list(names))
        self.levelsChanged.emit()
        if current in targets:
            self.activeLevelChanged.emit(targets[current])   # P7: the deleted active level's own target
        self._push_level_step()                      # after the active-level fallback has settled

    def _duplicate_level(self):
        sel = self._selected_levels()
        if len(sel) != 1:
            return                                   # section 12.4: single row only
        self._duplicate_level_from(sel[0])

    def _duplicate_level_from(self, source_lvl: Level):
        new_lvl = self.manager.add_level(elevation=source_lvl.elevation)
        self.populate()
        self._select_level(new_lvl.name)
        sc = self.scene
        prev = getattr(sc, "_history_suspended", False) if sc is not None else False
        if sc is not None:
            sc._history_suspended = True          # copy_items_to_level pushes its own step
        try:
            self.duplicateLevel.emit(source_lvl.name, new_lvl.name)
        finally:
            if sc is not None:
                sc._history_suspended = prev
        self.levelsChanged.emit()
        self._push_level_step()                   # level + copies = one step

    def _build_context_menu(self) -> QMenu:
        """Add / Duplicate / Delete over the current selection (section 12.4 Context menu).
        Separate from the popup so tests can inspect the actions."""
        sel = self._selected_levels()
        n = len(sel)
        all_selected = n > 0 and n >= len(self.manager.levels)
        menu = QMenu(self)
        menu.setObjectName("uwMenu")             # house menu rule in build_dialog_qss
        menu.setToolTipsVisible(True)
        add = menu.addAction("Add Level")                       # section 12.4 order: Add / Delete / Duplicate
        add.triggered.connect(self._add_level)
        dele = menu.addAction("Delete Level" if n <= 1 else "Delete Levels")
        dele.setEnabled(n > 0 and not all_selected)
        dele.setToolTip(_TIP_DELETE_ALL if all_selected else _TIP_DELETE)
        dele.triggered.connect(self._delete_level)
        dup = menu.addAction("Duplicate Level")
        dup.setEnabled(n == 1)
        dup.setToolTip(_TIP_DUPLICATE if n == 1 else _TIP_DUPLICATE_NEEDS_ONE)
        dup.triggered.connect(self._duplicate_level)
        return menu

    def _on_table_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row >= 0 and row not in {ix.row() for ix in self.table.selectionModel().selectedRows()}:
            self.table.setCurrentCell(row, _COL_NAME)   # right-click outside the selection re-targets it
        self._build_context_menu().exec(self.table.viewport().mapToGlobal(pos))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _plan_views(self):
        return getattr(self.scene, "_plan_view_manager", None) if self.scene else None

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
        # Loose 2D primitives are level-less (containment C3) — not remapped.
        items += getattr(self.scene, "_block_instances", [])
        items += getattr(self.scene, "_gridlines", [])
        items += getattr(self.scene, "_roofs", [])
        # Walls (+ their openings), rooms and design areas carry a level too; without
        # them a rename / delete orphaned their level and undo had nothing to restore.
        for wall in getattr(self.scene, "_walls", []):
            items.append(wall)
            items += getattr(wall, "openings", [])
        items += getattr(self.scene, "_rooms", [])
        items += getattr(self.scene, "design_areas", [])
        ann = getattr(self.scene, "annotations", None)
        if ann:
            items += getattr(ann, "dimensions", [])
            items += getattr(ann, "notes", [])
        ws = getattr(self.scene, "water_supply_node", None)
        if ws is not None:
            items.append(ws)
        return items
