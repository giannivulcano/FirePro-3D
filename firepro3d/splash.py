"""FirePro 3D splash screen — PyQt6.

Usage:
    from firepro3d.splash import FireProSplash
    app = QApplication(sys.argv)
    splash = FireProSplash(version="1.0.0")
    splash.show()
    app.processEvents()

    splash.set_progress(20, "Loading hydraulic calculation module…")
    ...  # startup work, calling set_progress as you go
    splash.finish(main_window)  # or splash.close()
"""
from __future__ import annotations

import math
import time

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap, QPolygonF, QRadialGradient,
)
from PyQt6.QtWidgets import QSplashScreen

from .theme import FONT_UI, FONT_VALUE

# Brand palette — theme-exempt. The splash is a fixed brand artifact (like a
# logo), shown before the app theme is applied; its navy/steel/orange identity
# is intentionally independent of the light/dark house tokens. Only the fonts
# are tokenised (see __init__).
NAVY = QColor("#0b1628")
NAVY_2 = QColor("#10203a")
STEEL = QColor("#5f8fd6")
STEEL_SOFT = QColor("#8fb0e0")
BLUE = QColor("#2f6fd1")
ORANGE = QColor("#f47c20")
TEXT = QColor("#ffffff")
TEXT_DIM = QColor("#b9c8de")
TEXT_MUTED = QColor("#5a7196")

COMPANY = "Vulcan FLS Ltd."
TAGLINE = ["DESIGN", "BUILD", "ANALYZE"]


class FireProSplash(QSplashScreen):
    W, H = 720, 400
    RADIUS = 12
    MARGIN = 64

    def __init__(self, version: str = "1.0.0"):
        base = QPixmap(QSize(self.W, self.H))
        base.fill(Qt.GlobalColor.transparent)
        super().__init__(base)
        self.setWindowFlags(Qt.WindowType.SplashScreen
                            | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.version = version
        self.progress = 0
        self.status = "Starting…"
        self._glow = 0.0

        # Typography follows the house roles (docs/architecture/theming.md):
        # FONT_UI for prose/labels/wordmark; FONT_VALUE (monospace) for the
        # numeric readouts (progress %, version) so digit columns align.
        self.f_title = QFont(FONT_UI, 58, QFont.Weight.ExtraBold)
        self.f_tag = QFont(FONT_UI, 11, QFont.Weight.DemiBold)
        self.f_status = QFont(FONT_UI, 10)
        self.f_value = QFont(FONT_VALUE, 10)
        self.f_small = QFont(FONT_UI, 8)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    # ---- public API ------------------------------------------------------
    def set_progress(self, value: int, status: str | None = None) -> None:
        # Clamp to [0,100] and never regress: startup progress is monotonic, so
        # a caller passing a lower value (e.g. main() and MainWindow.__init__
        # narrating with mismatched numbering) must not rewind the bar. The
        # status text still updates so the message always tracks the real step.
        self.progress = max(self.progress, min(100, max(0, value)))
        if status is not None:
            self.status = status
        self.repaint()

    # ---- painting --------------------------------------------------------
    def drawContents(self, p: QPainter) -> None:  # noqa: N802 (Qt override)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, self.W, self.H)
        clip = QPainterPath()
        clip.addRoundedRect(rect, self.RADIUS, self.RADIUS)
        p.setClipPath(clip)

        # Background layers
        p.fillRect(rect, NAVY)
        self._draw_hex_grid(p)

        glow = QRadialGradient(QPointF(120, 80), 240)
        a = 0.6 + 0.4 * self._glow
        glow.setColorAt(0.0, QColor(244, 124, 32, int(0.22 * 255 * a)))
        glow.setColorAt(0.45, QColor(30, 70, 140, int(0.16 * 255 * a)))
        glow.setColorAt(0.70, QColor(11, 22, 40, 0))
        p.fillRect(rect, glow)

        slab = QPolygonF([QPointF(520, -10), QPointF(self.W + 10, -10),
                          QPointF(self.W + 10, self.H + 10), QPointF(415, self.H + 10)])
        grad = QLinearGradient(520, 0, self.W, self.H)
        grad.setColorAt(0, NAVY_2)
        grad.setColorAt(1, NAVY)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawPolygon(slab)
        edge = QColor(STEEL)
        edge.setAlphaF(0.22)
        p.setPen(QPen(edge, 1))
        p.drawLine(QPointF(520, -10), QPointF(415, self.H + 10))

        x0 = self.MARGIN
        x1 = self.W - self.MARGIN

        # Wordmark
        y = 168
        p.setFont(self.f_title)
        fm = p.fontMetrics()
        x = x0
        for word, color in (("FIRE", TEXT), ("PRO", ORANGE), (" 3D", TEXT)):
            p.setPen(color)
            p.drawText(QPointF(x, y), word)
            x += fm.horizontalAdvance(word)

        # Tagline with orange dots
        p.setFont(self.f_tag)
        fm = p.fontMetrics()
        ty = y + 34
        x = x0
        for i, word in enumerate(TAGLINE):
            p.setPen(STEEL_SOFT)
            self._draw_spaced(p, x, ty, word, 4)
            x += self._spaced_width(fm, word, 4) + 14
            if i < len(TAGLINE) - 1:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(ORANGE)
                p.drawEllipse(QPointF(x + 2, ty - fm.xHeight() / 2), 2, 2)
                x += 4 + 14

        # Divider
        dy = ty + 30
        line = QLinearGradient(x0, 0, x1, 0)
        line.setColorAt(0.0, QColor(244, 124, 32, 230))
        line.setColorAt(0.55, QColor(95, 143, 214, 90))
        line.setColorAt(1.0, QColor(95, 143, 214, 0))
        p.fillRect(QRectF(x0, dy, x1 - x0, 1), line)

        # Status (prose → FONT_UI) + progress readout (numeric → FONT_VALUE)
        sy = dy + 34
        p.setFont(self.f_status)
        p.setPen(STEEL_SOFT)
        p.drawText(QPointF(x0, sy), self.status)
        p.setFont(self.f_value)
        p.setPen(TEXT)
        pct = f"{self.progress}%"
        p.drawText(QPointF(x1 - p.fontMetrics().horizontalAdvance(pct), sy), pct)

        track = QRectF(x0, sy + 10, x1 - x0, 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(95, 143, 214, 46))
        p.drawRoundedRect(track, 3, 3)
        if self.progress > 0:
            fill = QRectF(track.x(), track.y(), track.width() * self.progress / 100, 6)
            bar = QLinearGradient(fill.topLeft(), fill.topRight())
            bar.setColorAt(0, BLUE)
            bar.setColorAt(1, ORANGE)
            p.setBrush(bar)
            p.drawRoundedRect(fill, 3, 3)

        # Footer
        fy = self.H - 22
        p.setFont(self.f_small)
        p.setPen(TEXT_MUTED)
        p.drawText(QPointF(x0, fy), f"© 2026 {COMPANY} All rights reserved.")
        p.setFont(self.f_value)
        p.setPen(TEXT_DIM)
        v = f"Version {self.version}"
        p.drawText(QPointF(x1 - p.fontMetrics().horizontalAdvance(v), fy), v)

    # ---- helpers ---------------------------------------------------------
    def _draw_hex_grid(self, p: QPainter) -> None:
        p.setPen(QPen(QColor(95, 143, 214, 30), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        w, h = 64.0, 55.4
        hexagon = QPolygonF([QPointF(32, 0), QPointF(64, 13.85), QPointF(64, 41.55),
                             QPointF(32, 55.4), QPointF(0, 41.55), QPointF(0, 13.85)])
        y = -h
        while y < self.H + h:
            x = -w
            while x < self.W + w:
                p.drawPolygon(hexagon.translated(x, y))
                x += w
            y += h

    @staticmethod
    def _draw_spaced(p: QPainter, x: float, y: float, text: str, spacing: float) -> None:
        fm = p.fontMetrics()
        for ch in text:
            p.drawText(QPointF(x, y), ch)
            x += fm.horizontalAdvance(ch) + spacing

    @staticmethod
    def _spaced_width(fm, text: str, spacing: float) -> float:
        return sum(fm.horizontalAdvance(ch) + spacing for ch in text) - spacing

    def _tick(self) -> None:
        self._glow = 0.5 + 0.5 * math.sin(time.monotonic() * 1.6)
        self.update()


if __name__ == "__main__":  # quick demo
    import sys
    from PyQt6.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)
    splash = FireProSplash(version="1.0.0")
    splash.show()

    steps = [(15, "Loading preferences…"), (35, "Initializing Graphics View scene…"),
             (62, "Loading hydraulic calculation module…"), (85, "Loading sprinkler catalog…"),
             (100, "Ready")]
    win = QMainWindow()
    win.setWindowTitle("FirePro 3D")
    win.resize(1200, 800)

    def advance(i=0):
        if i < len(steps):
            splash.set_progress(*steps[i])
            QTimer.singleShot(600, lambda: advance(i + 1))
        else:
            win.show()
            splash.finish(win)

    QTimer.singleShot(300, advance)
    sys.exit(app.exec())
