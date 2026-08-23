"""
feature_browser.py — read-only Feature Browser tree panel (§7.13).

Lists loaded Features grouped Category → Type → Feature-leaf.
Activating a leaf emits featureActivated(str) with the Feature id,
which the app uses to enter opening placement mode.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QSizePolicy,
)

from .feature import features_by_category


class FeatureBrowser(QWidget):
    """
    Read-only Feature Browser panel.  Embed in a QTabWidget or QDockWidget.

    Signals:
        featureActivated(str): emitted when a leaf Feature item is activated,
            carrying the FeatureDef.id.
    """

    featureActivated = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(16)
        self._tree.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )

        self._tree.itemActivated.connect(self._on_item_activated)
        self._tree.itemDoubleClicked.connect(self._on_item_activated)

        layout.addWidget(self._tree)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self.refresh()

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Clear and rebuild the tree from the current feature registry."""
        self._tree.clear()
        self._build_tree()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_tree(self) -> None:
        """Populate tree: Category → Type → FeatureDef leaf."""
        data = features_by_category()
        for category, types in sorted(data.items()):
            cat_item = QTreeWidgetItem(self._tree, [category])
            cat_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )
            for type_key, fdefs in sorted(types.items()):
                type_item = QTreeWidgetItem(cat_item, [type_key.title()])
                type_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                )
                for fdef in sorted(fdefs, key=lambda f: f.display_name):
                    leaf = QTreeWidgetItem(type_item, [fdef.display_name])
                    leaf.setData(0, Qt.ItemDataRole.UserRole, fdef.id)
                    leaf.setFlags(
                        Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                    )
        self._tree.expandAll()

    def _on_item_activated(self, item: QTreeWidgetItem, col: int) -> None:
        """Emit featureActivated if item is a leaf (carries a feature id)."""
        feature_id = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(feature_id, str) and feature_id:
            self.featureActivated.emit(feature_id)

    def _find_leaf(self, feature_id: str) -> QTreeWidgetItem | None:
        """
        Return the leaf QTreeWidgetItem whose stored id == *feature_id*,
        or None if not found.
        """
        return self._search_items(self._tree.invisibleRootItem(), feature_id)

    def _search_items(
        self, parent: QTreeWidgetItem, feature_id: str
    ) -> QTreeWidgetItem | None:
        for i in range(parent.childCount()):
            child = parent.child(i)
            stored = child.data(0, Qt.ItemDataRole.UserRole)
            if stored == feature_id:
                return child
            result = self._search_items(child, feature_id)
            if result is not None:
                return result
        return None
