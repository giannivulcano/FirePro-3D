"""tests/test_geo2d_fill_opacity.py

Per-layer fill opacity on the two-layer shape fill (UP1; legacy default 45%).

The pre-UP1 solid-only "Fill Opacity" string row is retired (design R13-R15):
opacity is a field of each layer, edited through the "Fill" / "Fill Pattern"
fill rows. Tests:
  1. A new shape has no fill; a legacy record without an opacity key reads 0.45.
  2. The retired "Fill Opacity" row never appears; the two fill rows do (and
     only on fillable shapes).
  3. Writing a layer through the "Fill" row stores its opacity fraction.
  4. The painted alpha is int(round(opacity * 255)) (spy on the renderer call).
  5. Higher opacity renders more opaque.
  6. Round-trip: the layer opacity survives to_dict / from_dict.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QImage, QPainter, QColor
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.fill_layers import (BackgroundLayer, FillLayers, PatternLayer,
                                   from_record)
from firepro3d.geometry_2d import RectangleItem, CircleItem, LineItem


def _pixel(img: QImage, x: int, y: int) -> QColor:
    return QColor(img.pixel(x, y))


# 1. Defaults

def test_new_shape_has_no_fill(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    assert r.fill_layers.is_empty


def test_new_circle_has_no_fill(qapp):
    c = CircleItem(QPointF(50, 50), 40.0)
    assert c.fill_layers.is_empty


def test_legacy_record_without_opacity_reads_045():
    """A legacy fill block without an 'opacity' key keeps the old 0.45 look."""
    fl = from_record({"type": "solid", "color": "#deadbe"})
    assert fl.background == BackgroundLayer("#deadbe", pytest.approx(0.45))


# 2. Rows

def test_retired_opacity_row_never_appears(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    for layers in (FillLayers(), FillLayers(background=BackgroundLayer("#112233")),
                   FillLayers(pattern=PatternLayer("builtin-hatch-diagonal"))):
        r.fill_layers = layers
        props = r.get_properties()
        assert "Fill Opacity" not in props
        assert props["Fill"]["type"] == "fill" and props["Fill Pattern"]["type"] == "fill"


def test_fill_rows_absent_for_non_fillable(qapp):
    """LineItem (not fillable) exposes no fill rows."""
    props = LineItem(QPointF(0, 0), QPointF(100, 0)).get_properties()
    assert "Fill Opacity" not in props
    assert "Fill" not in props and "Fill Pattern" not in props


# 3. Writing a layer stores its opacity

@pytest.mark.parametrize("opacity", [0.0, 0.8, 1.0])
def test_fill_row_write_stores_opacity(qapp, opacity):
    scene = QGraphicsScene()
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    scene.addItem(r)
    r.set_property("Fill", BackgroundLayer("#0000ff", opacity))
    assert r.fill_layers.background.opacity == pytest.approx(opacity)


def test_pattern_row_write_stores_opacity(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.set_property("Fill Pattern", PatternLayer("builtin-hatch-diagonal", "#00ff00", 0.6, 1.0))
    assert r.fill_layers.pattern.opacity == pytest.approx(0.6)


# 4 / 5. Render

def _luminosity(c: QColor) -> int:
    """Approximate luminosity (0=black, 255=white)."""
    return (c.red() * 299 + c.green() * 587 + c.blue() * 114) // 1000


def _render_rect_at_opacity(opacity: float) -> QColor:
    scene = QGraphicsScene()
    r = RectangleItem(QPointF(10, 10), QPointF(110, 110))
    r.fill_layers = FillLayers(background=BackgroundLayer("#0000ff", opacity))
    scene.addItem(r)
    img = QImage(120, 120, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, 120, 120), QRectF(0, 0, 120, 120))
    p.end()
    return _pixel(img, 60, 60)


def test_higher_opacity_renders_more_opaque(qapp):
    """Pure blue on white: higher alpha -> less white bleed -> lower luminosity."""
    lum_80 = _luminosity(_render_rect_at_opacity(0.80))
    lum_30 = _luminosity(_render_rect_at_opacity(0.30))
    assert lum_80 < lum_30, (
        f"0.8 opacity (lum={lum_80}) should be darker than 0.3 opacity (lum={lum_30})")


def test_background_alpha_is_rounded_opacity_times_255(qapp, monkeypatch):
    """The background colour handed to the renderer carries
    int(round(opacity * 255)) = 153 for opacity 0.60."""
    import firepro3d.hatch_render as hr

    captured: list[int] = []
    real = hr.paint_fill

    def spy(painter, clip, **kw):
        if kw.get("background") is not None:
            captured.append(kw["background"].alpha())
        return real(painter, clip, **kw)

    monkeypatch.setattr(hr, "paint_fill", spy)
    _render_rect_at_opacity(0.60)
    assert captured, "paint_fill was never called with a background"
    assert captured[0] == int(round(0.60 * 255))


# 6. Serialisation round-trip

def test_to_dict_includes_opacity_for_background(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.fill_layers = FillLayers(background=BackgroundLayer("#112233", 0.70))
    d = r.to_dict()
    assert d["fill"]["background"]["opacity"] == pytest.approx(0.70)


def test_from_dict_restores_opacity(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.fill_layers = FillLayers(background=BackgroundLayer("#aabbcc", 0.80))
    r2 = RectangleItem.from_dict(r.to_dict())
    assert r2.fill_layers.background.opacity == pytest.approx(0.80)


def test_from_dict_legacy_missing_opacity_defaults_to_045(qapp):
    """A legacy solid fill block without an 'opacity' key loads at 0.45."""
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    d = r.to_dict()
    d["fill"] = {"type": "solid", "color": "#deadbe"}
    r2 = RectangleItem.from_dict(d)
    assert r2.fill_layers.background.opacity == pytest.approx(0.45)


def test_fill_omitted_when_both_layers_off(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    assert "fill" not in r.to_dict()


def test_to_dict_includes_opacity_for_pattern(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.fill_layers = FillLayers(pattern=PatternLayer("builtin-hatch-diagonal", "#336699", 0.60, 1.0))
    d = r.to_dict()
    assert d["fill"]["pattern"]["opacity"] == pytest.approx(0.60)
