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
      Layout 1         ← real sheet, clicking switches to it
      Layout 2 …       ← additional sheets added dynamically

Signals
-------
activateModelSpace()      — user clicked the Model Space root or any sub-item
                            that maps to the current model space canvas
activatePaperSheet(name)  — user double-clicked a Paper Space sheet by name
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QBrush, QIcon
import theme as th


# ─────────────────────────────────────────────────────────────────────────────
# Tree item role constants
# ─────────────────────────────────────────────────────────────────────────────

_ROLE_TYPE  = Qt.ItemDataRole.UserRole         # "model_root" | "ms_stub" | "paper_root" | "sheet" | "plan" | "elevation"
_ROLE_NAME  = Qt.ItemDataRole.UserRole + 1     # str name for sheets / levels / elevations


class ProjectBrowser(QWidget):
    """
    Project Browser panel.  Embed in a QDockWidget.

    Parameters
    ----------
    parent : QWidget | None
    """

    activateModelSpace = pyqtSignal()
    activatePaperSheet = pyqtSignal(str)   # sheet name

    # Stub categories under 2D Model (Plans and Elevations are live)
    _MS_STUBS = ["Schematics", "Details", "Schedules"]

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
        self._tree.itemActivated.connect(self._on_item_activated)
        layout.addWidget(self._tree)

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._build_tree()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_scale_manager(self, sm):
        self._scale_manager = sm

    def _fmt_elev(self, elev_mm: float) -> str:
        """Format a level elevation using the ScaleManager."""
        if self._scale_manager:
            return self._scale_manager.format_length(elev_mm)
        return f"{elev_mm:.1f} mm"

    def set_sheets(self, sheet_names: list[str]):
        """
        Refresh the Paper Space children with the given sheet names.
        Call this whenever sheets are added/removed.
        """
        self._paper_root.takeChildren()
        for name in sheet_names:
            item = QTreeWidgetItem(self._paper_root, [name])
            item.setData(0, _ROLE_TYPE, "sheet")
            item.setData(0, _ROLE_NAME, name)
        self._paper_root.setExpanded(True)

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
        self._plans_root.setExpanded(True)

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
        self._elev_root = elev_root

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

        # Default single sheet
        self.set_sheets(["Layout 1"])

    def _on_item_activated(self, item: QTreeWidgetItem, _col: int):
        role = item.data(0, _ROLE_TYPE)
        if role in ("model_root", "ms_stub", "plan", "elevation"):
            # For now: plans and elevations activate model space
            self.activateModelSpace.emit()
        elif role == "sheet":
            name = item.data(0, _ROLE_NAME)
            self.activatePaperSheet.emit(name)
