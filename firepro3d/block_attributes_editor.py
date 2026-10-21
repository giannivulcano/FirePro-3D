"""Attributes editor for the Block Editor (SB1a S4 / A7).

A table of attribute records (key, label, type, source, host key, default,
prefix, suffix, precision, placeholder) with Add / Remove / Up / Down. OK
validates (empty or duplicate keys refused inline; removing a key that text
primitives still reference is refused with "used by N text fields") and
applies through ``BlockEditorWidget.apply_attributes_edit`` -- renames
cascade through every ``@[old]`` in the editor's text items, all in one
editor undo step.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPushButton,
                             QTableWidget, QTableWidgetItem, QWidget)

from .block_attributes import ATTR_SOURCES, ATTR_TYPES, references_of
from .house_dialog import HouseDialog

COLUMNS = ("key", "label", "type", "source", "host_key", "default",
           "prefix", "suffix", "precision", "placeholder")
_HEADERS = ("Key", "Label", "Type", "Source", "Host key", "Default",
            "Prefix", "Suffix", "Precision", "Placeholder")
_ORIG_ROLE = 0x0100 + 7       # Qt.ItemDataRole.UserRole + 7: the row's original key


class AttributesEditorDialog(HouseDialog):
    """Modal table editor for the edited block's attribute records."""

    def __init__(self, editor, parent=None):
        super().__init__(parent, title="Attributes", min_width=720, resizable=True)
        self._editor = editor
        self._scene = editor.editor_scene
        self._msg = QLabel()
        self.table = QTableWidget(0, len(COLUMNS), self)
        self.table.setHorizontalHeaderLabels(_HEADERS)
        for rec in self._scene.block_meta["attributes"]:
            self._append(rec, orig=rec["key"])
        btns = QWidget()
        bl = QHBoxLayout(btns)
        for label, slot in (("Add", self.add_row), ("Remove", self._remove_current),
                            ("Up", lambda: self._move(-1)), ("Down", lambda: self._move(1))):
            b = QPushButton(label)
            b.clicked.connect(slot)
            bl.addWidget(b)
        bl.addStretch(1)
        self.body_layout().addWidget(self.table)
        self.body_layout().addWidget(btns)
        self.body_layout().addWidget(self._msg)
        self.set_footer_buttons(primary=("OK", self.accept), cancel=True)

    # -- table helpers (also the test seam) ------------------------------
    def _append(self, rec: dict, orig: str | None) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, col in enumerate(COLUMNS):
            if col in ("type", "source"):
                box = QComboBox()
                box.addItems(list(ATTR_TYPES if col == "type" else ATTR_SOURCES))
                box.setCurrentText(str(rec.get(col, box.itemText(0))))
                self.table.setCellWidget(r, c, box)
            else:
                it = QTableWidgetItem(str(rec.get(col, "")))
                if c == 0:
                    it.setData(_ORIG_ROLE, orig)
                self.table.setItem(r, c, it)

    def add_row(self) -> None:
        self._append({"key": "", "placeholder": "?", "precision": "0"}, orig=None)

    def remove_row(self, row: int) -> None:
        self.table.removeRow(row)

    def _remove_current(self) -> None:
        r = self.table.currentRow()
        if r >= 0:
            self.remove_row(r)

    def _move(self, delta: int) -> None:
        """Up / Down: swap the current row with its neighbour (rebuilds the
        table from the row list -- cell widgets cannot be moved in place)."""
        r = self.table.currentRow()
        t = r + delta
        if r < 0 or t < 0 or t >= self.table.rowCount():
            return
        rows = [(self.row_record(i), self._orig(i)) for i in range(self.table.rowCount())]
        rows[r], rows[t] = rows[t], rows[r]
        self.table.setRowCount(0)
        for rec, orig in rows:
            self._append(rec, orig)
        self.table.setCurrentCell(t, 0)

    def set_cell(self, row: int, col: str, value: str) -> None:
        c = COLUMNS.index(col)
        w = self.table.cellWidget(row, c)
        if w is not None:
            w.setCurrentText(value)
        else:
            self.table.item(row, c).setText(value)

    def _orig(self, row: int):
        return self.table.item(row, 0).data(_ORIG_ROLE)

    def row_record(self, row: int) -> dict:
        out = {}
        for c, col in enumerate(COLUMNS):
            w = self.table.cellWidget(row, c)
            out[col] = w.currentText() if w is not None else self.table.item(row, c).text()
        return out

    def message(self) -> str:
        return self._msg.text()

    # -- validation + apply ----------------------------------------------
    def try_accept(self) -> bool:
        """Validate; on success apply (one editor undo step) and return True.
        On refusal set ``message()`` and return False (dialog stays open)."""
        records, renames, kept = [], {}, set()
        for r in range(self.table.rowCount()):
            rec = self.row_record(r)
            key = rec["key"].strip()
            if not key:
                self._msg.setText("Attribute key must not be empty.")
                return False
            if key in {x["key"] for x in records}:
                self._msg.setText(f"Duplicate key: {key} -- keys must be unique.")
                return False
            try:
                rec["precision"] = int(rec["precision"] or 0)
            except ValueError:
                self._msg.setText(f"Precision of {key} must be a whole number.")
                return False
            orig = self._orig(r)
            if orig is not None:
                kept.add(orig)
                if orig != key:
                    renames[orig] = key
            records.append(rec)
        prims = self._editor_text_prims()
        for old in (a["key"] for a in self._scene.block_meta["attributes"]):
            if old not in kept:
                n = len(references_of(prims, old))
                if n:
                    self._msg.setText(f"Cannot remove {old}: used by {n} text field"
                                      f"{'' if n == 1 else 's'}.")
                    return False
        self._editor.apply_attributes_edit(records, renames)
        return True

    def _editor_text_prims(self) -> list:
        from .text_item import TextItem
        return [it.to_dict() for it in self._scene.items() if isinstance(it, TextItem)]

    def accept(self) -> None:
        if self.try_accept():
            super().accept()
