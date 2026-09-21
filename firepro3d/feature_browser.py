"""
feature_browser.py — read-only Feature Browser tree panel (§7.13).

Lists loaded Features grouped Feature → Family → Type-leaf
(docs/specs/feature-system.md F4).  Activating a Type leaf emits
featureActivated(str) with the FeatureDef id, which the app uses to enter
opening placement mode.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFrame,
    QTreeWidget,
    QTreeWidgetItem,
    QSizePolicy,
)

from .feature import features_by_hierarchy


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
        self._tree.setFrameShape(QFrame.Shape.NoFrame)   # no faded inset border
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(16)
        from firepro3d.ui_kit import browser_tree_qss
        self._tree.setStyleSheet(browser_tree_qss())
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
        """Populate tree: Feature → Family → Type leaf."""
        data = features_by_hierarchy()
        for feature, families in sorted(data.items()):
            feat_item = QTreeWidgetItem(self._tree, [feature])
            feat_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )
            for family, fdefs in sorted(families.items()):
                fam_item = QTreeWidgetItem(feat_item, [family])
                fam_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                )
                for fdef in sorted(fdefs, key=lambda f: f.type_name):
                    leaf = QTreeWidgetItem(fam_item, [fdef.type_name])
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
