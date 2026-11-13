"""Display Manager Phases tab (project-phasing PH2; D-PH10, D-PH11, AC6, AC7).

Edits a working copy of the project phase registry (the ``materials_tab.py``
pattern); the Display Manager installs it on OK. "—" (None) = no override.
Governing spec: docs/specs/project-phasing.md.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QHeaderView, QSpinBox,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import colour_picker, phase_registry
from .constants import PHASE_NEW, PHASE_OPACITY_UNSET
from .ui_kit import Swatch

DASH = "\u2014"
_COLS = ("colour", "fill", "weight", "linetype", "opacity")
_HEADERS = ["STATUS", "COLOUR", "FILL", "LINE WT", "LINETYPE", "OPACITY"]
_NEW_TIP = "New plots as authored: no override (D-PH9)."


class PhasesTab(QWidget):
    """One row per status; cells edit the working copy.

    Signals:
        edited: The working copy changed.
    """

    edited = pyqtSignal()

    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self._scene = scene
        self._work = phase_registry.project_table().copy()
        self.dirty = False
        self._loading = False
        self._cells: dict[tuple[str, str], QWidget] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._grid = QTableWidget()
        self._grid.setObjectName("underlayTable")      # Line Weights tab look
        self._grid.setColumnCount(len(_HEADERS))
        self._grid.setHorizontalHeaderLabels(_HEADERS)
        hdr = self._grid.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, len(_HEADERS)):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self._grid.verticalHeader().hide()
        self._grid.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        lay.addWidget(self._grid)
        self._rebuild()

    # -- public API (Display Manager + tests) --------------------------------
    def table(self) -> phase_registry.PhaseRegistry:
        return self._work

    def set_cell(self, sid: str, key: str, value) -> None:
        """Set one slot (None = "—") and refresh its cell."""
        if self._work.set_graphic(sid, key, value):
            self._touch()
            self._rebuild()

    def reset_to_factory(self) -> None:
        self._work.reset_graphics_to_factory()
        self._touch()
        self._rebuild()

    def swatch(self, sid: str, key: str) -> Swatch:
        return self._cells[(sid, key)]

    def cell(self, sid: str, key: str) -> QWidget:
        """The live cell widget (Swatch / QComboBox / QSpinBox)."""
        return self._cells[(sid, key)]

    def row_names(self) -> list[str]:
        return [self._grid.item(r, 0).text() for r in range(self._grid.rowCount())]

    def cell_text(self, sid: str, key: str) -> str:
        w = self._cells[(sid, key)]
        if isinstance(w, Swatch):
            return w._label.text()
        if isinstance(w, QSpinBox):
            return w.specialValueText() if w.value() == w.minimum() else str(w.value())
        return w.currentText()

    # -- build ----------------------------------------------------------------
    def _touch(self) -> None:
        self.dirty = True
        self.edited.emit()

    def _rebuild(self) -> None:
        self._loading = True
        try:
            rows = self._work.statuses()
            self._grid.setRowCount(len(rows))
            self._cells.clear()
            for r, row in enumerate(rows):
                name = QTableWidgetItem(row["name"])       # read-only (rename = PH8)
                name.setFlags(name.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._grid.setItem(r, 0, name)
                g = row["graphics"]
                locked = row["id"] == PHASE_NEW            # Q2 / D-PH9: shown, locked to "—"
                for c, key in enumerate(_COLS, start=1):
                    w = self._make_cell(row["id"], key, None if locked else g.get(key))
                    if locked:
                        w.setEnabled(False)
                        w.setToolTip(_NEW_TIP)
                        if isinstance(w, Swatch):
                            w.set_tooltip(_NEW_TIP)
                    self._cells[(row["id"], key)] = w
                    self._grid.setCellWidget(r, c, w)
        finally:
            self._loading = False

    def _make_cell(self, sid, key, value) -> QWidget:
        if key in ("colour", "fill"):
            sw = Swatch(value, context=key.title(), unset_ok=True, auto_pick=False)
            sw.clicked.connect(lambda s=sid, k=key: self._pick(s, k))
            return sw
        if key == "opacity":
            sp = QSpinBox()
            sp.setRange(PHASE_OPACITY_UNSET, 100)      # percent, as the Model tab's opacity
            sp.setSpecialValueText(DASH)               # the minimum shows "—" = no override
            sp.setSuffix(" %")
            sp.setValue(PHASE_OPACITY_UNSET if value is None else int(value))
            sp.valueChanged.connect(lambda v, s=sid: self._on_value(
                s, "opacity", None if v == PHASE_OPACITY_UNSET else v))
            return sp
        combo = QComboBox()
        items = [(DASH, None)] + self._choices(key)
        if value is not None and value not in [ref for _, ref in items]:
            from .linetype_choices import missing_label
            items.append((missing_label(value) if key == "linetype" else str(value), value))
        for label, ref in items:
            combo.addItem(label, ref)
        combo.setCurrentIndex(next(i for i, (_, ref) in enumerate(items) if ref == value))
        combo.currentIndexChanged.connect(
            lambda i, s=sid, k=key, cb=combo: self._on_value(s, k, cb.itemData(i)))
        return combo

    def _choices(self, key) -> list[tuple[str, str]]:
        if key == "weight":
            from .paper_display import weight_names
            return [(n, n) for n in weight_names()]
        from .linetype_choices import linetype_choices
        return linetype_choices(getattr(self._scene, "block_registry", None))

    def _on_value(self, sid, key, value) -> None:
        if self._loading:
            return
        if self._work.set_graphic(sid, key, value):
            self._touch()

    def _pick(self, sid, key) -> None:
        cur = self._work.graphics_of(sid).get(key)
        v = colour_picker.pick_colour(cur or "", self, f"{key.title()} override",
                                      allow_unset=True)
        if v is None:
            return
        self.set_cell(sid, key, None if v == colour_picker.NO_OVERRIDE else v)
