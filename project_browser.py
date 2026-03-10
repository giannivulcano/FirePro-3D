"""
project_browser.py
==================
Revit-style Project Browser dock widget.

Tree structure
--------------
  ▼ Model Space
      ▶ Plans          (future: elevation-linked plan views)
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

_ROLE_TYPE  = Qt.ItemDataRole.UserRole         # "model_root" | "ms_stub" | "paper_root" | "sheet"
_ROLE_NAME  = Qt.ItemDataRole.UserRole + 1     # str name for sheets


class ProjectBrowser(QWidget):
    """
    Project Browser panel.  Embed in a QDockWidget.

    Parameters
    ----------
    parent : QWidget | None
    """

    activateModelSpace = pyqtSignal()
    activatePaperSheet = pyqtSignal(str)   # sheet name

    # Labels shown under Model Space as stub placeholders
    _MS_STUBS = ["Plans", "Schematics", "Details", "Schedules"]

    def __init__(self, parent=None):
        super().__init__(parent)

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

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_tree(self):
        _t = th.detect()
        stub_brush = QBrush(QColor(_t.text_disabled if hasattr(_t, "text_disabled") else "#888888"))

        # ── Model Space root ─────────────────────────────────────────────────
        ms_root = QTreeWidgetItem(self._tree, ["2D Model"])
        ms_root.setData(0, _ROLE_TYPE, "model_root")
        f_bold = QFont(); f_bold.setBold(True)
        ms_root.setFont(0, f_bold)
        ms_root.setExpanded(True)

        for stub_name in self._MS_STUBS:
            stub = QTreeWidgetItem(ms_root, [stub_name])
            stub.setData(0, _ROLE_TYPE, "ms_stub")
            stub.setData(0, _ROLE_NAME, stub_name)
            stub.setForeground(0, stub_brush)
            stub.setToolTip(0, "Coming soon")
        self._ms_root = ms_root

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
        if role in ("model_root", "ms_stub"):
            # For now: stubs just activate model space (Plans maps to model space)
            self.activateModelSpace.emit()
        elif role == "sheet":
            name = item.data(0, _ROLE_NAME)
            self.activatePaperSheet.emit(name)
