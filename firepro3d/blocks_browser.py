"""BlocksBrowser — left-dock tree of the project's block definitions.

Mirrors feature_browser.py: Library > Series > block leaf; activating a leaf
emits blockActivated(id), which the app routes into place_block mode.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
                             QFrame)


class BlocksBrowser(QWidget):
    """Tree browser of embedded block definitions (Library > Series > block).

    Same tree chrome as the sibling browsers (feature/model/project): 16px
    indentation with decorated root chevrons, no frame, 4px margins, and bold
    grouping (folder) rows over regular-weight leaves.
    """

    blockActivated = pyqtSignal(str)

    def __init__(self, scene, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = scene
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
        self.refresh()

    def _grouped(self) -> dict:
        """Group block definitions as {library: {series: [BlockDefinition, ...]}}."""
        tree: dict = {}
        for b in self._scene._block_definitions.values():
            tree.setdefault(b.library, {}).setdefault(b.series, []).append(b)
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
        """Rebuild the tree from the current block registry, keeping the
        user's collapsed folders collapsed (new folders open by default)."""
        collapsed = self._collapsed_paths()
        self._tree.clear()
        f_bold = QFont()
        f_bold.setBold(True)
        grouped = self._grouped()
        for library in sorted(grouped):
            lib_item = QTreeWidgetItem(self._tree, [library])
            lib_item.setFont(0, f_bold)
            for series in sorted(grouped[library]):
                s_item = QTreeWidgetItem(lib_item, [series])
                s_item.setFont(0, f_bold)
                for b in sorted(grouped[library][series], key=lambda x: x.name):
                    leaf = QTreeWidgetItem(s_item, [b.name])
                    leaf.setData(0, Qt.ItemDataRole.UserRole, b.id)
                s_item.setExpanded((library, series) not in collapsed)
            lib_item.setExpanded((library,) not in collapsed)

    def _on_item_activated(self, item: QTreeWidgetItem, col: int) -> None:
        """Emit blockActivated with the leaf's block id (ignores group rows)."""
        block_id = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(block_id, str) and block_id:
            self.blockActivated.emit(block_id)
