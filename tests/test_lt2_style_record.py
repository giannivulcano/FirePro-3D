"""LT2-1 / LT2-2 / H-a / H-b -- the stroke style record (stroke_style.py)."""
import copy

import pytest

from firepro3d import stroke_style as ss


def test_default_style_is_continuous_by_linetype():
    # WM-10 (retired LT2-1 "By Block" default): Continuous / By Linetype.
    st = ss.default_style("#ff0000")
    assert st == {
        "linetype": "continuous", "weight": "by_linetype",
        "start": {"end": "by_linetype", "visible": True},
        "finish": {"end": "by_linetype", "visible": True},
        "colour": "#ff0000",
    }


def test_normalize_fills_missing_and_defaults_empty_weight():
    st = ss.normalize_style({"weight": "Heavy", "colour": "#00FF00",
                             "start": {"visible": False}})
    assert st["linetype"] == "continuous"
    assert st["weight"] == "Heavy"
    assert st["colour"] == "#00ff00"
    assert st["start"] == {"end": "by_linetype", "visible": False}
    assert st["finish"] == {"end": "by_linetype", "visible": True}
    assert ss.normalize_style({"weight": ""})["weight"] == "by_linetype"  # WM-10
    assert ss.normalize_style(None) == ss.default_style("#ffffff")


def test_normalize_deep_copies():
    src = ss.default_style("#123456")
    out = ss.normalize_style(src)
    out["start"]["visible"] = False
    assert src["start"]["visible"] is True


def test_migrate_legacy_drops_px_and_keeps_colour():
    legacy = {"type": "draw_line", "pt1": [0, 0], "pt2": [1, 0],
              "color": "#abcdef", "lineweight": 3.0}
    out = ss.migrate_primitive(legacy)
    assert "lineweight" not in out and "color" not in out
    assert out["style"] == ss.default_style("#abcdef")
    assert legacy["lineweight"] == 3.0        # input untouched (copy)


def test_migrate_leaves_text_reference_and_nested_alone():
    for rec in ({"type": "text", "border_weight": "Medium"},
                {"type": "reference_line", "color": "#888888", "lineweight": 1.0},
                {"type": "block_instance", "block_id": "x"}):
        assert ss.migrate_primitive(rec) == rec


def test_migrate_is_idempotent_on_new_records():
    rec = {"type": "draw_circle", "style": ss.default_style("#ffffff")}
    assert ss.migrate_primitive(rec) == rec


def test_copy_style_resets_fresh_ends_only():
    class _P:
        style = None
    a, b = _P(), _P()
    # WM-9: by_block is no longer storable -- an end id is the marker.
    a.style = ss.normalize_style({"weight": "Heavy",
                                  "start": {"end": "end-marker"},
                                  "finish": {"end": "end-marker"}})
    b.style = ss.default_style()      # dst must itself be styled (else no-op)
    ss.copy_style(a, b, fresh_ends=("finish",))
    assert b.style["weight"] == "Heavy"
    assert b.style["start"]["end"] == "end-marker"
    assert b.style["finish"]["end"] == "by_linetype"
    b.style["start"]["end"] = "x"
    assert a.style["start"]["end"] == "end-marker"    # deep copy


def test_copy_style_noop_for_unstyled():
    class _P:
        style = None
    a, b = _P(), _P()
    ss.copy_style(a, b)
    assert b.style is None


def test_weight_name_for_by_block_is_model_blocks(monkeypatch):
    from firepro3d import paper_display as pd
    monkeypatch.setattr(pd, "model_blocks_weight", lambda: "Heavy")
    assert ss.canvas_weight_name("by_block") == "Heavy"
    assert ss.canvas_weight_name("by_linetype") == "Heavy"
    assert ss.canvas_weight_name("Light") == "Light"


def test_canvas_px_real_path():
    from firepro3d import paper_display as pd
    pd.reset_project_line_weights()
    pd.set_model_blocks_weight(None)
    assert ss.canvas_px("by_block") == 1.0
    assert ss.canvas_px("Heavy") == pd.canvas_weight_px(
        pd.resolve_line_weight_mm("Heavy"))


# ---------------------------------------------------------------------------
# Task 3 -- primitives carry the record; pen derived at paint (H-c)
# ---------------------------------------------------------------------------

from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtGui import QPen  # noqa: E402
from firepro3d.geometry_2d import (ArcItem, CircleItem, EllipseItem,  # noqa: E402
                                   LineItem, PolylineItem, RectangleItem,
                                   ReferenceLineItem, RegularPolygonItem,
                                   SplineItem)
from firepro3d.block_definition import _PRIMITIVE_FACTORY  # noqa: E402


def _all_styled(qapp):
    p0, p1 = QPointF(0, 0), QPointF(100, 0)
    pl = PolylineItem(p0, "#ff0000"); pl.append_point(p1)
    return [pl, LineItem(p0, p1, "#ff0000"),
            RectangleItem(p0, QPointF(50, 50), "#ff0000"),
            CircleItem(p0, 10.0, "#ff0000"),
            ArcItem(p0, 10.0, 0.0, 90.0, color="#ff0000"),
            RegularPolygonItem(p0, sides=6, radius_mm=10.0, color="#ff0000"),
            EllipseItem(p0, 20.0, 10.0, color="#ff0000"),
            SplineItem([p0, QPointF(50, 50), p1], color="#ff0000")]


def test_every_styled_class_round_trips_style(qapp):
    for it in _all_styled(qapp):
        it.style["weight"] = "Heavy"
        it.style["finish"]["visible"] = False
        d = it.to_dict()
        assert "lineweight" not in d and "color" not in d, type(it).__name__
        back = _PRIMITIVE_FACTORY[d["type"]].from_dict(d)
        assert back.style == it.style, type(it).__name__
        assert back.style["colour"] == "#ff0000"


def test_reference_line_and_text_have_no_style(qapp):
    rl = ReferenceLineItem(QPointF(0, 0), QPointF(1, 0))
    assert rl.style is None
    d = rl.to_dict()
    assert "style" not in d and d["lineweight"] == 1.0


def test_legacy_dict_loads_continuous_by_block(qapp):
    d = {"type": "draw_line", "pt1": [0, 0], "pt2": [10, 0],
         "color": "#00ff00", "lineweight": 4.0}
    it = LineItem.from_dict(d)
    assert it.style == ss.default_style("#00ff00")
    assert it.pen().widthF() == 1.0                 # px dropped


def test_display_colour_never_serialised(qapp):
    """T-colour: a Display Manager colour tints the pen, not the record."""
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QGraphicsScene, QStyleOptionGraphicsItem
    ln = LineItem(QPointF(0, 0), QPointF(10, 0), "#ff0000")
    sc = QGraphicsScene(); sc.addItem(ln)
    ln._display_color = "#00ff00"
    img = QImage(20, 20, QImage.Format.Format_ARGB32)
    p = QPainter(img); ln.paint(p, QStyleOptionGraphicsItem()); p.end()
    assert ln.pen().color().name() == "#00ff00"     # painted tint
    assert ln.to_dict()["style"]["colour"] == "#ff0000"
    assert ln.style["colour"] == "#ff0000"


def test_paint_pen_follows_weight(qapp, monkeypatch):
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QGraphicsScene, QStyleOptionGraphicsItem
    from firepro3d import paper_display as pd
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    sc = QGraphicsScene(); sc.addItem(ln)
    img = QImage(20, 20, QImage.Format.Format_ARGB32)

    def _paint():
        p = QPainter(img); ln.paint(p, QStyleOptionGraphicsItem()); p.end()
        return ln.pen().widthF()

    pd.set_model_blocks_weight(None)
    assert _paint() == pytest.approx(1.0)           # By Block -> Light -> 1 px
    ln.style["weight"] = "Heavy"
    assert _paint() == pytest.approx(
        pd.canvas_weight_px(pd.resolve_line_weight_mm("Heavy")))
    pd.set_thin_lines(True)
    try:
        assert _paint() == pytest.approx(1.0)
    finally:
        pd.set_thin_lines(False)


def _paint_item(item):
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QStyleOptionGraphicsItem
    img = QImage(20, 20, QImage.Format.Format_ARGB32)
    p = QPainter(img); item.paint(p, QStyleOptionGraphicsItem()); p.end()


@pytest.fixture
def heavy_blocks(qapp):
    """Model Blocks weight -> Heavy, so an unflagged paint-time re-derive would
    visibly change a ghost pen's width (it would be 1 px under the default)."""
    from firepro3d import paper_display as pd
    pd.set_model_blocks_weight("Heavy")
    heavy = pd.canvas_weight_px(pd.resolve_line_weight_mm("Heavy"))
    assert heavy not in (1.0, 2.0)
    try:
        yield heavy
    finally:
        pd.set_model_blocks_weight(None)


def _editor_scene():
    from firepro3d.model_space import Model_Space
    return Model_Space(scene_role="block_editor")


def test_polyline_ghost_pen_survives_paint_until_finalize(heavy_blocks):
    """Real placement path: _press_polyline ghosts, paint keeps it, finish solid."""
    from PyQt6.QtCore import Qt
    ms = _editor_scene()
    ms.set_mode("polyline")
    for pt in (QPointF(0, 0), QPointF(100, 0), QPointF(100, 100)):
        ms._press_polyline(None, None, pt, None, None, None)
    pl = ms._polyline_active
    assert pl is not None
    _paint_item(pl)
    assert pl.pen().style() == Qt.PenStyle.DashLine
    assert pl.pen().widthF() == pytest.approx(1.0)
    ms._finish_polyline()
    assert pl._ghost_pen is False
    _paint_item(pl)
    assert pl.pen().style() == Qt.PenStyle.SolidLine
    assert pl.pen().widthF() == pytest.approx(heavy_blocks)   # record-derived


def test_polygon_ghost_pen_survives_paint(heavy_blocks):
    from PyQt6.QtCore import Qt
    ms = _editor_scene()
    ms.set_mode("polygon")
    ms._press_polygon(None, None, QPointF(0, 0), None, None, None)
    ms._press_polygon(None, None, QPointF(100, 0), None, None, None)
    ghost = ms._polygon_preview
    assert ghost is not None
    _paint_item(ghost)
    assert ghost.pen().style() == Qt.PenStyle.DashLine
    assert ghost.pen().widthF() == pytest.approx(1.0)


def test_ellipse_preview_pen_survives_paint(heavy_blocks):
    ms = _editor_scene()
    ms.set_mode("draw_ellipse")
    ms._press_draw_ellipse(None, None, QPointF(0, 0), None, None, None)
    ms._press_draw_ellipse(None, None, QPointF(100, 0), None, None, None)
    prev = ms._ellipse_preview
    assert prev is not None
    _paint_item(prev)
    assert prev.pen().widthF() == pytest.approx(2.0)


def test_spline_preview_pen_survives_paint(heavy_blocks):
    ms = _editor_scene()
    ms.set_mode("draw_spline")
    for pt in (QPointF(0, 0), QPointF(100, 50), QPointF(200, 0)):
        ms._press_draw_spline(None, None, pt, None, None, None)
    prev = ms._spline_preview
    assert prev is not None
    _paint_item(prev)
    assert prev.pen().widthF() == pytest.approx(2.0)


def test_paper_pass_leaves_styled_pen_untouched(qapp):
    """I2: during a real paper pass, paint must not re-derive the pen (an
    EllipseItem is not Construction-mapped, so its pen stays cosmetic)."""
    from PyQt6.QtCore import QRectF
    from firepro3d import paper_display as pd
    ms = _editor_scene()
    el = EllipseItem(QPointF(0, 0), 20.0, 10.0, color="#ff0000")
    el.style["weight"] = "Heavy"
    ms.addItem(el)
    ms._draw_ellipses.append(el)
    pd.set_thin_lines(True)
    try:
        _paint_item(el)
        assert el.pen().widthF() == pytest.approx(1.0)       # Thin Lines
        assert el.pen().isCosmetic()
        saved = pd.apply_paper_overrides(ms, QRectF(-100, -100, 200, 200))
        try:
            assert pd.paper_pass_active()
            before = QPen(el.pen())
            _paint_item(el)
            assert el.pen() == before
        finally:
            pd.restore_model_display(saved)
        assert not pd.paper_pass_active()
    finally:
        pd.set_thin_lines(False)
