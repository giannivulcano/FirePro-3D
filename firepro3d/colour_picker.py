"""colour_picker.py — house colour picker (todo #70).

One modal ``ColourPickerDialog(HouseDialog)`` + one entry point
``pick_colour(initial, parent, context)`` (every row, always) replacing the
native Qt colour dialog app-wide. Result contract:
    None        → cancelled (caller changes nothing)
    ""          → No Fill (always offered)
    "#RRGGBB"   → a colour
    "token:*"   → a theme token (Automatic / Accent; always offered)
Callers must import the MODULE and call ``colour_picker.pick_colour`` so tests
can monkeypatch one attribute. See docs/specs/ui-design-system.md.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import (Qt, QRectF, QPointF, QRegularExpression, QSettings,
                          pyqtSignal)
from PyQt6.QtGui import (QColor, QPainter, QPen, QLinearGradient, QBrush,
                         QRegularExpressionValidator, QDoubleValidator)
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                             QLineEdit, QGridLayout, QDialog, QDialogButtonBox,
                             QPushButton, QToolButton, QMenu)

from .colour_tokens import is_token, resolve_colour, token_label
from .constants import TOKEN_ACCENT, TOKEN_AUTO
from .fill_layers import NO_LAYER, BackgroundLayer, PatternLayer
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
    No Fill ("") and colour tokens are never recorded (a token is theme-relative,
    not a colour to remember)."""
    if not hex_color or is_token(hex_color):
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
                p.fillRect(rr, resolve_colour(v))
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
            p.setBrush(resolve_colour(self.value))
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


class _PatternChip(QWidget):
    """Pattern-row chip (UP1): ``value`` is a tile ref, or None for the None
    chip (pattern off). Painted by the shared preview (``pattern_preview``)."""
    picked = pyqtSignal(object)
    committed = pyqtSignal(object)

    def __init__(self, value, tip, registry=None, parent=None, theme=None):
        super().__init__(parent)
        self._t = theme
        self.value = value
        self.selected = False
        self._registry = registry
        self._colour = QColor("#808080")      # theme-exempt: replaced by set_colour before show
        self.setFixedSize(M.COLOUR_PATTERN_CHIP_W, M.COLOUR_CHIP)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tip)

    def set_selected(self, on):
        self.selected = on
        self.update()

    def set_colour(self, qc):
        self._colour = QColor(qc)
        self.update()

    def paintEvent(self, e):
        t = self._t or detect()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring = M.COLOUR_SEL_RING
        r = QRectF(self.rect()).adjusted(ring + 0.5, ring + 0.5, -ring - 0.5, -ring - 0.5)
        rad = M.COLOUR_CHIP_RADIUS
        if self.value is None:
            paint_no_fill(p, r, rad)
        else:
            from .hatch_render import pattern_preview
            p.drawPixmap(r.toRect(), pattern_preview(
                self.value, self._colour, max(1, int(r.width())),
                max(1, int(r.height())), self._registry,
                background=QColor(t.bg_sunken)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(t.line_strong), 1))
        p.drawRoundedRect(r, rad, rad)
        if self.selected:
            p.setPen(QPen(QColor(t.accent), ring))
            o = QRectF(self.rect()).adjusted(ring / 2, ring / 2, -ring / 2, -ring / 2)
            p.drawRoundedRect(o, rad + 1, rad + 1)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(self.value)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.committed.emit(self.value)


def _section_label(text):
    lbl = QLabel(text.upper())
    lbl.setProperty("role", "overline")          # build_dialog_qss: accent 10px 600
    return lbl


class ColourPickerDialog(HouseDialog):
    """House colour picker. Read the outcome with ``result_value()``."""

    def __init__(self, parent=None, *, initial="#000000", context="",
                 theme=None, mode="colour", layer=None, registry=None,
                 exclude=()):
        """``mode``: ``"colour"`` (today's dialog), ``"fill"`` (adds Opacity;
        No Fill = background off) or ``"pattern"`` (adds the Pattern row,
        Opacity and Scale; No Fill hidden). ``layer`` seeds the Fill block."""
        super().__init__(parent, title="Colour", icon=None, theme=theme)
        self.setFixedWidth(M.COLOUR_DLG_W)
        self._token = initial if is_token(initial) else None
        self._syncing = False
        self._chips: list[_PaletteChip] = []
        self._mode = mode
        self._layer = layer
        self._pattern_ref = layer.ref if isinstance(layer, PatternLayer) else None
        self._pattern_chips: list[_PatternChip] = []
        self._more_btn = None
        self._opacity = None
        self._scale = None
        self._result_layer = None
        if initial == NO_FILL:
            start = NO_FILL
        elif self._token:
            start = resolve_colour(self._token).name().upper()
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
        self._preview = _PreviewChip(self._token or start, theme=self._theme); side.addWidget(self._preview)
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

        self._theme_row_chips = self._add_token_row(lay)
        std = list(zip(STANDARD, STANDARD_NAMES))
        self._standard_row_chips = self._add_row(lay, "Standard", [(v, f"{n} · {v}") for v, n in std]
                                                 + [(NO_FILL, "No Fill (transparent)")])
        self._add_row(lay, "Greys", [(v, v) for v in GREYS])
        rec = load_recents()
        self._recent_row_chips = self._add_row(
            lay, "Recent", [(v, v) for v in rec] + [(None, "")] * (RECENTS_MAX - len(rec)))

        if mode == "pattern":
            self._standard_row_chips[-1].hide()       # No Fill: the None chip owns "off"
        if mode in ("fill", "pattern"):
            self._build_fill_block(lay, registry, exclude)

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

    def _add_token_row(self, lay):
        """Overline **Theme** row: Automatic + Accent chips, each drawn in its
        current-canvas colour with a caption (D-A18, ui-design-system D6)."""
        lay.addSpacing(M.COLOUR_SEC_GAP)
        lay.addWidget(_section_label("Theme"))
        lay.addSpacing(4)
        row = QHBoxLayout(); row.setSpacing(M.COLOUR_CHIP_GAP); row.setContentsMargins(0, 0, 0, 0)
        chips = []
        for value in (TOKEN_AUTO, TOKEN_ACCENT):
            c = _PaletteChip(value, token_label(value), theme=self._theme)
            c.picked.connect(self._on_chip)
            c.committed.connect(self._on_chip_commit)
            row.addWidget(c)
            row.addWidget(QLabel(token_label(value)))
            row.addSpacing(M.COLOUR_COL_GAP)
            chips.append(c)
        row.addStretch(1)
        lay.addLayout(row)
        self._chips.extend(chips)
        return chips

    def _build_fill_block(self, lay, registry, exclude):
        """Fill block below the Recent row (D3): Pattern row (pattern mode),
        Opacity, Scale (pattern mode)."""
        lay.addSpacing(M.COLOUR_SEC_GAP)
        lay.addWidget(_section_label("Fill"))
        lay.addSpacing(4)
        layer = self._layer
        if self._mode == "pattern":
            self._add_pattern_row(lay, registry, exclude)
        grid = QGridLayout(); grid.setHorizontalSpacing(6); grid.setVerticalSpacing(6)
        self._opacity = Stepper()
        self._opacity.setRange(0, 100)
        self._opacity.setValue(round((layer.opacity if layer is not None else 1.0) * 100))
        self._opacity.setToolTip("Fill opacity (0–100 %)")
        grid.addWidget(QLabel("Opacity"), 0, 0)
        grid.addWidget(self._opacity, 0, 1)
        grid.addWidget(QLabel("%"), 0, 2)
        if self._mode == "pattern":
            self._scale = QLineEdit(f"{layer.scale:g}" if layer is not None else "1")
            self._scale.setFixedHeight(M.PROP_FIELD_H)
            v = QDoubleValidator(0.0001, 1.0e6, 4, self)
            v.setNotation(QDoubleValidator.Notation.StandardNotation)
            self._scale.setValidator(v)
            self._scale.setToolTip("Pattern scale (a positive multiplier)")
            grid.addWidget(QLabel("Scale"), 1, 0)
            grid.addWidget(self._scale, 1, 1)
        grid.setColumnStretch(3, 1)
        lay.addLayout(grid)

    def _add_pattern_row(self, lay, registry, exclude):
        """None chip, the first ``M.COLOUR_PATTERN_ROW_MAX`` tiles, then
        "More..." with the rest (``tile_choices`` -- the one pattern source).
        An unresolvable current ref shows first as a missing chip (D-A36)."""
        from .hatch_patterns import MISSING_PATTERN_LABEL, tile_choices
        choices = tile_choices(registry, exclude)
        refs = [r for _n, r in choices]
        row = QHBoxLayout(); row.setSpacing(M.COLOUR_CHIP_GAP); row.setContentsMargins(0, 0, 0, 0)
        shown = [(None, "None (no pattern)")]
        if self._pattern_ref is not None and self._pattern_ref not in refs:
            shown.append((self._pattern_ref, MISSING_PATTERN_LABEL))
        shown += [(r, n) for n, r in choices[:M.COLOUR_PATTERN_ROW_MAX]]
        for value, tip in shown:
            c = _PatternChip(value, tip, registry, theme=self._theme)
            c.picked.connect(self._on_pattern)
            c.committed.connect(self._on_pattern_commit)
            row.addWidget(c)
            self._pattern_chips.append(c)
        rest = choices[M.COLOUR_PATTERN_ROW_MAX:]
        if rest:
            btn = QToolButton()
            btn.setText("More…")
            btn.setCheckable(True)
            btn.setToolTip("More patterns")
            menu = QMenu(btn)
            for name, ref in rest:
                act = menu.addAction(name)
                act.triggered.connect(lambda _=False, r=ref: self._on_pattern(r))
            btn.setMenu(menu)
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            row.addWidget(btn)
            self._more_btn = btn
        row.addStretch(1)
        lay.addLayout(row)

    def _on_pattern(self, ref):
        self._pattern_ref = ref
        self._sync_widgets()

    def _on_pattern_commit(self, ref):
        self._on_pattern(ref)
        self.accept()

    def _scale_value(self) -> float:
        prior = self._layer.scale if isinstance(self._layer, PatternLayer) else 1.0
        try:
            v = float(self._scale.text())
        except (TypeError, ValueError):
            return prior
        return v if math.isfinite(v) and v > 0.0 else prior

    def result_layer(self):
        """Fill-mode outcome: a layer, ``NO_LAYER`` (layer off) or None (cancelled)."""
        return self._result_layer

    # ── state ──────────────────────────────────────────────────────────────
    def current_value(self) -> str:
        if self._token:
            return self._token
        return NO_FILL if self._no_fill else self._color.name().upper()

    def result_value(self):
        """None if cancelled, NO_FILL (""), a colour token 
        or "#RRGGBB" if accepted."""
        return self._result_value

    def _set_colour(self, qc: QColor, *, keep_hue=False):
        self._token = None
        self._no_fill = False
        self._color = QColor(qc)
        if not keep_hue and qc.hsvHueF() >= 0:
            self._h = qc.hsvHueF()
        self._sync_widgets()

    def _set_no_fill(self):
        self._token = None
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
                self._hex.setText("" if (self._no_fill or self._token) else v)
            self._hex.setPlaceholderText(
                "None" if self._no_fill else (token_label(self._token) or ""))
            for st, val in ((self._r, c.red()), (self._g, c.green()), (self._b, c.blue())):
                st.setValue(val)
            for chip in self._chips:
                chip.set_selected(chip.value is not None and chip.value == v)
            if self._pattern_chips:
                shown = False
                for chip in self._pattern_chips:
                    chip.set_selected(chip.value == self._pattern_ref)
                    chip.set_colour(self._color)
                    shown = shown or chip.value == self._pattern_ref
                if self._more_btn is not None:
                    self._more_btn.setChecked(not shown)
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
        if is_token(value):
            self._token = value
            self._no_fill = False
            self._color = resolve_colour(value)
            self._sync_widgets()
            return
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
        push_recent(self._result_value)          # no-op for NO_FILL; colour only
        if self._mode in ("fill", "pattern"):
            v = self._result_value
            col = v.lower() if v.startswith("#") else v
            op = self._opacity.value() / 100.0
            if self._mode == "fill":
                self._result_layer = (NO_LAYER if v == NO_FILL
                                      else BackgroundLayer(col, op))
            elif self._pattern_ref is None:
                self._result_layer = NO_LAYER
            else:
                self._result_layer = PatternLayer(self._pattern_ref, col, op,
                                                  self._scale_value())
        super().accept()

    def reject(self):
        self._result_value = None
        self._result_layer = None
        super().reject()


def pick_colour(initial, parent=None, context=""):
    """Open the house picker. Returns None (cancelled), NO_FILL (""), a colour
    token or a lower-case "#rrggbb" — the same convention
    QColor.name() gave every caller, so stored data / no-op comparisons keep
    their existing form. (The dialog DISPLAYS upper-case hex; only the
    returned value is lower-cased.)"""
    dlg = ColourPickerDialog(parent, initial=initial or "", context=context)
    try:
        code = dlg.exec()
        v = dlg.result_value() if code == QDialog.DialogCode.Accepted else None
    finally:
        dlg.deleteLater()
    return None if v is None else v.lower()


def pick_fill(initial, parent=None, *, pattern: bool, context="",
              registry=None, exclude=()):
    """Open the picker in fill mode (``pattern=False``: background colour +
    opacity) or pattern mode (pattern + colour + opacity + scale).

    Args:
        initial: The current ``BackgroundLayer`` / ``PatternLayer``, or None.
        parent: Dialog parent.
        pattern: Pattern mode when True.
        context: Header context label.
        registry: Project block registry for the Pattern row (pattern mode).
        exclude: Tile ids the Pattern row must not offer (``picker_exclude``).

    Returns:
        A layer, ``NO_LAYER`` (turn the layer off) or None (cancelled).
    """
    if initial is not None:
        colour = initial.color
    else:
        colour = TOKEN_AUTO if pattern else NO_FILL      # D2 / unfilled shape
    dlg = ColourPickerDialog(parent, initial=colour, context=context,
                             mode="pattern" if pattern else "fill",
                             layer=initial, registry=registry, exclude=exclude)
    try:
        code = dlg.exec()
        return dlg.result_layer() if code == QDialog.DialogCode.Accepted else None
    finally:
        dlg.deleteLater()
