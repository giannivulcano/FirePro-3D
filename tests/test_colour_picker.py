"""House colour picker (todo #70) — dialog behaviour, recents, glyph, themes.

Drives real widgets (QTest mouse/key events), asserts observable results."""
import pytest
from PyQt6.QtCore import Qt, QRectF, QPoint
from PyQt6.QtGui import QImage, QPainter, QColor
from PyQt6.QtTest import QTest


def _render_glyph(w=22, h=22):
    from firepro3d.ui_kit import paint_no_fill
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor("#00ff00"))             # sentinel ground: must be fully covered
    p = QPainter(img)
    paint_no_fill(p, QRectF(0, 0, w, h), 0)
    p.end()
    return img


def test_no_fill_glyph_white_with_red_diagonal(qapp):
    img = _render_glyph()
    # corner off the diagonal (top-left) is white
    assert QColor(img.pixel(2, 2)).name() == "#ffffff"
    # centre sits on the bottom-left -> top-right slash: strongly red
    c = QColor(img.pixel(11, 11))
    assert c.red() > 180 and c.green() < 110 and c.blue() < 110


def test_chip_paints_no_fill_when_empty(qapp):
    from firepro3d.ui_kit import _Chip
    chip = _Chip("")
    chip.resize(chip.size())
    img = chip.grab().toImage()
    cx, cy = img.width() // 2, img.height() // 2
    c = QColor(img.pixel(cx, cy))
    assert c.red() > 180 and c.green() < 110     # red slash through the centre
    assert QColor.fromRgba(img.pixel(3, 3)).alpha() == 255     # glyph fully covers the chip (not transparent)


def test_colour_metric_tokens_match_mockup():
    from firepro3d.theme import M
    assert (M.COLOUR_DLG_W, M.COLOUR_SV_W, M.COLOUR_SV_H, M.COLOUR_HUE_W) == (440, 210, 170, 16)
    assert (M.COLOUR_COL_GAP, M.COLOUR_CHIP, M.COLOUR_CHIP_GAP, M.COLOUR_CHIP_RADIUS) == (16, 22, 4, 3)
    assert (M.COLOUR_SEL_RING, M.COLOUR_SEC_GAP, M.COLOUR_PREVIEW_H) == (2, 12, 40)


def test_palette_is_fixed_cad_set():
    from firepro3d import colour_picker as cp
    assert cp.STANDARD == ("#FF0000", "#FF7F00", "#FFFF00", "#00FF00", "#00FFFF",
                           "#0000FF", "#FF00FF", "#808080", "#C0C0C0", "#FFFFFF")
    assert cp.GREYS == ("#000000", "#1C1C1C", "#393939", "#555555", "#717171",
                        "#8E8E8E", "#AAAAAA", "#C6C6C6", "#E3E3E3", "#FFFFFF")
    assert cp.NO_FILL == ""


def test_recents_mru_dedupe_cap_and_persist(qapp):
    from firepro3d import colour_picker as cp
    cp.clear_recents()
    for h in ["#111111", "#222222", "#111111"]:
        cp.push_recent(h)
    assert cp.load_recents() == ["#111111", "#222222"]     # MRU first, deduped
    cp.push_recent("#abcdef")
    assert cp.load_recents()[0] == "#ABCDEF"               # normalised upper
    cp.push_recent("#AbCdEf")
    assert cp.load_recents().count("#ABCDEF") == 1          # case-insensitive dedupe
    for i in range(20):
        cp.push_recent(f"#0000{i:02X}")
    assert len(cp.load_recents()) == cp.RECENTS_MAX == 10
    cp.push_recent("")                                      # No Fill is never recorded
    assert "" not in cp.load_recents()
