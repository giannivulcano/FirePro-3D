"""G11 -- a missing linetype draws Continuous + a canvas-only badge."""
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d import theme
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _is_warn(c):
    warn = QColor(theme.detect().warn)
    return (abs(c.red() - warn.red()) < 40 and abs(c.green() - warn.green()) < 40
            and abs(c.blue() - warn.blue()) < 40)


def _amber_fills(pdf):
    import fitz
    doc = fitz.open(str(pdf))
    try:
        return [x for x in doc[0].get_drawings() if "f" in (x.get("type") or "")
                and x.get("fill") and x["fill"][0] > 0.6 and x["fill"][2] < 0.5]
    finally:
        doc.close()


def test_missing_linetype_solid_plus_badge_on_canvas(qapp):
    ms = Model_Space(scene_role="block_editor")
    ln = LineItem(QPointF(0, 0), QPointF(36, 0))
    ln.style["linetype"] = "deadbeef"
    ms.addItem(ln)
    img = QImage(400, 120, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, 400, 120), QRectF(0, -6, 40, 12))
    p.end()
    row = [QColor(img.pixel(x, 60)).lightness() > 128 for x in range(400)]
    # The line spans 0..360 px; the badge sits at mid-length (180 px).
    assert all(row[5:150]) and all(row[250:355])        # solid away from the badge
    near = [QColor(img.pixel(x, y)) for x in range(170, 230) for y in range(40, 80)]
    assert any(_is_warn(c) for c in near)
    far = [QColor(img.pixel(x, y)) for x in range(400) for y in range(120)
           if abs(x - 180) > 20 or abs(y - 60) > 20]
    assert not any(_is_warn(c) for c in far)             # one badge, at mid-length


def _missing_block_scene(at=(0.0, 0.0)):
    ms = Model_Space()
    ln = LineItem(QPointF(-1500, 0), QPointF(1500, 0))
    ln.style["linetype"] = "deadbeef"
    d = BlockDefinition.new(name="B", library="L", series="S",
                            primitives=[ln.to_dict()], origin=(0.0, 0.0))
    ms.register_block_definition(d)
    ms.place_block_instance(d.id, at, level=ms.active_level)
    return ms


def test_placed_block_missing_badge_at_insertion_point(qapp):
    ms = _missing_block_scene(at=(1000.0, 500.0))
    img = QImage(400, 400, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, 400, 400), QRectF(-2000, -2000, 4000, 4000))
    p.end()
    # Insertion (1000, 500) mm -> (300, 250) px at 0.1 px/mm.
    near = [QColor(img.pixel(x, y)) for x in range(285, 315) for y in range(235, 265)]
    assert any(_is_warn(c) for c in near)
    far = [QColor(img.pixel(x, y)) for x in range(400) for y in range(400)
           if abs(x - 300) > 20 or abs(y - 250) > 20]
    assert not any(_is_warn(c) for c in far)             # once, at the insertion
    row = [QColor(img.pixel(x, 250)).lightness() > 128 for x in range(400)]
    assert all(row[160:280])                              # solid (Continuous)


def test_missing_badge_never_plots(qapp, tmp_path):
    from tests.test_lt1_block_paper import _export
    pdf = _export(tmp_path, _missing_block_scene(), 0.02, "g11.pdf")
    assert _amber_fills(pdf) == []                       # no amber glyph on paper


def test_missing_raw_primitive_badge_never_plots(qapp, tmp_path):
    from tests.test_lt1_block_paper import _export
    ms = Model_Space()
    ln = LineItem(QPointF(-1500, 0), QPointF(1500, 0))
    ln.style["linetype"] = "deadbeef"
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    pdf = _export(tmp_path, ms, 0.02, "g11raw.pdf")
    assert _amber_fills(pdf) == []


@pytest.mark.xfail(strict=True, reason="Task 13")
def test_panel_shows_missing(qapp):
    ms = Model_Space(scene_role="block_editor")
    ln = LineItem(QPointF(0, 0), QPointF(36, 0))
    ln.style["linetype"] = "deadbeef"
    ms.addItem(ln)
    assert ln.get_properties()["Linetype"]["value"] == "Missing (deadbeef)"
