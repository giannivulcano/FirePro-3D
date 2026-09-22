"""colour_picker.py — house colour picker (todo #70).

One modal ``ColourPickerDialog(HouseDialog)`` + one entry point
``pick_colour(initial, parent, context, *, allow_none=False)`` replacing the
native Qt colour dialog app-wide. Result contract:
    None        → cancelled (caller changes nothing)
    ""          → No Fill (only possible when allow_none=True)
    "#RRGGBB"   → a colour
Callers must import the MODULE and call ``colour_picker.pick_colour`` so tests
can monkeypatch one attribute. See docs/specs/ui-design-system.md.
"""
from __future__ import annotations

from PyQt6.QtCore import (Qt, QRectF, QPointF, QRegularExpression, QSettings,
                          pyqtSignal)
from PyQt6.QtGui import (QColor, QPainter, QPen, QLinearGradient, QBrush,
                         QRegularExpressionValidator)
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                             QLineEdit, QGridLayout, QDialog, QDialogButtonBox,
                             QPushButton)

from .house_dialog import HouseDialog
from .theme import M, detect
from .ui_kit import Stepper, paint_no_fill

NO_FILL = ""

# Fixed drawing colours (same in both themes) — AutoCAD ACI standard set.
STANDARD = ("#FF0000", "#FF7F00", "#FFFF00", "#00FF00", "#00FFFF",
            "#0000FF", "#FF00FF", "#808080", "#C0C0C0", "#FFFFFF")
STANDARD_NAMES = ("ACI 1 red", "ACI 30 orange", "ACI 2 yellow", "ACI 3 green",
                  "ACI 4 cyan", "ACI 5 blue", "ACI 6 magenta", "ACI 8 grey",
                  "ACI 9 light grey", "ACI 7 white")
GREYS = tuple("#" + f"{v:02X}" * 3
              for v in (0, 28, 57, 85, 113, 142, 170, 198, 227, 255))

RECENTS_KEY = "ui/colour_picker/recents"
RECENTS_MAX = 10


def _settings() -> QSettings:
    return QSettings("GV", "FirePro3D")


def load_recents() -> list[str]:
    raw = _settings().value(RECENTS_KEY, "", type=str) or ""
    return [h for h in raw.split(",") if h]


def _save_recents(lst: list[str]) -> None:
    _settings().setValue(RECENTS_KEY, ",".join(lst[:RECENTS_MAX]))


def push_recent(hex_color: str) -> None:
    """Record a committed colour: MRU-first, case-insensitive dedupe, cap 10.
    No Fill ("") is never recorded."""
    if not hex_color:
        return
    h = hex_color.upper()
    lst = [c for c in load_recents() if c.upper() != h]
    lst.insert(0, h)
    _save_recents(lst)


def clear_recents() -> None:
    _save_recents([])


class _SVField(QWidget):
    """Saturation (x) / value (y) square for the current hue."""
    changed = pyqtSignal(float, float)          # s, v in 0..1

    def __init__(self, parent=None, theme=None):
        super().__init__(parent)
        self._t = theme
        self.setFixedSize(M.COLOUR_SV_W, M.COLOUR_SV_H)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip("Saturation (left→right) and brightness (bottom→top)")
        self._h, self._s, self._v, self._show_pt = 0.0, 1.0, 1.0, True

    def set_hsv(self, h, s, v, show_pt=True):
        self._h, self._s, self._v, self._show_pt = h, s, v, show_pt
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor.fromHsvF(self._h, 1.0, 1.0))
        p.drawRoundedRect(r, 4, 4)
        gw = QLinearGradient(r.topLeft(), r.topRight())
        gw.setColorAt(0, QColor(255, 255, 255, 255)); gw.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(gw)); p.drawRoundedRect(r, 4, 4)
        gb = QLinearGradient(r.bottomLeft(), r.topLeft())
        gb.setColorAt(0, QColor(0, 0, 0, 255)); gb.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(gb)); p.drawRoundedRect(r, 4, 4)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor((self._t or detect()).line_strong), 1)); p.drawRoundedRect(r, 4, 4)
        if self._show_pt:
            c = QPointF(r.left() + self._s * r.width(), r.top() + (1 - self._v) * r.height())
            p.setPen(QPen(QColor(0, 0, 0), 1)); p.drawEllipse(c, 7, 7)
            p.setPen(QPen(QColor(255, 255, 255), 2)); p.drawEllipse(c, 6, 6)

    def _emit_at(self, pos):
        s = min(1.0, max(0.0, pos.x() / max(1, self.width() - 1)))
        v = 1.0 - min(1.0, max(0.0, pos.y() / max(1, self.height() - 1)))
        self.changed.emit(s, v)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._emit_at(e.position())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._emit_at(e.position())


class _HueBar(QWidget):
    """Vertical hue strip (top = 0°, bottom = 360°)."""
    changed = pyqtSignal(float)                  # hue 0..1

    def __init__(self, parent=None, theme=None):
        super().__init__(parent)
        self._t = theme
        self.setFixedSize(M.COLOUR_HUE_W, M.COLOUR_SV_H)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setToolTip("Hue")
        self._h = 0.0

    def set_hue(self, h):
        self._h = h
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        for i in range(7):
            g.setColorAt(i / 6, QColor.fromHsvF((i / 6) % 1.0, 1.0, 1.0))
        p.setPen(QPen(QColor((self._t or detect()).line_strong), 1)); p.setBrush(QBrush(g))
        p.drawRoundedRect(r, 4, 4)
        y = r.top() + self._h * r.height()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0), 1)); p.drawRoundedRect(QRectF(r.left() - 1, y - 3, r.width() + 2, 6), 3, 3)
        p.setPen(QPen(QColor(255, 255, 255), 2)); p.drawRoundedRect(QRectF(r.left(), y - 2, r.width(), 4), 2, 2)

    def _emit_at(self, pos):
        self.changed.emit(min(0.9999, max(0.0, pos.y() / max(1, self.height() - 1))))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._emit_at(e.position())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._emit_at(e.position())


class _PreviewChip(QWidget):
    """New (left) vs Current (right) comparison chip."""

    def __init__(self, current, parent=None, theme=None):
        super().__init__(parent)
        self._t = theme
        self.setFixedHeight(M.COLOUR_PREVIEW_H)
        self.setToolTip("New colour (left) vs current colour (right)")
        self._new, self._cur = current, current

    def set_new(self, v):
        self._new = v
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        half = QRectF(r.left(), r.top(), r.width() / 2, r.height())
        for v, rr in ((self._new, half), (self._cur, half.translated(r.width() / 2, 0))):
            if v == NO_FILL:
                paint_no_fill(p, rr, 0)
            else:
                p.fillRect(rr, QColor(v))
        p.setPen(QPen(QColor((self._t or detect()).line_strong), 1)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 4, 4)


class _PaletteChip(QWidget):
    """A palette/recent chip. ``value``: "#RRGGBB", NO_FILL (""), or None (empty
    recent slot — dashed, inert)."""
    picked = pyqtSignal(str)
    committed = pyqtSignal(str)

    def __init__(self, value, tip="", parent=None, theme=None):
        super().__init__(parent)
        self._t = theme
        self.value = value
        self.selected = False
        self.setFixedSize(M.COLOUR_CHIP, M.COLOUR_CHIP)
        if value is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tip or ("No Fill (transparent)" if value == NO_FILL
                                else value or "Empty — committed colours appear here"))

    def set_selected(self, on):
        self.selected = on
        self.update()

    def paintEvent(self, e):
        t = self._t or detect()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring = M.COLOUR_SEL_RING
        r = QRectF(self.rect()).adjusted(ring + 0.5, ring + 0.5, -ring - 0.5, -ring - 0.5)
        rad = M.COLOUR_CHIP_RADIUS
        if self.value is None:
            p.setPen(QPen(QColor(t.line_strong), 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush); p.drawRoundedRect(r, rad, rad)
            return
        if self.value == NO_FILL:
            paint_no_fill(p, r, rad)
            p.setBrush(Qt.BrushStyle.NoBrush)
        else:
            p.setBrush(QColor(self.value))
        p.setPen(QPen(QColor(t.line_strong), 1)); p.drawRoundedRect(r, rad, rad)
        if self.selected:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(t.accent), ring))
            o = QRectF(self.rect()).adjusted(ring / 2, ring / 2, -ring / 2, -ring / 2)
            p.drawRoundedRect(o, rad + 1, rad + 1)

    def mousePressEvent(self, e):
        if self.value is not None and e.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(self.value)

    def mouseDoubleClickEvent(self, e):
        if self.value is not None and e.button() == Qt.MouseButton.LeftButton:
            self.committed.emit(self.value)


def _section_label(text):
    lbl = QLabel(text.upper())
    lbl.setProperty("role", "overline")          # build_dialog_qss: accent 10px 600
    return lbl


class ColourPickerDialog(HouseDialog):
    """House colour picker. Read the outcome with ``result_value()``."""

    def __init__(self, parent=None, *, initial="#000000", context="",
                 allow_none=False, theme=None):
        super().__init__(parent, title="Colour", icon=None, theme=theme)
        self.setFixedWidth(M.COLOUR_DLG_W)
        self._allow_none = allow_none
        self._syncing = False
        self._chips: list[_PaletteChip] = []
        if initial == NO_FILL and allow_none:
            start = NO_FILL
        else:
            q = QColor(initial) if initial else QColor()
            start = q.name().upper() if q.isValid() else "#000000"
        self._no_fill = start == NO_FILL
        self._color = QColor("#000000") if self._no_fill else QColor(start)
        self._h = max(0.0, self._color.hsvHueF())
        if context:
            self.set_header_context(context)

        lay = self.body_layout()
        top = QHBoxLayout(); top.setSpacing(M.COLOUR_COL_GAP); top.setContentsMargins(0, 0, 0, 0)
        self._sv = _SVField(theme=self._theme); self._sv.changed.connect(self._on_sv)
        self._hue = _HueBar(theme=self._theme); self._hue.changed.connect(self._on_hue)
        top.addWidget(self._sv); top.addWidget(self._hue)
        side = QVBoxLayout(); side.setSpacing(6); side.setContentsMargins(0, 0, 0, 0)
        self._preview = _PreviewChip(start, theme=self._theme); side.addWidget(self._preview)
        grid = QGridLayout(); grid.setHorizontalSpacing(6); grid.setVerticalSpacing(6)
        self._hex = QLineEdit()
        self._hex.setFixedHeight(M.PROP_FIELD_H)
        self._hex.setValidator(QRegularExpressionValidator(QRegularExpression(r"#?[0-9A-Fa-f]{0,6}"), self))
        self._hex.setToolTip("Hex colour (#RRGGBB)")
        self._hex.textEdited.connect(self._on_hex_edited)
        self._hex.editingFinished.connect(self._sync_widgets)   # reformat on focus-out
        grid.addWidget(QLabel("Hex"), 0, 0); grid.addWidget(self._hex, 0, 1)
        self._r, self._g, self._b = Stepper(), Stepper(), Stepper()
        for i, (name, st) in enumerate((("R", self._r), ("G", self._g), ("B", self._b)), start=1):
            st.setRange(0, 255)
            st.setToolTip({"R": "Red (0–255)", "G": "Green (0–255)", "B": "Blue (0–255)"}[name])
            st.valueChanged.connect(self._on_rgb)
            grid.addWidget(QLabel(name), i, 0); grid.addWidget(st, i, 1)
        side.addLayout(grid); side.addStretch(1)
        top.addLayout(side, 1)
        lay.addLayout(top)

        std = list(zip(STANDARD, STANDARD_NAMES))
        self._standard_row_chips = self._add_row(lay, "Standard", [(v, f"{n} · {v}") for v, n in std]
                                                 + ([(NO_FILL, "No Fill (transparent)")] if allow_none else []))
        self._add_row(lay, "Greys", [(v, v) for v in GREYS])
        rec = load_recents()
        self._recent_row_chips = self._add_row(
            lay, "Recent", [(v, v) for v in rec] + [(None, "")] * (RECENTS_MAX - len(rec)))

        btns = self.set_footer_buttons(primary=("OK", self.accept), cancel=True)
        self._ok_btn = btns["primary"]
        self._ok_btn.setToolTip("Apply the selected colour")
        self._footer_box.button(QDialogButtonBox.StandardButton.Cancel).setToolTip(
            "Close without changing the colour")
        # Return/Enter must commit. Two HouseDialog seams defeat that today:
        # (1) set_footer_buttons calls setDefault(True) while the footer is still
        # unparented, so QDialog never records OK as its main default (and a
        # repeat setDefault(True) is a no-op) → on show Qt promotes the first
        # autoDefault button in the focus chain instead; (2) the frameless
        # title-bar dots are autoDefault QPushButtons that take initial focus.
        for pb in self._titlebar.findChildren(QPushButton):
            pb.setAutoDefault(False)
        self._ok_btn.setDefault(False)
        self._ok_btn.setDefault(True)            # now parented → registers with QDialog
        self._result_value = None
        self._sync_widgets()

    # ── build helpers ──────────────────────────────────────────────────────
    def _add_row(self, lay, title, entries):
        lay.addSpacing(M.COLOUR_SEC_GAP)
        lay.addWidget(_section_label(title))
        lay.addSpacing(4)
        row = QHBoxLayout(); row.setSpacing(M.COLOUR_CHIP_GAP); row.setContentsMargins(0, 0, 0, 0)
        chips = []
        for value, tip in entries:
            c = _PaletteChip(value, tip, theme=self._theme)
            c.picked.connect(self._on_chip)
            c.committed.connect(self._on_chip_commit)
            row.addWidget(c); chips.append(c)
        row.addStretch(1)
        lay.addLayout(row)
        self._chips.extend(chips)
        return chips

    # ── state ──────────────────────────────────────────────────────────────
    def current_value(self) -> str:
        return NO_FILL if self._no_fill else self._color.name().upper()

    def result_value(self):
        """None if cancelled, NO_FILL ("") or "#RRGGBB" if accepted."""
        return self._result_value

    def _set_colour(self, qc: QColor, *, keep_hue=False):
        self._no_fill = False
        self._color = QColor(qc)
        if not keep_hue and qc.hsvHueF() >= 0:
            self._h = qc.hsvHueF()
        self._sync_widgets()

    def _set_no_fill(self):
        if self._allow_none:
            self._no_fill = True
            self._sync_widgets()

    def _sync_widgets(self):
        self._syncing = True
        try:
            v = self.current_value()
            c = self._color
            self._sv.set_hsv(self._h, max(0.0, c.hsvSaturationF()), c.valueF(), show_pt=not self._no_fill)
            self._hue.set_hue(self._h)
            self._preview.set_new(v)
            if not self._hex.hasFocus() or self._no_fill:
                self._hex.setText("" if self._no_fill else v)
            self._hex.setPlaceholderText("None" if self._no_fill else "")
            for st, val in ((self._r, c.red()), (self._g, c.green()), (self._b, c.blue())):
                st.setValue(val)
            for chip in self._chips:
                chip.set_selected(chip.value is not None and chip.value == v)
        finally:
            self._syncing = False

    # ── slots ──────────────────────────────────────────────────────────────
    def _on_sv(self, s, v):
        self._set_colour(QColor.fromHsvF(self._h, s, v), keep_hue=True)

    def _on_hue(self, h):
        self._h = h
        c = self._color
        s, v = max(0.0, c.hsvSaturationF()), c.valueF()
        # Achromatic start (No Fill / black / grey): hue alone would stay
        # black/grey, so the bar looked dead — lift the missing component(s).
        if s == 0.0:
            s = 1.0
        if v == 0.0:
            v = 1.0
        self._set_colour(QColor.fromHsvF(h, s, v), keep_hue=True)

    def _on_hex_edited(self, text):
        t = text.strip()
        t = t if t.startswith("#") else "#" + t
        if len(t) == 7 and QColor(t).isValid():
            self._set_colour(QColor(t))

    def _on_rgb(self, _v):
        if not self._syncing:
            self._set_colour(QColor(self._r.value(), self._g.value(), self._b.value()))

    def _on_chip(self, value):
        if value == NO_FILL:
            self._set_no_fill()
        else:
            self._set_colour(QColor(value))

    def _on_chip_commit(self, value):
        self._on_chip(value)
        self.accept()

    # ── outcome ────────────────────────────────────────────────────────────
    def accept(self):
        self._result_value = self.current_value()
        push_recent(self._result_value)          # no-op for NO_FILL
        super().accept()

    def reject(self):
        self._result_value = None
        super().reject()


def pick_colour(initial, parent=None, context="", *, allow_none=False):
    """Open the house picker. Returns None (cancelled), NO_FILL ("") or a
    lower-case "#rrggbb" — the same convention QColor.name() gave every caller,
    so stored data / no-op comparisons keep their existing form. (The dialog
    DISPLAYS upper-case hex; only the returned value is lower-cased.)"""
    dlg = ColourPickerDialog(parent, initial=initial or "", context=context,
                             allow_none=allow_none)
    try:
        code = dlg.exec()
        v = dlg.result_value() if code == QDialog.DialogCode.Accepted else None
    finally:
        dlg.deleteLater()
    return None if v is None else v.lower()
