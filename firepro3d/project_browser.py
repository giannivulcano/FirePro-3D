"""
project_browser.py
==================
Revit-style Project Browser dock widget.

Tree structure
--------------
  ▼ 2D Model
      ▼ Plans
          Level 1          ← one item per defined level
          Level 2 …
      ▼ Elevations
          North
          South
          East
          West
      ▶ Schematics     (future: separate drawing canvas)
      ▶ Details        (future)
      ▶ Schedules      (future: tabular data)
  ▼ Paper Space
      FP-1.0 - Plans   ← sheet rows keyed by Sheet.number; pushed by MainWindow
      FP-2.0 - Details …

Signals (pure push contract)
-----------------------------
activateModelSpace()           — model space root / sub-item activated
activatePaperSheet(number)     — sheet double-clicked; number = Sheet.number
sheetSelected(number)          — single-click selection → sheet props panel
createPaperSheet()             — instant create request; MainWindow owns the dialog
deletePaperSheet(number)       — delete request; MainWindow owns the confirm
sheetOrderChanged(list[str])   — post-drop reorder; numbers in new document order

The tree never self-mutates from its own gestures (pure-push contract,
spec §"Multi-sheet design deltas").  Gestures emit signals; MainWindow
mutates data and pushes authoritative state back via set_sheets().
"""

from __future__ import annotations

import json

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel, QSizePolicy,
    QMenu, QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QByteArray
from PyQt6.QtGui import QFont, QColor, QBrush, QIcon
from . import theme as th


# ─────────────────────────────────────────────────────────────────────────────
# Tree item role constants
# ─────────────────────────────────────────────────────────────────────────────

_ROLE_TYPE  = Qt.ItemDataRole.UserRole         # "model_root" | "ms_stub" | "paper_root" | "sheet" | "plan" | "elevation"
_ROLE_NAME  = Qt.ItemDataRole.UserRole + 1     # str name for sheets / levels / elevations
_ROLE_VIEW  = Qt.ItemDataRole.UserRole + 2


# ─────────────────────────────────────────────────────────────────────────────
# Drag-enabled tree
# ─────────────────────────────────────────────────────────────────────────────

class _ProjectTree(QTreeWidget):
    """QTreeWidget with drag-out for view items + guarded internal sheet moves."""

    sheetDropped = pyqtSignal(str, str)   # (dragged number, target number|"")

    def mimeData(self, items):
        mime = QMimeData()
        for item in items:
            role_type = item.data(0, _ROLE_TYPE)
            if role_type in ("plan", "elevation", "detail"):
                view_name = item.data(0, _ROLE_NAME)
                # For plan views, the ViewResolver expects "Plan: Level 1" format
                if role_type == "plan":
                    view_name = f"Plan: {view_name}"
                payload = json.dumps({
                    "view_type": role_type,
                    "view_name": view_name,
                })
                mime.setData(
                    "application/x-firepro3d-view",
                    QByteArray(payload.encode("utf-8")),
                )
                break
            if role_type == "sheet":
                mime.setData(
                    "application/x-firepro3d-sheet",
                    QByteArray(str(item.data(0, _ROLE_NAME)).encode("utf-8")),
                )
                break
        return mime

    def mimeTypes(self):
        return ["application/x-firepro3d-view",
                "application/x-firepro3d-sheet"]

    def _is_internal_sheet_drag(self, e) -> bool:
        return (e.source() is self
                and e.mimeData().hasFormat("application/x-firepro3d-sheet"))

    def dragEnterEvent(self, e):
        if self._is_internal_sheet_drag(e):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if self._is_internal_sheet_drag(e):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if not self._is_internal_sheet_drag(e):
            e.ignore()
            return
        number = bytes(
            e.mimeData().data("application/x-firepro3d-sheet")).decode("utf-8")
        target = self.itemAt(e.position().toPoint())
        role = target.data(0, _ROLE_TYPE) if target is not None else None
        if role not in ("sheet", "paper_root"):
            e.ignore()                      # drops outside the sheet zone
            return
        target_number = target.data(0, _ROLE_NAME) if role == "sheet" else ""
        # Pure push: NEVER let Qt move the item — data reorders, then
        # MainWindow pushes set_sheets back.
        e.setDropAction(Qt.DropAction.IgnoreAction)
        e.accept()
        self.sheetDropped.emit(number, target_number or "")


class ProjectBrowser(QWidget):
    """
    Project Browser panel.  Embed in a QDockWidget.

    Parameters
    ----------
    parent : QWidget | None
    """

    activateModelSpace = pyqtSignal()
    activatePaperSheet = pyqtSignal(str)   # sheet NUMBER (identity, spec §19.1)
    activateElevation = pyqtSignal(str)    # direction name (North/South/East/West)
    activatePlanView = pyqtSignal(str)     # level name (Level 1, Level 2, etc.)
    activateDetailView = pyqtSignal(str)   # detail view name
    deleteDetailView = pyqtSignal(str)     # detail view name to delete
    createPaperSheet = pyqtSignal()        # instant create — MainWindow owns it
    deletePaperSheet = pyqtSignal(str)     # sheet number; MainWindow confirms
    sheetSelected = pyqtSignal(str)        # single-click → sheet props panel
    sheetOrderChanged = pyqtSignal(list)   # numbers in new document-set order

    # Stub categories under 2D Model (Plans and Elevations are live)
    _MS_STUBS = ["Schematics", "Schedules"]

    # Pre-defined elevation view names
    _ELEVATIONS = ["North", "South", "East", "West"]

    def __init__(self, level_manager=None, scale_manager=None, parent=None):
        super().__init__(parent)
        self._level_manager = level_manager
        self._scale_manager = scale_manager

        _t = th.detect()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header label
        hdr = QLabel("Project Browser")
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

        # Tree
        self._tree = _ProjectTree()
        self._tree.setHeaderHidden(True)
        self._tree.setDragEnabled(True)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self._tree.setDefaultDropAction(Qt.DropAction.IgnoreAction)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(16)
        self._tree.setStyleSheet(
            f"QTreeWidget {{ background: {_t.bg_raised}; color: {_t.text_primary}; "
            f"border: 1px solid {_t.border_subtle}; }}"
            f"QTreeWidget::item:selected {{ background: {_t.accent_primary}; color: #ffffff; }}"
            f"QTreeWidget::item:hover   {{ background: {_t.bg_base}; }}"
        )
        self._tree.itemActivated.connect(self._on_item_activated)
        self._tree.itemDoubleClicked.connect(self._on_item_activated)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.sheetDropped.connect(self._on_sheet_dropped)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._tree)

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._placed_views: set[tuple[str, str]] = set()
        self._build_tree()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_scale_manager(self, sm):
        self._scale_manager = sm

    def _fmt_elev(self, elev_mm: float) -> str:
        """Format a level elevation using the ScaleManager."""
        if self._scale_manager:
            return self._scale_manager.format_length(elev_mm)
        return f"{elev_mm:.1f} mm"

    def set_sheets(self, sheets: "list[tuple[str, str]]"):
        """Refresh the Paper Space children (pure push from MainWindow).

        Preserves the selected sheet row (by number) across rebuilds so a
        push triggered by an edit doesn't drop the user's selection.

        Args:
            sheets: ``[(number, display_text), …]`` in document-set order.
        """
        selected = None
        cur = self._tree.selectedItems()
        if len(cur) == 1 and cur[0].data(0, _ROLE_TYPE) == "sheet":
            selected = cur[0].data(0, _ROLE_NAME)
        self._paper_root.takeChildren()
        for number, display in sheets:
            item = QTreeWidgetItem(self._paper_root, [display])
            item.setData(0, _ROLE_TYPE, "sheet")
            item.setData(0, _ROLE_NAME, number)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
            if number == selected:
                self._tree.blockSignals(True)
                self._tree.setCurrentItem(item)
                self._tree.blockSignals(False)
        self._paper_root.setExpanded(True)

    def set_placed_views(self, placed: "set[tuple[str, str]]"):
        """Italicize placed view rows IN PLACE (covers elevations too)."""
        self._placed_views = placed
        for role, root in (("plan", self._plans_root),
                           ("elevation", self._elev_root),
                           ("detail", self._details_root)):
            if root is None:
                continue
            for i in range(root.childCount()):
                it = root.child(i)
                name = it.data(0, _ROLE_NAME)
                key = f"Plan: {name}" if role == "plan" else name
                f = it.font(0)
                f.setItalic((role, key) in placed)
                it.setFont(0, f)

    def set_level_manager(self, level_manager):
        """Set or replace the level manager and rebuild the Plans sub-tree."""
        self._level_manager = level_manager
        self.refresh_levels()

    def refresh_levels(self):
        """Rebuild the Plans sub-tree from the current level manager."""
        if self._plans_root is None:
            return
        self._plans_root.takeChildren()
        if self._level_manager is not None:
            for lvl in self._level_manager.levels:
                item = QTreeWidgetItem(self._plans_root, [lvl.name])
                item.setData(0, _ROLE_TYPE, "plan")
                item.setData(0, _ROLE_NAME, lvl.name)
                item.setToolTip(0, f"Plan view — {lvl.name}  (elev {self._fmt_elev(lvl.elevation)})")
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
                if ("plan", f"Plan: {lvl.name}") in self._placed_views:
                    italic_font = QFont()
                    italic_font.setItalic(True)
                    item.setFont(0, italic_font)
        self._plans_root.setExpanded(True)

    def refresh_details(self, detail_names: list[str]):
        """Rebuild the Details sub-tree from a list of detail view names."""
        if self._details_root is None:
            return
        self._details_root.takeChildren()
        for name in detail_names:
            item = QTreeWidgetItem(self._details_root, [name])
            item.setData(0, _ROLE_TYPE, "detail")
            item.setData(0, _ROLE_NAME, name)
            item.setToolTip(0, f"Detail view — {name}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
            if ("detail", name) in self._placed_views:
                italic_font = QFont()
                italic_font.setItalic(True)
                item.setFont(0, italic_font)
        self._details_root.setExpanded(True)

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_tree(self):
        _t = th.detect()
        stub_brush = QBrush(QColor(_t.text_disabled if hasattr(_t, "text_disabled") else "#888888"))
        f_bold = QFont(); f_bold.setBold(True)

        # ── Model Space root ─────────────────────────────────────────────────
        ms_root = QTreeWidgetItem(self._tree, ["2D Model"])
        ms_root.setData(0, _ROLE_TYPE, "model_root")
        ms_root.setFont(0, f_bold)
        ms_root.setExpanded(True)
        self._ms_root = ms_root

        # ── Plans (populated from level manager) ─────────────────────────────
        plans_root = QTreeWidgetItem(ms_root, ["Plans"])
        plans_root.setData(0, _ROLE_TYPE, "ms_stub")
        plans_root.setData(0, _ROLE_NAME, "Plans")
        plans_root.setFont(0, f_bold)
        plans_root.setExpanded(True)
        self._plans_root = plans_root
        self.refresh_levels()

        # ── Elevations ───────────────────────────────────────────────────────
        elev_root = QTreeWidgetItem(ms_root, ["Elevations"])
        elev_root.setData(0, _ROLE_TYPE, "ms_stub")
        elev_root.setData(0, _ROLE_NAME, "Elevations")
        elev_root.setFont(0, f_bold)
        for elev_name in self._ELEVATIONS:
            item = QTreeWidgetItem(elev_root, [elev_name])
            item.setData(0, _ROLE_TYPE, "elevation")
            item.setData(0, _ROLE_NAME, elev_name)
            item.setToolTip(0, f"Elevation view — {elev_name}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
            if ("elevation", elev_name) in self._placed_views:
                italic_font = QFont()
                italic_font.setItalic(True)
                item.setFont(0, italic_font)
        self._elev_root = elev_root

        # ── Details (populated dynamically) ───────────────────────────────
        details_root = QTreeWidgetItem(ms_root, ["Details"])
        details_root.setData(0, _ROLE_TYPE, "ms_stub")
        details_root.setData(0, _ROLE_NAME, "Details")
        details_root.setFont(0, f_bold)
        self._details_root = details_root

        # ── Future stubs ─────────────────────────────────────────────────────
        for stub_name in self._MS_STUBS:
            stub = QTreeWidgetItem(ms_root, [stub_name])
            stub.setData(0, _ROLE_TYPE, "ms_stub")
            stub.setData(0, _ROLE_NAME, stub_name)
            stub.setForeground(0, stub_brush)
            stub.setToolTip(0, "Coming soon")

        # ── Paper Space root ─────────────────────────────────────────────────
        ps_root = QTreeWidgetItem(self._tree, ["Paper Space"])
        ps_root.setData(0, _ROLE_TYPE, "paper_root")
        ps_root.setFont(0, f_bold)
        ps_root.setExpanded(True)
        self._paper_root = ps_root
        # Tree starts empty — MainWindow pushes authoritative sheet list via set_sheets()

    def _on_item_activated(self, item: QTreeWidgetItem, _col: int):
        role = item.data(0, _ROLE_TYPE)
        if role == "elevation":
            name = item.data(0, _ROLE_NAME)
            self.activateElevation.emit(name)
        elif role == "plan":
            name = item.data(0, _ROLE_NAME)
            self.activatePlanView.emit(name)
        elif role == "detail":
            name = item.data(0, _ROLE_NAME)
            self.activateDetailView.emit(name)
        elif role in ("model_root", "ms_stub"):
            self.activateModelSpace.emit()
        elif role == "sheet":
            name = item.data(0, _ROLE_NAME)
            self.activatePaperSheet.emit(name)

    def _on_selection_changed(self):
        items = self._tree.selectedItems()
        if len(items) == 1 and items[0].data(0, _ROLE_TYPE) == "sheet":
            self.sheetSelected.emit(items[0].data(0, _ROLE_NAME))

    def _on_sheet_dropped(self, number: str, target_number: str):
        """Compute the new order from a drop gesture and emit it (pure push)."""
        order = [self._paper_root.child(i).data(0, _ROLE_NAME)
                 for i in range(self._paper_root.childCount())]
        if number not in order:
            return
        if number == target_number:
            return
        old = list(order)
        order.remove(number)
        if target_number and target_number in order:
            order.insert(order.index(target_number), number)
        else:
            order.append(number)
        if order != old:
            self.sheetOrderChanged.emit(order)

    def _on_context_menu(self, pos):
        item = self._tree.itemAt(pos)
        if item is None:
            return
        role = item.data(0, _ROLE_TYPE)
        menu = QMenu(self)
        if role in ("paper_root", "sheet"):
            act_new = menu.addAction("New Drawing")
            act_new.triggered.connect(self.createPaperSheet.emit)
            if role == "sheet":
                number = item.data(0, _ROLE_NAME)
                act_open = menu.addAction("Open")
                act_open.triggered.connect(
                    lambda: self.activatePaperSheet.emit(number))
                act_del = menu.addAction("Delete")
                act_del.triggered.connect(
                    lambda: self.deletePaperSheet.emit(number))
        elif role == "detail":
            name = item.data(0, _ROLE_NAME)
            act_open = menu.addAction("Open")
            act_open.triggered.connect(lambda: self.activateDetailView.emit(name))
            act_del = menu.addAction("Delete")
            act_del.triggered.connect(lambda: self.deleteDetailView.emit(name))
        else:
            return
        menu.exec(self._tree.viewport().mapToGlobal(pos))
