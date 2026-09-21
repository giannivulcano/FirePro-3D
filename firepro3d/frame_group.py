"""Ribbon "Frame" group for the text box border (text-annotation-system.md).

Sibling to FontGroupController: every commit routes through TextItem.set_property
so paper targets get FormatTextCommand undo and model targets snapshot via the
scene, with multi-select wrapped in one macro. Border toggle + a 3-way corner
radio (Square/Fillet/Chamfer) + stacked Line-type/Line-weight combos.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QToolButton, QVBoxLayout, QWidget

from . import theme as th
from .paper_space import _text_panel_change

_CORNERS = (("square", "corner_square.svg", "Square corner"),
            ("round", "corner_fillet.svg", "Fillet (rounded) corner"),
            ("chamfer", "corner_chamfer.svg", "Chamfer (cut) corner"))
_LINE_TYPES = ("solid", "dashed", "dotted", "dashdot")
_WEIGHTS = ("Very Light", "Light", "Medium", "Heavy", "Very Heavy")


class FrameGroupController(QObject):
    """Frame controls driving text-box border props via TextItem.set_property.

    Args:
        get_targets: Callable returning a list of TextItem targets.
        icon_loader: Optional callable(name) -> QIcon for the button icons.
        parent: Optional QObject parent.
    """

    def __init__(self, get_targets, icon_loader=None, parent=None):
        super().__init__(parent)
        self._get_targets = get_targets
        self._icon = icon_loader
        self._syncing = False
        self._theme = th.detect()
        self._build_widgets()

    def _build_widgets(self):
        self.container = QWidget()
        col = QVBoxLayout(self.container)
        col.setContentsMargins(2, 4, 2, 0)
        col.setSpacing(2)

        row1 = QHBoxLayout()
        row1.setSpacing(2)
        self.border_btn = QToolButton()
        self.border_btn.setCheckable(True)
        self.border_btn.setFixedSize(28, 26)
        self.border_btn.setToolTip("Border visibility")
        if self._icon:
            self.border_btn.setIcon(self._icon("text_border.svg"))
        else:
            self.border_btn.setText("▢")
        self.border_btn.clicked.connect(lambda on: self._commit("Border", bool(on)))
        row1.addWidget(self.border_btn)

        self.corner_btns = {}
        for key, icon_name, tip in _CORNERS:
            b = QToolButton()
            b.setCheckable(True)
            b.setFixedSize(28, 26)
            b.setToolTip(tip)
            if self._icon:
                b.setIcon(self._icon(icon_name))
            else:
                b.setText(key[0].upper())
            b.clicked.connect(lambda _c, k=key: self.commit_corner(k))
            self.corner_btns[key] = b
            row1.addWidget(b)
        col.addLayout(row1)

        self.line_type_combo = QComboBox()
        self.line_type_combo.addItems(_LINE_TYPES)
        self.line_type_combo.activated.connect(
            lambda _i: self.commit_line_type(self.line_type_combo.currentText()))
        col.addWidget(self.line_type_combo)

        self.weight_combo = QComboBox()
        self.weight_combo.addItems(_WEIGHTS)
        self.weight_combo.activated.connect(
            lambda _i: self.commit_weight(self.weight_combo.currentText()))
        col.addWidget(self.weight_combo)

    def _targets(self):
        return [t for t in self._get_targets() if t is not None]

    def _commit(self, key, value):
        if self._syncing:
            return
        targets = [t for t in self._targets()
                   if _text_panel_change(t.data, key, value) is not None]
        if not targets:
            self.sync()
            return
        scene = targets[0].scene()
        stack = getattr(scene, "undo_stack", None) if scene is not None else None
        macro = stack is not None and len(targets) > 1
        if macro:
            stack.beginMacro(f"Frame ({key})")
        try:
            for t in targets:
                t.set_property(key, value)
        finally:
            if macro:
                stack.endMacro()
        self.sync()

    def commit_corner(self, key):
        """Set the corner radio exclusively to *key* and commit.

        Args:
            key: One of ``'square'``, ``'round'``, ``'chamfer'``.
        """
        for k, b in self.corner_btns.items():
            b.setChecked(k == key)
        self._commit("Corner", key)

    def commit_line_type(self, value):
        """Commit a line-type change.

        Args:
            value: One of ``'solid'``, ``'dashed'``, ``'dotted'``, ``'dashdot'``.
        """
        self._commit("Line Type", value)

    def commit_weight(self, value):
        """Commit a border-weight change.

        Args:
            value: Named weight token, e.g. ``'Medium'``.
        """
        self._commit("Border Weight", value)

    def set_enabled(self, on: bool):
        """Enable or disable the entire controller container.

        Args:
            on: True to enable, False to disable.
        """
        self.container.setEnabled(on)

    def sync(self):
        """Reflect target state into widgets; mixed values render blank/unpressed."""
        targets = self._targets()
        self._syncing = True
        try:
            if not targets:
                return

            def uniform(getter):
                vals = {getter(t.data) for t in targets}
                return vals.pop() if len(vals) == 1 else None

            self.border_btn.setChecked(uniform(lambda d: d.border) is True)
            corner = uniform(lambda d: d.border_corner)
            for k, b in self.corner_btns.items():
                b.setChecked(corner == k)
            lt = uniform(lambda d: d.border_line_type)
            if lt in _LINE_TYPES:
                self.line_type_combo.setCurrentText(lt)
            wt = uniform(lambda d: d.border_weight)
            if wt in _WEIGHTS:
                self.weight_combo.setCurrentText(wt)
            on = self.border_btn.isChecked()
            for w in (self.line_type_combo, self.weight_combo, *self.corner_btns.values()):
                w.setEnabled(on)
        finally:
            self._syncing = False
