"""BlockOpenDialog — the Block Editor tab's Open… picker.

A compact house dialog: a search box over a tree grouped **Project** (the
project's block definitions) then **Library** ▸ library ▸ series (library-only
blocks — on-disk blocks not yet in the project). Choosing a library-only block
loads it into the project (``blocks_browser.ensure_block_loaded``, the same
loader the Blocks browser uses) before the dialog accepts; the caller then
opens ``chosen_id()`` in the Block Editor. See docs/specs/block-system.md and
docs/specs/ribbon-bar.md (Block Editor tab).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QDialogButtonBox, QFrame, QLabel, QLineEdit,
                             QStackedWidget, QTreeWidget, QTreeWidgetItem)

from .blocks_browser import (_ROLE_ID, _ROLE_PATH, ensure_block_loaded,
                             library_only_entries)
from .house_dialog import HouseDialog
from .theme import M

EMPTY_NO_BLOCKS = "No blocks yet — create one with New"
EMPTY_NO_MATCH = "No blocks match"


class BlockOpenDialog(HouseDialog):
    """Pick a project or library block to open in the Block Editor.

    Project blocks are listed first; library-only blocks (not yet in the
    project) are grouped library ▸ series and are loaded into the project on
    Open (ribbon-bar.md Block Editor tab; block-system.md).

    Args:
        scene: The project ``Model_Space`` (block registry + loader).
        parent: Optional Qt parent.
        root: Block-library root override (None = the configured library).
    """

    def __init__(self, scene, parent=None, *, root: str | None = None) -> None:
        super().__init__(parent, title="Open Block", min_width=M.BLOCK_OPEN_MIN_W)
        self._scene = scene
        self._lib_root = root
        self._chosen: str | None = None

        lay = self.body_layout()
        lay.setSpacing(M.SECTION_GAP)

        self._search = QLineEdit(placeholderText="Search blocks…")
        self._search.setClearButtonEnabled(True)
        self._search.setToolTip("Filter the list by block name")
        self._search.textChanged.connect(self._apply_search)
        lay.addWidget(self._search)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setFrameShape(QFrame.Shape.NoFrame)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(16)
        from .ui_kit import browser_tree_qss
        self._tree.setStyleSheet(browser_tree_qss())

        # Empty state shares the list area (stack page 1): no blocks at all,
        # or a search that matches nothing.
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
        self._sync_empty_state()

        btns = self.set_footer_buttons(primary=("Open", self._accept_choice))
        self._open_btn = btns["primary"]
        self._tree.currentItemChanged.connect(self._sync_open_enabled)
        self._tree.itemActivated.connect(self._on_item_activated)
        self._open_btn.setToolTip("Open the selected block in the Block Editor "
                                  "(a library block is loaded into the project)")
        cancel = self._footer_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel is not None:
            cancel.setToolTip("Close without opening a block")
        self._sync_open_enabled()
        self._search.setFocus()

    # ── data ──────────────────────────────────────────────────────────────

    def _populate(self) -> None:
        """Build the Project / Library roots (empty roots are omitted)."""
        f_bold = QFont()
        f_bold.setBold(True)

        project = sorted((d for d in self._scene._block_definitions.values()
                          if d.kind != "schematic"),      # D-S4
                         key=lambda d: d.name.lower())
        if project:
            root = QTreeWidgetItem(self._tree, ["Project"])
            root.setFont(0, f_bold)
            for d in project:
                self._leaf(root, d.name, d.id, None,
                           "In the project — open it in the Block Editor")

        grouped: dict = {}
        for lib, ser, name, block_id, path in library_only_entries(
                self._scene, self._lib_root):
            grouped.setdefault(lib, {}).setdefault(ser, []).append(
                (name, block_id, path))
        if grouped:
            root = QTreeWidgetItem(self._tree, ["Library"])
            root.setFont(0, f_bold)
            for lib in sorted(grouped):
                lib_item = QTreeWidgetItem(root, [lib])
                lib_item.setFont(0, f_bold)
                for ser in sorted(grouped[lib]):
                    s_item = QTreeWidgetItem(lib_item, [ser])
                    s_item.setFont(0, f_bold)
                    for name, block_id, path in sorted(grouped[lib][ser],
                                                       key=lambda x: x[0].lower()):
                        self._leaf(s_item, name, block_id, path,
                                   "In the library — Open loads it into the "
                                   "project, then edits it")
        self._tree.expandAll()

    @staticmethod
    def _leaf(parent: QTreeWidgetItem, name: str, block_id: str,
              path: str | None, tip: str) -> QTreeWidgetItem:
        leaf = QTreeWidgetItem(parent, [name])
        leaf.setData(0, _ROLE_ID, block_id)
        if path:
            leaf.setData(0, _ROLE_PATH, path)
        leaf.setToolTip(0, tip)
        return leaf

    @staticmethod
    def _is_leaf(item: QTreeWidgetItem | None) -> bool:
        if item is None:
            return False
        block_id = item.data(0, _ROLE_ID)
        return isinstance(block_id, str) and bool(block_id)

    # ── search ────────────────────────────────────────────────────────────

    def _apply_search(self, text: str) -> None:
        """Hide leaves whose name doesn't contain *text* (case-insensitive) and
        any folder left with no visible child."""
        needle = text.strip().lower()

        def walk(item: QTreeWidgetItem) -> bool:
            if self._is_leaf(item):
                show = not needle or needle in item.text(0).lower()
            else:
                show = False
                for i in range(item.childCount()):
                    show = walk(item.child(i)) or show
            item.setHidden(not show)
            return show

        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i))
        self._sync_empty_state()
        self._sync_open_enabled()

    def _sync_empty_state(self) -> None:
        """Show the muted empty message in place of the list when there is
        nothing to pick (no blocks at all, or no search match)."""
        roots = [self._tree.topLevelItem(i)
                 for i in range(self._tree.topLevelItemCount())]
        if not roots:
            self._empty_lbl.setText(EMPTY_NO_BLOCKS)
            self._list_stack.setCurrentWidget(self._empty_lbl)
        elif all(r.isHidden() for r in roots):
            self._empty_lbl.setText(EMPTY_NO_MATCH)
            self._list_stack.setCurrentWidget(self._empty_lbl)
        else:
            self._list_stack.setCurrentWidget(self._tree)

    # ── choice ────────────────────────────────────────────────────────────

    def _sync_open_enabled(self, *_args) -> None:
        item = self._tree.currentItem()
        ok = self._is_leaf(item) and not item.isHidden()
        self._open_btn.setEnabled(ok)

    def _on_item_activated(self, item: QTreeWidgetItem, _col: int = 0) -> None:
        if self._is_leaf(item):
            self._tree.setCurrentItem(item)
            self._accept_choice()

    def _accept_choice(self) -> None:
        """Load a library-only choice into the project, then accept."""
        item = self._tree.currentItem()
        if not self._is_leaf(item) or item.isHidden():
            return
        block_id = item.data(0, _ROLE_ID)
        path = item.data(0, _ROLE_PATH)
        if not ensure_block_loaded(self._scene, block_id, path, item.text(0),
                                   self._lib_root, self):
            return
        self._chosen = block_id
        self.accept()

    def chosen_id(self) -> str | None:
        """The accepted block's id (now a project definition), else None."""
        return self._chosen
