"""LT3-9 / G-tile: strokes stamped from a pattern tile stay Continuous.

``hatch_render._tile_paths`` merges the tile's op paths under one pattern pen
and never calls the linetype expander, so a tile primitive carrying a Hidden
linetype must still stamp as one unbroken line. Composition check: the same
primitive drawn RAW in the same scene IS dashed, so the scenario could show
dashes. No-change regression guard: green at base by design.
"""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import hidden

TILE = 2000.0        # mm; Hidden period on the plan canvas is 9 x 100 = 900 mm
PX = 0.2             # px per mm -> period 180 px, gap 60 px, tile 400 px
W, H = 1400, 1200
X0, Y0 = -500.0, -2000.0   # scene mm at the image's top-left
RAW_Y = 2800.0      # scene mm: the raw (non-tile) line, below the filled rect


def _scene():
    ms = Model_Space()
    lid = hidden(ms)
    ln = LineItem(QPointF(0, -TILE / 2), QPointF(TILE, -TILE / 2))
    ln.style["linetype"] = lid
    tile = BlockDefinition.new(
        name="HiddenTile", library="L", series="S", origin=(0.0, 0.0),
        primitives=[ln.to_dict()],
        tile={"w": TILE, "h": TILE, "row_shift": 0.0, "size": "model"})
    ms.register_block_definition(tile)
    r = RectangleItem(QPointF(0, 0), QPointF(3 * TILE, TILE))
    r.fill_type, r.fill_pattern = "hatch", tile.id
    r._display_fill_color, r.fill_opacity = "#ff0000", 1.0
    host = BlockDefinition.new(name="Host", library="L", series="S",
                               primitives=[r.to_dict()], origin=(0.0, 0.0))
    ms.register_block_definition(host)
    ms.place_block_instance(host.id, (0.0, 0.0))
    raw = LineItem(QPointF(0, RAW_Y), QPointF(3 * TILE, RAW_Y))
    raw.style["linetype"] = lid
    ms.addItem(raw)
    return ms


def _render(ms):
    img = QImage(W, H, QImage.Format.Format_RGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, W, H), QRectF(X0, Y0, W / PX, H / PX))
    p.end()
    return img


def _ink_run(img, y_mm, x0_px, x1_px):
    """Per-column ink flags over a 3 px band around scene y (mm)."""
    yc = round((y_mm - Y0) * PX)
    out = []
    for x in range(x0_px, x1_px):
        out.append(any(max(QColor(img.pixel(x, y)).getRgb()[:3]) > 100
                       for y in range(yc - 1, yc + 2)))
    return out


def _gaps(flags):
    """Count unlit runs strictly inside the first..last lit column."""
    lit = [i for i, f in enumerate(flags) if f]
    if not lit:
        return None
    return sum(1 for f in flags[lit[0]:lit[-1] + 1] if not f)


def test_g_tile_stamped_stroke_is_continuous_and_raw_is_dashed(qapp):
    ms = _scene()
    img = _render(ms)
    x0, x1 = round((0 - X0) * PX) + 5, round((3 * TILE - X0) * PX) - 5
    tile_row = _ink_run(img, TILE / 2, x0, x1)          # stamped, mid-rect
    raw_row = _ink_run(img, RAW_Y, x0, x1)           # same linetype, raw
    # Composition: the raw line shows Hidden gaps (>= 40 px of the 75 px gap).
    assert _gaps(raw_row) is not None and _gaps(raw_row) >= 40
    # Guard: across all three tile widths (1500 px) the stamped line has no gap.
    assert sum(tile_row) > 0.95 * len(tile_row)
    assert _gaps(tile_row) == 0
