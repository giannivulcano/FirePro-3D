"""Edit Attributes dialog for a placed BlockInstance (SB1a A3 / A4).

Rows: label / source / value. A host-sourced row shows the resolved value
read-only with an Override checkbox that enables an editor (uncheck =
binding restored, i.e. the key is deleted -- design D4). OK commits one
``set_attributes`` inside ``Model_Space.deferred_undo_push`` (one undo
step); Cancel discards. ``AttributeRowsWidget`` is shared with the Block
Editor's Attributes editor (block_attributes_editor.py).
"""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import (QCheckBox, QGridLayout, QLabel, QLineEdit,
                             QWidget)

from .block_attributes import resolve_values
from .house_dialog import HouseDialog


@dataclass
class AttributeRow:
    key: str
    record: dict
    label: QLabel
    source: QLabel
    resolved: QLabel          # host rows: the provider's value (read-only)
    override: QCheckBox | None
    editor: QLineEdit


class AttributeRowsWidget(QWidget):
    """A grid of attribute rows: Label | Source | Resolved | Override | Value."""

    def __init__(self, attrs: list, instance_values: dict,
                 host_values: dict | None, parent=None):
        super().__init__(parent)
        self.rows: list[AttributeRow] = []
        grid = QGridLayout(self)
        for h, col in (("Attribute", 0), ("Source", 1), ("Value", 2),
                       ("Override", 3), ("Edit", 4)):
            grid.addWidget(QLabel(h), 0, col)
        resolved = resolve_values(attrs, {}, host_values)   # provider values, no override
        for i, rec in enumerate(attrs, start=1):
            key = rec["key"]
            is_host = rec.get("source") == "host"
            lab = QLabel(rec.get("label") or key)
            src = QLabel("Host: " + rec.get("host_key", "") if is_host else "Instance")
            res = QLabel(resolved[key] if is_host else "")
            ed = QLineEdit()
            if rec.get("type") == "number":
                v = QDoubleValidator()
                v.setNotation(QDoubleValidator.Notation.StandardNotation)
                ed.setValidator(v)
            ov = None
            if is_host:
                ov = QCheckBox()
                on = key in instance_values
                ov.setChecked(on)
                ed.setEnabled(on)
                ed.setText(str(instance_values.get(key, "")))
                ov.toggled.connect(ed.setEnabled)
            else:
                ed.setText(str(instance_values.get(key, rec.get("default", ""))))
            grid.addWidget(lab, i, 0)
            grid.addWidget(src, i, 1)
            grid.addWidget(res, i, 2)
            if ov is not None:
                grid.addWidget(ov, i, 3)
            grid.addWidget(ed, i, 4)
            self.rows.append(AttributeRow(key, rec, lab, src, res, ov, ed))

    def values(self) -> dict:
        """The instance ``attributes`` dict these rows describe (D4: a host
        key is present only while its Override is checked; a number editor
        with unacceptable text contributes nothing)."""
        out: dict = {}
        for r in self.rows:
            if r.override is not None and not r.override.isChecked():
                continue
            if r.editor.validator() is not None and not r.editor.hasAcceptableInput():
                continue
            out[r.key] = r.editor.text()
        return out


class EditAttributesDialog(HouseDialog):
    """Edit a placed instance's attribute values (A3)."""

    def __init__(self, instance, scene, parent=None):
        super().__init__(parent, title="Edit Attributes", min_width=420)
        self._inst = instance
        self._scene = scene
        d = instance.definition()
        attrs = d.effective_attributes() if d is not None else []
        self.rows = AttributeRowsWidget(attrs, instance.attributes,
                                        instance.host_values(), self)
        self.body_layout().addWidget(self.rows)
        self.set_footer_buttons(primary=("OK", self.accept), cancel=True)

    def accept(self) -> None:
        new = self.rows.values()
        if new != self._inst.attributes:
            with self._scene.deferred_undo_push():
                self._inst.set_attributes(new)
                self._scene.request_undo_push()
        super().accept()
