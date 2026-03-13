"""
display_manager.py
==================
Revit-style Display Manager dialog for fire-suppression component appearance.

Provides per-category and per-instance control over visibility, colour, scale
factor, and opacity.  Changes are applied live to the canvas; cancelling the
dialog reverts all changes to their prior state.

Replaces the older FSVisibilityDialog.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QDialogButtonBox, QPushButton, QDoubleSpinBox, QSpinBox, QCheckBox,
    QHeaderView, QColorDialog, QGraphicsColorizeEffect, QWidget, QLabel,
    QAbstractItemView,
)
from PyQt6.QtGui import QColor, QFont, QBrush, QPen
from PyQt6.QtCore import Qt, QSettings

import theme as th

# ---------------------------------------------------------------------------
# Category definitions — order matches the tree from top to bottom
# ---------------------------------------------------------------------------

_CATEGORIES: list[dict] = [
    {"key": "Pipe",         "color": "#4488ff", "scale": 1.0, "opacity": 100, "visible": True},
    {"key": "Sprinkler",    "color": "#ff4444", "scale": 1.0, "opacity": 100, "visible": True},
    {"key": "Fitting",      "color": "#44cc44", "scale": 1.0, "opacity": 100, "visible": True},
    {"key": "Water Supply", "color": "#00cccc", "scale": 1.0, "opacity": 100, "visible": True},
    {"key": "Node",         "color": "#888888", "scale": 1.0, "opacity": 100, "visible": True},
]

# Tree-column indices
_COL_NAME    = 0
_COL_VIS     = 1
_COL_COLOR   = 2
_COL_SCALE   = 3
_COL_OPACITY = 4
_COL_RESET   = 5


# ──────────────────────────────────────────────────────────────────────────────
# Public helper — apply display settings to a single item
# ──────────────────────────────────────────────────────────────────────────────

def apply_display_to_item(item, color: str | None, scale: float,
                          opacity: float, visible: bool):
    """Apply display settings to *item* (Pipe, Sprinkler, Fitting, Node, or
    WaterSupply).  Called both by the live-preview loop and at project load."""
    from pipe import Pipe
    from sprinkler import Sprinkler
    from fitting import Fitting
    from water_supply import WaterSupply
    from node import Node

    if isinstance(item, Pipe):
        _apply_pipe(item, color, scale, opacity, visible)
    elif isinstance(item, Sprinkler):
        _apply_svg_item(item, color, scale, opacity, visible)
        item._display_scale = scale
        item._centre_on_node()
    elif isinstance(item, Fitting):
        _apply_fitting(item, color, scale, opacity, visible)
    elif isinstance(item, WaterSupply):
        _apply_svg_item(item, color, scale, opacity, visible)
        item._display_scale = scale
        item._centre_on_origin()
    elif isinstance(item, Node):
        _apply_node(item, color, scale, opacity, visible)


def _apply_pipe(pipe, color, scale, opacity, visible):
    pipe._display_color = color  # override pen colour (None falls back to property)
    pipe._display_scale = scale
    pipe.set_pipe_display()
    pipe.setOpacity(opacity / 100.0 if opacity > 1 else opacity)
    pipe.setVisible(visible)
    # Also hide/show the label child if present
    for child in pipe.childItems():
        child.setVisible(visible)


def _apply_svg_item(item, color, scale, opacity, visible):
    """Apply colour effect + opacity to a QGraphicsSvgItem (Sprinkler or WaterSupply)."""
    if color:
        effect = item.graphicsEffect()
        if not isinstance(effect, QGraphicsColorizeEffect):
            effect = QGraphicsColorizeEffect(item)
            item.setGraphicsEffect(effect)
        effect.setColor(QColor(color))
        effect.setStrength(1.0)
    else:
        item.setGraphicsEffect(None)
    item.setOpacity(opacity / 100.0 if opacity > 1 else opacity)
    item.setVisible(visible)


def _apply_fitting(fitting, color, scale, opacity, visible):
    """Apply to a Fitting (non-QGraphicsItem wrapper)."""
    fitting._display_color = color
    fitting._display_scale = scale
    fitting._display_opacity = opacity
    fitting._display_visible = visible
    sym = fitting.symbol
    if sym is None:
        return
    if color:
        effect = sym.graphicsEffect()
        if not isinstance(effect, QGraphicsColorizeEffect):
            effect = QGraphicsColorizeEffect(sym)
            sym.setGraphicsEffect(effect)
        effect.setColor(QColor(color))
        effect.setStrength(1.0)
    else:
        sym.setGraphicsEffect(None)
    sym.setOpacity(opacity / 100.0 if opacity > 1 else opacity)
    # Visibility: fittings are hidden when sprinkler is present (handled by
    # Fitting.update()), so only override when we explicitly hide.
    if not visible:
        sym.setVisible(False)
    # Re-apply scale by calling align_fitting which reads _display_scale
    fitting.align_fitting()


def _apply_node(node, color, scale, opacity, visible):
    node.setOpacity(opacity / 100.0 if opacity > 1 else opacity)
    node.setVisible(visible)


# ──────────────────────────────────────────────────────────────────────────────
# DisplayManager dialog
# ──────────────────────────────────────────────────────────────────────────────

class DisplayManager(QDialog):
    """Modal dialog providing Revit-style display settings for fire-
    suppression model items."""

    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Display Manager")
        self.setMinimumSize(700, 420)
        self._scene = scene
        self._settings = QSettings()
        self._suppress = False  # guard against recursive signal loops

        # {id(item): {visible, opacity, color, scale, effect}} — for revert
        self._snapshot: dict[int, dict] = {}
        # {category_key: {items: [item, ...], tree_item: QTreeWidgetItem,
        #                  widgets: {vis, color_btn, scale, opacity}}}
        self._cat_data: dict[str, dict] = {}
        # {id(item): {tree_item, widgets, item_ref}}
        self._inst_data: dict[int, dict] = {}

        self._take_snapshot()
        self._build_ui()

    # ------------------------------------------------------------------
    # Snapshot / revert
    # ------------------------------------------------------------------

    def _take_snapshot(self):
        """Capture the current visual state of every FS item for cancel-revert."""
        for item in self._iter_all_items():
            entry: dict = {
                "visible": item.isVisible(),
                "opacity": item.opacity(),
                "effect_color": None,
                "display_color": getattr(item, "_display_color", None),
                "display_scale": getattr(item, "_display_scale", 1.0),
                "overrides": dict(getattr(item, "_display_overrides", {})),
            }
            eff = item.graphicsEffect()
            if isinstance(eff, QGraphicsColorizeEffect):
                entry["effect_color"] = eff.color().name()
            self._snapshot[id(item)] = entry

        # Also snapshot Fitting wrappers (not QGraphicsItems themselves)
        for node in self._scene.sprinkler_system.nodes:
            f = node.fitting
            if f and f.symbol:
                fid = id(f)
                eff = f.symbol.graphicsEffect()
                self._snapshot[fid] = {
                    "visible": f.symbol.isVisible(),
                    "opacity": f.symbol.opacity(),
                    "effect_color": eff.color().name() if isinstance(eff, QGraphicsColorizeEffect) else None,
                    "overrides": dict(getattr(f, "_display_overrides", {})),
                    "display_color": getattr(f, "_display_color", None),
                    "display_scale": getattr(f, "_display_scale", 1.0),
                    "display_opacity": getattr(f, "_display_opacity", 100),
                    "display_visible": getattr(f, "_display_visible", True),
                }

    def _restore_snapshot(self):
        """Revert every item to its snapshotted state."""
        from fitting import Fitting
        from pipe import Pipe
        from sprinkler import Sprinkler
        from water_supply import WaterSupply

        for item in self._iter_all_items():
            snap = self._snapshot.get(id(item))
            if snap is None:
                continue
            item.setVisible(snap["visible"])
            item.setOpacity(snap["opacity"])
            if snap["effect_color"]:
                eff = item.graphicsEffect()
                if not isinstance(eff, QGraphicsColorizeEffect):
                    eff = QGraphicsColorizeEffect(item)
                    item.setGraphicsEffect(eff)
                eff.setColor(QColor(snap["effect_color"]))
            else:
                item.setGraphicsEffect(None)
            item._display_overrides = snap.get("overrides", {})
            # Restore per-type display attributes
            if isinstance(item, Pipe):
                item._display_color = snap.get("display_color")
                item._display_scale = snap.get("display_scale", 1.0)
                item.set_pipe_display()
            elif isinstance(item, (Sprinkler, WaterSupply)):
                item._display_scale = snap.get("display_scale", 1.0)
                if isinstance(item, Sprinkler):
                    item._centre_on_node()
                else:
                    item._centre_on_origin()

        # Restore fittings
        for node in self._scene.sprinkler_system.nodes:
            f = node.fitting
            if f is None:
                continue
            snap = self._snapshot.get(id(f))
            if snap is None:
                continue
            f._display_color = snap.get("display_color")
            f._display_scale = snap.get("display_scale", 1.0)
            f._display_opacity = snap.get("display_opacity", 100)
            f._display_visible = snap.get("display_visible", True)
            f._display_overrides = snap.get("overrides", {})
            if f.symbol:
                f.symbol.setVisible(snap["visible"])
                f.symbol.setOpacity(snap["opacity"])
                if snap["effect_color"]:
                    eff = f.symbol.graphicsEffect()
                    if not isinstance(eff, QGraphicsColorizeEffect):
                        eff = QGraphicsColorizeEffect(f.symbol)
                        f.symbol.setGraphicsEffect(eff)
                    eff.setColor(QColor(snap["effect_color"]))
                else:
                    f.symbol.setGraphicsEffect(None)
                f.align_fitting()

        # Force scene repaint
        self._scene.update()

    # ------------------------------------------------------------------
    # Item iteration helpers
    # ------------------------------------------------------------------

    def _iter_all_items(self):
        """Yield every fire-suppression QGraphicsItem in the scene."""
        ss = self._scene.sprinkler_system
        yield from ss.pipes
        for node in ss.nodes:
            yield node
            if node.has_sprinkler():
                yield node.sprinkler
        ws = getattr(self._scene, "water_supply_node", None)
        if ws is not None:
            yield ws

    def _items_for_category(self, key: str) -> list:
        """Return the list of items (or Fitting wrappers) for a category."""
        ss = self._scene.sprinkler_system
        if key == "Pipe":
            return list(ss.pipes)
        elif key == "Sprinkler":
            return [n.sprinkler for n in ss.nodes if n.has_sprinkler()]
        elif key == "Fitting":
            return [n.fitting for n in ss.nodes if n.has_fitting() and n.fitting.symbol]
        elif key == "Water Supply":
            ws = getattr(self._scene, "water_supply_node", None)
            return [ws] if ws else []
        elif key == "Node":
            return list(ss.nodes)
        return []

    def _label_for_item(self, item, index: int, category: str) -> str:
        """Human-readable label for an instance row."""
        if category == "Pipe":
            dia = item._properties.get("Diameter", {}).get("value", "?")
            return f"Pipe {index}  ({dia})"
        elif category == "Sprinkler":
            mfr = item._properties.get("Manufacturer", {}).get("value", "")
            ori = item._properties.get("Orientation", {}).get("value", "")
            return f"Sprinkler {index}  ({mfr} {ori})"
        elif category == "Fitting":
            return f"Fitting {index}  ({item.type})"
        elif category == "Water Supply":
            return "Water Supply"
        elif category == "Node":
            n_pipes = len(item.pipes)
            return f"Node {index}  ({n_pipes} conn.)"
        return f"{category} {index}"

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        _t = th.detect()
        outer = QVBoxLayout(self)

        # ── Tree widget ──────────────────────────────────────────────
        self._tree = QTreeWidget()
        self._tree.setColumnCount(6)
        self._tree.setHeaderLabels(["Name", "Vis", "Colour", "Scale", "Opacity", ""])
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(20)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        hdr = self._tree.header()
        hdr.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_VIS, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_COL_COLOR, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_COL_SCALE, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_COL_OPACITY, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_COL_RESET, QHeaderView.ResizeMode.Fixed)
        self._tree.setColumnWidth(_COL_VIS, 40)
        self._tree.setColumnWidth(_COL_COLOR, 60)
        self._tree.setColumnWidth(_COL_SCALE, 90)
        self._tree.setColumnWidth(_COL_OPACITY, 90)
        self._tree.setColumnWidth(_COL_RESET, 40)

        self._populate_tree()
        outer.addWidget(self._tree)

        # ── Button box ───────────────────────────────────────────────
        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.RestoreDefaults)
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        reset_btn = bbox.button(QDialogButtonBox.StandardButton.RestoreDefaults)
        reset_btn.setText("Reset All")
        reset_btn.clicked.connect(self._reset_all)
        outer.addWidget(bbox)

    # ------------------------------------------------------------------
    # Tree population
    # ------------------------------------------------------------------

    def _populate_tree(self):
        _t = th.detect()
        bold = QFont()
        bold.setBold(True)

        for cat_def in _CATEGORIES:
            key = cat_def["key"]
            items = self._items_for_category(key)

            # Read saved category settings from QSettings (or defaults)
            saved_color = self._settings.value(
                f"display/{key}/color", cat_def["color"])
            saved_scale = float(self._settings.value(
                f"display/{key}/scale", cat_def["scale"]))
            saved_opacity = int(float(self._settings.value(
                f"display/{key}/opacity", cat_def["opacity"])))
            saved_visible = self._settings.value(
                f"display/{key}/visible", cat_def["visible"])
            if isinstance(saved_visible, str):
                saved_visible = saved_visible.lower() not in ("false", "0")

            # ── Category row ─────────────────────────────────────────
            cat_item = QTreeWidgetItem(self._tree)
            cat_item.setText(_COL_NAME, f"{key}  ({len(items)})")
            cat_item.setFont(_COL_NAME, bold)
            cat_item.setFlags(Qt.ItemFlag.ItemIsEnabled)

            cat_widgets = self._make_row_widgets(
                cat_item, saved_visible, saved_color, saved_scale,
                saved_opacity, is_category=True, category_key=key)

            self._cat_data[key] = {
                "items": items,
                "tree_item": cat_item,
                "widgets": cat_widgets,
            }

            # ── Instance sub-rows ────────────────────────────────────
            for i, obj in enumerate(items, 1):
                overrides = getattr(obj, "_display_overrides", {})
                inst_color = overrides.get("color", saved_color)
                inst_scale = overrides.get("scale", saved_scale)
                inst_opacity = overrides.get("opacity", saved_opacity)
                inst_visible = overrides.get("visible", saved_visible)

                child = QTreeWidgetItem(cat_item)
                child.setText(_COL_NAME, self._label_for_item(obj, i, key))
                child.setFlags(Qt.ItemFlag.ItemIsEnabled)

                inst_widgets = self._make_row_widgets(
                    child, inst_visible, inst_color, inst_scale,
                    inst_opacity, is_category=False, category_key=key,
                    item_ref=obj)

                self._inst_data[id(obj)] = {
                    "tree_item": child,
                    "widgets": inst_widgets,
                    "item_ref": obj,
                    "category": key,
                }

    def _make_row_widgets(self, tree_item: QTreeWidgetItem,
                          visible: bool, color: str, scale: float,
                          opacity: int, *, is_category: bool,
                          category_key: str,
                          item_ref=None) -> dict:
        """Create and embed widgets for one tree row. Returns widget dict."""
        _t = th.detect()

        # ── Visibility checkbox ──────────────────────────────────────
        vis_container = QWidget()
        vis_layout = QHBoxLayout(vis_container)
        vis_layout.setContentsMargins(0, 0, 0, 0)
        vis_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vis_cb = QCheckBox()
        vis_cb.setChecked(visible)
        vis_layout.addWidget(vis_cb)
        self._tree.setItemWidget(tree_item, _COL_VIS, vis_container)

        # ── Colour swatch ────────────────────────────────────────────
        color_btn = QPushButton()
        color_btn.setFixedSize(40, 20)
        color_btn.setProperty("_color", color)
        color_btn.setStyleSheet(
            f"background: {color}; border: 1px solid {_t.border_subtle}; "
            f"border-radius: 2px;")
        self._tree.setItemWidget(tree_item, _COL_COLOR, color_btn)

        # ── Scale spinbox ────────────────────────────────────────────
        scale_spin = QDoubleSpinBox()
        scale_spin.setRange(0.1, 10.0)
        scale_spin.setSingleStep(0.1)
        scale_spin.setDecimals(1)
        scale_spin.setValue(scale)
        scale_spin.setSuffix("x")
        scale_spin.setFixedHeight(22)
        self._tree.setItemWidget(tree_item, _COL_SCALE, scale_spin)

        # ── Opacity spinbox ──────────────────────────────────────────
        opacity_spin = QSpinBox()
        opacity_spin.setRange(0, 100)
        opacity_spin.setSingleStep(5)
        opacity_spin.setValue(opacity)
        opacity_spin.setSuffix("%")
        opacity_spin.setFixedHeight(22)
        self._tree.setItemWidget(tree_item, _COL_OPACITY, opacity_spin)

        # ── Reset button (instance rows only) ────────────────────────
        reset_btn = None
        if not is_category:
            reset_btn = QPushButton("\u21ba")  # ↺
            reset_btn.setFixedSize(28, 22)
            reset_btn.setToolTip("Reset to category defaults")
            self._tree.setItemWidget(tree_item, _COL_RESET, reset_btn)

        # ── Connect signals ──────────────────────────────────────────
        if is_category:
            vis_cb.toggled.connect(
                lambda v, k=category_key: self._on_category_changed(k, "visible", v))
            color_btn.clicked.connect(
                lambda _, k=category_key: self._pick_category_color(k))
            scale_spin.valueChanged.connect(
                lambda v, k=category_key: self._on_category_changed(k, "scale", v))
            opacity_spin.valueChanged.connect(
                lambda v, k=category_key: self._on_category_changed(k, "opacity", v))
        else:
            vis_cb.toggled.connect(
                lambda v, ref=item_ref: self._on_instance_changed(ref, "visible", v))
            color_btn.clicked.connect(
                lambda _, ref=item_ref: self._pick_instance_color(ref))
            scale_spin.valueChanged.connect(
                lambda v, ref=item_ref: self._on_instance_changed(ref, "scale", v))
            opacity_spin.valueChanged.connect(
                lambda v, ref=item_ref: self._on_instance_changed(ref, "opacity", v))
            if reset_btn:
                reset_btn.clicked.connect(
                    lambda _, ref=item_ref: self._reset_instance(ref))

        return {
            "vis": vis_cb,
            "color_btn": color_btn,
            "scale": scale_spin,
            "opacity": opacity_spin,
            "reset": reset_btn,
        }

    # ------------------------------------------------------------------
    # Colour pickers
    # ------------------------------------------------------------------

    def _pick_category_color(self, category_key: str):
        widgets = self._cat_data[category_key]["widgets"]
        cur = QColor(widgets["color_btn"].property("_color"))
        color = QColorDialog.getColor(cur, self, f"{category_key} colour")
        if color.isValid():
            self._update_color_btn(widgets["color_btn"], color.name())
            self._on_category_changed(category_key, "color", color.name())

    def _pick_instance_color(self, item_ref):
        data = self._inst_data.get(id(item_ref))
        if data is None:
            return
        widgets = data["widgets"]
        cur = QColor(widgets["color_btn"].property("_color"))
        color = QColorDialog.getColor(cur, self, "Instance colour")
        if color.isValid():
            self._update_color_btn(widgets["color_btn"], color.name())
            self._on_instance_changed(item_ref, "color", color.name())

    def _update_color_btn(self, btn: QPushButton, hex_color: str):
        _t = th.detect()
        btn.setProperty("_color", hex_color)
        btn.setStyleSheet(
            f"background: {hex_color}; border: 1px solid {_t.border_subtle}; "
            f"border-radius: 2px;")

    # ------------------------------------------------------------------
    # Change handlers
    # ------------------------------------------------------------------

    def _on_category_changed(self, category_key: str, prop: str, value):
        """Category-level setting changed — propagate to all instances
        that don't have a per-instance override for this property."""
        if self._suppress:
            return
        self._suppress = True
        try:
            cat = self._cat_data[category_key]
            for obj in cat["items"]:
                overrides = getattr(obj, "_display_overrides", {})
                if prop not in overrides:
                    # Update the instance row widget to match
                    inst = self._inst_data.get(id(obj))
                    if inst:
                        self._set_widget_value(inst["widgets"], prop, value)
            self._apply_preview()
        finally:
            self._suppress = False

    def _on_instance_changed(self, item_ref, prop: str, value):
        """Per-instance override changed."""
        if self._suppress:
            return
        if not hasattr(item_ref, "_display_overrides"):
            item_ref._display_overrides = {}
        item_ref._display_overrides[prop] = value
        self._apply_preview()

    def _reset_instance(self, item_ref):
        """Clear all per-instance overrides and revert widgets to category defaults."""
        if not hasattr(item_ref, "_display_overrides"):
            return
        item_ref._display_overrides.clear()

        inst = self._inst_data.get(id(item_ref))
        if inst is None:
            return
        cat_key = inst["category"]
        cat_widgets = self._cat_data[cat_key]["widgets"]

        self._suppress = True
        try:
            w = inst["widgets"]
            w["vis"].setChecked(cat_widgets["vis"].isChecked())
            self._update_color_btn(w["color_btn"],
                                   cat_widgets["color_btn"].property("_color"))
            w["scale"].setValue(cat_widgets["scale"].value())
            w["opacity"].setValue(cat_widgets["opacity"].value())
        finally:
            self._suppress = False
        self._apply_preview()

    def _reset_all(self):
        """Reset all categories and instances to factory defaults."""
        self._suppress = True
        try:
            for cat_def in _CATEGORIES:
                key = cat_def["key"]
                cw = self._cat_data[key]["widgets"]
                cw["vis"].setChecked(cat_def["visible"])
                self._update_color_btn(cw["color_btn"], cat_def["color"])
                cw["scale"].setValue(cat_def["scale"])
                cw["opacity"].setValue(cat_def["opacity"])

                for obj in self._cat_data[key]["items"]:
                    if hasattr(obj, "_display_overrides"):
                        obj._display_overrides.clear()
                    inst = self._inst_data.get(id(obj))
                    if inst:
                        iw = inst["widgets"]
                        iw["vis"].setChecked(cat_def["visible"])
                        self._update_color_btn(iw["color_btn"], cat_def["color"])
                        iw["scale"].setValue(cat_def["scale"])
                        iw["opacity"].setValue(cat_def["opacity"])
        finally:
            self._suppress = False
        self._apply_preview()

    # ------------------------------------------------------------------
    # Widget value helpers
    # ------------------------------------------------------------------

    def _set_widget_value(self, widgets: dict, prop: str, value):
        """Programmatically set a widget's value (suppress re-entry)."""
        if prop == "visible":
            widgets["vis"].setChecked(value)
        elif prop == "color":
            self._update_color_btn(widgets["color_btn"], value)
        elif prop == "scale":
            widgets["scale"].setValue(value)
        elif prop == "opacity":
            widgets["opacity"].setValue(value)

    def _read_category_settings(self, key: str) -> dict:
        """Read current widget values for a category row."""
        w = self._cat_data[key]["widgets"]
        return {
            "visible": w["vis"].isChecked(),
            "color": w["color_btn"].property("_color"),
            "scale": w["scale"].value(),
            "opacity": w["opacity"].value(),
        }

    # ------------------------------------------------------------------
    # Live preview
    # ------------------------------------------------------------------

    def _apply_preview(self):
        """Apply current dialog state to all scene items (live preview)."""
        from fitting import Fitting

        for cat_def in _CATEGORIES:
            key = cat_def["key"]
            cat_settings = self._read_category_settings(key)

            for obj in self._cat_data[key]["items"]:
                overrides = getattr(obj, "_display_overrides", {})
                eff_color = overrides.get("color", cat_settings["color"])
                eff_scale = overrides.get("scale", cat_settings["scale"])
                eff_opacity = overrides.get("opacity", cat_settings["opacity"])
                eff_visible = overrides.get("visible", cat_settings["visible"])

                apply_display_to_item(obj, eff_color, eff_scale,
                                      eff_opacity, eff_visible)

        self._scene.update()

    # ------------------------------------------------------------------
    # Accept / Reject
    # ------------------------------------------------------------------

    def accept(self):
        """Persist category settings to QSettings and keep scene state."""
        for cat_def in _CATEGORIES:
            key = cat_def["key"]
            s = self._read_category_settings(key)
            self._settings.setValue(f"display/{key}/color", s["color"])
            self._settings.setValue(f"display/{key}/scale", s["scale"])
            self._settings.setValue(f"display/{key}/opacity", s["opacity"])
            self._settings.setValue(f"display/{key}/visible", s["visible"])
        super().accept()

    def reject(self):
        """Cancel — revert all changes."""
        self._restore_snapshot()
        super().reject()


# ──────────────────────────────────────────────────────────────────────────────
# Startup helper — called after project load to apply saved display settings
# ──────────────────────────────────────────────────────────────────────────────

def apply_saved_display_settings(scene):
    """Read QSettings + per-item overrides and apply to all FS items."""
    from pipe import Pipe
    from sprinkler import Sprinkler
    from fitting import Fitting
    from water_supply import WaterSupply
    from node import Node

    settings = QSettings()
    cat_defaults = {c["key"]: c for c in _CATEGORIES}

    for cat_def in _CATEGORIES:
        key = cat_def["key"]
        color = settings.value(f"display/{key}/color", cat_def["color"])
        scale = float(settings.value(f"display/{key}/scale", cat_def["scale"]))
        opacity = int(float(settings.value(
            f"display/{key}/opacity", cat_def["opacity"])))
        visible = settings.value(f"display/{key}/visible", cat_def["visible"])
        if isinstance(visible, str):
            visible = visible.lower() not in ("false", "0")

        items = _items_for_category_static(scene, key)
        for obj in items:
            overrides = getattr(obj, "_display_overrides", {})
            eff_color = overrides.get("color", color)
            eff_scale = overrides.get("scale", scale)
            eff_opacity = overrides.get("opacity", opacity)
            eff_visible = overrides.get("visible", visible)
            apply_display_to_item(obj, eff_color, eff_scale,
                                  eff_opacity, eff_visible)


def _items_for_category_static(scene, key: str) -> list:
    """Same as DisplayManager._items_for_category but as a free function."""
    ss = scene.sprinkler_system
    if key == "Pipe":
        return list(ss.pipes)
    elif key == "Sprinkler":
        return [n.sprinkler for n in ss.nodes if n.has_sprinkler()]
    elif key == "Fitting":
        return [n.fitting for n in ss.nodes if n.has_fitting() and n.fitting.symbol]
    elif key == "Water Supply":
        ws = getattr(scene, "water_supply_node", None)
        return [ws] if ws else []
    elif key == "Node":
        return list(ss.nodes)
    return []
