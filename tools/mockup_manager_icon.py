"""Throwaway harness: render Underlay Manager icon candidates for the mockup gate.

Renders the import-icon reference, the current manager icon, and 3 candidates
(each harmonised into the import stacked-layer family with a different 'manage'
affordance) at 48px + 28px on dark and light swatches, composed into one grid PNG.

No text labels (offscreen QPA renders text as tofu) — row order is described by
the caller. Run:  venv/Scripts/python.exe tools/mockup_manager_icon.py
"""
import os
import math
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage, QPainter, QColor
from PyQt6.QtCore import QByteArray, QRectF
from PyQt6.QtSvg import QSvgRenderer


def _gear_ticks(cx, cy, r_in, r_out, n, accent):
    parts = []
    for i in range(n):
        a = (2 * math.pi * i) / n
        x1, y1 = cx + r_in * math.cos(a), cy + r_in * math.sin(a)
        x2, y2 = cx + r_out * math.cos(a), cy + r_out * math.sin(a)
        parts.append(f'<path stroke="{accent}" d="M{x1:.1f} {y1:.1f} L{x2:.1f} {y2:.1f}"/>')
    return "\n".join(parts)


def svg_import_ref(primary, accent):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none"
     stroke="{primary}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path fill="{accent}" stroke="{accent}" d="M24 8 L40 17 L24 26 L8 17 Z"/>
  <path d="M8 24 L24 33 L40 24"/>
  <path d="M8 31 L24 40 L40 31"/>
</svg>'''


def svg_current(primary, accent):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none"
     stroke="{primary}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M24 8 L39 16 L24 24 L9 16 Z"/>
  <path d="M9 23 L24 31 L39 23"/>
  <path stroke="{accent}" d="M12 39 H36"/>
  <circle cx="28" cy="39" r="3" fill="{accent}" stroke="none"/>
</svg>'''


# Candidate A — "accent sliders": 3 neutral stacked layers (import family) + an
# accent slider/handle beneath (manage = adjust). Keeps ONE accent element.
def svg_cand_sliders(primary, accent):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none"
     stroke="{primary}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M24 6 L38 14 L24 22 L10 14 Z"/>
  <path d="M10 21 L24 29 L38 21"/>
  <path d="M10 28 L24 36 L38 28"/>
  <path stroke="{accent}" d="M11 42 H37"/>
  <circle cx="30" cy="42" r="2.8" fill="{accent}" stroke="none"/>
</svg>'''


# Candidate B — "accent top + list dots": import's exact accent-solid-top stack
# (keeps the import identity) + three accent dots below (manage = list/roster).
def svg_cand_dots(primary, accent):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none"
     stroke="{primary}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path fill="{accent}" stroke="{accent}" d="M24 6 L38 14 L24 22 L10 14 Z"/>
  <path d="M10 21 L24 29 L38 21"/>
  <path d="M10 28 L24 36 L38 28"/>
  <circle cx="16" cy="42" r="1.9" fill="{accent}" stroke="none"/>
  <circle cx="24" cy="42" r="1.9" fill="{accent}" stroke="none"/>
  <circle cx="32" cy="42" r="1.9" fill="{accent}" stroke="none"/>
</svg>'''


# Candidate C — "accent gear": 3 neutral stacked layers + an accent cog at the
# bottom-right (manage = settings). Accent lives in the control, like the import
# icon's accent lives in its top layer.
def svg_cand_gear(primary, accent):
    ticks = _gear_ticks(32, 39, 3.4, 5.2, 8, accent)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none"
     stroke="{primary}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M22 6 L36 13 L22 20 L8 13 Z"/>
  <path d="M8 20 L22 27 L36 20"/>
  <path d="M8 27 L22 34 L36 27"/>
  {ticks}
  <circle cx="32" cy="39" r="3.4" stroke="{accent}"/>
  <circle cx="32" cy="39" r="0.9" fill="{accent}" stroke="none"/>
</svg>'''


def render(svg_str, size, bg):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor(bg))
    r = QSvgRenderer(QByteArray(svg_str.encode("utf-8")))
    p = QPainter(img)
    pad = size * 0.10
    r.render(p, QRectF(pad, pad, size - 2 * pad, size - 2 * pad))
    p.end()
    return img


def main():
    _ = QApplication([])
    DARK_BG, LIGHT_BG = "#2b2b2b", "#f0f0f0"
    DARK_PRIMARY, DARK_ACCENT = "#dcdcdc", "#63BE8B"
    LIGHT_PRIMARY, LIGHT_ACCENT = "#3a3a3a", "#2f9e63"

    rows = [svg_import_ref, svg_current, svg_cand_sliders, svg_cand_dots, svg_cand_gear]
    # columns: (size, bg, primary, accent)
    cols = [
        (48, DARK_BG, DARK_PRIMARY, DARK_ACCENT),
        (28, DARK_BG, DARK_PRIMARY, DARK_ACCENT),
        (48, LIGHT_BG, LIGHT_PRIMARY, LIGHT_ACCENT),
        (28, LIGHT_BG, LIGHT_PRIMARY, LIGHT_ACCENT),
    ]
    cell = 72
    gap = 10
    W = len(cols) * cell + (len(cols) + 1) * gap
    H = len(rows) * cell + (len(rows) + 1) * gap
    canvas = QImage(W, H, QImage.Format.Format_ARGB32)
    canvas.fill(QColor("#565656"))
    cp = QPainter(canvas)
    for ri, svg_fn in enumerate(rows):
        for ci, (size, bg, primary, accent) in enumerate(cols):
            icon = render(svg_fn(primary, accent), size, bg)
            x = gap + ci * (cell + gap)
            y = gap + ri * (cell + gap)
            # swatch background behind the icon so dark/light is visible
            cp.fillRect(x, y, cell, cell, QColor(bg))
            ox = x + (cell - size) // 2
            oy = y + (cell - size) // 2
            cp.drawImage(ox, oy, icon)
    cp.end()
    out = os.path.join(os.path.dirname(__file__), "_manager_icon_candidates.png")
    canvas.save(out)
    print(out)


if __name__ == "__main__":
    main()
