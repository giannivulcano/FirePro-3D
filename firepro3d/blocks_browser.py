"""BlocksBrowser — left-dock tree of the project's block definitions.

Mirrors feature_browser.py: Library > Series > block leaf; activating a leaf
emits blockActivated(id), which the app routes into place_block mode.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem


class BlocksBrowser(QWidget):
    """Tree browser of embedded block definitions (Library > Series > block)."""

    blockActivated = pyqtSignal(str)

    def __init__(self, scene, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = scene
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
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

    def refresh(self) -> None:
        """Clear and rebuild the tree from the current block registry."""
        self._tree.clear()
        grouped = self._grouped()
        for library in sorted(grouped):
            lib_item = QTreeWidgetItem([library])
            self._tree.addTopLevelItem(lib_item)
            for series in sorted(grouped[library]):
                s_item = QTreeWidgetItem([series])
                lib_item.addChild(s_item)
                for b in sorted(grouped[library][series], key=lambda x: x.name):
                    leaf = QTreeWidgetItem([b.name])
                    leaf.setData(0, Qt.ItemDataRole.UserRole, b.id)
                    s_item.addChild(leaf)
            lib_item.setExpanded(True)

    def _on_item_activated(self, item: QTreeWidgetItem, col: int) -> None:
        """Emit blockActivated with the leaf's block id (ignores group rows)."""
        block_id = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(block_id, str) and block_id:
            self.blockActivated.emit(block_id)
