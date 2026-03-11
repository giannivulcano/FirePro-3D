"""
property_manager.py
===================
Properties dock panel for FirePro 3D.

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
from PyQt6.QtCore import Qt, QTimer

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
        self._user_layer_manager = None
        self._targets: list = []
        self._refreshing = False   # guard against re-entrant refresh

        # Debounced auto-refresh timer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(50)
        self._refresh_timer.timeout.connect(self._do_refresh)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_level_manager(self, lm):
        self._level_manager = lm

    def set_user_layer_manager(self, ulm):
        self._user_layer_manager = ulm

    def show_properties(self, item):
        """Display properties for *item* (single entity, list, or None)."""
        self._refreshing = True

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

            # Detect mixed values across multi-selection
            is_mixed = False
            if len(self._targets) > 1:
                primary_val = str(meta.get("value", ""))
                for other in self._targets[1:]:
                    other_props = other.get_properties() if hasattr(other, "get_properties") else {}
                    other_meta = other_props.get(key)
                    if other_meta and str(other_meta.get("value", "")) != primary_val:
                        is_mixed = True
                        break

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
                btn.setProperty("_color_value", meta["value"])
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

            # ── layer_ref (user-layer dropdown from UserLayerManager) ──────
            elif prop_type == "layer_ref":
                combo = QComboBox()
                if self._user_layer_manager is not None:
                    for lyr in self._user_layer_manager.layers:
                        combo.addItem(lyr.name)
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

            # Show mixed-value indicator for multi-select with differing values
            if is_mixed and widget is not None:
                if isinstance(widget, QLineEdit):
                    widget.setPlaceholderText("< mixed >")
                    widget.clear()
                elif isinstance(widget, QComboBox):
                    widget.insertItem(0, "< mixed >")
                    widget.setCurrentIndex(0)

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

        self._refreshing = False

    # ── Private helpers ───────────────────────────────────────────────────────

    def _apply_property(self, key: str, value):
        """Apply a property change to ALL selected targets, then refresh."""
        if self._refreshing:
            return  # ignore signals fired during form rebuild
        for t in self._targets:
            if hasattr(t, "set_property"):
                t.set_property(key, value)
        # Notify the scene so the 3D view rebuilds
        if self._targets:
            scene = None
            for t in self._targets:
                scene = t.scene() if callable(getattr(t, "scene", None)) else None
                if scene is not None:
                    break
            if scene is not None and hasattr(scene, "sceneModified"):
                scene.sceneModified.emit()
        # Auto-refresh so dependent fields (e.g. elevation) update immediately
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def _do_refresh(self):
        """Re-display properties for the current targets."""
        if self._targets:
            self.show_properties(
                self._targets if len(self._targets) > 1 else self._targets[0]
            )

    def _pick_color(self, key: str, btn: QPushButton):
        """Open a colour dialog, update swatch, and apply to all targets."""
        _t = th.detect()
        stored = btn.property("_color_value")
        current = QColor(stored) if stored else QColor("#cccccc")

        color = QColorDialog.getColor(current, self, "Pick a colour")
        if color.isValid():
            btn.setProperty("_color_value", color.name())
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
