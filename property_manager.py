from PyQt6.QtWidgets import QWidget, QFormLayout, QLabel, QLineEdit, QComboBox, QSpinBox
from PyQt6.QtGui import QDoubleValidator
from node import Node
from pipe import Pipe
from sprinkler import Sprinkler

class PropertyManager(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QFormLayout(self)
        self.labels = {}
        self._level_manager = None

    def set_level_manager(self, lm):
        self._level_manager = lm

    def show_properties(self, item):
        # Clear old props
        for i in reversed(range(self.layout.count())):
            widget = self.layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        if item is None:
            return

        # If Node with sprinkler, resolve sprinkler
        if isinstance(item, Node) and item.has_sprinkler():
            item = item.sprinkler

        # Only handle objects with get_properties
        if not hasattr(item, "get_properties"):
            return

        for key, meta in item.get_properties().items():
            widget = None

            if meta["type"] == "enum":
                widget = QComboBox()
                widget.addItems(meta["options"])
                widget.setCurrentText(meta["value"])
                widget.currentTextChanged.connect(
                    lambda val, key=key, target=item: target.set_property(key, val)
                )

            else:  # fallback to text — with optional numeric validation
                widget = QLineEdit(str(meta["value"]))

                # Auto-detect numeric fields and add validator
                try:
                    float(meta["value"])
                    validator = QDoubleValidator()
                    validator.setNotation(QDoubleValidator.Notation.StandardNotation)
                    widget.setValidator(validator)
                except (ValueError, TypeError):
                    pass  # truly a text field — no validator

                widget.editingFinished.connect(
                    lambda key=key, field=widget, target=item: target.set_property(key, field.text())
                )

            self.layout.addRow(QLabel(key), widget)

        # Level assignment (dynamic — options come from LevelManager)
        if hasattr(item, "level") and self._level_manager is not None:
            combo = QComboBox()
            for lv in self._level_manager.levels:
                combo.addItem(lv.name)
            combo.setCurrentText(item.level)
            combo.currentTextChanged.connect(
                lambda val, target=item: self._change_level(target, val)
            )
            self.layout.addRow(QLabel("Level"), combo)

    def _change_level(self, item, new_level):
        item.level = new_level
        if self._level_manager is not None:
            scene = item.scene()
            if scene:
                self._level_manager.apply_to_scene(scene)