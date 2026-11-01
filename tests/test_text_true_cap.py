"""T-L96 (text-sizing-wrap D1 / AC1): model and Block-Editor text draws its
true cap height, with glyph advances that are not quantized to whole pixels.

Ground truth is rendered pixels: the TextItem is painted through its own
``paint()`` (the model-surface glyph-outline path the canvas uses) into a
QImage on the NATIVE platform -- the offscreen platform has no real fonts.
The ink height of an "H" is the drawn cap; the ink-span difference of eleven
"m" vs one "m" is ten 'm' advances. The ideal advance comes from Arial's own
metrics at the 1000 px reference size, never from the module under test.
The render scale (zoom) is parametrized so the cap spans 150 or 300 px
(1 px <= 0.7 % of it); the defect lives in scene geometry, so every zoom shows it.
"""
import numpy as np
import pytest
from PyQt6.QtGui import (
    QColor, QFont, QFontMetricsF, QGuiApplication, QImage, QPainter, QTransform,
)
from PyQt6.QtWidgets import QStyleOptionGraphicsItem

from firepro3d.model_space import Model_Space
from firepro3d.text_item import TextAnnotationData, TextItem

_ZOOMS = (150.0, 300.0)   # rendered cap span in px (the render scale per height)
_REF_PX = 1000      # Arial metric reference pixel size (raw font metric)
_ROLES = ("plan", "block_editor")


def _native_platform():
    assert QGuiApplication.platformName() != "offscreen", (
        "T-L96 needs the native platform's real fonts; unset QT_QPA_PLATFORM")


def _ink_mm(text: str, h: float, role: str, cap_px: float) -> tuple[float, float]:
    """(ink height, ink width) in scene mm of *text* at cap *h* on a *role*
    scene, rendered so the cap spans *cap_px* image px."""
    sc = Model_Space(scene_role=role)
    d = TextAnnotationData(text=text, height_mm=h, font_family="Arial", color="#000000")
    d.cell_padding_mm = 0.0
    it = TextItem(d)
    sc.addItem(it)
    ppm = cap_px / h
    br = it.sceneBoundingRect()
    w = int(br.width() * ppm) + 20
    hh = int(br.height() * ppm) + 20
    img = QImage(w, hh, QImage.Format.Format_RGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    world = QTransform()
    world.translate(10, 10)
    world.scale(ppm, ppm)
    world.translate(-br.left(), -br.top())
    p.setTransform(it.sceneTransform() * world)
    it.paint(p, QStyleOptionGraphicsItem(), None)
    p.end()
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    arr = np.frombuffer(ptr, np.uint8).reshape(hh, img.bytesPerLine())
    red = arr[:, : w * 4].reshape(hh, w, 4)[:, :, 2]
    ys, xs = np.nonzero(red < 128)
    assert ys.size, f"no ink for {text!r} at {h} mm"
    return ((ys.max() - ys.min() + 1) / ppm, (xs.max() - xs.min() + 1) / ppm)


def _ideal_m_advance_mm(h: float) -> float:
    f = QFont("Arial")
    f.setPixelSize(_REF_PX)
    fm = QFontMetricsF(f)
    return fm.horizontalAdvance("m") * h / fm.capHeight()


@pytest.mark.parametrize("cap_px", _ZOOMS)
@pytest.mark.parametrize("role", _ROLES)
@pytest.mark.parametrize("h", [2.0, 3.0, 100.0])
def test_drawn_cap_is_the_height(qapp, h, role, cap_px):
    _native_platform()
    cap, _w = _ink_mm("H", h, role, cap_px)
    assert cap == pytest.approx(h, rel=0.01), f"drawn cap {cap:.4f} mm for {h} mm text"


@pytest.mark.parametrize("cap_px", _ZOOMS)
@pytest.mark.parametrize("role", _ROLES)
@pytest.mark.parametrize("h", [2.0, 3.0])
def test_m_advance_is_the_font_advance(qapp, h, role, cap_px):
    _native_platform()
    _c, w1 = _ink_mm("m", h, role, cap_px)
    _c, w11 = _ink_mm("m" * 11, h, role, cap_px)
    adv = (w11 - w1) / 10.0
    ideal = _ideal_m_advance_mm(h)
    assert adv == pytest.approx(ideal, rel=0.02), f"'m' advance {adv:.4f} mm, ideal {ideal:.4f}"


@pytest.mark.parametrize("name", ["RoomTag", "PipeLabel"])
def test_shipped_tag_seed_sizes_unchanged(name):
    """AC4 / G9 parity pin: the L96 fix moves no authored size -- every text in
    the shipped System tag keeps its 3 mm cap and 1 mm padding."""
    import json
    from pathlib import Path
    import firepro3d
    path = Path(firepro3d.__file__).parent / "system_blocks" / "Tags" / f"{name}.fpdb"
    prims = json.loads(path.read_text(encoding="utf-8"))["primitives"]
    texts = [p for p in prims if p.get("type") == "text"]
    assert texts
    assert all(p["height_mm"] == 3.0 and p["cell_padding_mm"] == 1.0 for p in texts)
