"""
sprinkler_db.py
===============
Sprinkler product database for FirePro 3D.

Classes
-------
SprinklerRecord       — immutable data record for one sprinkler model
SprinklerDatabase     — JSON-backed store with built-in default products
SprinklerManagerDialog— full-featured manager dialog (library + templates)

Usage
-----
    from .sprinkler_db import SprinklerManagerDialog, SprinklerDatabase

    # In MainWindow.open_sprinkler_manager():
    dlg = SprinklerManagerDialog(parent=self)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        record = dlg.selected_record()
        if record:
            # Apply the record as the active sprinkler template
            self._apply_sprinkler_template(record)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QLabel, QLineEdit, QPushButton, QComboBox, QDoubleSpinBox,
    QSpinBox, QDialogButtonBox, QGroupBox, QFormLayout, QMessageBox,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SprinklerRecord:
    """Immutable data record describing one sprinkler product."""
    id:            str          # unique identifier (e.g. "tyco_ty315")
    manufacturer:  str
    model:         str
    type:          str          # "Pendent" | "Upright" | "Sidewall" | "Concealed"
    k_factor:      float        # gpm / psi^0.5
    min_pressure:  float        # psi
    coverage_area: float        # sq ft
    temp_rating:   int          # °F
    orifice:       str          # e.g. '1/2"'
    notes:         str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SprinklerRecord":
        return cls(
            id            = str(d.get("id", "")),
            manufacturer  = str(d.get("manufacturer", "")),
            model         = str(d.get("model", "")),
            type          = str(d.get("type", "Pendent")),
            k_factor      = float(d.get("k_factor", 5.6)),
            min_pressure  = float(d.get("min_pressure", 7.0)),
            coverage_area = float(d.get("coverage_area", 130.0)),
            temp_rating   = int(d.get("temp_rating", 155)),
            orifice       = str(d.get("orifice", '1/2"')),
            notes         = str(d.get("notes", "")),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Default library (~15 common products)
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULTS: list[SprinklerRecord] = [
    # ── Tyco / Johnson Controls ───────────────────────────────────────────────
    SprinklerRecord("tyco_ty315",    "Tyco / JCI", "TY315",    "Pendent",   5.6,  7.0, 130, 155, '1/2"',
                    "Standard response, light/ordinary hazard"),
    SprinklerRecord("tyco_ty323",    "Tyco / JCI", "TY323",    "Pendent",   5.6,  7.0, 130, 155, '1/2"',
                    "Quick response, light/ordinary hazard"),
    SprinklerRecord("tyco_ty3131",   "Tyco / JCI", "TY3131",   "Upright",   5.6,  7.0, 130, 155, '1/2"',
                    "Quick response upright"),
    SprinklerRecord("tyco_ty4131",   "Tyco / JCI", "TY4131",   "Upright",   8.0,  7.0, 130, 155, '1/2"',
                    "Large orifice upright, K8.0"),
    SprinklerRecord("tyco_ty5131",   "Tyco / JCI", "TY5131",   "Sidewall",  5.6,  7.0,  96, 155, '1/2"',
                    "Horizontal sidewall, residential"),
    SprinklerRecord("tyco_ty3251",   "Tyco / JCI", "TY3251",   "Concealed", 5.6,  7.0, 196, 155, '1/2"',
                    "Concealed pendent, white cover plate"),

    # ── Viking ────────────────────────────────────────────────────────────────
    SprinklerRecord("viking_vk100",  "Viking",     "VK100",    "Pendent",   5.6,  7.0, 130, 155, '1/2"',
                    "Standard response pendent"),
    SprinklerRecord("viking_vk102",  "Viking",     "VK102",    "Upright",   5.6,  7.0, 130, 155, '1/2"',
                    "Standard response upright"),
    SprinklerRecord("viking_vk200",  "Viking",     "VK200",    "Pendent",   8.0,  7.0, 196, 155, '1/2"',
                    "Large orifice pendent, K8.0"),
    SprinklerRecord("viking_vk457",  "Viking",     "VK457",    "Concealed", 5.6,  7.0, 196, 155, '1/2"',
                    "Concealed pendent, adjustable cover"),
    SprinklerRecord("viking_vk500",  "Viking",     "VK500",    "Sidewall",  5.6,  7.0,  96, 155, '1/2"',
                    "Horizontal sidewall standard response"),

    # ── Victaulic ─────────────────────────────────────────────────────────────
    SprinklerRecord("vic_v2710",     "Victaulic",  "V2710",    "Pendent",   5.6,  7.0, 130, 155, '1/2"',
                    "Standard response, light hazard"),
    SprinklerRecord("vic_v2720",     "Victaulic",  "V2720",    "Upright",   5.6,  7.0, 130, 155, '1/2"',
                    "Standard response upright"),

    # ── Central / Senju ───────────────────────────────────────────────────────
    SprinklerRecord("central_a1",    "Central",    "A-1 Pendent", "Pendent", 5.6, 7.0, 130, 155, '1/2"',
                    "Classic standard response pendent"),
    SprinklerRecord("senju_ec14",    "Senju",      "EC-14",    "Pendent",   5.6,  7.0, 130, 165, '1/2"',
                    "Extended coverage, higher temp rating"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────────────────────

class SprinklerDatabase:
    """
    JSON-backed sprinkler product store.

    Layout of the JSON file
    -----------------------
    {
        "library":   [ { ...SprinklerRecord fields... }, ... ],
        "templates": [ { ...SprinklerRecord fields... }, ... ]
    }

    The "library" contains all products (defaults + user additions).
    The "templates" tab holds user-starred favourites.
    """

    DEFAULT_PATH = "sprinklers.json"

    def __init__(self, path: str | None = None):
        self._path = path or self.DEFAULT_PATH
        self._library: list[SprinklerRecord] = []
        self._templates: list[SprinklerRecord] = []
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self):
        if os.path.isfile(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._library   = [SprinklerRecord.from_dict(d) for d in data.get("library",   [])]
                self._templates = [SprinklerRecord.from_dict(d) for d in data.get("templates", [])]
            except Exception as exc:
                print(f"⚠️  sprinkler_db: failed to load {self._path}: {exc}")
                self._library   = list(_DEFAULTS)
                self._templates = []
        else:
            # First run — seed with defaults
            self._library   = list(_DEFAULTS)
            self._templates = []
            self._save()

    def _save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump({
                    "library":   [r.to_dict() for r in self._library],
                    "templates": [r.to_dict() for r in self._templates],
                }, f, indent=2)
        except Exception as exc:
            print(f"⚠️  sprinkler_db: failed to save {self._path}: {exc}")

    # ── Library CRUD ─────────────────────────────────────────────────────────

    @property
    def library(self) -> list[SprinklerRecord]:
        return list(self._library)

    @property
    def templates(self) -> list[SprinklerRecord]:
        return list(self._templates)

    def add_to_library(self, record: SprinklerRecord):
        self._library.append(record)
        self._save()

    def update_in_library(self, index: int, record: SprinklerRecord):
        if 0 <= index < len(self._library):
            self._library[index] = record
            self._save()

    def delete_from_library(self, index: int):
        if 0 <= index < len(self._library):
            del self._library[index]
            self._save()

    # ── Cascading query helpers ──────────────────────────────────────────────

    def get_unique_manufacturers(self) -> list[str]:
        return sorted({r.manufacturer for r in self._library})

    def get_models_for(self, manufacturer: str) -> list[str]:
        return sorted({r.model for r in self._library if r.manufacturer == manufacturer})

    def get_types_for(self, manufacturer: str, model: str | None = None) -> list[str]:
        recs = [r for r in self._library if r.manufacturer == manufacturer]
        if model:
            recs = [r for r in recs if r.model == model]
        return sorted({r.type for r in recs})

    def find_records(self, manufacturer: str | None = None,
                     model: str | None = None,
                     type_: str | None = None) -> list[SprinklerRecord]:
        recs = list(self._library)
        if manufacturer:
            recs = [r for r in recs if r.manufacturer == manufacturer]
        if model:
            recs = [r for r in recs if r.model == model]
        if type_:
            recs = [r for r in recs if r.type == type_]
        return recs

    def add_to_templates(self, record: SprinklerRecord):
        """Star a product as a user template (avoid duplicates by id)."""
        if not any(t.id == record.id for t in self._templates):
            self._templates.append(record)
            self._save()

    def delete_from_templates(self, index: int):
        if 0 <= index < len(self._templates):
            del self._templates[index]
            self._save()


# ─────────────────────────────────────────────────────────────────────────────
# Manager dialog
# ─────────────────────────────────────────────────────────────────────────────

_COLUMNS = ("Manufacturer", "Model", "Type", "K-factor", "Min P (psi)",
            "Coverage (ft²)", "Temp (°F)", "Orifice")

class SprinklerManagerDialog(QDialog):
    """
    Full sprinkler manager with two tabs:

    Library tab   — all records from the database, with filter bar, Add,
                    Edit, Delete, and ★ Star (add to My Templates).
    My Templates  — user-starred favourites, with Use and Remove buttons.

    Closing with "Use as Template" sets ``self._selected`` to the chosen
    record.  Call ``selected_record()`` after exec() to retrieve it.
    """

    # Emitted when the user presses "Use as Template" or double-clicks
    templateChosen = pyqtSignal(object)   # SprinklerRecord

    def __init__(self, db: SprinklerDatabase | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sprinkler Manager")
        self.setMinimumSize(780, 520)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._db = db or SprinklerDatabase()
        self._selected: SprinklerRecord | None = None

        root = QVBoxLayout(self)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_library_tab(), "Library")
        self._tabs.addTab(self._build_templates_tab(), "My Templates")
        root.addWidget(self._tabs)

        # Bottom action buttons
        btn_box = QDialogButtonBox()
        self._use_btn = btn_box.addButton(
            "Use as Template", QDialogButtonBox.ButtonRole.AcceptRole)
        btn_box.addButton(QDialogButtonBox.StandardButton.Close)
        btn_box.accepted.connect(self._on_use)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

        self._refresh_library()
        self._refresh_templates()

    # ── Library tab ───────────────────────────────────────────────────────────

    def _build_library_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        # Filter bar
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Search:"))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Manufacturer, model, notes…")
        self._search_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self._search_edit)

        filter_row.addWidget(QLabel("Type:"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(["(All)", "Pendent", "Upright", "Sidewall", "Concealed"])
        self._type_combo.currentTextChanged.connect(self._apply_filter)
        filter_row.addWidget(self._type_combo)
        lay.addLayout(filter_row)

        # Table
        self._lib_table = self._make_table()
        self._lib_table.doubleClicked.connect(self._on_use)
        lay.addWidget(self._lib_table)

        # CRUD buttons
        crud_row = QHBoxLayout()
        add_btn  = QPushButton("Add…")
        edit_btn = QPushButton("Edit…")
        del_btn  = QPushButton("Delete")
        star_btn = QPushButton("★ Star")
        add_btn.clicked.connect(self._add_record)
        edit_btn.clicked.connect(self._edit_record)
        del_btn.clicked.connect(self._delete_record)
        star_btn.clicked.connect(self._star_record)
        for btn in (add_btn, edit_btn, del_btn, star_btn):
            crud_row.addWidget(btn)
        crud_row.addStretch()
        lay.addLayout(crud_row)
        return w

    # ── Templates tab ─────────────────────────────────────────────────────────

    def _build_templates_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        self._tmpl_table = self._make_table()
        self._tmpl_table.doubleClicked.connect(self._on_use)
        lay.addWidget(self._tmpl_table)

        btn_row = QHBoxLayout()
        use_btn = QPushButton("Use as Template")
        rem_btn = QPushButton("Remove")
        use_btn.clicked.connect(self._on_use)
        rem_btn.clicked.connect(self._remove_template)
        btn_row.addWidget(use_btn)
        btn_row.addWidget(rem_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)
        return w

    # ── Table factory ─────────────────────────────────────────────────────────

    def _make_table(self) -> QTableWidget:
        t = QTableWidget(0, len(_COLUMNS))
        t.setHorizontalHeaderLabels(list(_COLUMNS))
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        t.horizontalHeader().setStretchLastSection(True)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setAlternatingRowColors(True)
        f = QFont()
        f.setPointSizeF(8.5)
        t.setFont(f)
        return t

    def _populate_table(self, table: QTableWidget, records: list[SprinklerRecord]):
        table.setRowCount(len(records))
        for row, r in enumerate(records):
            cells = (
                r.manufacturer, r.model, r.type,
                f"{r.k_factor:.1f}",
                f"{r.min_pressure:.1f}",
                f"{r.coverage_area:.0f}",
                str(r.temp_rating),
                r.orifice,
            )
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, r)
                table.setItem(row, col, item)

    # ── Refresh ───────────────────────────────────────────────────────────────

    def _refresh_library(self):
        self._lib_records = self._db.library
        self._apply_filter()

    def _refresh_templates(self):
        self._populate_table(self._tmpl_table, self._db.templates)

    def _apply_filter(self):
        text = self._search_edit.text().lower()
        type_filter = self._type_combo.currentText()
        filtered = [
            r for r in self._lib_records
            if (not text or
                text in r.manufacturer.lower() or
                text in r.model.lower() or
                text in r.notes.lower())
            and (type_filter == "(All)" or r.type == type_filter)
        ]
        self._populate_table(self._lib_table, filtered)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def _current_library_record(self) -> tuple[int, SprinklerRecord] | None:
        row = self._lib_table.currentRow()
        if row < 0:
            return None
        item = self._lib_table.item(row, 0)
        if item is None:
            return None
        record = item.data(Qt.ItemDataRole.UserRole)
        # Find index in master list
        try:
            idx = next(i for i, r in enumerate(self._db.library) if r.id == record.id)
        except StopIteration:
            return None
        return idx, record

    def _add_record(self):
        dlg = _RecordEditDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._db.add_to_library(dlg.get_record())
            self._refresh_library()

    def _edit_record(self):
        result = self._current_library_record()
        if result is None:
            return
        idx, record = result
        dlg = _RecordEditDialog(record=record, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._db.update_in_library(idx, dlg.get_record())
            self._refresh_library()

    def _delete_record(self):
        result = self._current_library_record()
        if result is None:
            return
        idx, record = result
        reply = QMessageBox.question(
            self, "Delete Sprinkler",
            f"Delete '{record.manufacturer} {record.model}' from the library?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._db.delete_from_library(idx)
            self._refresh_library()

    def _star_record(self):
        result = self._current_library_record()
        if result is None:
            return
        _, record = result
        self._db.add_to_templates(record)
        self._refresh_templates()
        self._tabs.setCurrentIndex(1)

    def _remove_template(self):
        row = self._tmpl_table.currentRow()
        if row < 0:
            return
        self._db.delete_from_templates(row)
        self._refresh_templates()

    # ── Use as template ───────────────────────────────────────────────────────

    def _on_use(self):
        # Determine which tab is active and which table to read from
        if self._tabs.currentIndex() == 0:
            table = self._lib_table
        else:
            table = self._tmpl_table

        row = table.currentRow()
        if row < 0:
            QMessageBox.information(self, "No Selection",
                                    "Please select a sprinkler first.")
            return
        item = table.item(row, 0)
        if item is None:
            return
        self._selected = item.data(Qt.ItemDataRole.UserRole)
        self.templateChosen.emit(self._selected)
        self.accept()

    # ── Public ────────────────────────────────────────────────────────────────

    def selected_record(self) -> SprinklerRecord | None:
        """Return the record chosen via 'Use as Template', or None."""
        return self._selected


# ─────────────────────────────────────────────────────────────────────────────
# Record edit dialog (Add / Edit)
# ─────────────────────────────────────────────────────────────────────────────

class _RecordEditDialog(QDialog):
    """Small form dialog for adding or editing a SprinklerRecord."""

    _TYPES = ("Pendent", "Upright", "Sidewall", "Concealed")

    def __init__(self, record: SprinklerRecord | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Sprinkler" if record else "Add Sprinkler")
        self.setMinimumWidth(360)

        lay = QFormLayout(self)
        lay.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)

        self._id_edit   = QLineEdit(record.id if record else "")
        self._mfg_edit  = QLineEdit(record.manufacturer if record else "")
        self._mdl_edit  = QLineEdit(record.model if record else "")

        self._type_combo = QComboBox()
        self._type_combo.addItems(self._TYPES)
        if record:
            idx = self._type_combo.findText(record.type)
            self._type_combo.setCurrentIndex(max(0, idx))

        self._k_spin    = QDoubleSpinBox()
        self._k_spin.setRange(0.1, 30.0)
        self._k_spin.setDecimals(2)
        self._k_spin.setSingleStep(0.1)
        self._k_spin.setValue(record.k_factor if record else 5.6)

        self._pmin_spin = QDoubleSpinBox()
        self._pmin_spin.setRange(0.0, 100.0)
        self._pmin_spin.setDecimals(1)
        self._pmin_spin.setSuffix(" psi")
        self._pmin_spin.setValue(record.min_pressure if record else 7.0)

        self._cov_spin  = QDoubleSpinBox()
        self._cov_spin.setRange(1.0, 400.0)
        self._cov_spin.setDecimals(0)
        self._cov_spin.setSuffix(" ft²")
        self._cov_spin.setValue(record.coverage_area if record else 130.0)

        self._temp_spin = QSpinBox()
        self._temp_spin.setRange(100, 500)
        self._temp_spin.setSuffix(" °F")
        self._temp_spin.setValue(record.temp_rating if record else 155)

        self._ori_edit  = QLineEdit(record.orifice if record else '1/2"')
        self._notes_edit= QLineEdit(record.notes if record else "")

        lay.addRow("ID:",             self._id_edit)
        lay.addRow("Manufacturer:",   self._mfg_edit)
        lay.addRow("Model:",          self._mdl_edit)
        lay.addRow("Type:",           self._type_combo)
        lay.addRow("K-factor:",       self._k_spin)
        lay.addRow("Min Pressure:",   self._pmin_spin)
        lay.addRow("Coverage Area:",  self._cov_spin)
        lay.addRow("Temp Rating:",    self._temp_spin)
        lay.addRow("Orifice:",        self._ori_edit)
        lay.addRow("Notes:",          self._notes_edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addRow(btns)

    def get_record(self) -> SprinklerRecord:
        import uuid
        rid = self._id_edit.text().strip() or str(uuid.uuid4())[:8]
        return SprinklerRecord(
            id            = rid,
            manufacturer  = self._mfg_edit.text().strip(),
            model         = self._mdl_edit.text().strip(),
            type          = self._type_combo.currentText(),
            k_factor      = self._k_spin.value(),
            min_pressure  = self._pmin_spin.value(),
            coverage_area = self._cov_spin.value(),
            temp_rating   = self._temp_spin.value(),
            orifice       = self._ori_edit.text().strip(),
            notes         = self._notes_edit.text().strip(),
        )
