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


# -- I1: the glyph is inside the item's bounds; tooltip names the id ----------

_TIP = "Missing linetype: deadbeef \u2014 drawn Continuous"


def _warn_px(ms, src, w, h):
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, w, h), src)
    p.end()
    return sum(_is_warn(QColor(img.pixel(x, y))) for x in range(w) for y in range(h))


def test_block_badge_renders_when_only_the_insertion_point_is_exposed(qapp):
    """Geometry 1000..3000 mm, insertion at 0: an expose of just the insertion
    point still paints the glyph (it is inside boundingRect at this zoom)."""
    from tests._snap_polish_helpers import close_view, make_view
    view, ms = make_view(role="plan", scale=0.1, mode=None)
    try:
        ln = LineItem(QPointF(1000, 0), QPointF(3000, 0))
        ln.style["linetype"] = "deadbeef"
        d = BlockDefinition.new(name="B", library="L", series="S",
                                primitives=[ln.to_dict()], origin=(0.0, 0.0))
        ms.register_block_definition(d)
        inst = ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
        assert _warn_px(ms, QRectF(-400, -400, 800, 800), 80, 80) > 10
        # The glyph's device box (+/-7 px x, -7/+5 px y) at 0.1 px/mm.
        glyph = QRectF(-70, -70, 140, 120)
        assert inst.sceneBoundingRect().contains(glyph)
    finally:
        close_view(view, ms)


def test_raw_badge_inside_bounds_on_a_short_vertical_stroke(qapp):
    from tests._snap_polish_helpers import close_view, make_view
    view, ms = make_view(role="block_editor", scale=1.0, mode=None)
    try:
        ln = LineItem(QPointF(0, 0), QPointF(0, 20))
        ln.style["linetype"] = "deadbeef"
        ms.addItem(ln)
        ms._draw_lines.append(ln)
        # Badge at mid-length (0, 10); its left part lies at x < -3 mm, outside
        # the pen pad -- an expose of that strip alone must still paint it.
        assert _warn_px(ms, QRectF(-20, -10, 17, 40), 17, 40) > 0
        assert ln.sceneBoundingRect().contains(QRectF(-7, 3, 14, 12))
    finally:
        close_view(view, ms)


def test_missing_tooltip_names_the_id_and_restores(qapp):
    from tests.lt3_support import hidden
    ms = Model_Space(scene_role="block_editor")
    ln = LineItem(QPointF(0, 0), QPointF(36, 0))
    ln.setToolTip("orig")
    ln.style["linetype"] = "deadbeef"
    ms.addItem(ln)
    _warn_px(ms, QRectF(0, -6, 40, 12), 40, 12)          # paint
    assert ln.toolTip() == _TIP
    ln.style["linetype"] = hidden(ms)                    # resolves now
    _warn_px(ms, QRectF(0, -6, 40, 12), 40, 12)
    assert ln.toolTip() == "orig"


def test_block_missing_tooltip(qapp):
    ms = _missing_block_scene()
    inst = ms._block_instances[0]
    _warn_px(ms, QRectF(-2000, -2000, 4000, 4000), 40, 40)
    assert inst.toolTip() == _TIP
