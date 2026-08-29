"""Per-column delegates for the Underlay Manager tree: visibility/snap toggles,
colour swatch, named line-weight, and level chips.

Ported from the standalone prototype (``underlay_manager_pyqt6``), adapted for
the FirePro3D tree model, which differs from the prototype in three ways:

1. The model is a **tree** with two row kinds — top-level *underlay* rows and
   *layer child* rows.  Each delegate must paint/edit both (or blank the kind
   it doesn't apply to).
2. Colour is a single hex string (no mono/tint/original-quad modes).
3. Weight commits a **named** weight string (``""`` = Default/no override);
   there is no opacity delegate.

All editing goes through ``model.setData(index, value, EditRole)`` so the
shared ``Underlay`` record stays the single source of truth — the delegates
never mutate records directly (see ``UnderlayTreeModel.setData``).
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QPointF, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QApplication, QColorDialog, QMenu, QStyle, QStyledItemDelegate,
    QStyleOptionViewItem,
)

from .underlay_manager_model import (
    AppearanceEditableRole,
    LayerRole,
    UnderlayRole,
)
from .theme import Theme

ROW_HEIGHT = 34


class KeepOpenMenu(QMenu):
    """QMenu that does not close when a checkable action is clicked —
    gives level assignment the feel of a popover with checkboxes."""

    def mouseReleaseEvent(self, event):
        action = self.actionAt(event.position().toPoint())
        if action is not None and action.isCheckable() and action.isEnabled():
            action.trigger()
            return  # swallow: keep the menu open
        super().mouseReleaseEvent(event)


def make_menu(parent, keep_open: bool = False) -> QMenu:
    menu = KeepOpenMenu(parent) if keep_open else QMenu(parent)
    menu.setObjectName("uwMenu")
    return menu


# ---------------------------------------------------------------------------
# painting helpers
# ---------------------------------------------------------------------------

def _round_pen(color: QColor, width: float = 1.6) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


def _draw_eye(p: QPainter, r: QRectF, on: bool, color: QColor) -> None:
    p.setPen(_round_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width() / 2, r.height() / 2.4
    if on:
        path = QPainterPath()
        path.moveTo(cx - w, cy)
        path.quadTo(cx, cy - h * 1.5, cx + w, cy)
        path.quadTo(cx, cy + h * 1.5, cx - w, cy)
        p.drawPath(path)
        p.drawEllipse(QPointF(cx, cy), 2.3, 2.3)
    else:
        path = QPainterPath()  # closed lid
        path.moveTo(cx - w, cy - 1)
        path.quadTo(cx, cy + h, cx + w, cy - 1)
        p.drawPath(path)
        for dx, dy in ((-w * 0.62, 3.6), (0.0, 4.6), (w * 0.62, 3.6)):
            p.drawLine(QPointF(cx + dx, cy + dy * 0.55), QPointF(cx + dx, cy + dy * 0.55 + 3))


def _draw_snap(p: QPainter, r: QRectF, color: QColor) -> None:
    """OSNAP aperture: square with crosshair ticks."""
    p.setPen(_round_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    cx, cy = r.center().x(), r.center().y()
    s = min(r.width(), r.height()) * 0.30
    p.drawRect(QRectF(cx - s, cy - s, s * 2, s * 2))
    t = s * 0.9
    p.drawLine(QPointF(cx, cy - s - t), QPointF(cx, cy - s - 1))
    p.drawLine(QPointF(cx, cy + s + 1), QPointF(cx, cy + s + t))
    p.drawLine(QPointF(cx - s - t, cy), QPointF(cx - s - 1, cy))
    p.drawLine(QPointF(cx + s + 1, cy), QPointF(cx + s + t, cy))


# ---------------------------------------------------------------------------
# base
# ---------------------------------------------------------------------------

class _BaseDelegate(QStyledItemDelegate):
    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.t = theme

    # -- row-kind + editability helpers -----------------------------------
    def _record(self, index):
        """The ``Underlay`` record (present on both row kinds)."""
        return index.data(UnderlayRole)

    def _layer(self, index):
        """Layer-name str for a layer child row; ``None`` for an underlay row."""
        return index.data(LayerRole)

    def _appearance_editable(self, index) -> bool:
        """True unless this is a raster-PDF underlay row."""
        return bool(index.data(AppearanceEditableRole))

    def _paint_background(self, painter, option, index) -> None:
        """Draw the QSS-styled item background (hover/selected), no text."""
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

    def sizeHint(self, option, index) -> QSize:
        return QSize(60, ROW_HEIGHT)

    @staticmethod
    def _released_inside(event, option) -> bool:
        return (
            event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
            and option.rect.contains(event.position().toPoint())
        )

    def _menu_pos(self, option):
        return option.widget.viewport().mapToGlobal(option.rect.bottomLeft())


# ---------------------------------------------------------------------------
# visibility / snap toggles
# ---------------------------------------------------------------------------

class ToggleDelegate(_BaseDelegate):
    def __init__(self, theme: Theme, field: str, parent=None):
        super().__init__(theme, parent)
        self.field = field  # "visible" | "snap"

    def paint(self, painter, option, index):
        self._paint_background(painter, option, index)
        record = self._record(index)
        if record is None:
            return
        layer = self._layer(index)

        if self.field == "visible":
            on = record.visible if layer is None else (layer not in record.hidden_layers)
            self._draw(painter, option, on, eye=True)
            return

        # snap: only for a vector underlay row (skip layer rows + raster PDF).
        if layer is not None or not self._appearance_editable(index):
            return
        self._draw(painter, option, record.snap, eye=False)

    def _draw(self, painter, option, on: bool, eye: bool) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.t.color("accent") if on else self.t.color("faint", 170)
        r = QRectF(0, 0, 17, 17)
        r.moveCenter(QRectF(option.rect).center())
        if eye:
            _draw_eye(painter, r, on, color)
        else:
            _draw_snap(painter, r, color)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if not self._released_inside(event, option):
            return False
        record = self._record(index)
        if record is None:
            return False
        layer = self._layer(index)

        if self.field == "visible":
            cur = record.visible if layer is None else (layer not in record.hidden_layers)
            model.setData(index, not cur, Qt.ItemDataRole.EditRole)
            return True

        # snap: underlay-only, vector-only.
        if layer is not None or not self._appearance_editable(index):
            return False
        model.setData(index, not record.snap, Qt.ItemDataRole.EditRole)
        return True


# ---------------------------------------------------------------------------
# colour (single hex swatch, no menu)
# ---------------------------------------------------------------------------

class ColourDelegate(_BaseDelegate):
    SWATCH = 15

    def _shown_hex(self, index) -> str:
        record = self._record(index)
        layer = self._layer(index)
        if layer is not None:
            return record.effective_layer_colour(layer)
        return record.colour

    def paint(self, painter, option, index):
        self._paint_background(painter, option, index)
        record = self._record(index)
        if record is None:
            return
        layer = self._layer(index)
        # Raster-PDF underlay row: nothing to recolour -> blank.
        if layer is None and not self._appearance_editable(index):
            return

        hex_colour = self._shown_hex(index)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = option.rect
        sw = QRectF(r.x() + 8, r.center().y() - self.SWATCH / 2, self.SWATCH, self.SWATCH)

        painter.setPen(QPen(self.t.color("line_strong"), 1))
        painter.setBrush(QColor(hex_colour))
        painter.drawRoundedRect(sw, 3, 3)

        painter.setPen(self.t.color("muted"))
        text_rect = QRect(int(sw.right()) + 7, r.y(), r.width(), r.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, str(hex_colour).upper())
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if not self._released_inside(event, option):
            return False
        record = self._record(index)
        if record is None:
            return False
        layer = self._layer(index)
        if layer is None and not self._appearance_editable(index):
            return False
        current = self._shown_hex(index)
        colour = QColorDialog.getColor(QColor(current), option.widget, "Underlay colour")
        if colour.isValid():
            model.setData(index, colour.name(), Qt.ItemDataRole.EditRole)
        return True


# ---------------------------------------------------------------------------
# line weight (named weights; "" = Default / no override)
# ---------------------------------------------------------------------------

class WeightDelegate(_BaseDelegate):
    def _current_name(self, index) -> str:
        record = self._record(index)
        layer = self._layer(index)
        if layer is not None:
            return record.effective_layer_weight(layer) or ""
        return record.line_weight_name or ""

    def paint(self, painter, option, index):
        self._paint_background(painter, option, index)
        record = self._record(index)
        if record is None:
            return
        layer = self._layer(index)
        if layer is None and not self._appearance_editable(index):
            return
        label = self._current_name(index) or "Default"
        painter.save()
        painter.setPen(self.t.color("muted"))
        painter.drawText(
            option.rect.adjusted(8, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, label
        )
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if not self._released_inside(event, option):
            return False
        record = self._record(index)
        if record is None:
            return False
        layer = self._layer(index)
        if layer is None and not self._appearance_editable(index):
            return False

        # Lazy import + call to avoid QSettings access at module import time.
        from .paper_display import load_line_weights
        names = [lw.name for lw in load_line_weights()]

        current = self._current_name(index)
        menu = make_menu(option.widget)
        act_default = menu.addAction("Default")
        act_default.setCheckable(True)
        act_default.setChecked(current == "")
        act_default.setData("")
        for name in names:
            action = menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(name == current)
            action.setData(name)
        chosen = menu.exec(self._menu_pos(option))
        if chosen is not None:
            model.setData(index, chosen.data() or "", Qt.ItemDataRole.EditRole)
        return True


# ---------------------------------------------------------------------------
# levels (chips + keep-open checkbox menu) — underlay rows only
# ---------------------------------------------------------------------------

class LevelsDelegate(_BaseDelegate):
    def __init__(self, theme: Theme, known_levels, parent=None):
        super().__init__(theme, parent)
        self._known_levels = known_levels  # callable -> list[str]

    def paint(self, painter, option, index):
        self._paint_background(painter, option, index)
        if self._layer(index) is not None:
            return  # layer rows have no level assignment
        record = self._record(index)
        if record is None:
            return
        known = self._known_levels()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fm = QFontMetrics(option.font)
        x = option.rect.x() + 6
        cy = option.rect.center().y()

        def chip(text: str, bg: QColor, fg: QColor, strike: bool = False) -> None:
            nonlocal x
            w = fm.horizontalAdvance(text) + 14
            r = QRectF(x, cy - 9, w, 18)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(r, 9, 9)
            painter.setPen(fg)
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
            if strike:
                painter.drawLine(
                    QPointF(r.x() + 6, r.center().y()), QPointF(r.right() - 6, r.center().y())
                )
            x += w + 5

        if record.levels == ["*"]:
            chip("All Levels", self.t.color("accent", 40), self.t.color("accent"))
        elif not record.levels:
            chip("No levels", self.t.color("warn", 40), self.t.color("warn"))
        else:
            shown = 1 if len(record.levels) > 2 else len(record.levels)
            for level in record.levels[:shown]:
                orphan = level not in known
                chip(
                    level,
                    self.t.color("warn", 40) if orphan else self.t.color("chip"),
                    self.t.color("warn") if orphan else self.t.color("chip_ink"),
                    strike=orphan,
                )
            if len(record.levels) > shown:
                painter.setPen(self.t.color("accent"))
                painter.drawText(
                    QRect(int(x), option.rect.y(), 40, option.rect.height()),
                    Qt.AlignmentFlag.AlignVCenter,
                    f"+{len(record.levels) - shown}",
                )
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(150, ROW_HEIGHT)

    def editorEvent(self, event, model, option, index):
        if not self._released_inside(event, option):
            return False
        if self._layer(index) is not None:
            return False  # underlay rows only
        record = self._record(index)
        if record is None:
            return False
        known = self._known_levels()
        menu = make_menu(option.widget, keep_open=True)

        def apply(levels: list[str]) -> None:
            model.setData(index, levels, Qt.ItemDataRole.EditRole)

        for level in known:
            action = menu.addAction(level)
            action.setCheckable(True)
            action.setChecked(level in record.levels)

            def toggled(checked: bool, lv: str = level) -> None:
                current = model.data(index, UnderlayRole)
                cur_levels = [] if current.levels == ["*"] else list(current.levels)
                # Preserve any names not in the known list (still visible as
                # struck chips) alongside the toggled known levels.
                orphans = [v for v in cur_levels if v not in known]
                kept = [v for v in known if (v in cur_levels or (checked and v == lv))]
                if not checked:
                    kept = [v for v in kept if v != lv]
                apply(kept + orphans)

            action.triggered.connect(toggled)

        menu.addSeparator()
        all_action = menu.addAction("All Levels")
        all_action.triggered.connect(lambda _=False: apply(["*"]))
        clear_action = menu.addAction("Clear")
        clear_action.triggered.connect(lambda _=False: apply([]))

        menu.exec(self._menu_pos(option))
        return True
