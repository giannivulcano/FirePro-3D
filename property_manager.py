"""
property_manager.py
===================
Properties dock panel for FireFlow Pro.

Displays editable properties for the currently selected entity (or template).
Supports multi-select: property changes apply to every selected item.

Property types recognised from ``get_properties()`` dict:
    label      — read-only informational text
    string     — editable QLineEdit (auto-detects numeric fields)
    enum       — QComboBox with fixed options list
    color      — colour swatch + QColorDialog picker
    level_ref  — QComboBox populated from LevelManager
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QColorDialog, QSizePolicy, QScrollArea,
)
from PyQt6.QtGui import QDoubleValidator, QColor, QFont
from PyQt6.QtCore import Qt

from node import Node
from pipe import Pipe
from sprinkler import Sprinkler
import theme as th


class PropertyManager(QWidget):
    """Right-dock panel that shows / edits properties for one or more items."""

    def __init__(self, parent=None):
        super().__init__(parent)

        _t = th.detect()

        # ── Outer layout ──────────────────────────────────────────────────────
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        # Header — matches project_browser / model_browser style
        hdr = QLabel("Properties")
        hdr.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        f = QFont()
        f.setBold(True)
        f.setPointSize(9)
        hdr.setFont(f)
        hdr.setStyleSheet(
            f"color: {_t.text_primary}; "
            f"background: {_t.bg_raised}; "
            f"padding: 4px; "
            f"border-radius: 3px;"
        )
        outer.addWidget(hdr)

        # Scrollable form area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._form_container = QWidget()
        self._form = QFormLayout(self._form_container)
        self._form.setContentsMargins(4, 4, 4, 4)
        self._form.setSpacing(6)
        scroll.setWidget(self._form_container)
        outer.addWidget(scroll)

        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Expanding)

        # State
        self._level_manager = None
        self._targets: list = []

    # ── Public API ────────────────────────────────────────────────────────────

    def set_level_manager(self, lm):
        self._level_manager = lm

    def show_properties(self, item):
        """Display properties for *item* (single entity, list, or None)."""

        # Clear existing rows
        for i in reversed(range(self._form.count())):
            w = self._form.itemAt(i).widget()
            if w:
                w.deleteLater()

        if item is None:
            self._targets = []
            return

        # Normalise to list (multi-select support)
        targets = item if isinstance(item, list) else [item]

        # Resolve sprinklers sitting on nodes
        resolved = []
        for t in targets:
            if isinstance(t, Node) and t.has_sprinkler():
                resolved.append(t.sprinkler)
            else:
                resolved.append(t)
        self._targets = resolved

        if not self._targets:
            return

        primary = self._targets[0]
        if not hasattr(primary, "get_properties"):
            return

        _t = th.detect()
        has_level_ref = False

        for key, meta in primary.get_properties().items():
            widget = None
            prop_type = meta.get("type", "string")

            # ── label (read-only) ─────────────────────────────────────────
            if prop_type == "label":
                widget = QLabel(str(meta["value"]))
                widget.setStyleSheet(
                    f"background: {_t.bg_sunken}; "
                    f"padding: 4px; "
                    f"border-radius: 2px; "
                    f"color: {_t.text_secondary};"
                )

            # ── color (colour picker swatch) ──────────────────────────────
            elif prop_type == "color":
                btn = QPushButton()
                btn.setFixedSize(60, 24)
                btn.setStyleSheet(
                    f"background: {meta['value']}; "
                    f"border: 1px solid {_t.border_subtle}; "
                    f"border-radius: 2px;"
                )
                btn.clicked.connect(
                    lambda _, k=key, b=btn: self._pick_color(k, b)
                )
                widget = btn

            # ── level_ref (level dropdown from LevelManager) ──────────────
            elif prop_type == "level_ref":
                has_level_ref = True
                combo = QComboBox()
                if self._level_manager is not None:
                    for lv in self._level_manager.levels:
                        combo.addItem(lv.name)
                combo.setCurrentText(str(meta["value"]))
                combo.currentTextChanged.connect(
                    lambda val, k=key: self._apply_property(k, val)
                )
                widget = combo

            # ── enum (fixed option list) ──────────────────────────────────
            elif prop_type == "enum":
                widget = QComboBox()
                widget.addItems(meta.get("options", []))
                widget.setCurrentText(str(meta["value"]))
                widget.currentTextChanged.connect(
                    lambda val, k=key: self._apply_property(k, val)
                )

            # ── string / fallback (editable line edit) ────────────────────
            else:
                widget = QLineEdit(str(meta["value"]))
                # Auto-detect numeric fields for input validation
                try:
                    float(meta["value"])
                    validator = QDoubleValidator()
                    validator.setNotation(
                        QDoubleValidator.Notation.StandardNotation)
                    widget.setValidator(validator)
                except (ValueError, TypeError):
                    pass
                widget.editingFinished.connect(
                    lambda k=key, field=widget: self._apply_property(
                        k, field.text())
                )

            self._form.addRow(QLabel(key), widget)

        # ── Legacy Level assignment (nodes, pipes, sprinklers) ────────────
        # Only show if the item doesn't already expose level_ref properties
        if (not has_level_ref
                and hasattr(primary, "level")
                and self._level_manager is not None):
            combo = QComboBox()
            for lv in self._level_manager.levels:
                combo.addItem(lv.name)
            combo.setCurrentText(primary.level)
            combo.currentTextChanged.connect(
                lambda val: self._change_level(val)
            )
            self._form.addRow(QLabel("Level"), combo)

        # ── Read-only absolute elevation for nodes ────────────────────────
        node = None
        if isinstance(primary, Node):
            node = primary
        elif isinstance(primary, Sprinkler) and primary.node is not None:
            node = primary.node
        if node is not None:
            abs_field = QLineEdit(f"{node.z_pos:.2f}")
            abs_field.setReadOnly(True)
            abs_field.setStyleSheet(
                f"background: {_t.bg_sunken}; "
                f"color: {_t.text_secondary};"
            )
            self._form.addRow(QLabel("Absolute Elev. (ft)"), abs_field)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _apply_property(self, key: str, value):
        """Apply a property change to ALL selected targets."""
        for t in self._targets:
            if hasattr(t, "set_property"):
                t.set_property(key, value)

    def _pick_color(self, key: str, btn: QPushButton):
        """Open a colour dialog, update swatch, and apply to all targets."""
        _t = th.detect()
        # Parse current colour from button stylesheet
        try:
            raw = btn.styleSheet().split("background:")[1].split(";")[0].strip()
            current = QColor(raw)
        except Exception:
            current = QColor("#cccccc")

        color = QColorDialog.getColor(current, self, "Pick a colour")
        if color.isValid():
            btn.setStyleSheet(
                f"background: {color.name()}; "
                f"border: 1px solid {_t.border_subtle}; "
                f"border-radius: 2px;"
            )
            self._apply_property(key, color.name())

    def _change_level(self, new_level: str):
        """Change level for all targets (legacy path for nodes/pipes)."""
        for t in self._targets:
            t.level = new_level
            if self._level_manager is not None:
                node = t if isinstance(t, Node) else None
                if isinstance(t, Sprinkler) and t.node:
                    node = t.node
                if node is not None:
                    lvl = self._level_manager.get(new_level)
                    if lvl:
                        node.z_pos = lvl.elevation + node.z_offset
                scene = t.scene()
                if scene:
                    self._level_manager.apply_to_scene(scene)
        # Refresh to update absolute elevation display
        if self._targets:
            self.show_properties(
                self._targets if len(self._targets) > 1 else self._targets[0]
            )
