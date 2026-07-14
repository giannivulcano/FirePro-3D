"""
property_manager.py
===================
Properties dock panel for FirePro 3D.

Displays editable properties for the currently selected entity (or template).
Supports multi-select: property changes apply to every selected item.

Property types recognised from ``get_properties()`` dict:
    header     — section-divider label (no editor, no "value" key needed)
    label      — read-only informational text
    string     — editable QLineEdit (auto-detects numeric fields)
    enum       — QComboBox with fixed options list
    combo      — alias for enum
    color      — colour swatch + QColorDialog picker
    level_ref  — QComboBox populated from LevelManager
    button     — QPushButton that calls meta["callback"] when clicked
    dimension  — DimensionEdit for mm-based values (requires value_mm in meta)
    bool       — QCheckBox
    font       — QFontComboBox family picker
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QColorDialog, QSizePolicy, QScrollArea,
    QCheckBox, QFontComboBox,
)
from PyQt6.QtGui import QDoubleValidator, QColor, QFont
from PyQt6.QtCore import Qt, QTimer

from .node import Node
from .pipe import Pipe
from .sprinkler import Sprinkler
from .sprinkler_db import SprinklerDatabase
from .dimension_edit import DimensionEdit
from . import theme as th

# Lazy-loaded singleton sprinkler database
_sprinkler_db: SprinklerDatabase | None = None

def _get_sprinkler_db() -> SprinklerDatabase:
    global _sprinkler_db
    if _sprinkler_db is None:
        _sprinkler_db = SprinklerDatabase()
    return _sprinkler_db


class _MixedStateCheckBox(QCheckBox):
    """Checkbox with Word-like mixed-state semantics for multi-select.

    PartiallyChecked is a *display-only* state (set programmatically when a
    multi-selection has differing values). A user click always resolves to a
    definite state: partial -> checked, then checked <-> unchecked — never
    cycling back into partial (Qt's default tristate cycle does, and its
    partial state also reports isChecked() True, so ``toggled`` never fires
    on the partial -> checked click; commit via ``clicked`` instead).
    """

    def nextCheckState(self):
        if self.checkState() == Qt.CheckState.PartiallyChecked:
            self.setCheckState(Qt.CheckState.Checked)
        else:
            self.setChecked(not self.isChecked())


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
        # No visible scrollbars — mouse-wheel scrolling still works
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

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
        self._refreshing = False   # guard against re-entrant refresh

        # Debounced auto-refresh timer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(50)
        self._refresh_timer.timeout.connect(self._do_refresh)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_level_manager(self, lm):
        self._level_manager = lm

    def show_properties(self, item):
        """Display properties for *item* (single entity, list, or None)."""
        self._refreshing = True
        try:
            self._show_properties_inner(item)
        finally:
            self._refreshing = False

    def _show_properties_inner(self, item):
        """Internal: build the property form (called inside _refreshing guard)."""
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

        # Populate cascading options for sprinklers before rendering
        if isinstance(primary, Sprinkler):
            self._cascade_sprinkler_props(primary)

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

            # ── header (section divider — no editor) ─────────────────────
            if prop_type == "header":
                hdr_lbl = QLabel(f"── {key} ──")
                hdr_lbl.setStyleSheet(
                    f"color: {_t.text_secondary}; font-weight: bold; "
                    f"padding-top: 6px;"
                )
                self._form.addRow(hdr_lbl)
                continue

            # ── label (read-only) ─────────────────────────────────────────
            elif prop_type == "label":
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
                # Cap the minimum width so long entries can't force the
                # form wider than the dock (panel clips: ScrollBarAlwaysOff)
                combo.setMinimumContentsLength(8)
                if self._level_manager is not None:
                    for lv in self._level_manager.levels:
                        combo.addItem(lv.name)
                combo.setCurrentText(str(meta["value"]))
                combo.currentTextChanged.connect(
                    lambda val, k=key: self._apply_property(k, val)
                )
                widget = combo

            # ── dimension (DimensionEdit for mm values) ─────────────────
            elif prop_type == "dimension":
                sm = self._get_scale_manager()
                val_mm = meta.get("value_mm", 0.0)
                dim_edit = DimensionEdit(sm, initial_mm=float(val_mm),
                                         parser=meta.get("parser"),
                                         minimum=meta.get("minimum"),
                                         formatter=meta.get("formatter"))
                dim_edit.editingFinished.connect(
                    lambda k=key, de=dim_edit: self._apply_property(
                        k, de.value_mm())
                )
                widget = dim_edit

            # ── bool (checkbox) ───────────────────────────────────────────
            elif prop_type == "bool":
                chk = _MixedStateCheckBox()
                chk.setChecked(bool(meta["value"]))
                # clicked (not toggled): fires on every user click, after
                # nextCheckState resolves — the partial -> checked click
                # never changes the checked bool, so toggled misses it.
                chk.clicked.connect(
                    lambda _, k=key, c=chk: self._apply_property(
                        k, c.isChecked())
                )
                widget = chk

            # ── font (family picker) ──────────────────────────────────────
            elif prop_type == "font":
                fcombo = QFontComboBox()
                fcombo.setMinimumContentsLength(8)
                if meta["value"]:
                    fcombo.setCurrentFont(QFont(str(meta["value"])))
                fcombo.currentFontChanged.connect(
                    lambda f, k=key: self._apply_property(k, f.family())
                )
                widget = fcombo

            # ── enum (fixed option list) ──────────────────────────────────
            elif prop_type == "enum":
                widget = QComboBox()
                widget.setMinimumContentsLength(8)
                widget.addItems(meta.get("options", []))
                widget.setCurrentText(str(meta["value"]))
                widget.currentTextChanged.connect(
                    lambda val, k=key: self._apply_property(k, val)
                )

            # ── button (opens a callback) ───────────────────────────────
            elif prop_type == "button":
                btn = QPushButton(str(meta.get("value", "Edit…")))
                # Long faces (e.g. Design Point) must never force the form
                # width — Ignored lets the button shrink; tooltip keeps the
                # full text readable.
                btn.setSizePolicy(QSizePolicy.Policy.Ignored,
                                  btn.sizePolicy().verticalPolicy())
                btn.setToolTip(str(meta.get("value", "")))
                callback = meta.get("callback")
                if callback:
                    btn.clicked.connect(
                        lambda _, cb=callback: self._on_button_callback(cb)
                    )
                widget = btn

            # ── combo (alias for enum) ──────────────────────────────────
            elif prop_type == "combo":
                widget = QComboBox()
                widget.setMinimumContentsLength(8)
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
                    validator.setBottom(-1e9)
                    validator.setNotation(
                        QDoubleValidator.Notation.StandardNotation)
                    widget.setValidator(validator)
                except (ValueError, TypeError):
                    pass
                widget.editingFinished.connect(
                    lambda k=key, field=widget: self._apply_property(
                        k, field.text())
                )

            # Enforce readonly flag from meta (e.g. template node sections)
            if meta.get("readonly") and widget is not None:
                if isinstance(widget, QComboBox):
                    widget.setEnabled(False)
                elif isinstance(widget, QLineEdit):
                    widget.setReadOnly(True)
                    widget.setStyleSheet(
                        f"background: {_t.bg_sunken}; "
                        f"color: {_t.text_secondary};"
                    )

            # Show mixed-value indicator for multi-select with differing values
            if is_mixed and widget is not None:
                if isinstance(widget, QLineEdit):
                    widget.setPlaceholderText("< mixed >")
                    widget.clear()
                elif isinstance(widget, QCheckBox):
                    widget.setTristate(True)
                    widget.setCheckState(Qt.CheckState.PartiallyChecked)
                elif isinstance(widget, QComboBox):
                    widget.insertItem(0, "< mixed >")
                    widget.setCurrentIndex(0)

            suffix = meta.get("suffix")
            if suffix and widget is not None:
                row_layout = QHBoxLayout()
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.addWidget(widget, 1)
                suffix_lbl = QLabel(suffix)
                suffix_lbl.setStyleSheet("color: grey; font-style: italic;")
                row_layout.addWidget(suffix_lbl)
                container = QWidget()
                container.setLayout(row_layout)
                self._form.addRow(QLabel(key), container)
            else:
                self._form.addRow(QLabel(key), widget)

        # ── Legacy Level assignment (nodes, pipes, sprinklers) ────────────
        # Only show if the item doesn't already expose level_ref properties
        if (not has_level_ref
                and hasattr(primary, "level")
                and self._level_manager is not None):
            combo = QComboBox()
            combo.setMinimumContentsLength(8)
            for lv in self._level_manager.levels:
                combo.addItem(lv.name)
            combo.setCurrentText(primary.level)
            combo.currentTextChanged.connect(
                lambda val: self._change_level(val)
            )
            self._form.addRow(QLabel("Level"), combo)

        # ── Node properties for pipes ──────────────────────────────────────
        if isinstance(primary, Pipe):
            for idx, node_attr in enumerate(("node1", "node2"), 1):
                node = getattr(primary, node_attr, None)
                if node is None:
                    continue
                # Section header
                hdr_lbl = QLabel(f"── Node {idx} ──")
                hdr_lbl.setStyleSheet(
                    f"color: {_t.text_secondary}; font-weight: bold;"
                )
                self._form.addRow(hdr_lbl, QLabel(""))

                node_props = node.get_properties()
                for nkey, nmeta in node_props.items():
                    ntype = nmeta.get("type", "string")
                    nwidget = None

                    if ntype == "level_ref":
                        nwidget = QComboBox()
                        nwidget.setMinimumContentsLength(8)
                        if self._level_manager is not None:
                            for lv in self._level_manager.levels:
                                nwidget.addItem(lv.name)
                        nwidget.setCurrentText(str(nmeta["value"]))
                        nwidget.currentTextChanged.connect(
                            lambda val, k=nkey, n=node: self._apply_node_property(n, k, val)
                        )
                    elif ntype == "label":
                        nwidget = QLabel(str(nmeta["value"]))
                        nwidget.setStyleSheet(
                            f"background: {_t.bg_sunken}; "
                            f"padding: 4px; border-radius: 2px; "
                            f"color: {_t.text_secondary};"
                        )
                    else:
                        nwidget = QLineEdit(str(nmeta["value"]))
                        try:
                            float(nmeta["value"])
                            validator = QDoubleValidator()
                            validator.setBottom(-1e9)
                            validator.setNotation(
                                QDoubleValidator.Notation.StandardNotation)
                            nwidget.setValidator(validator)
                        except (ValueError, TypeError):
                            pass
                        nwidget.editingFinished.connect(
                            lambda k=nkey, field=nwidget, n=node: self._apply_node_property(n, k, field.text())
                        )

                    nsuffix = nmeta.get("suffix")
                    if nsuffix and nwidget is not None:
                        row_layout = QHBoxLayout()
                        row_layout.setContentsMargins(0, 0, 0, 0)
                        row_layout.addWidget(nwidget, 1)
                        suffix_lbl = QLabel(nsuffix)
                        suffix_lbl.setStyleSheet("color: grey; font-style: italic;")
                        row_layout.addWidget(suffix_lbl)
                        container = QWidget()
                        container.setLayout(row_layout)
                        self._form.addRow(QLabel(nkey), container)
                    else:
                        self._form.addRow(QLabel(nkey), nwidget)

                # Read-only absolute elevation
                sc = node.scene()
                sm = sc.scale_manager if sc and hasattr(sc, "scale_manager") else None
                elev_text = sm.format_length(node.z_pos) if sm else f"{node.z_pos:.1f} mm"
                abs_field = QLineEdit(elev_text)
                abs_field.setReadOnly(True)
                abs_field.setStyleSheet(
                    f"background: {_t.bg_sunken}; "
                    f"color: {_t.text_secondary};"
                )
                self._form.addRow(QLabel("Absolute Elev."), abs_field)

        # ── Read-only absolute elevation for nodes ────────────────────────
        node = None
        if isinstance(primary, Node):
            node = primary
        elif isinstance(primary, Sprinkler) and primary.node is not None:
            node = primary.node
        if node is not None:
            sc = node.scene()
            sm = sc.scale_manager if sc and hasattr(sc, "scale_manager") else None
            elev_text = sm.format_length(node.z_pos) if sm else f"{node.z_pos:.1f} mm"
            abs_field = QLineEdit(elev_text)
            abs_field.setReadOnly(True)
            abs_field.setStyleSheet(
                f"background: {_t.bg_sunken}; "
                f"color: {_t.text_secondary};"
            )
            self._form.addRow(QLabel("Absolute Elev."), abs_field)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _on_button_callback(self, callback):
        """Execute a property button callback and refresh the panel."""
        try:
            callback()
        except Exception:
            pass
        # Refresh properties to reflect any changes
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def _apply_node_property(self, node: Node, key: str, value):
        """Apply a property change to a specific node, then refresh."""
        if self._refreshing:
            return
        node.set_property(key, value)
        scene = node.scene() if callable(getattr(node, "scene", None)) else None
        if scene is not None and hasattr(scene, "sceneModified"):
            scene.sceneModified.emit()
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def _apply_property(self, key: str, value):
        """Apply a property change to ALL selected targets, then refresh.

        When several targets share a scene exposing a QUndoStack (paper
        space), the per-target commands are wrapped in a single macro so one
        panel commit is one undo step (spec property-panel.md §3.3).
        """
        if self._refreshing:
            return  # ignore signals fired during form rebuild
        stack = None
        if len(self._targets) > 1:
            for t in self._targets:
                sc = t.scene() if callable(getattr(t, "scene", None)) else None
                stack = getattr(sc, "undo_stack", None) if sc is not None else None
                if stack is not None:
                    break
        if stack is not None and hasattr(stack, "beginMacro"):
            stack.beginMacro(f"Edit {key}")
        try:
            for t in self._targets:
                if hasattr(t, "set_property"):
                    t.set_property(key, value)
                # Cascade sprinkler property updates from database
                if isinstance(t, Sprinkler) and key in ("Manufacturer", "Model", "Orientation"):
                    self._cascade_sprinkler_props(t)
        finally:
            if stack is not None and hasattr(stack, "endMacro"):
                stack.endMacro()
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

    def _get_scale_manager(self):
        """Return the ScaleManager from the first target's scene, or fallback ref."""
        for t in self._targets:
            sc = t.scene() if callable(getattr(t, "scene", None)) else None
            if sc is not None and hasattr(sc, "scale_manager"):
                return sc.scale_manager
            # Templates not in a scene may have a direct reference
            ref = getattr(t, "_scale_manager_ref", None)
            if ref is not None and hasattr(ref, "format_length"):
                return ref
            # Pipe/sprinkler templates use _scene_ref
            scene_ref = getattr(t, "_scene_ref", None)
            if scene_ref is not None and hasattr(scene_ref, "scale_manager"):
                return scene_ref.scale_manager
        return None

    def _do_refresh(self):
        """Re-display properties for the current targets."""
        if self._targets:
            self.show_properties(
                self._targets if len(self._targets) > 1 else self._targets[0]
            )

    def _cascade_sprinkler_props(self, sprinkler: Sprinkler):
        """Update sprinkler property options based on database cascading filters."""
        db = _get_sprinkler_db()
        props = sprinkler._properties
        mfr = props["Manufacturer"]["value"]

        # Update Model options filtered by manufacturer
        models = db.get_models_for(mfr)
        props["Model"]["options"] = models
        if props["Model"]["value"] not in models and models:
            props["Model"]["value"] = models[0]

        # Update Orientation options filtered by manufacturer + model
        model = props["Model"]["value"]
        types = db.get_types_for(mfr, model)
        props["Orientation"]["options"] = types or ["Upright", "Pendent", "Sidewall"]
        if props["Orientation"]["value"] not in props["Orientation"]["options"]:
            if props["Orientation"]["options"]:
                props["Orientation"]["value"] = props["Orientation"]["options"][0]

        # Auto-fill read-only fields from the matched record
        records = db.find_records(manufacturer=mfr, model=model)
        if len(records) == 1:
            rec = records[0]
            props["K-Factor"]["value"] = str(rec.k_factor)
            props["Coverage Area"]["value"] = str(int(rec.coverage_area))
            props["Min Pressure"]["value"] = str(rec.min_pressure)
            props["Temperature"]["value"] = f"{rec.temp_rating}°F"

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
                    node.ceiling_level = new_level
                    node._properties["Ceiling Level"]["value"] = new_level
                    lvl = self._level_manager.get(new_level)
                    if lvl:
                        node.z_pos = lvl.elevation + node.ceiling_offset
                scene = t.scene() if hasattr(t, "scene") else None
                if scene:
                    self._level_manager.apply_to_scene(scene)
        # Refresh to update absolute elevation display
        if self._targets:
            self.show_properties(
                self._targets if len(self._targets) > 1 else self._targets[0]
            )
