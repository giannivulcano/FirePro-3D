"""NewSchematicDialog — the Project Browser's New Schematic… picker.

Shape ratified at the 2026-10-09 mockup gate (schematics.md D-S9; concept
SD6 Option A): one tree whose first leaf is **Blank schematic** (pre-selected)
followed by a **Templates** root listing the templates folder
(``app_data.schematics_dir()``) — ungrouped leaves first, then Series
folders. Search filters templates; Blank is always listed. Double-click or
**Create** accepts. The caller (``MainWindow._new_schematic``) opens a blank
Schematic editor or loads the chosen ``.fpdb`` into the project through the
shared block loader and opens its editor.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QDialogButtonBox, QFrame, QLabel, QLineEdit,
                             QStackedWidget, QTreeWidget, QTreeWidgetItem)

from . import block_library
from .house_dialog import HouseDialog
from .theme import M

_ROLE_KIND = Qt.ItemDataRole.UserRole          # "blank" | "template" (leaves only)
_ROLE_PATH = Qt.ItemDataRole.UserRole + 1      # template .fpdb path
_ROLE_ID = Qt.ItemDataRole.UserRole + 2        # template definition id

EMPTY_NO_MATCH = "No templates match"
BLANK_TIP = "Start from an empty Schematic editor"
TEMPLATE_TIP = "Template — Create copies it into the project, then opens it"


def _template_entries(root: str | None) -> list[dict]:
    """Index entries of the templates folder that are schematics.

    ``root`` None = the configured ``app_data.schematics_dir()`` (resolved
    here so a changed override is honoured on every open)."""
    from .app_data import schematics_dir
    return [e for e in block_library.list_library(
                root if root is not None else schematics_dir())
            if e.get("kind") == "schematic"]


class NewSchematicDialog(HouseDialog):
    """Pick Blank or a template for a new schematic (schematics.md D-S9).

    Args:
        parent: Optional Qt parent.
        root: Templates root override (None = ``app_data.schematics_dir()``).
    """

    @staticmethod
    def has_templates(root: str | None = None) -> bool:
        """True when the templates folder lists at least one schematic."""
        return bool(_template_entries(root))

    def __init__(self, parent=None, *, root: str | None = None) -> None:
        super().__init__(parent, title="New Schematic", min_width=M.BLOCK_OPEN_MIN_W)
        # Resolved ONCE: block_library's own ``root=None`` means the BLOCK
        # library, never the templates folder (schematics.md D-S5).
        from .app_data import schematics_dir
        self._lib_root = root if root is not None else schematics_dir()
        self._choice: tuple | None = None

        lay = self.body_layout()
        lay.setSpacing(M.SECTION_GAP)

        self._search = QLineEdit(placeholderText="Search templates…")
        self._search.setClearButtonEnabled(True)
        self._search.setToolTip("Filter the templates by name")
        self._search.textChanged.connect(self._apply_search)
        lay.addWidget(self._search)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setFrameShape(QFrame.Shape.NoFrame)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(16)
        from .ui_kit import browser_tree_qss
        self._tree.setStyleSheet(browser_tree_qss())

        from .theme import detect
        t = detect()
        self._empty_lbl = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setWordWrap(True)
        self._empty_lbl.setStyleSheet(
            f"color: {t.muted}; font-size: {M.BLOCK_OPEN_EMPTY_PT}pt;"
            f" background: {t.surface};")
        self._list_stack = QStackedWidget()
        self._list_stack.setMinimumHeight(M.BLOCK_OPEN_LIST_H)
        self._list_stack.addWidget(self._tree)
        self._list_stack.addWidget(self._empty_lbl)
        lay.addWidget(self._list_stack, 1)

        self._populate()

        btns = self.set_footer_buttons(primary=("Create", self._accept_choice))
        self._create_btn = btns["primary"]
        self._create_btn.setToolTip(
            "Open a Schematic editor (a template is copied into the project)")
        cancel = self._footer_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel is not None:
            cancel.setToolTip("Close without creating a schematic")
        self._tree.currentItemChanged.connect(self._sync_create_enabled)
        self._tree.itemActivated.connect(self._on_item_activated)
        self._sync_create_enabled()
        self._tree.setFocus()

    # ── data ──────────────────────────────────────────────────────────────

    def _populate(self) -> None:
        """Blank leaf first (selected), then Templates ▸ ungrouped ▸ Series."""
        f_bold = QFont()
        f_bold.setBold(True)
        blank = QTreeWidgetItem(self._tree, ["Blank schematic"])
        blank.setFont(0, f_bold)
        blank.setData(0, _ROLE_KIND, "blank")
        blank.setToolTip(0, BLANK_TIP)

        grouped: dict[str, list[tuple[str, str, str]]] = {}
        for e in _template_entries(self._lib_root):
            grouped.setdefault(e["series"], []).append(
                (e.get("name") or e["filename"], e.get("id", ""),
                 block_library.entry_path(e, self._lib_root)))
        if grouped:
            root = QTreeWidgetItem(self._tree, ["Templates"])
            root.setFont(0, f_bold)
            for name, block_id, path in sorted(grouped.get("", []),
                                               key=lambda x: x[0].lower()):
                self._leaf(root, name, block_id, path)
            for series in sorted((s for s in grouped if s), key=str.lower):
                s_item = QTreeWidgetItem(root, [series])
                s_item.setFont(0, f_bold)
                for name, block_id, path in sorted(grouped[series],
                                                   key=lambda x: x[0].lower()):
                    self._leaf(s_item, name, block_id, path)
        self._tree.expandAll()
        self._tree.setCurrentItem(blank)

    @staticmethod
    def _leaf(parent: QTreeWidgetItem, name: str, block_id: str,
              path: str) -> QTreeWidgetItem:
        leaf = QTreeWidgetItem(parent, [name])
        leaf.setData(0, _ROLE_KIND, "template")
        leaf.setData(0, _ROLE_PATH, path)
        leaf.setData(0, _ROLE_ID, block_id)
        leaf.setToolTip(0, TEMPLATE_TIP)
        return leaf

    @staticmethod
    def _is_leaf(item: QTreeWidgetItem | None) -> bool:
        return item is not None and item.data(0, _ROLE_KIND) in ("blank", "template")

    # ── search ────────────────────────────────────────────────────────────

    def _apply_search(self, text: str) -> None:
        """Hide template leaves whose name lacks *text* and any folder left
        empty; the Blank leaf is never hidden."""
        needle = text.strip().lower()

        def walk(item: QTreeWidgetItem) -> bool:
            if item.data(0, _ROLE_KIND) == "blank":
                show = True
            elif self._is_leaf(item):
                show = not needle or needle in item.text(0).lower()
            else:
                show = False
                for i in range(item.childCount()):
                    show = walk(item.child(i)) or show
            item.setHidden(not show)
            return show

        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i))
        self._list_stack.setCurrentWidget(self._tree)   # Blank always listed
        self._sync_create_enabled()

    # ── choice ────────────────────────────────────────────────────────────

    def _sync_create_enabled(self, *_args) -> None:
        item = self._tree.currentItem()
        self._create_btn.setEnabled(self._is_leaf(item) and not item.isHidden())

    def _on_item_activated(self, item: QTreeWidgetItem, _col: int = 0) -> None:
        if self._is_leaf(item):
            self._tree.setCurrentItem(item)
            self._accept_choice()

    def _accept_choice(self) -> None:
        item = self._tree.currentItem()
        if not self._is_leaf(item) or item.isHidden():
            return
        if item.data(0, _ROLE_KIND) == "blank":
            self._choice = ("blank", None, None, None)
        else:
            self._choice = ("template", item.data(0, _ROLE_PATH),
                            item.data(0, _ROLE_ID), item.text(0))
        self.accept()

    def choice(self) -> tuple | None:
        """``("blank", None, None, None)`` or ``("template", path, id, name)``
        once accepted, else None."""
        return self._choice
