"""Fidelity gate: render the final Blocks-group icons through the REAL loader
(icons.themed_icon -> token substitution -> QSvgRenderer) at 54/27 px on both
theme swatches, composed into one PNG. This is what actually ships, not a browser
approximation. Run: venv/Scripts/python.exe tools/render_block_icons.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage, QPainter, QColor
from PyQt6.QtCore import QSize

from firepro3d import icons

NAMES = ["make_block_icon.svg", "insert_block_icon.svg", "block_manager_icon.svg"]
DARK_BG, LIGHT_BG = "#2b2b2b", "#f0f0f0"


def main():
    _ = QApplication([])
    icons._cache.clear()
    # cols: (size, theme, bg)
    cols = [(54, icons.DARK, DARK_BG), (27, icons.DARK, DARK_BG),
            (54, icons.LIGHT, LIGHT_BG), (27, icons.LIGHT, LIGHT_BG)]
    cell, gap = 72, 10
    W = len(cols) * cell + (len(cols) + 1) * gap
    H = len(NAMES) * cell + (len(NAMES) + 1) * gap
    canvas = QImage(W, H, QImage.Format.Format_ARGB32)
    canvas.fill(QColor("#565656"))
    cp = QPainter(canvas)
    for ri, name in enumerate(NAMES):
        for ci, (size, theme, bg) in enumerate(cols):
            pm = icons.themed_icon(name, theme).pixmap(QSize(size, size))
            x = gap + ci * (cell + gap)
            y = gap + ri * (cell + gap)
            cp.fillRect(x, y, cell, cell, QColor(bg))
            cp.drawPixmap(x + (cell - size) // 2, y + (cell - size) // 2, pm)
    cp.end()
    out = os.path.join(os.path.dirname(__file__), "block_icons_final.png")
    canvas.save(out)
    print(out)


if __name__ == "__main__":
    main()
