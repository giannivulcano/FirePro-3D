"""
paper_export_dialog.py
======================
Batch export / print sheet-selection dialog (paper-space spec §19.6).

Pure selection UI: returns which sheets, which mode, where, and at what DPI.
The caller (MainWindow) owns the actual export/print calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from firepro3d.paper_space import Sheet

from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QScrollArea,
    QVBoxLayout, QWidget,
)


@dataclass
class ExportSelection:
    """Result of the dialog: selected sheets in document-set order."""
    sheets: list[Sheet]
    separate_files: bool
    path: str
    dpi: int


class PaperExportDialog(QDialog):
    """Sheet checklist + mode + output + DPI (spec §19.6).

    Args:
        sheets: All project sheets in document-set order.
        parent: Qt parent.
        print_mode: Hide path + DPI rows (print uses QPrintDialog after).
    """

    def __init__(self, sheets, parent=None, print_mode: bool = False):
        super().__init__(parent)
        self._sheets = list(sheets)
        self._print_mode = print_mode
        self.setWindowTitle("Print Sheets" if print_mode else "Export Sheets to PDF")

        lay = QVBoxLayout(self)

        self._select_all = QCheckBox("Select All")
        self._select_all.setChecked(True)
        self._select_all.toggled.connect(self._on_select_all)
        lay.addWidget(self._select_all)

        list_host = QWidget()
        list_lay = QVBoxLayout(list_host)
        list_lay.setContentsMargins(12, 0, 0, 0)
        self._checks: list[QCheckBox] = []
        for s in self._sheets:
            cb = QCheckBox(f"{s.number} - {s.name}")
            cb.setChecked(True)
            cb.toggled.connect(self._update_ok)
            self._checks.append(cb)
            list_lay.addWidget(cb)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(list_host)
        lay.addWidget(scroll)

        self._radio_single = QRadioButton("Single multi-page PDF")
        self._radio_separate = QRadioButton("Separate file per sheet")
        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self._radio_single)
        self._mode_group.addButton(self._radio_separate)
        self._radio_single.setChecked(True)
        self._radio_single.toggled.connect(self._on_mode_changed)

        path_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.textChanged.connect(self._update_ok)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        path_row.addWidget(QLabel("Output:"))
        path_row.addWidget(self._path_edit, 1)
        path_row.addWidget(browse)

        dpi_row = QHBoxLayout()
        self._dpi_combo = QComboBox()
        self._dpi_combo.addItems(["150 DPI", "300 DPI", "600 DPI"])
        self._dpi_combo.setCurrentIndex(1)
        dpi_row.addWidget(QLabel("Resolution:"))
        dpi_row.addWidget(self._dpi_combo)
        dpi_row.addStretch(1)

        self._path_row_hidden = print_mode
        self._dpi_hidden = print_mode
        if not print_mode:
            lay.addWidget(self._radio_single)
            lay.addWidget(self._radio_separate)
            lay.addLayout(path_row)
            lay.addLayout(dpi_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        lay.addWidget(buttons)
        self._update_ok()

    # ── behaviour ─────────────────────────────────────────────────────────

    def _on_select_all(self, on: bool):
        for cb in self._checks:
            cb.setChecked(on)

    def _on_mode_changed(self):
        self._path_edit.clear()             # file vs directory semantics differ

    def _browse(self):
        if self._radio_separate.isChecked():
            path = QFileDialog.getExistingDirectory(self, "Output Folder")
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Export to PDF", "sheets.pdf", "PDF Files (*.pdf)")
        if path:
            self._path_edit.setText(path)

    def _update_ok(self):
        checked = [cb.isChecked() for cb in self._checks]
        any_checked = any(checked)
        path_ok = self._print_mode or bool(self._path_edit.text().strip())
        self._ok_btn.setEnabled(any_checked and path_ok)
        self._select_all.blockSignals(True)
        self._select_all.setChecked(bool(checked) and all(checked))
        self._select_all.blockSignals(False)

    def selection(self) -> ExportSelection:
        """Selected sheets in document-set order + mode/path/dpi."""
        sheets = [s for s, cb in zip(self._sheets, self._checks)
                  if cb.isChecked()]
        return ExportSelection(
            sheets=sheets,
            separate_files=self._radio_separate.isChecked(),
            path=self._path_edit.text().strip(),
            dpi=int(self._dpi_combo.currentText().split()[0]),
        )
