"""Block Manager — modeless MVC dialog over the project's block definitions.

Slice S4 of the Block system (see docs/specs/block-system.md and
docs/superpowers/specs/2026-09-04-block-manager-s4-design.md). Thin Qt view over
the Model_Space block-management API (instance_count / delete_block_definition /
reload_block_definition / set_block_metadata + blockInstancesChanged). Thumbnails
are DEFERRED.
"""
from __future__ import annotations

from enum import IntEnum

from PyQt6.QtCore import (Qt, QAbstractTableModel, QAbstractItemModel,
                          QModelIndex, QRectF, QSize)
from PyQt6.QtGui import QPainter, QFontMetrics
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFrame,
                             QPushButton, QLabel, QLineEdit, QTableView,
                             QTreeView, QAbstractItemView, QHeaderView,
                             QFormLayout, QWidget, QStyledItemDelegate)

from . import block_library
from .frameless_shell import FramelessShellMixin
from .theme import detect, build_block_manager_qss


def _format_load_summary(summary: dict) -> str:
    """Human summary of a load batch, omitting zero categories."""
    parts = []
    if summary["loaded"]:
        parts.append(f"Loaded {len(summary['loaded'])}")
    if summary["replaced"]:
        parts.append(f"replaced {len(summary['replaced'])}")
    if summary["skipped"]:
        parts.append(f"skipped {len(summary['skipped'])} (already present)")
    if summary["refused"]:
        parts.append(f"refused {len(summary['refused'])} (name in use)")
    if summary["failed"]:
        parts.append(f"{len(summary['failed'])} unreadable")
    return " · ".join(parts) if parts else "Nothing to load."


class Col(IntEnum):
    NAME = 0
    LIBRARY = 1
    SERIES = 2
    COUNT = 3
    STATUS = 4


_HEADERS = {Col.NAME: "Name", Col.LIBRARY: "Library", Col.SERIES: "Series",
            Col.COUNT: "Instances", Col.STATUS: "Source"}

BlockDefRole = Qt.ItemDataRole.UserRole + 1   # leaf -> BlockDefinition; group -> None


class _Node:
    """Explicit tree node. kind: 'library' | 'series' | 'block'."""
    __slots__ = ("kind", "label", "defn", "parent", "children", "row")

    def __init__(self, kind, label, defn, parent, row):
        self.kind = kind
        self.label = label        # display text for group rows
        self.defn = defn          # BlockDefinition on a 'block' leaf, else None
        self.parent = parent
        self.row = row
        self.children = []


class BlockTreeModel(QAbstractItemModel):
    """Library -> Series -> block tree over ``scene._block_definitions``.

    Live: resets on both ``blockDefinitionsChanged`` and ``blockInstancesChanged``
    (place/remove changes leaf counts). ``root`` overrides the library root for
    ``source_status`` (tests inject a temp dir; production passes None).
    """

    def __init__(self, scene, root: str | None = None, parent=None):
        super().__init__(parent)
        self._scene = scene
        self._root = root
        self._root_node = _Node("root", "", None, None, 0)
        self._counts: dict = {}
        self._rebuild()
        for signame in ("blockDefinitionsChanged", "blockInstancesChanged"):
            sig = getattr(scene, signame, None)
            if sig is not None:
                sig.connect(self._on_changed)

    # -- snapshot ----------------------------------------------------------
    def _rebuild(self) -> None:
        self._counts = {}
        for inst in self._scene._block_instances:
            self._counts[inst.block_id] = self._counts.get(inst.block_id, 0) + 1
        self._root_node = _Node("root", "", None, None, 0)
        grouped: dict = {}
        for d in self._scene._block_definitions.values():
            grouped.setdefault(d.library, {}).setdefault(d.series, []).append(d)
        for li, lib in enumerate(sorted(grouped)):
            lib_node = _Node("library", lib, None, self._root_node, li)
            self._root_node.children.append(lib_node)
            for si, ser in enumerate(sorted(grouped[lib])):
                ser_node = _Node("series", ser, None, lib_node, si)
                lib_node.children.append(ser_node)
                for bi, d in enumerate(sorted(grouped[lib][ser], key=lambda x: x.name)):
                    ser_node.children.append(_Node("block", d.name, d, ser_node, bi))

    def _on_changed(self) -> None:
        self.beginResetModel()
        self._rebuild()
        self.endResetModel()

    def refresh(self) -> None:
        """Re-read the definitions snapshot (e.g. after a library write that
        changed source-status but did not mutate the registry)."""
        self._on_changed()

    def _node(self, index) -> _Node:
        return index.internalPointer() if index.isValid() else self._root_node

    def definition_at_index(self, index):
        node = self._node(index)
        return node.defn if node.kind == "block" else None

    def index_for_id(self, block_id):
        """QModelIndex of the leaf whose definition id == block_id (else invalid)."""
        for lib in self._root_node.children:
            for ser in lib.children:
                for leaf in ser.children:
                    if leaf.defn is not None and leaf.defn.id == block_id:
                        return self.createIndex(leaf.row, 0, leaf)
        return QModelIndex()

    # -- tree structure ----------------------------------------------------
    def index(self, row, column, parent=QModelIndex()):
        if row < 0 or column < 0 or column >= len(Col):
            return QModelIndex()
        parent_node = self._node(parent)
        if row >= len(parent_node.children):
            return QModelIndex()
        return self.createIndex(row, column, parent_node.children[row])

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        node = index.internalPointer()
        p = node.parent
        if p is None or p is self._root_node:
            return QModelIndex()
        return self.createIndex(p.row, 0, p)

    def rowCount(self, parent=QModelIndex()):
        return len(self._node(parent).children)

    def columnCount(self, parent=QModelIndex()):
        return len(Col)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if (orientation == Qt.Orientation.Horizontal
                and role == Qt.ItemDataRole.DisplayRole):
            return _HEADERS.get(Col(section), "")
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    # -- data --------------------------------------------------------------
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node = index.internalPointer()
        if role == BlockDefRole:
            return node.defn if node.kind == "block" else None
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        col = index.column()
        if node.kind != "block":
            # group rows: only the NAME column shows the label
            return node.label if col == Col.NAME else None
        d = node.defn
        if col == Col.NAME:
            return d.name
        if col == Col.LIBRARY:
            return d.library
        if col == Col.SERIES:
            return d.series
        if col == Col.COUNT:
            return str(self._counts.get(d.id, 0))
        if col == Col.STATUS:
            return block_library.source_status(d, root=self._root)
        return None


# ---------------------------------------------------------------------------
# SourceStatusDelegate — status badge
# ---------------------------------------------------------------------------

_STATUS_TOKEN = {"project-only": "muted", "library": "ok", "modified": "warn"}


class SourceStatusDelegate(QStyledItemDelegate):
    """Paint the source-status column as a rounded pill (level-chip pattern).

    Falls back to a plain text draw if the theme lacks the mapped token.
    """

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.t = theme

    def token_for(self, status: str) -> str:
        """Return the theme token name for *status*."""
        return _STATUS_TOKEN.get(status, "muted")

    def paint(self, painter, option, index):
        status = index.data(Qt.ItemDataRole.DisplayRole) or ""
        token = self.token_for(status)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fm = QFontMetrics(option.font)
        text = status
        w = fm.horizontalAdvance(text) + 16
        r = QRectF(option.rect.x() + 6, option.rect.center().y() - 9, w, 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.t.color(token, 40))
        painter.drawRoundedRect(r, 9, 9)
        painter.setPen(self.t.color(token))
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(110, 34)


# ---------------------------------------------------------------------------
# BlockManagerDialog — modeless chrome + table + details panel
# ---------------------------------------------------------------------------

class BlockManagerDialog(FramelessShellMixin, QDialog):
    """Modeless Block Manager — instant apply, no OK/Apply. Open with ``.show()``."""

    def __init__(self, scene, main_window, theme=None, parent=None,
                 apply_stylesheet: bool = True, root: str | None = None):
        theme = theme or detect()
        super().__init__(parent)
        self.init_frameless_shell(title="Block Manager",
                                  controls=("min", "max", "close"),
                                  resizable=True)
        self.scene = scene
        self.main_window = main_window
        self.t = theme
        self._root = root
        self.setObjectName("BlockManagerDialog")
        self.setWindowTitle("Block Manager")
        if apply_stylesheet:
            self.setStyleSheet(build_block_manager_qss(theme))
        self.setMinimumSize(720, 420)
        self.resize(980, 520)
        self.setModal(False)

        self.model = BlockTreeModel(scene, root=root, parent=self)
        self._build_ui()
        self._wire()
        self._sync_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._titlebar)

        toolbar = QFrame(objectName="toolbarBar")
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(12, 9, 12, 9)
        bar.setSpacing(8)
        self.btn_load = QPushButton("Load from Library…")
        self.btn_load.setProperty("variant", "primary")
        self.btn_save = QPushButton("Save to Library")
        self.btn_reload = QPushButton("Reload from Library")
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setProperty("variant", "danger")
        self.btn_editor = QPushButton("Open in Editor")
        for w in (self.btn_load, self.btn_save, self.btn_reload,
                  self.btn_delete, self.btn_editor):
            bar.addWidget(w)
        bar.addStretch(1)
        root.addWidget(toolbar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.view = QTreeView(objectName="underlayTable")
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setRootIsDecorated(True)
        self.view.setItemDelegateForColumn(
            Col.STATUS, SourceStatusDelegate(self.t, self.view))
        header = self.view.header()
        header.setStretchLastSection(True)
        for col, width in ((Col.NAME, 220), (Col.LIBRARY, 120),
                           (Col.SERIES, 120), (Col.COUNT, 70), (Col.STATUS, 110)):
            self.view.setColumnWidth(col, width)
        self.view.expandAll()
        body.addWidget(self.view, 1)

        self.details = self._build_details_panel()
        body.addWidget(self.details)
        root.addLayout(body, 1)

        footer = QFrame(objectName="footerBar")
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(12, 8, 12, 8)
        self.count_label = QLabel()
        self.count_label.setProperty("role", "muted")
        self.btn_close = QPushButton("Close")
        foot.addWidget(self.count_label)
        foot.addStretch(1)
        foot.addWidget(self.btn_close)
        root.addWidget(footer)

    def _build_details_panel(self) -> QWidget:
        panel = QFrame(objectName="detailsPanel")
        panel.setFixedWidth(268)
        form = QFormLayout(panel)
        form.setContentsMargins(14, 14, 14, 14)
        self.ed_name = QLineEdit()
        self.ed_library = QLineEdit()
        self.ed_series = QLineEdit()
        self.lbl_status = QLabel()
        self.lbl_count = QLabel()
        form.addRow("Name", self.ed_name)
        form.addRow("Library", self.ed_library)
        form.addRow("Series", self.ed_series)
        form.addRow("Source", self.lbl_status)
        form.addRow("Instances", self.lbl_count)
        return panel

    # ---------------------------------------------------------------- wiring
    def _wire(self) -> None:
        self.btn_close.clicked.connect(self.close)
        self.btn_load.clicked.connect(self._load_from_library)
        self.btn_delete.clicked.connect(self._delete)
        self.btn_save.clicked.connect(self._save_to_library)
        self.btn_reload.clicked.connect(self._reload)
        self.btn_editor.clicked.connect(self._open_in_editor)
        self.view.selectionModel().selectionChanged.connect(lambda *_: self._sync_ui())
        # Preserve the selected row across model resets (e.g. after a metadata
        # edit emits blockDefinitionsChanged → beginResetModel/endResetModel
        # clears the selection). Snapshot the id before the reset, then
        # re-select by id after. _after_reset calls _sync_ui itself so the
        # panel repopulates; we do NOT also connect modelReset→_sync_ui
        # directly to avoid double-calling.
        self._selected_id_before_reset: str | None = None
        self.model.modelAboutToBeReset.connect(self._before_reset)
        self.model.modelReset.connect(self._after_reset)
        for ed in (self.ed_name, self.ed_library, self.ed_series):
            ed.editingFinished.connect(self._commit_metadata)

    # ------------------------------------------------- reset guard (selection)
    def _before_reset(self) -> None:
        """Snapshot the currently-selected definition's id before a model reset."""
        defn = self._current_def()
        self._selected_id_before_reset = defn.id if defn is not None else None

    def _after_reset(self) -> None:
        """After a model reset, re-select the previously-selected leaf (by id).

        If the id no longer exists (e.g. after Delete), selects nothing —
        the panel blanks, which is the correct post-delete state. Calls
        _sync_ui so the details panel repopulates in either case.
        """
        block_id = getattr(self, "_selected_id_before_reset", None)
        if block_id is not None:
            idx = self.model.index_for_id(block_id)
            if idx.isValid():
                self.view.setCurrentIndex(idx)
        self._sync_ui()

    # ------------------------------------------------------------- selection
    def _current_def(self):
        idxs = self.view.selectionModel().selectedRows()
        if not idxs:
            return None
        return self.model.definition_at_index(idxs[0])

    def _sync_ui(self) -> None:
        defn = self._current_def()
        n_def = len(self.scene._block_definitions)
        n_inst = len(self.scene._block_instances)
        self.count_label.setText(f"{n_def} blocks · {n_inst} instances")
        has = defn is not None
        for ed in (self.ed_name, self.ed_library, self.ed_series):
            ed.setEnabled(has)
        if not has:
            self.ed_name.clear()
            self.ed_library.clear()
            self.ed_series.clear()
            self.lbl_status.clear()
            self.lbl_count.clear()
            for b in (self.btn_save, self.btn_reload, self.btn_delete, self.btn_editor):
                b.setEnabled(False)
            return
        # block signals so setText doesn't retrigger editingFinished commits
        for ed, val in ((self.ed_name, defn.name), (self.ed_library, defn.library),
                        (self.ed_series, defn.series)):
            ed.blockSignals(True)
            ed.setText(val)
            ed.blockSignals(False)
        status = block_library.source_status(defn, root=self._root)
        count = self.scene.instance_count(defn.id)
        self.lbl_status.setText(status)
        self.lbl_count.setText(str(count))
        self.btn_delete.setEnabled(True)
        self.btn_editor.setEnabled(True)
        self.btn_save.setEnabled(status in ("project-only", "modified"))
        self.btn_reload.setEnabled(status == "modified")

    # -------------------------------------------------------------- actions
    def _commit_metadata(self) -> None:
        defn = self._current_def()
        if defn is None:
            return
        ok = self.scene.set_block_metadata(
            defn.id, self.ed_name.text(), self.ed_library.text(),
            self.ed_series.text())
        if not ok:
            # revert-on-invalid
            self._sync_ui()

    def _delete(self) -> None:
        from .themed_message import themed_info
        defn = self._current_def()
        if defn is None:
            return
        n = self.scene.instance_count(defn.id)
        if n > 0:
            themed_info(self, "Delete Block",
                        f"Can’t delete “{defn.name}” — {n} instance(s) in the model.")
            return
        self.scene.delete_block_definition(defn.id)

    def _save_to_library(self) -> None:
        from .themed_message import themed_info
        defn = self._current_def()
        if defn is None:
            return
        try:
            block_library.save_to_library(defn, root=self._root)
            self.model.refresh()  # force table cell repaint (status col)
        except OSError as exc:
            themed_info(self, "Save to Library", f"Could not save:\n{exc}")
            self._sync_ui()

    def _reload(self) -> None:
        defn = self._current_def()
        if defn is None:
            return
        self.scene.reload_block_definition(defn.id, root=self._root)

    def _load_from_library(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        from .app_data import app_data_dir
        from .themed_message import themed_info
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Load Blocks", app_data_dir("blocks"),
            "FirePro3D Blocks (*.fpdb)")
        if not paths:
            return
        summary = self.scene.load_blocks_from_files(paths, root=self._root)
        themed_info(self, "Load from Library", _format_load_summary(summary))

    def _open_in_editor(self) -> None:
        from .themed_message import themed_info
        if self._current_def() is None:
            return
        themed_info(self, "Block Editor",
                    "The Block Editor arrives in a later slice.")
