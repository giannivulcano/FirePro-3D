"""Reference geometry -- panel toggles (RG10), hidden refs (RG15), hidden
fill hit test on every closed shape (RG4)."""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF, QRectF, QSettings
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication

from firepro3d.fill_layers import BackgroundLayer, FillLayers, PatternLayer
from firepro3d.geometry_2d import (ArcItem, CircleItem, EllipseItem, LineItem,
                                   PolylineItem, RectangleItem,
                                   RegularPolygonItem, SplineItem)

_SOLID = FillLayers(background=BackgroundLayer("#888888", 0.45))   # the old fill_type="solid"


# -- RG10: panel Reference / Printed toggles ---------------------------------

def test_panel_reference_toggle_hides_style_rows_and_restores(shown_model_view):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    c = CircleItem(QPointF(0, 0), 50.0)
    c.fill_layers = _SOLID
    scene.addItem(c); scene._draw_circles.append(c)
    scene.push_undo_state()
    before = c.to_dict()
    rows = c.get_properties()
    assert "Reference" in rows and rows["Reference"]["type"] == "toggle"
    assert rows["Reference"]["value"] is False
    assert "Printed" not in rows and "Linetype" in rows and "Fill" in rows
    assert "Fill Pattern" in rows
    pos0 = scene._undo_pos
    c.set_property("Reference", True)
    assert scene._undo_pos == pos0 + 1                     # one undo step
    rows = c.get_properties()
    assert c.reference is True and rows["Reference"]["value"] is True
    assert "Printed" in rows and rows["Printed"]["type"] == "toggle"
    for k in ("Linetype", "Weight", "Colour", "Fill", "Fill Pattern",
              "Fill Colour", "Fill Opacity"):
        assert k not in rows, k
    c.set_property("Printed", True)
    assert c.printed is True and scene._undo_pos == pos0 + 2
    c.set_property("Reference", False)
    assert c.reference is False and c.printed is False
    assert scene._undo_pos == pos0 + 3
    assert c.to_dict() == before                           # RG4 restore exact
    rows = c.get_properties()
    assert "Printed" not in rows and "Linetype" in rows and "Fill" in rows


def test_open_line_end_rows_hide_while_reference(qapp):
    line = LineItem(QPointF(0, 0), QPointF(100, 0))
    rows = line.get_properties()
    assert "Start End" in rows and "Finish End" in rows
    line.set_property("Reference", True)
    rows = line.get_properties()
    assert "Start End" not in rows and "Finish End" not in rows
    assert "Linetype" not in rows and "Weight" not in rows


def test_panel_undo_restores_flag(shown_model_view):
    view, scene = shown_model_view
    c = CircleItem(QPointF(0, 0), 50.0)
    scene.addItem(c); scene._draw_circles.append(c)
    scene.push_undo_state()
    c.set_property("Reference", True)
    scene.undo()
    live = scene._draw_circles[-1]
    assert live.reference is False
    scene.redo()
    assert scene._draw_circles[-1].reference is True


def test_multi_select_panel_flip_is_one_undo_step(shown_model_view):
    from firepro3d.property_manager import PropertyManager
    view, scene = shown_model_view
    c = CircleItem(QPointF(0, 0), 50.0)
    ln = LineItem(QPointF(0, 0), QPointF(100, 0))
    scene.addItem(c); scene._draw_circles.append(c)
    scene.addItem(ln); scene._draw_lines.append(ln)
    scene.push_undo_state()
    pm = PropertyManager()
    pm.show_properties([c, ln])
    QApplication.processEvents()
    assert "Reference" in pm._prop_widgets
    pos0 = scene._undo_pos
    pm._apply_property("Reference", True)
    from PyQt6.QtTest import QTest              # the panel's refresh timer
    for _ in range(60):
        if "Printed" in pm._prop_widgets:
            break
        QTest.qWait(50)
    assert c.reference is True and ln.reference is True
    assert scene._undo_pos == pos0 + 1
    assert "Printed" in pm._prop_widgets and "Linetype" not in pm._prop_widgets


@pytest.fixture
def _scratch_display_keys():
    keys = ("display/Reference Geometry/color", "display/2D Geometry/color")
    st = QSettings("GV", "FirePro3D")
    before = {k: st.value(k) for k in keys if st.contains(k)}
    yield
    st = QSettings("GV", "FirePro3D")
    for k in keys:
        st.remove(k)
    for k, v in before.items():
        st.setValue(k, v)
    st.sync()


def test_panel_flip_takes_the_new_category_colour(shown_model_view,
                                                 _scratch_display_keys):
    """REWRITTEN for RG17 (seam review): the flip ON takes the Reference
    Geometry colour; the flip back no longer takes the 2D Geometry colour --
    it restores the prior display state (None stays None)."""
    view, scene = shown_model_view
    st = QSettings("GV", "FirePro3D")
    st.setValue("display/Reference Geometry/color", "#777777")
    st.setValue("display/2D Geometry/color", "#eeeeee")
    c = CircleItem(QPointF(0, 0), 50.0)
    scene.addItem(c); scene._draw_circles.append(c)
    c.set_property("Reference", True)
    assert c._display_color == "#777777"
    assert c._reference_pen().color() == QColor("#777777")
    c.set_property("Reference", False)
    assert c._display_color is None                  # RG17: prior state back


@pytest.mark.parametrize("prior", [None, "#123456"])
def test_flip_back_restores_the_prior_display_colour(
        shown_model_view, _scratch_display_keys, prior):
    """RG17 / AC5: on -> off renders exactly as before; _display_color is
    the prior value again (None stays None, a set colour comes back)."""
    from tests.test_reference_geometry import _render_item
    view, scene = shown_model_view
    st = QSettings("GV", "FirePro3D")
    st.setValue("display/Reference Geometry/color", "#777777")
    st.setValue("display/2D Geometry/color", "#eeeeee")
    c = CircleItem(QPointF(0, 0), 40.0)
    c.style["colour"] = "#ab12cd"
    c._display_color = prior
    scene.addItem(c); scene._draw_circles.append(c)
    scene.removeItem(c)
    before = _render_item(c)
    scene.addItem(c)
    c.set_property("Reference", True)
    assert c._display_color == "#777777"
    c.set_property("Reference", False)
    assert c._display_color == prior
    scene.removeItem(c)
    assert _render_item(c) == before                 # same pixels as before


def test_flip_back_survives_undo_redo(shown_model_view, _scratch_display_keys):
    view, scene = shown_model_view
    QSettings("GV", "FirePro3D").setValue("display/Reference Geometry/color",
                                          "#777777")
    c = CircleItem(QPointF(0, 0), 50.0)
    scene.addItem(c); scene._draw_circles.append(c)
    scene.push_undo_state()
    c.set_property("Reference", True)
    c.set_property("Reference", False)
    scene.undo(); scene.undo()
    back = scene._draw_circles[-1]
    assert back.reference is False
    assert back._display_color != "#777777"           # not left in the ref colour
    scene.redo()
    redone = scene._draw_circles[-1]
    assert redone.reference is True
    assert redone._display_color == "#777777"         # restore re-applies RG18


# -- Review Minor: stale missing-linetype tooltip on a flip -------------------

def _paint(scene):
    img = QImage(64, 64, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, 64, 64), QRectF(-50, -50, 100, 100))
    p.end()


def test_missing_linetype_tooltip_clears_on_reference_and_returns(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    ln = LineItem(QPointF(-40, 0), QPointF(40, 0))
    ln.style["linetype"] = "no_such_linetype_id"
    s.addItem(ln); s._draw_lines.append(ln)
    _paint(s)
    assert "no_such_linetype_id" in ln.toolTip()
    ln.set_property("Reference", True)
    assert ln.toolTip() == ""
    _paint(s)
    assert ln.toolTip() == ""
    ln.set_property("Reference", False)
    _paint(s)
    assert "no_such_linetype_id" in ln.toolTip()


# -- RG15: hidden refs are not block dependencies -----------------------------

def _ref_records(flag: bool):
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ln.style["linetype"] = "lt_block_id"
    c = CircleItem(QPointF(0, 0), 5.0)
    c.fill_layers = FillLayers(pattern=PatternLayer("pattern_block_id"))
    ln.reference = c.reference = flag
    return [ln.to_dict(), c.to_dict()]


def test_prim_refs_skip_reference_records(qapp):
    from firepro3d.block_registry import prim_refs
    assert prim_refs(_ref_records(True)) == set()
    assert {"lt_block_id", "pattern_block_id"} <= prim_refs(_ref_records(False))


def test_prim_refs_skip_reference_explicit_end_ids(qapp):
    from firepro3d.block_registry import prim_refs
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ln.style["start"] = dict(ln.style.get("start") or {}, end="end_block_id")
    assert "end_block_id" in prim_refs([ln.to_dict()])
    ln.reference = True
    assert prim_refs([ln.to_dict()]) == set()


def test_linetype_editor_saves_a_reference_line_carrying_its_own_linetype(qapp):
    from firepro3d.block_editor import BlockEditorWidget
    from firepro3d.model_space import Model_Space
    from tests.lt3_support import make_linetype
    proj = Model_Space()
    defn = make_linetype()
    proj.register_block_definition(defn)
    w = BlockEditorWidget(proj, block_id=defn.id)
    w.seed_from_definition(defn)
    msgs = []
    proj._show_status = lambda m, *a, **k: msgs.append(m)
    w.editor_scene._show_status = lambda m, *a, **k: msgs.append(m)
    rl = LineItem(QPointF(0, 5), QPointF(9, 5))
    rl.reference = True
    rl.style["linetype"] = defn.id                     # its own linetype
    w._add_primitive(rl)
    w.editor_scene.push_undo_state()
    v0 = defn.version
    saved = w.save()
    assert saved is not None, msgs              # no cycle refusal (RG15)
    stored = proj.get_block_definition(defn.id)
    assert stored.version > v0
    refs = [p for p in stored.primitives if p.get("reference")]
    assert len(refs) == 1 and refs[0]["style"]["linetype"] == defn.id


# -- RG4 hidden fill: every closed shape --------------------------------------

def _closed_polyline():
    p = PolylineItem(QPointF(-50, -50))
    for pt in ((50, -50), (50, 50), (-50, 50)):
        p.append_point(QPointF(*pt))
    p.close()
    return p


def _rotated_rect():
    r = RectangleItem(QPointF(-50, -30), QPointF(50, 30))
    r.set_angle(30.0)
    return r


_CLOSED = {
    "PolylineItem": _closed_polyline,
    "RectangleItem": lambda: RectangleItem(QPointF(-50, -30), QPointF(50, 30)),
    "RectangleItem-rotated": _rotated_rect,
    "CircleItem": lambda: CircleItem(QPointF(0, 0), 50.0),
    "ArcItem": lambda: ArcItem(QPointF(0, 0), 50.0, 0.0, 360.0),
    "RegularPolygonItem": lambda: RegularPolygonItem(QPointF(0, 0), 6, 50.0),
    "EllipseItem": lambda: EllipseItem(QPointF(0, 0), 60.0, 30.0, 0.0),
    # 8 control points: Qt's stroker outline of a 4-point periodic spline
    # already encloses its centre unfilled (pre-existing, not a fill path).
    "SplineItem": lambda: SplineItem(
        [QPointF(100 * math.cos(k * math.pi / 4), 100 * math.sin(k * math.pi / 4))
         for k in range(8)], 3, closed=True),
}


@pytest.mark.parametrize("name", list(_CLOSED))
def test_hidden_fill_never_hit_tests_on_any_closed_shape(qapp, name):
    from firepro3d.halo import halo_is_area
    from firepro3d.model_space import Model_Space
    s = Model_Space(scene_role="block_editor")
    item = _CLOSED[name]()
    s.addItem(item)
    assert item.is_fillable()
    assert not item.shape().contains(QPointF(0, 0))      # unfilled baseline
    item.fill_layers = _SOLID
    inside = QPointF(0, 0)                    # centre: far from every stroke
    assert item.shape().contains(inside) and halo_is_area(item)
    item.reference = True
    assert not item.shape().contains(inside)
    assert not halo_is_area(item)


# -- Unit C review follow-ups: no-op flips are no-ops ------------------------

def test_noop_reference_flip_pushes_no_undo_step(shown_model_view):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    a = CircleItem(QPointF(0, 0), 50.0)
    b = CircleItem(QPointF(100, 0), 20.0)
    b.reference = True
    for it in (a, b):
        scene.addItem(it); scene._draw_circles.append(it)
    scene.push_undo_state()
    pos0 = scene._undo_pos
    a.set_property("Reference", False)          # already normal
    b.set_property("Reference", True)           # already reference
    assert scene._undo_pos == pos0
    assert a.reference is False and b.reference is True


def test_printed_on_a_non_reference_item_is_a_noop(shown_model_view):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    a = CircleItem(QPointF(0, 0), 50.0)
    scene.addItem(a); scene._draw_circles.append(a)
    scene.push_undo_state()
    pos0 = scene._undo_pos
    a.set_property("Printed", True)
    assert a.printed is False and scene._undo_pos == pos0


def test_noop_reference_flip_leaves_a_directly_set_display_colour(qapp):
    c = CircleItem(QPointF(0, 0), 50.0)
    c._display_color = "#123456"                # set directly, not an override
    c._set_reference_flag("Reference", False)   # no-op: already normal
    assert c._display_color == "#123456"
    c.reference = True
    c._display_color = "#654321"
    c._set_reference_flag("Reference", True)
    assert c._display_color == "#654321"
