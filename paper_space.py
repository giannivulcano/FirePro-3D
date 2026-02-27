"""
paper_space.py
==============
Sprint 4B — Paper Space layout with title block and live model-space viewport.

Classes
-------
TitleBlockItem   — QGraphicsItem that draws a professional engineering title block
PaperViewport    — QGraphicsRectItem that live-renders Model_Space content
PaperScene       — QGraphicsScene representing one paper layout
PaperSpaceWidget — QWidget wrapping a view of PaperScene + paper-size/title controls
"""

from __future__ import annotations

import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsScene, QGraphicsView,
    QGraphicsItem, QGraphicsRectItem, QComboBox, QPushButton, QLabel,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QSizeF
from PyQt6.QtGui import (
    QPen, QBrush, QColor, QPainter, QFont, QFontMetricsF, QTransform,
)


# ─────────────────────────────────────────────────────────────────────────────
# Paper sizes (width × height in mm, portrait orientation)
# ─────────────────────────────────────────────────────────────────────────────

PAPER_SIZES: dict[str, tuple[float, float]] = {
    "A4":     (210.0,  297.0),
    "A3":     (297.0,  420.0),
    "A2":     (420.0,  594.0),
    "A1":     (594.0,  841.0),
    "A0":     (841.0, 1189.0),
    "Letter": (215.9,  279.4),
    "D-size": (558.8,  863.6),
}

# Margins (mm)
MARGIN        = 10.0    # outer border
INNER_MARGIN  = 5.0     # inside border to content
TITLE_H       = 65.0    # title block height


# ─────────────────────────────────────────────────────────────────────────────
# Title block
# ─────────────────────────────────────────────────────────────────────────────

class TitleBlockItem(QGraphicsItem):
    """
    Engineering title block rendered at the bottom of the sheet.

    The block spans the full inner width (inside the drawing border) and is
    TITLE_H mm tall.  All sizes are in scene mm units.
    """

    def __init__(self, sheet_w: float, sheet_h: float, parent=None):
        super().__init__(parent)
        self._sheet_w = sheet_w
        self._sheet_h = sheet_h
        self.setZValue(10)

        self.fields: dict[str, str] = {
            "Company":      "Celerity Engineering Limited",
            "Project":      "",
            "Title":        "Fire Suppression Layout",
            "Scale":        "1:100",
            "Drawing No":   "FP-001",
            "Rev":          "A",
            "Date":         datetime.date.today().strftime("%d %b %Y"),
            "Drawn By":     "",
            "Checked By":   "",
        }

    # -- Geometry helpers

    def _inner_x(self) -> float:
        return MARGIN + INNER_MARGIN

    def _block_y(self) -> float:
        return self._sheet_h - MARGIN - INNER_MARGIN - TITLE_H

    def _block_w(self) -> float:
        return self._sheet_w - 2 * (MARGIN + INNER_MARGIN)

    def boundingRect(self) -> QRectF:
        return QRectF(
            self._inner_x(), self._block_y(),
            self._block_w(), TITLE_H,
        )

    # -- Paint

    def paint(self, painter: QPainter, option, widget=None):
        x  = self._inner_x()
        y  = self._block_y()
        w  = self._block_w()
        h  = TITLE_H

        pen_thick = QPen(Qt.GlobalColor.black, 0.5)
        pen_thin  = QPen(Qt.GlobalColor.black, 0.25)
        white     = QBrush(Qt.GlobalColor.white)

        painter.setBrush(white)
        painter.setPen(pen_thick)
        painter.drawRect(QRectF(x, y, w, h))

        # ── Column layout ────────────────────────────────────────────────────
        #  col0: Company  (30% width)
        #  col1: Project / Title  (40% width)
        #  col2: Scale / DRG No  (15% width)
        #  col3: Rev / Date  (15% width)

        c0 = x
        c1 = x + w * 0.30
        c2 = x + w * 0.70
        c3 = x + w * 0.85

        # Row dividers
        r0 = y
        r1 = y + h * 0.33
        r2 = y + h * 0.66
        r3 = y + h

        painter.setPen(pen_thin)

        # Vertical dividers
        for cx in (c1, c2, c3):
            painter.drawLine(QPointF(cx, r0), QPointF(cx, r3))

        # Horizontal dividers (col1+)
        for rx in (r1, r2):
            painter.drawLine(QPointF(c1, rx), QPointF(x + w, rx))

        # ── Text ─────────────────────────────────────────────────────────────

        def label(rect, text, bold=False, big=False):
            f = QFont("Arial")
            f.setPointSizeF(2.5 if big else 2.0)
            f.setBold(bold)
            painter.setFont(f)
            painter.setPen(QPen(Qt.GlobalColor.black, 0.1))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter |
                             Qt.TextFlag.TextWordWrap, text)

        def small_label(rect, caption, value):
            """Two-line cell: small caption + larger value."""
            cap_rect = QRectF(rect.x() + 1, rect.y() + 0.5,
                              rect.width() - 2, rect.height() * 0.40)
            val_rect = QRectF(rect.x() + 1,
                              rect.y() + rect.height() * 0.40,
                              rect.width() - 2, rect.height() * 0.55)
            f = QFont("Arial"); f.setPointSizeF(1.6)
            painter.setFont(f)
            painter.setPen(QPen(QColor("#666666"), 0.1))
            painter.drawText(cap_rect, Qt.AlignmentFlag.AlignLeft |
                             Qt.AlignmentFlag.AlignVCenter, caption)
            f2 = QFont("Arial"); f2.setPointSizeF(2.2); f2.setBold(True)
            painter.setFont(f2)
            painter.setPen(QPen(Qt.GlobalColor.black, 0.1))
            painter.drawText(val_rect, Qt.AlignmentFlag.AlignLeft |
                             Qt.AlignmentFlag.AlignVCenter, " " + value)

        cell_h = (r3 - r1) / 2   # height of lower rows

        # Col 0 — company (full height)
        label(QRectF(c0 + 1, r0 + 1, c1 - c0 - 2, h - 2),
              self.fields["Company"], bold=True, big=True)

        # Col 1 rows
        small_label(QRectF(c1, r0, c2 - c1, r1 - r0),
                    "PROJECT", self.fields["Project"])
        small_label(QRectF(c1, r1, c2 - c1, r2 - r1),
                    "TITLE",   self.fields["Title"])
        f3 = QFont("Arial"); f3.setPointSizeF(1.8)
        painter.setFont(f3)
        painter.setPen(QPen(QColor("#666666"), 0.1))
        painter.drawText(QRectF(c1 + 1, r2 + 0.5, (c2 - c1) / 2 - 2, r3 - r2 - 1),
                         Qt.AlignmentFlag.AlignLeft, "DRAWN BY")
        painter.drawText(QRectF(c1 + (c2 - c1) / 2 + 1, r2 + 0.5,
                                (c2 - c1) / 2 - 2, r3 - r2 - 1),
                         Qt.AlignmentFlag.AlignLeft, "CHECKED BY")
        f4 = QFont("Arial"); f4.setPointSizeF(2.0); f4.setBold(True)
        painter.setFont(f4); painter.setPen(QPen(Qt.GlobalColor.black, 0.1))
        painter.drawText(QRectF(c1 + 1, r2 + (r3 - r2) * 0.4,
                                (c2 - c1) / 2 - 2, r3 - r2 - (r3 - r2) * 0.4),
                         Qt.AlignmentFlag.AlignLeft,
                         " " + self.fields["Drawn By"])
        painter.drawText(QRectF(c1 + (c2 - c1) / 2 + 1, r2 + (r3 - r2) * 0.4,
                                (c2 - c1) / 2 - 2,
                                r3 - r2 - (r3 - r2) * 0.4),
                         Qt.AlignmentFlag.AlignLeft,
                         " " + self.fields["Checked By"])
        # Vertical divider inside col1 bottom row
        painter.setPen(pen_thin)
        painter.drawLine(QPointF(c1 + (c2 - c1) / 2, r2),
                         QPointF(c1 + (c2 - c1) / 2, r3))

        # Col 2 rows
        small_label(QRectF(c2, r0, c3 - c2, r1 - r0), "SCALE",      self.fields["Scale"])
        small_label(QRectF(c2, r1, c3 - c2, r2 - r1), "DRAWING NO", self.fields["Drawing No"])
        small_label(QRectF(c2, r2, c3 - c2, r3 - r2), "SHEET",      "1 of 1")

        # Col 3 rows
        small_label(QRectF(c3, r0, x + w - c3, r1 - r0), "REV",  self.fields["Rev"])
        small_label(QRectF(c3, r1, x + w - c3, r2 - r1), "DATE", self.fields["Date"])
        small_label(QRectF(c3, r2, x + w - c3, r3 - r2), "NFPA", "13")

        # Outer border (redraw thick on top to cover thin)
        painter.setPen(pen_thick)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(x, y, w, h))


# ─────────────────────────────────────────────────────────────────────────────
# Viewport
# ─────────────────────────────────────────────────────────────────────────────

class PaperViewport(QGraphicsRectItem):
    """
    A rectangle in Paper Space that live-renders Model_Space content.

    The source area of the model scene can be overridden; if not set the
    entire scene rect is used.
    """

    def __init__(self, model_scene, x: float, y: float,
                 w: float, h: float, parent=None):
        super().__init__(x, y, w, h, parent)
        self._model_scene = model_scene
        self._source_rect: QRectF | None = None  # None = full scene rect

        pen = QPen(Qt.GlobalColor.black, 0.5)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.GlobalColor.white))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(5)

    @property
    def source_rect(self) -> QRectF | None:
        return self._source_rect

    @source_rect.setter
    def source_rect(self, rect: QRectF | None):
        self._source_rect = rect
        self.update()

    def paint(self, painter: QPainter, option, widget=None):
        r = self.rect()

        # White background
        painter.fillRect(r, Qt.GlobalColor.white)

        # Clip to viewport bounds
        painter.setClipRect(r)

        # Determine model-space source rect
        src = self._source_rect
        if src is None:
            src = self._model_scene.sceneRect()
        if not src.isNull() and not src.isEmpty():
            self._model_scene.render(painter, r, src)

        # Release clip before drawing border
        painter.setClipping(False)

        # Border
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.isSelected():
            painter.setPen(QPen(QColor("#0055ff"), 0.8, Qt.PenStyle.DashLine))
        else:
            painter.setPen(QPen(Qt.GlobalColor.black, 0.5))
        painter.drawRect(r)


# ─────────────────────────────────────────────────────────────────────────────
# Paper scene
# ─────────────────────────────────────────────────────────────────────────────

class PaperScene(QGraphicsScene):
    """
    QGraphicsScene representing one paper layout.

    Coordinate system: 1 scene unit = 1 mm.
    The paper sits at (0, 0) with width × height in mm.
    """

    def __init__(self, model_scene, paper_size: str = "A1"):
        super().__init__()
        self._model_scene = model_scene
        self._paper_size  = paper_size
        self._bg_item     = None
        self._border_item = None
        self._title       = None
        self._viewport    = None
        self._setup()

    def _setup(self):
        """Build/rebuild all paper scene items."""
        self.clear()

        w, h = PAPER_SIZES[self._paper_size]

        # White paper background with drop shadow
        self._bg_item = self.addRect(
            0, 0, w, h,
            QPen(Qt.GlobalColor.black, 0.3),
            QBrush(Qt.GlobalColor.white),
        )
        self._bg_item.setZValue(0)

        # Drawing border (inner margin)
        bx = MARGIN; by = MARGIN
        bw = w - 2 * MARGIN; bh = h - 2 * MARGIN
        border = self.addRect(
            bx, by, bw, bh,
            QPen(Qt.GlobalColor.black, 0.5),
            QBrush(Qt.BrushStyle.NoBrush),
        )
        border.setZValue(1)

        # Title block
        self._title = TitleBlockItem(w, h)
        self.addItem(self._title)

        # Viewport — fills the area above the title block (inside border)
        vp_x = bx + INNER_MARGIN
        vp_y = by + INNER_MARGIN
        vp_w = bw - 2 * INNER_MARGIN
        vp_h = bh - 2 * INNER_MARGIN - TITLE_H - 2
        self._viewport = PaperViewport(self._model_scene,
                                       vp_x, vp_y, vp_w, vp_h)
        self.addItem(self._viewport)

        self.setSceneRect(-20, -20, w + 40, h + 40)

    # ── Public API ──────────────────────────────────────────────────────────

    @property
    def paper_size(self) -> str:
        return self._paper_size

    @paper_size.setter
    def paper_size(self, size: str):
        if size in PAPER_SIZES:
            self._paper_size = size
            self._setup()

    @property
    def title_block(self) -> TitleBlockItem:
        return self._title

    def refresh_viewport(self):
        """Force the viewport to repaint (call after model changes)."""
        if self._viewport:
            self._viewport.update()


# ─────────────────────────────────────────────────────────────────────────────
# Title-block editor dialog
# ─────────────────────────────────────────────────────────────────────────────

class TitleBlockDialog(QDialog):
    def __init__(self, title_block: TitleBlockItem, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Title Block")
        self._tb = title_block

        layout = QFormLayout(self)
        self._edits: dict[str, QLineEdit] = {}

        for key, value in title_block.fields.items():
            edit = QLineEdit(value)
            self._edits[key] = edit
            layout.addRow(key + ":", edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _save(self):
        for key, edit in self._edits.items():
            self._tb.fields[key] = edit.text()
        self._tb.update()
        self.accept()


# ─────────────────────────────────────────────────────────────────────────────
# PaperSpaceWidget — the full dock/tab widget
# ─────────────────────────────────────────────────────────────────────────────

class PaperSpaceWidget(QWidget):
    """
    Complete Paper Space panel: toolbar + QGraphicsView of PaperScene.

    Parameters
    ----------
    model_scene : Model_Space
        The drawing scene whose content will be rendered in the viewport.
    """

    def __init__(self, model_scene, parent=None):
        super().__init__(parent)
        self._model_scene = model_scene

        self.paper_scene = PaperScene(model_scene, "A1")

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # ── Toolbar ────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 2, 4, 2)

        toolbar.addWidget(QLabel("Paper:"))
        self._size_combo = QComboBox()
        self._size_combo.addItems(list(PAPER_SIZES.keys()))
        self._size_combo.setCurrentText("A1")
        self._size_combo.currentTextChanged.connect(self._change_paper)
        toolbar.addWidget(self._size_combo)

        toolbar.addSpacing(12)

        edit_title_btn = QPushButton("Edit Title Block…")
        edit_title_btn.clicked.connect(self._edit_title)
        toolbar.addWidget(edit_title_btn)

        refresh_btn = QPushButton("⟳ Refresh Viewport")
        refresh_btn.setToolTip("Repaint the model-space preview")
        refresh_btn.clicked.connect(self._refresh)
        toolbar.addWidget(refresh_btn)

        fit_btn = QPushButton("Fit Sheet")
        fit_btn.clicked.connect(self._fit)
        toolbar.addWidget(fit_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # ── View ─────────────────────────────────────────────────────────────
        self.view = QGraphicsView(self.paper_scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setBackgroundBrush(QBrush(QColor("#c0c0c0")))
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        layout.addWidget(self.view)

        # Fit to sheet on first show
        self._fit()

    # ── Toolbar actions ───────────────────────────────────────────────────────

    def _change_paper(self, size: str):
        self.paper_scene.paper_size = size
        self._fit()

    def change_paper(self, size: str):
        """Public: change paper size and fit the view."""
        self._size_combo.setCurrentText(size)  # keeps combo in sync

    def _edit_title(self):
        dlg = TitleBlockDialog(self.paper_scene.title_block, self)
        dlg.exec()
        self.paper_scene.refresh_viewport()

    def edit_title_block(self):
        """Public: open the title block editor dialog."""
        self._edit_title()

    def _refresh(self):
        self.paper_scene.refresh_viewport()

    def _fit(self):
        self.view.fitInView(self.paper_scene.sceneRect(),
                            Qt.AspectRatioMode.KeepAspectRatio)

    # ── Zoom wheel ────────────────────────────────────────────────────────────

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.view.scale(factor, factor)
