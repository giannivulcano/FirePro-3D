"""Ribbon Font group for sheet text (Word's Font group as reference).

Governing specs: docs/specs/ribbon-bar.md (D3 add_widget primitive),
docs/specs/paper-space.md §9.6 (undo-routed formatting writes),
docs/specs/units-and-formatting.md (Word-style pt display, mm storage).
"""
from __future__ import annotations

from .constants import FONT_SIZE_LADDER_PT


def next_ladder_pt(pt: float) -> float:
    """Return the next Word-ladder step above *pt* (clamp at the top)."""
    for step in FONT_SIZE_LADDER_PT:
        if step > pt:
            return step
    return pt


def prev_ladder_pt(pt: float) -> float:
    """Return the next Word-ladder step below *pt* (clamp at the bottom)."""
    for step in reversed(FONT_SIZE_LADDER_PT):
        if step < pt:
            return step
    return pt


from PyQt6.QtCore import QObject  # noqa: E402
from PyQt6.QtGui import QColor, QFont  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QColorDialog, QComboBox, QFontComboBox, QHBoxLayout, QToolButton,
    QVBoxLayout, QWidget,
)

from .paper_space import _font_pt_from_mm, _mm_from_font_pt, _parse_height_pt  # noqa: E402

_ALIGN_LABELS = ("Left", "Center", "Right")
_CODE_TO_LABEL = {"L": "Left", "C": "Center", "R": "Right"}


class FontGroupController(QObject):
    """Word-style Font controls driving sheet-text targets via set_property.

    Every commit routes through TextAnnotationItem.set_property, so
    scene-attached targets get FormatTextCommand undo for free and the
    off-scene template writes direct (paper-space.md §9.6). Multi-target
    commits wrap in one undo-stack macro (property-panel.md §3.3 semantics).

    Args:
        get_targets: Callable returning a list of TextAnnotationItem targets.
        parent: Optional QObject parent.
    """

    def __init__(self, get_targets, parent=None):
        super().__init__(parent)
        self._get_targets = get_targets
        self._syncing = False
        self._build_widgets()

    def _build_widgets(self):
        self.container = QWidget()
        col = QVBoxLayout(self.container)
        col.setContentsMargins(2, 4, 2, 0)
        col.setSpacing(2)

        row1 = QHBoxLayout()
        row1.setSpacing(2)
        self.family_combo = QFontComboBox()
        self.family_combo.setMaximumWidth(160)
        self.family_combo.activated.connect(
            lambda _i: self._commit("Font", self.family_combo.currentFont().family()))
        row1.addWidget(self.family_combo)

        self.size_combo = QComboBox()
        self.size_combo.setEditable(True)
        self.size_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.size_combo.addItems([str(s) for s in FONT_SIZE_LADDER_PT])
        self.size_combo.setFixedWidth(56)
        self.size_combo.activated.connect(
            lambda _i: self.commit_size_text(self.size_combo.currentText()))
        self.size_combo.lineEdit().editingFinished.connect(
            lambda: self.commit_size_text(self.size_combo.currentText()))
        row1.addWidget(self.size_combo)

        self.grow_btn = self._tool_btn("A▲", "Grow font (next standard size)", self.grow)
        self.shrink_btn = self._tool_btn("A▼", "Shrink font (previous standard size)", self.shrink)
        row1.addWidget(self.grow_btn)
        row1.addWidget(self.shrink_btn)
        col.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(2)
        self.bold_btn = self._toggle_btn("B", "Bold", "Bold", bold=True)
        self.italic_btn = self._toggle_btn("I", "Italic", "Italic", italic=True)
        self.underline_btn = self._toggle_btn("U", "Underline", "Underline", underline=True)
        for b in (self.bold_btn, self.italic_btn, self.underline_btn):
            row2.addWidget(b)

        self.color_btn = QToolButton()
        self.color_btn.setToolTip("Font color")
        self.color_btn.setFixedSize(28, 26)
        self.color_btn.clicked.connect(self._pick_color)
        self._set_swatch("#000000")
        row2.addWidget(self.color_btn)

        self.align_btns = {}
        for label in _ALIGN_LABELS:
            b = QToolButton()
            b.setText({"Left": "⯇", "Center": "≡", "Right": "⯈"}[label])
            b.setToolTip(f"Align {label.lower()}")
            b.setCheckable(True)
            b.setFixedSize(28, 26)
            b.clicked.connect(lambda _c, l=label: self.commit_alignment(l))
            self.align_btns[label] = b
            row2.addWidget(b)
        col.addLayout(row2)

    def _tool_btn(self, text, tip, slot):
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setFixedSize(28, 26)
        b.clicked.connect(slot)
        return b

    def _toggle_btn(self, text, tip, key, *, bold=False, italic=False, underline=False):
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setCheckable(True)
        b.setFixedSize(28, 26)
        f = b.font()
        f.setBold(bold)
        f.setItalic(italic)
        f.setUnderline(underline)
        b.setFont(f)
        b.clicked.connect(lambda checked, k=key: self._commit(k, bool(checked)))
        return b

    def _set_swatch(self, hex_color: str):
        self._swatch = hex_color
        self.color_btn.setStyleSheet(
            f"QToolButton {{ border: 1px solid #888; background: {hex_color}; }}")

    # ── Commits (all routed through set_property) ─────────────────────────

    def _targets(self):
        return [t for t in self._get_targets() if t is not None]

    def _commit(self, key, value):
        """Commit a single property change to all targets, wrapped in one macro.

        Args:
            key: Property key accepted by TextAnnotationItem.set_property.
            value: New property value.
        """
        if self._syncing:
            return
        targets = self._targets()
        if not targets:
            return
        scene = targets[0].scene()
        stack = getattr(scene, "undo_stack", None) if scene is not None else None
        macro = stack is not None and len(targets) > 1
        if macro:
            stack.beginMacro(f"Format Text ({key})")
        try:
            for t in targets:
                t.set_property(key, value)
        finally:
            if macro:
                stack.endMacro()
        self.sync()

    def commit_size_text(self, text: str):
        """Parse Word-style pt (or explicit dimension) per target and commit.

        Args:
            text: User-entered size string, e.g. ``"12"``, ``"12 pt"``,
                ``'1/8"'``, ``"3mm"``.
        """
        if self._syncing:
            return
        targets = self._targets()
        if not targets:
            return
        changes = []
        for t in targets:
            mm = _parse_height_pt(t.data, text)
            if mm is None or mm <= 0:
                continue
            changes.append((t, mm))
        if not changes:
            self.sync()   # revert the visible text to the stored value
            return
        scene = changes[0][0].scene()
        stack = getattr(scene, "undo_stack", None) if scene is not None else None
        macro = stack is not None and len(changes) > 1
        if macro:
            stack.beginMacro("Format Text (Size)")
        try:
            for t, mm in changes:
                t.set_property("Height", mm)
        finally:
            if macro:
                stack.endMacro()
        self.sync()

    def _step_size(self, step_fn):
        targets = self._targets()
        if not targets:
            return
        scene = targets[0].scene()
        stack = getattr(scene, "undo_stack", None) if scene is not None else None
        macro = stack is not None and len(targets) > 1
        if macro:
            stack.beginMacro("Format Text (Size)")
        try:
            for t in targets:
                cur_pt = _font_pt_from_mm(t.data, t.data.height_mm)
                new_pt = step_fn(cur_pt)
                if abs(new_pt - cur_pt) < 1e-9:
                    continue
                t.set_property("Height", _mm_from_font_pt(t.data, new_pt))
        finally:
            if macro:
                stack.endMacro()
        self.sync()

    def grow(self):
        """Step all targets up one ladder size."""
        self._step_size(next_ladder_pt)

    def shrink(self):
        """Step all targets down one ladder size."""
        self._step_size(prev_ladder_pt)

    def commit_alignment(self, label: str):
        """Commit an alignment change (``"Left"``, ``"Center"``, or ``"Right"``).

        Args:
            label: One of the _ALIGN_LABELS strings.
        """
        self._commit("Alignment", label)

    def _pick_color(self):
        targets = self._targets()
        initial = QColor(targets[0].data.color) if targets else QColor("#000000")
        c = QColorDialog.getColor(initial, self.container, "Font Color")
        if c.isValid():
            self._commit("Color", c.name())

    # ── Sync (targets → widgets) ──────────────────────────────────────────

    def set_enabled(self, on: bool):
        """Enable or disable the entire controller container.

        Args:
            on: True to enable, False to disable.
        """
        self.container.setEnabled(on)

    def sync(self):
        """Reflect target state into widgets; mixed values render blank/unpressed (Word)."""
        targets = self._targets()
        self._syncing = True
        try:
            if not targets:
                return

            def uniform(getter):
                vals = {getter(t.data) for t in targets}
                return vals.pop() if len(vals) == 1 else None

            fam = uniform(lambda d: d.font_family or "Arial")
            if fam is None:
                self.family_combo.setCurrentIndex(-1)
            else:
                self.family_combo.setCurrentFont(QFont(fam))

            pt = uniform(lambda d: round(_font_pt_from_mm(d, d.height_mm), 1))
            self.size_combo.setCurrentText("" if pt is None else f"{pt:g}")

            self.bold_btn.setChecked(uniform(lambda d: d.bold) is True)
            self.italic_btn.setChecked(uniform(lambda d: d.italic) is True)
            self.underline_btn.setChecked(uniform(lambda d: d.underline) is True)

            color = uniform(lambda d: d.color or "#000000")
            self._set_swatch(color or (targets[0].data.color or "#000000"))

            align = uniform(lambda d: d.align)
            for label, b in self.align_btns.items():
                b.setChecked(align is not None and _CODE_TO_LABEL.get(align) == label)
        finally:
            self._syncing = False
