"""Block Manager — modeless MVC dialog over the project's block definitions.

Slice S4 of the Block system (see docs/specs/block-system.md and
docs/superpowers/specs/2026-09-04-block-manager-s4-design.md). Thin Qt view over
the Model_Space block-management API (instance_count / delete_block_definition /
reload_block_definition / set_block_metadata + blockInstancesChanged). Thumbnails
are DEFERRED.
"""
from __future__ import annotations

from enum import IntEnum

from PyQt6.QtCore import (Qt, QAbstractTableModel, QSortFilterProxyModel,
                          QModelIndex, QRectF, QSize, pyqtSignal, QRect, QPoint)

from PyQt6.QtGui import QPainter, QFontMetrics, QColor
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFrame,
                             QPushButton, QLabel, QLineEdit, QTableView,
                             QTreeView, QAbstractItemView, QHeaderView,
                             QFormLayout, QWidget, QStyledItemDelegate,
                             QCheckBox, QScrollArea)

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

BlockDefRole = Qt.ItemDataRole.UserRole + 1   # any cell -> its row's BlockDefinition
SortRole = Qt.ItemDataRole.UserRole + 2       # per-column sort key (numeric for COUNT)


class BlockTableModel(QAbstractTableModel):
    """Flat table over ``scene._block_definitions``. Live: resets on both
    ``blockDefinitionsChanged`` and ``blockInstancesChanged``. ``root`` overrides
    the library root for ``source_status`` (tests inject a temp dir)."""

    def __init__(self, scene, root: str | None = None, parent=None):
        super().__init__(parent)
        self._scene = scene
        self._root = root
        self._defs = []
        self._counts = {}
        self._rebuild()
        for signame in ("blockDefinitionsChanged", "blockInstancesChanged"):
            sig = getattr(scene, signame, None)
            if sig is not None:
                sig.connect(self._on_changed)

    def _rebuild(self):
        self._defs = list(self._scene._block_definitions.values())
        self._counts = {}
        for inst in self._scene._block_instances:
            self._counts[inst.block_id] = self._counts.get(inst.block_id, 0) + 1

    def _on_changed(self):
        self.beginResetModel()
        self._rebuild()
        self.endResetModel()

    def refresh(self):
        """Re-read the snapshot after a non-signalling change (e.g. Save-to-Library
        changes source-status without a registry mutation)."""
        self._on_changed()

    def definition_at_row(self, row):
        return self._defs[row] if 0 <= row < len(self._defs) else None

    def row_for_id(self, block_id):
        for r, d in enumerate(self._defs):
            if d.id == block_id:
                return r
        return -1

    def distinct_values(self, col):
        """Sorted distinct DisplayRole strings for *col* (funnel checkbox list)."""
        vals = {self._display(d, col) for d in self._defs}
        return sorted(vals)

    # -- Qt --
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._defs)

    def columnCount(self, parent=QModelIndex()):
        return len(Col)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if (orientation == Qt.Orientation.Horizontal
                and role == Qt.ItemDataRole.DisplayRole):
            return _HEADERS.get(Col(section), "")
        return None

    def _display(self, d, col):
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
        return ""

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        d = self._defs[index.row()]
        col = index.column()
        if role == BlockDefRole:
            return d
        if role == SortRole:
            if col == Col.COUNT:
                return self._counts.get(d.id, 0)          # numeric sort key
            return self._display(d, col)
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(d, col)
        return None


# ---------------------------------------------------------------------------
# BlockFilterProxy — per-column multi-select autofilter + numeric-aware sort
# ---------------------------------------------------------------------------

class BlockFilterProxy(QSortFilterProxyModel):
    """Per-column multi-select autofilter + numeric-aware sort.

    ``_accepted[col]`` is the set of accepted DisplayRole strings for that column;
    a column absent from the dict accepts everything. A row is shown iff every
    filtered column's display string is in its accepted set (AND across columns).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._accepted: dict = {}
        self.setSortRole(SortRole)

    def set_column_filter(self, col, accepted):
        """accepted: a set of DisplayRole strings, or None to clear the column."""
        if accepted is None:
            self._accepted.pop(col, None)
        else:
            self._accepted[col] = set(accepted)
        self.invalidateFilter()

    def is_filtered(self, col) -> bool:
        return col in self._accepted

    def clear_all(self):
        self._accepted.clear()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        m = self.sourceModel()
        for col, accepted in self._accepted.items():
            idx = m.index(source_row, col, source_parent)
            if m.data(idx, Qt.ItemDataRole.DisplayRole) not in accepted:
                return False
        return True


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
# _FilterPopup — Excel-style per-column filter popup
# ---------------------------------------------------------------------------

class _FilterPopup(QFrame):
    """Excel-style per-column filter popup: Sort A→Z/Z→A, search, (Select All),
    multi-select checkboxes, OK/Cancel. Emits ``applied(set|None)`` (None = all →
    clear) and ``sortRequested(bool ascending)``."""

    applied = pyqtSignal(object)          # set[str] chosen, or None when all chosen
    sortRequested = pyqtSignal(bool)

    def __init__(self, theme, label, values, accepted, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.t = theme
        self._all_values = list(values)
        self.setObjectName("detailsPanel")     # reuse themed surface styling
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        # sort rows
        b_az = QPushButton("Sort A → Z")
        b_za = QPushButton("Sort Z → A")
        b_az.clicked.connect(lambda: (self.sortRequested.emit(True), self.close()))
        b_za.clicked.connect(lambda: (self.sortRequested.emit(False), self.close()))
        lay.addWidget(b_az)
        lay.addWidget(b_za)
        # search
        self._search = QLineEdit(placeholderText=f"Search {label.lower()}…")
        self._search.textChanged.connect(self._apply_search)
        lay.addWidget(self._search)
        # (Select All)
        self._all = QCheckBox("(Select All)")
        self._all.setTristate(True)
        self._all.clicked.connect(self._toggle_all)
        lay.addWidget(self._all)
        # value list (scroll)
        self._boxes = []
        inner = QWidget()
        ilay = QVBoxLayout(inner)
        ilay.setContentsMargins(0, 0, 0, 0)
        ilay.setSpacing(2)
        for v in self._all_values:
            cb = QCheckBox(v)
            cb.setChecked(v in accepted)
            cb.stateChanged.connect(self._sync_all)
            self._boxes.append(cb)
            ilay.addWidget(cb)
        ilay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        scroll.setFixedHeight(180)
        lay.addWidget(scroll)
        # OK/Cancel
        row = QHBoxLayout()
        row.addStretch(1)
        b_cancel = QPushButton("Cancel"); b_cancel.clicked.connect(self.close)
        b_ok = QPushButton("OK"); b_ok.setProperty("variant", "primary")
        b_ok.clicked.connect(self._emit_ok)
        row.addWidget(b_cancel); row.addWidget(b_ok)
        lay.addLayout(row)
        self.resize(240, 320)
        self._sync_all()

    # -- test/support API --
    def chosen_values(self):
        return {cb.text() for cb in self._boxes if cb.isChecked()}

    def set_checked(self, values):
        for cb in self._boxes:
            cb.setChecked(cb.text() in values)
        self._sync_all()

    # -- internals --
    def _apply_search(self, q):
        q = q.lower()
        for cb in self._boxes:
            cb.setVisible(q in cb.text().lower())

    def _toggle_all(self):
        want = self._all.checkState() != Qt.CheckState.Checked
        for cb in self._boxes:
            cb.setChecked(want)
        self._sync_all()

    def _sync_all(self):
        checked = sum(cb.isChecked() for cb in self._boxes)
        self._all.blockSignals(True)
        if checked == 0:
            self._all.setCheckState(Qt.CheckState.Unchecked)
        elif checked == len(self._boxes):
            self._all.setCheckState(Qt.CheckState.Checked)
        else:
            self._all.setCheckState(Qt.CheckState.PartiallyChecked)
        self._all.blockSignals(False)

    def _emit_ok(self):
        chosen = self.chosen_values()
        self.applied.emit(None if len(chosen) == len(self._all_values) else chosen)
        self.close()


# ---------------------------------------------------------------------------
# FilterHeader — paints funnel glyphs + emits filterClicked
# ---------------------------------------------------------------------------

class FilterHeader(QHeaderView):
    """Horizontal header that paints a funnel glyph per section (highlighted when
    that column is filtered) and emits ``filterClicked(col)`` when the funnel
    region is clicked; other clicks fall through to normal sort."""

    filterClicked = pyqtSignal(int)
    _FUNNEL_W = 18

    def __init__(self, theme, is_filtered, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.t = theme
        self._is_filtered = is_filtered      # callable(col) -> bool
        self.setSectionsClickable(True)
        self.setSortIndicatorShown(True)

    def paintSection(self, painter, rect, index):
        super().paintSection(painter, rect, index)
        active = bool(self._is_filtered(index))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = rect.right() - self._FUNNEL_W + 4
        cy = rect.center().y()
        color = self.t.color("accent") if active else self.t.color("faint")
        painter.setPen(color)
        painter.setBrush(color if active else Qt.BrushStyle.NoBrush)
        # simple funnel: trapezoid + stem via a small polygon
        from PyQt6.QtGui import QPolygon
        pts = QPolygon([QPoint(cx, cy - 4), QPoint(cx + 10, cy - 4),
                        QPoint(cx + 6, cy), QPoint(cx + 6, cy + 4),
                        QPoint(cx + 4, cy + 4), QPoint(cx + 4, cy)])
        painter.drawPolygon(pts)
        painter.restore()

    def _funnel_rect(self, logical):
        x = self.sectionViewportPosition(logical) + self.sectionSize(logical) - self._FUNNEL_W
        return QRect(x, 0, self._FUNNEL_W, self.height())

    def mousePressEvent(self, event):
        logical = self.logicalIndexAt(event.pos())
        if logical >= 0 and self._funnel_rect(logical).contains(event.pos()):
            self.filterClicked.emit(logical)
            return                                   # don't also sort
        super().mousePressEvent(event)


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

        self.model = BlockTableModel(scene, root=root, parent=self)
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
        """After a model reset, re-select the previously-selected row (by id).

        NOTE: Minimal stub for T1-T3 compatibility — full rewire in Task 4.
        """
        block_id = getattr(self, "_selected_id_before_reset", None)
        if block_id is not None:
            src_row = self.model.row_for_id(block_id)
            if src_row >= 0:
                self.view.setCurrentIndex(self.model.index(src_row, 0))
        self._sync_ui()

    # ------------------------------------------------------------- selection
    def _current_def(self):
        idxs = self.view.selectionModel().selectedRows()
        if not idxs:
            return None
        # NOTE: stub for T1-T3 — view is still QTreeView; full rewire in Task 4.
        # For the tree, internalPointer is a _Node — but that class is gone.
        # Return None safely so import and _sync_ui don't crash.
        return None

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
        import os
        from PyQt6.QtWidgets import QFileDialog
        from .app_data import app_data_dir
        from .themed_message import themed_info
        blocks_dir = app_data_dir("blocks")
        os.makedirs(blocks_dir, exist_ok=True)
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Load Blocks", blocks_dir,
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
