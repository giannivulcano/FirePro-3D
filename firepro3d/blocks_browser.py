"""BlocksBrowser — left-dock tree of the block library + the project's blocks.

Library > Series > block. The tree is the on-disk block library (every
Library/Series folder, even empty, and every indexed ``.fpdb``) merged with
the project's embedded definitions: a block already in the project shows in
regular weight, a library-only block in italic/dimmed. Activating a project
block emits ``blockActivated(id)`` (the app routes it into place_block mode);
activating a library-only block first loads it into the project (one undoable
batch via ``Model_Space.load_blocks_from_files``) and then emits the same.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
                             QFrame)

from . import block_library

_ROLE_ID = Qt.ItemDataRole.UserRole          # block id (project or library)
_ROLE_PATH = Qt.ItemDataRole.UserRole + 1    # .fpdb path for library-only leaves


class BlocksBrowser(QWidget):
    """Tree browser of the block library + project blocks (Library > Series > block).

    Same tree chrome as the sibling browsers (feature/model/project): 16px
    indentation with decorated root chevrons, no frame, 4px margins, and bold
    grouping (folder) rows over regular-weight leaves.

    Args:
        scene: The project ``Model_Space`` (block registry + loader).
        parent: Optional Qt parent.
        root: Block-library root override (None = the configured library).
    """

    blockActivated = pyqtSignal(str)

    def __init__(self, scene, parent: QWidget | None = None, *,
                 root: str | None = None) -> None:
        super().__init__(parent)
        self._scene = scene
        self._lib_root = root
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setFrameShape(QFrame.Shape.NoFrame)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(16)
        from firepro3d.ui_kit import browser_tree_qss
        self._tree.setStyleSheet(browser_tree_qss())
        self._tree.itemActivated.connect(self._on_item_activated)
        self._tree.itemDoubleClicked.connect(self._on_item_activated)
        layout.addWidget(self._tree)
        if hasattr(scene, "blockDefinitionsChanged"):
            scene.blockDefinitionsChanged.connect(self.refresh)
        block_library.add_change_listener(self.refresh)
        self.refresh()

    def showEvent(self, event):  # noqa: N802 (Qt API)
        # Re-read on show: the library root is a preference that can change
        # (System Settings) and other processes may write the folder.
        super().showEvent(event)
        self.refresh()

    # ── data ──────────────────────────────────────────────────────────────

    def _grouped(self) -> dict:
        """``{library: {series: [(name, id, path|None), ...]}}`` — the on-disk
        folders + indexed blocks merged with the project's definitions (a
        library entry whose id is in the project is listed once, as project)."""
        registry = self._scene._block_definitions
        tree: dict = {}
        for lib, series in block_library.list_folders(self._lib_root).items():
            node = tree.setdefault(lib, {})
            for ser in series:
                node.setdefault(ser, [])
        seen: set = set()
        for b in registry.values():
            tree.setdefault(b.library, {}).setdefault(b.series, []).append(
                (b.name, b.id, None))
            seen.add(b.id)
        for e in block_library.list_library(self._lib_root):
            if e.get("id") in seen:
                continue
            path = block_library.entry_path(e, self._lib_root)
            tree.setdefault(e["library"], {}).setdefault(e["series"], []).append(
                (e.get("name") or e["filename"], e.get("id", ""), path))
        return tree

    def _collapsed_paths(self) -> set:
        """``(library,)`` / ``(library, series)`` keys the user has collapsed."""
        out = set()
        for i in range(self._tree.topLevelItemCount()):
            lib = self._tree.topLevelItem(i)
            if not lib.isExpanded():
                out.add((lib.text(0),))
            for j in range(lib.childCount()):
                ser = lib.child(j)
                if not ser.isExpanded():
                    out.add((lib.text(0), ser.text(0)))
        return out

    def refresh(self) -> None:
        """Rebuild the tree, keeping the user's collapsed folders collapsed
        (new folders open by default)."""
        collapsed = self._collapsed_paths()
        self._tree.clear()
        f_bold = QFont()
        f_bold.setBold(True)
        f_lib = QFont()
        f_lib.setItalic(True)
        from . import theme as th
        dim = QBrush(QColor(th.detect().muted))
        grouped = self._grouped()
        for library in sorted(grouped):
            lib_item = QTreeWidgetItem(self._tree, [library])
            lib_item.setFont(0, f_bold)
            for series in sorted(grouped[library]):
                s_item = QTreeWidgetItem(lib_item, [series])
                s_item.setFont(0, f_bold)
                for name, block_id, path in sorted(grouped[library][series],
                                                   key=lambda x: x[0].lower()):
                    leaf = QTreeWidgetItem(s_item, [name])
                    leaf.setData(0, _ROLE_ID, block_id)
                    if path is None:
                        leaf.setToolTip(0, "Double-click to place")
                    else:
                        leaf.setData(0, _ROLE_PATH, path)
                        leaf.setFont(0, f_lib)
                        leaf.setForeground(0, dim)
                        leaf.setToolTip(0, "In the library — double-click to "
                                           "load into the project and place")
                s_item.setExpanded((library, series) not in collapsed)
            lib_item.setExpanded((library,) not in collapsed)

    # ── activation ────────────────────────────────────────────────────────

    def _on_item_activated(self, item: QTreeWidgetItem, col: int) -> None:
        """Place a block leaf; a library-only leaf is loaded first."""
        block_id = item.data(0, _ROLE_ID)
        if not isinstance(block_id, str) or not block_id:
            return                                   # folder row
        path = item.data(0, _ROLE_PATH)
        if path and block_id not in self._scene._block_definitions:
            summary = self._scene.load_blocks_from_files([path], root=self._lib_root)
            if block_id not in self._scene._block_definitions:
                from .themed_message import themed_info
                why = ("a different block already uses this name in the project"
                       if summary.get("refused") else "the file could not be read")
                themed_info(self, "Load block",
                            f"Could not load “{item.text(0)}”: {why}.")
                return
        self.blockActivated.emit(block_id)
