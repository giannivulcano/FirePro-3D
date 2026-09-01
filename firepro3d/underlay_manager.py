"""The Underlay Manager dialog — a modeless window bound to ``Model_Space``.

Ported from the standalone prototype (``underlay_manager_pyqt6``), adapted for
FirePro3D:

* The view is a :class:`QTreeView` over a live tree model
  (:class:`~firepro3d.underlay_manager_model.UnderlayTreeModel` behind
  :class:`~firepro3d.underlay_manager_model.UnderlayFilterProxy`) — top-level
  rows are underlays; child rows are that underlay's source layers.
* No ``AppBridge`` / ``UnderlayStore`` indirection: the dialog binds directly
  to the app's ``scene`` (``Model_Space``) and ``main_window`` (``MainWindow``).
  The model auto-refreshes off ``scene.underlaysChanged``.
* **No opacity anywhere.** The details panel placement rows are read-only.

Open it modeless::

    dlg = UnderlayManagerDialog(scene, main_window)
    dlg.show()
"""
from __future__ import annotations

import os

from PyQt6.QtCore import QModelIndex, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QTreeView,
    QVBoxLayout,
)

from .frameless_shell import FramelessShellMixin
from .underlay_manager_delegates import (
    ColourDelegate, LevelsDelegate, ToggleDelegate, WeightDelegate,
    make_menu,
)
from .underlay_manager_model import (
    Col, LayerRole, UnderlayFilterProxy, UnderlayRole, UnderlayTreeModel,
)
from .theme import Theme, detect, build_underlay_manager_qss


# ---------------------------------------------------------------------------
# Key-signal tree view (ported from the prototype's _TableView)
# ---------------------------------------------------------------------------
class _TreeView(QTreeView):
    modifyKey = pyqtSignal()
    deleteKey = pyqtSignal()
    spaceKey = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.modifyKey.emit()
        elif key == Qt.Key.Key_Delete:
            self.deleteKey.emit()
        elif key == Qt.Key.Key_Space:
            self.spaceKey.emit()
        else:
            super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Read-only details panel (ported, file-only — no URL / preview pixmap)
# ---------------------------------------------------------------------------
class _DetailsPanel(QFrame):
    WIDTH = 268

    relinkRequested = pyqtSignal()
    reloadRequested = pyqtSignal()

    def __init__(self, theme: Theme | None = None, parent=None):
        theme = theme or detect()
        super().__init__(parent)
        self.setObjectName("detailsPanel")
        self.t = theme
        self.setFixedWidth(self.WIDTH)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(9)

        header = QLabel("DETAILS")
        header.setProperty("role", "header")
        root.addWidget(header)

        self.name = QLabel()
        self.name.setProperty("role", "name")
        root.addWidget(self.name)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setProperty("role", "muted")
        root.addWidget(self.status)

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(4)
        self._rows: dict[str, QLabel] = {}
        for row, key in enumerate(("Scale", "Rotation", "Insertion", "Layers")):
            k = QLabel(key)
            k.setProperty("role", "faint")
            v = QLabel()
            v.setProperty("role", "muted")
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.grid.addWidget(k, row, 0)
            self.grid.addWidget(v, row, 1)
            self._rows[key] = v
        self.grid.setColumnStretch(1, 1)
        root.addLayout(self.grid)
        root.addStretch(1)

        buttons = QHBoxLayout()
        self.btn_reload = QPushButton("Reload")
        self.btn_relink = QPushButton("Relink…")
        buttons.addWidget(self.btn_reload)
        buttons.addWidget(self.btn_relink)
        root.addLayout(buttons)
        self.btn_reload.clicked.connect(self.reloadRequested)
        self.btn_relink.clicked.connect(self.relinkRequested)

        self.hint = QLabel("Select an underlay to see its\nplacement.")
        self.hint.setProperty("role", "faint")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.insertWidget(root.count() - 1, self.hint)

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _missing(record) -> bool:
        path = getattr(record, "path", None)
        if not path:
            return True
        try:
            return not os.path.exists(path)
        except Exception:
            return False

    @staticmethod
    def _name(record) -> str:
        return os.path.basename(getattr(record, "path", "") or "") or "(untitled)"

    # -- population --------------------------------------------------------
    def show_selection(self, records: list, layer_count: int = 0) -> None:
        single = len(records) == 1
        for widget in (self.name, self.status,
                       self.btn_reload, self.btn_relink):
            widget.setVisible(single)
        for i in range(self.grid.count()):
            self.grid.itemAt(i).widget().setVisible(single)
        self.hint.setVisible(not single)

        if not single:
            self.hint.setText(
                "Select an underlay to see its\nplacement."
                if not records
                else f"{len(records)} selected\n"
                     "Delete and Reload act on all of them.\n"
                     "Space toggles visibility of selected underlays."
            )
            return

        record = records[0]
        self.name.setText(self._name(record))
        missing = self._missing(record)
        if missing:
            self.status.setProperty("state", "warn")
            self.status.setText("Source file not found — Relink")
        else:
            self.status.setProperty("state", "")
            self.status.setText("File on disk")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

        self._rows["Scale"].setText(f"{getattr(record, 'scale', 1.0):g}")
        self._rows["Rotation"].setText(f"{getattr(record, 'rotation', 0.0):g}°")
        self._rows["Insertion"].setText(
            f"{getattr(record, 'x', 0.0):g}, {getattr(record, 'y', 0.0):g}")
        self._rows["Layers"].setText(
            f"{layer_count} layers" if layer_count else "—")
        self.btn_relink.setVisible(missing)


# ---------------------------------------------------------------------------
# The dialog
# ---------------------------------------------------------------------------
class UnderlayManagerDialog(FramelessShellMixin, QDialog):
    """Modeless manager — instant apply, no OK/Apply. Open with ``.show()``."""

    def __init__(self, scene, main_window, theme: Theme | None = None, parent=None,
                 apply_stylesheet: bool = True):
        theme = theme or detect()
        super().__init__(parent)
        self.init_frameless_shell(
            title="Underlay Manager",
            controls=("min", "max", "close"),
            resizable=True,
            icon="underlay_manager_icon.svg",
        )
        self.scene = scene
        self.main_window = main_window
        self.t = theme
        self.setObjectName("UnderlayManagerDialog")
        self.setWindowTitle("Underlay Manager")
        if apply_stylesheet:
            self.setStyleSheet(build_underlay_manager_qss(theme))
        self.setMinimumSize(720, 420)
        self.resize(1080, 560)  # restore baseline (size after un-maximize)
        self.setModal(False)
        self._did_initial_max = False

        self._known_levels = lambda: [
            l.name for l in main_window.level_mgr.levels]

        self.model = UnderlayTreeModel(scene, theme, self._known_levels, self)
        self.proxy = UnderlayFilterProxy(self)
        self.proxy.setSourceModel(self.model)

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
        self.btn_add = QPushButton("+  Add underlay…")
        self.btn_add.setProperty("variant", "primary")
        self.btn_modify = QPushButton("Modify…")
        self.btn_reload = QPushButton("Reload")
        self.btn_reload.setToolTip(
            "Reload selected underlays from their source — or all, "
            "when nothing is selected")
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setProperty("variant", "danger")
        self.filter_edit = QLineEdit(placeholderText="Filter underlays")
        self.filter_edit.setFixedWidth(220)
        self.filter_edit.setClearButtonEnabled(True)
        for w in (self.btn_add, self.btn_modify, self.btn_reload, self.btn_delete):
            bar.addWidget(w)
        bar.addStretch(1)
        bar.addWidget(self.filter_edit)
        root.addWidget(toolbar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.view = _TreeView(objectName="underlayTable")
        self.view.setModel(self.proxy)
        self.view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.view.setUniformRowHeights(True)
        self.view.setAllColumnsShowFocus(True)
        self.view.setRootIsDecorated(True)
        self.view.setExpandsOnDoubleClick(False)
        self.view.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.view.setWordWrap(False)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self.view.setItemDelegateForColumn(
            Col.VIS, ToggleDelegate(self.t, "visible", self.view))
        self.view.setItemDelegateForColumn(
            Col.SNAP, ToggleDelegate(self.t, "snap", self.view))
        self.view.setItemDelegateForColumn(
            Col.COLOUR, ColourDelegate(self.t, self.view))
        self.view.setItemDelegateForColumn(
            Col.WEIGHT, WeightDelegate(self.t, self.view))
        self.view.setItemDelegateForColumn(
            Col.LEVELS, LevelsDelegate(self.t, self._known_levels, self.view))

        header = self.view.header()
        header.setHighlightSections(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # Every inner divider (incl. SOURCE<->TYPE, NAME<->SOURCE) stays
        # draggable: keep all sections Interactive and let the LAST column
        # (LEVELS) absorb slack instead of a Stretch section (which resists
        # interactive resize of its neighbouring dividers).
        header.setStretchLastSection(True)
        for col, width in (
            (Col.NAME, 200), (Col.SOURCE, 220), (Col.TYPE, 64), (Col.VIS, 92),
            (Col.SNAP, 44), (Col.COLOUR, 110), (Col.WEIGHT, 84),
            (Col.LEVELS, 160),
        ):
            self.view.setColumnWidth(col, width)
        body.addWidget(self.view, 1)

        self.details = _DetailsPanel(self.t)
        body.addWidget(self.details)
        root.addLayout(body, 1)

        footer = QFrame(objectName="footerBar")
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(12, 8, 12, 8)
        self.count_label = QLabel()
        self.count_label.setProperty("role", "muted")
        hint = QLabel("Changes apply immediately — no OK needed")
        hint.setProperty("role", "faint")
        self.btn_close = QPushButton("Close")
        foot.addWidget(self.count_label)
        foot.addSpacing(14)
        foot.addWidget(hint)
        foot.addStretch(1)
        foot.addWidget(self.btn_close)
        root.addWidget(footer)

        # Underlays default to COLLAPSED (Bug 2). Expansion state is then
        # preserved across model resets by the _before_reset/_after_reset pair
        # (Bug 3) rather than force-expanded on every edit.

    # -------------------------------------------------------------- lifecycle
    def showEvent(self, event):
        # Chain to the mixin's showEvent (DWM rounded corners) via MRO, then
        # maximize once on first show. The guard keeps the 1080x560 resize() as
        # the restore baseline and prevents a later reshow (singleton reopen via
        # open_underlay_manager) or user restore from being re-maximized.
        super().showEvent(event)
        if not getattr(self, "_did_initial_max", False):
            self._did_initial_max = True
            self.showMaximized()

    # ---------------------------------------------------------------- wiring
    def _wire(self) -> None:
        self.btn_add.clicked.connect(self._add)
        self.btn_modify.clicked.connect(self._modify)
        self.btn_delete.clicked.connect(self._delete)
        self.btn_reload.clicked.connect(self._reload)
        self.btn_close.clicked.connect(self.close)
        self.filter_edit.textChanged.connect(self.proxy.set_filter_text)

        self.view.selectionModel().selectionChanged.connect(
            lambda *_: self._sync_ui())
        self.view.doubleClicked.connect(self._on_double_click)
        self.view.modifyKey.connect(self._modify)
        self.view.deleteKey.connect(self._delete)
        self.view.spaceKey.connect(self._toggle_visibility)
        self.view.customContextMenuRequested.connect(self._context_menu)

        self.details.reloadRequested.connect(self._reload)
        self.details.relinkRequested.connect(self._relink)

        # Model resets on scene.underlaysChanged (every VIS/appearance edit
        # routes through beginResetModel/endResetModel). Snapshot which
        # underlays the user had expanded BEFORE the reset and restore exactly
        # those afterwards, so an edit never force-re-expands collapsed rows
        # (Bug 3) and new/initial rows stay collapsed (Bug 2).
        self._expanded_keys: set = set()
        self.model.modelAboutToBeReset.connect(self._before_reset)
        self.model.modelReset.connect(self._after_reset)

    def _before_reset(self) -> None:
        """Snapshot the set of expanded top-level underlays, keyed by the
        stable record identity (``id(record)`` — records survive the reset;
        the model only rebuilds its _Node wrappers)."""
        keys: set = set()
        root = QModelIndex()
        for row in range(self.proxy.rowCount(root)):
            proxy_index = self.proxy.index(row, 0, root)
            if not proxy_index.isValid():
                continue
            if self.view.isExpanded(proxy_index):
                record = proxy_index.data(UnderlayRole)
                if record is not None:
                    keys.add(id(record))
        self._expanded_keys = keys

    def _after_reset(self) -> None:
        # Restore only the previously-expanded underlays; everything else
        # (incl. brand-new imports) stays collapsed.
        root = QModelIndex()
        for row in range(self.proxy.rowCount(root)):
            proxy_index = self.proxy.index(row, 0, root)
            if not proxy_index.isValid():
                continue
            record = proxy_index.data(UnderlayRole)
            if record is not None and id(record) in self._expanded_keys:
                self.view.expand(proxy_index)
        self._sync_ui()

    def _on_double_click(self, index: QModelIndex) -> None:
        # Double-click on an underlay row opens Modify; on a layer row, ignore.
        if index.isValid() and index.data(LayerRole) is None:
            self._modify()

    # ------------------------------------------------------------- selection
    def _selected_records(self) -> list:
        """Distinct underlay records for the current selection.

        A selected *layer child* row resolves to its parent underlay record, so
        Modify/Delete/Reload always act on top-level underlays.
        """
        sel = self.view.selectionModel()
        if sel is None:
            return []
        out = []
        for proxy_index in sel.selectedRows():
            record = proxy_index.data(UnderlayRole)
            if record is not None and record not in out:
                out.append(record)
        return out

    def _underlay_rows_selected(self) -> list:
        """Records for selections that are top-level underlay rows (LayerRole
        is None). Modify/Delete enablement keys off this."""
        sel = self.view.selectionModel()
        if sel is None:
            return []
        out = []
        for proxy_index in sel.selectedRows():
            if proxy_index.data(LayerRole) is not None:
                continue
            record = proxy_index.data(UnderlayRole)
            if record is not None and record not in out:
                out.append(record)
        return out

    def _pair_for(self, record):
        """Return the ``(record, item)`` pair from ``scene.underlays``."""
        for data, item in list(self.scene.underlays):
            if data is record:
                return data, item
        return None

    def _select_row(self, row: int) -> None:
        """Select the top-level underlay at source *row* (test hook)."""
        sel = self.view.selectionModel()
        if sel is None:
            return
        src_index = self.model.index(row, 0, QModelIndex())
        if not src_index.isValid():
            return
        proxy_index = self.proxy.mapFromSource(src_index)
        if not proxy_index.isValid():
            return
        sel.clearSelection()
        sel.select(
            proxy_index,
            sel.SelectionFlag.Select | sel.SelectionFlag.Rows)
        sel.setCurrentIndex(proxy_index, sel.SelectionFlag.NoUpdate)
        self._sync_ui()

    # ---------------------------------------------------------------- actions
    def _add(self) -> None:
        self.main_window.open_import_dialog()

    def _modify(self) -> None:
        records = self._underlay_rows_selected()
        if len(records) != 1:
            return
        self.main_window.modify_underlay(records[0])

    def _delete(self, confirm: bool = True) -> None:
        records = self._underlay_rows_selected()
        if not records:
            return
        if confirm and not self._confirm_delete(records):
            return
        for record in records:
            pair = self._pair_for(record)
            if pair is not None:
                self.scene.remove_underlay(pair[0], pair[1])
        self._sync_ui()

    def _confirm_delete(self, records: list) -> bool:
        if len(records) == 1:
            name = os.path.basename(getattr(records[0], "path", "") or "") \
                or "(untitled)"
            title = f'Delete "{name}"?'
        else:
            title = f"Delete {len(records)} underlays?"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Delete underlay")
        box.setText(title)
        box.setInformativeText("The source file on disk is not affected.")
        delete_button = box.addButton(
            "Delete", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        return box.clickedButton() is delete_button

    def _reload(self) -> None:
        records = self._selected_records()
        if not records:
            self.scene.refresh_all_underlays()
            self._sync_ui()
            return
        for record in records:
            pair = self._pair_for(record)
            if pair is not None:
                self.scene.refresh_underlay(pair[0], pair[1])
        self._sync_ui()

    def _relink(self) -> None:
        records = self._underlay_rows_selected()
        if len(records) != 1:
            return
        record = records[0]
        path, _ = QFileDialog.getOpenFileName(
            self, "Relink underlay",
            os.path.dirname(getattr(record, "path", "") or ""),
            "Underlays (*.pdf *.dxf *.dwg);;All files (*)")
        if not path:
            return
        record.path = path
        pair = self._pair_for(record)
        if pair is not None:
            self.scene.refresh_underlay(pair[0], pair[1])
        self._sync_ui()

    def _toggle_visibility(self) -> None:
        records = self._underlay_rows_selected()
        if not records:
            return
        target = not all(getattr(r, "visible", True) for r in records)
        for record in records:
            src_index = self._source_index_for(record)
            if src_index is not None:
                self.model.setData(
                    src_index.siblingAtColumn(Col.VIS), target,
                    Qt.ItemDataRole.EditRole)

    def _source_index_for(self, record) -> QModelIndex | None:
        for i, (data, _item) in enumerate(list(self.scene.underlays)):
            if data is record:
                idx = self.model.index(i, 0, QModelIndex())
                return idx if idx.isValid() else None
        return None

    # ------------------------------------------------------------ context menu
    def _context_menu(self, pos) -> None:
        index = self.view.indexAt(pos)
        if index.isValid():
            record = index.data(UnderlayRole)
            if record is not None and record not in self._selected_records():
                src = self._source_index_for(record)
                if src is not None:
                    self._select_row(src.row())
        records = self._underlay_rows_selected()
        if not records:
            return
        single = records[0] if len(records) == 1 else None

        menu = make_menu(self)
        if single is not None:
            menu.addAction("Modify…", self._modify)
        menu.addAction("Reload", self._reload)
        if single is not None and self.details._missing(single):
            menu.addAction("Relink…", self._relink)
        menu.addSeparator()
        label = "Delete…" if single is not None \
            else f"Delete {len(records)}…"
        menu.addAction(label, self._delete)
        menu.exec(self.view.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------- misc
    def _sync_ui(self) -> None:
        records = self._underlay_rows_selected()
        self.btn_modify.setEnabled(len(records) == 1)
        self.btn_delete.setEnabled(bool(records))
        selected = self._selected_records()
        layer_count = 0
        if len(selected) == 1:
            try:
                layer_count = len(self.model._layers_of(selected[0]))
            except Exception:
                layer_count = 0
        self.details.show_selection(selected, layer_count=layer_count)

        items = [d for d, _ in list(self.scene.underlays)]
        visible = sum(1 for r in items if getattr(r, "visible", True))
        if not items:
            text = "No underlays — Add one to trace over a PDF or DWG/DXF."
        else:
            text = (f"{len(items)} underlay{'s' if len(items) != 1 else ''}"
                    f" · {visible} visible")
        self.count_label.setText(text)
