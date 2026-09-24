"""Task 6 fold-ins: elevation bubble-label HALO resolve + band colour tokens.

(1) ``ElevationScene._halo_resolve`` walked only ONE parent level, so a
bubble's ``QGraphicsTextItem`` label (a grandchild of the gridline/datum)
never resolved to its owner and was dropped as a HALO candidate. Walk the
full parent chain instead.

(2) The scene-drawn rubber band reused the ``selection``/``ok`` tokens for
window/crossing; both read green in the dark theme. Add dedicated
``band_window`` (blue, alias of ``selection_hover``) / ``band_crossing``
(green, alias of ``ok``) semantic tokens.
"""
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QImage, QPainter, QTransform

from firepro3d import theme as th
from firepro3d.elevation_scene import ElevGridlineItem
from firepro3d.halo import paint_rubber_band


def _grid():
    return ElevGridlineItem(100.0, -50.0, 50.0, "A", 20.0,
                            QColor("#888"), QColor("#fff"), 1.0)


# ── (1) bubble label resolve ────────────────────────────────────────────────

def test_bubble_label_grandchild_resolves_to_gridline(qapp, elevation_scene_for):
    _ms, elev = elevation_scene_for("north")
    g = _grid()
    elev.addItem(g)
    label = g.bubble1._label                     # QGraphicsTextItem in the bubble
    assert elev._halo_resolve(label) is g


def test_bubble_label_hover_lights_gridline(qapp, elevation_scene_for):
    """Hovering the label text (via halo_update) resolves the gridline as the
    HALO-highlighted item, not just the identity-resolve unit above."""
    _ms, elev = elevation_scene_for("north")
    g = _grid()
    elev.addItem(g)
    label = g.bubble1._label
    center = label.mapToScene(label.boundingRect().center())
    dt = QTransform()  # identity: 1 scene unit == 1 px
    elev.halo_update(center, 15.0, dt)
    assert elev.halo_item() is g


# ── (2) band colour tokens ──────────────────────────────────────────────────

def test_band_tokens_are_distinct_in_both_themes():
    for t in (th.DARK, th.LIGHT):
        w, c = t.color("band_window"), t.color("band_crossing")
        assert w.isValid() and c.isValid() and w != c
    assert th.DARK.color("band_window") != th.DARK.color("selection")


def test_band_window_aliases_selection_hover():
    for t in (th.DARK, th.LIGHT):
        assert t.band_window == t.selection_hover


def test_band_crossing_aliases_ok():
    for t in (th.DARK, th.LIGHT):
        assert t.band_crossing == t.ok


def _render_band(rb_start, rb_end):
    img = QImage(200, 200, QImage.Format.Format_ARGB32)
    img.fill(0)
    painter = QPainter(img)
    paint_rubber_band(painter, None, QPointF(*rb_start), QPointF(*rb_end), th.DARK)
    painter.end()
    return img


def test_window_and_crossing_bands_paint_distinct_hues(qapp):
    # L->R = window (solid, band_window/blue); R->L = crossing (dashed, band_crossing/green).
    window_img = _render_band((20, 20), (150, 150))
    crossing_img = _render_band((150, 20), (20, 150))

    expected_window = QColor(th.DARK.band_window)
    expected_crossing = QColor(th.DARK.band_crossing)

    # Sample an interior pixel (the alpha fill, not the dash-patterned border
    # stroke, so the sample isn't flaky on a dash gap). The fill is the base
    # colour at alpha 40 painted over a transparent backdrop, so the sampled
    # RGB should equal the base colour.
    window_px = QColor(window_img.pixel(85, 85))
    crossing_px = QColor(crossing_img.pixel(85, 85))

    assert window_px != crossing_px
    assert abs(window_px.red() - expected_window.red()) < 20
    assert abs(window_px.green() - expected_window.green()) < 20
    assert abs(window_px.blue() - expected_window.blue()) < 20
    assert abs(crossing_px.red() - expected_crossing.red()) < 20
    assert abs(crossing_px.green() - expected_crossing.green()) < 20
    assert abs(crossing_px.blue() - expected_crossing.blue()) < 20
