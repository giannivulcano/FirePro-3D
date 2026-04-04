"""
LayerManager
============
A dock-widget panel that lists every DXF layer found in the imported underlays
and lets the user toggle each layer's visibility with a checkbox.

Usage
-----
    lm = LayerManager(scene)          # pass the Model_Space
    dock = QDockWidget("Layers", window)
    dock.setWidget(lm)
    scene.underlaysChanged.connect(lm.refresh)
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QScrollArea, QCheckBox,
                              QLabel, QFrame, QPushButton, QHBoxLayout)
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsItemGroup


class LayerManager(QWidget):
    """Displays DXF layers and lets the user toggle their visibility."""

    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self.scene = scene
        self._checkboxes: dict[str, QCheckBox] = {}   # layer_name → checkbox
        self._build_ui()
        # Refresh whenever underlays change
        scene.underlaysChanged.connect(self.refresh)

    # ─────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(4)

        # Header row with "All On / All Off" buttons
        header = QHBoxLayout()
        header.addWidget(QLabel("<b>Layers</b>"))
        header.addStretch()
        all_on = QPushButton("All On")
        all_on.setFixedHeight(20)
        all_on.clicked.connect(lambda: self._set_all(True))
        all_off = QPushButton("All Off")
        all_off.setFixedHeight(20)
        all_off.clicked.connect(lambda: self._set_all(False))
        header.addWidget(all_on)
        header.addWidget(all_off)
        root_layout.addLayout(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root_layout.addWidget(sep)

        # Scroll area for layer checkboxes
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._inner = QWidget()
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(2, 2, 2, 2)
        self._inner_layout.setSpacing(2)
        self._inner_layout.addStretch()
        self._scroll.setWidget(self._inner)
        root_layout.addWidget(self._scroll)

    # ─────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────

    def refresh(self):
        """Rebuild the layer list from all DXF underlays in the scene."""
        # Collect all unique layer names across all DXF group underlays
        all_layers: set[str] = set()
        for _data, group in self.scene.underlays:
            if isinstance(group, QGraphicsItemGroup):
                layers = group.data(2)   # stored in _on_dxf_finished
                if layers:
                    all_layers.update(layers)

        # Save existing checked state so toggling preserves user choices
        prev_state: dict[str, bool] = {
            name: cb.isChecked() for name, cb in self._checkboxes.items()
        }

        # Clear existing checkboxes
        self._checkboxes.clear()
        while self._inner_layout.count() > 1:   # keep the trailing stretch
            item = self._inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add one checkbox per layer
        for layer in sorted(all_layers):
            cb = QCheckBox(layer)
            cb.setChecked(prev_state.get(layer, True))   # default visible
            cb.toggled.connect(lambda checked, lyr=layer: self._toggle_layer(lyr, checked))
            self._checkboxes[layer] = cb
            self._inner_layout.insertWidget(self._inner_layout.count() - 1, cb)

        # Apply current visibility state to scene
        self._apply_all()

    # ─────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────

    def _toggle_layer(self, layer_name: str, visible: bool):
        """Show/hide all DXF items that belong to the given layer."""
        for _data, group in self.scene.underlays:
            if not isinstance(group, QGraphicsItemGroup):
                continue
            for item in group.childItems():
                if item.data(1) == layer_name:
                    item.setVisible(visible)

    def _set_all(self, visible: bool):
        for cb in self._checkboxes.values():
            cb.setChecked(visible)   # triggers _toggle_layer via toggled signal

    def _apply_all(self):
        """Enforce current checkbox states on the scene (e.g. after a refresh)."""
        for layer_name, cb in self._checkboxes.items():
            self._toggle_layer(layer_name, cb.isChecked())
