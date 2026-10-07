"""WM1 G3/G4 -- panel pickers without By Block, the GeometryTemplate rows,
the draw tools stamping the current, imports not (linetypes.md WM-5/WM-10)."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d import paper_display as pd
from firepro3d import stroke_style as ss
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import hidden


def _line(ms):
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ms.addItem(ln); ms._draw_lines.append(ln)
    ms.push_undo_state()
    return ln


def test_primitive_rows_have_no_by_block(qapp):
    ms = Model_Space(scene_role="block_editor")
    props = _line(ms).get_properties()
    assert "By Block" not in props["Linetype"]["options"]
    assert not any(o.startswith("By Block") for o in props["Weight"]["options"])
    assert props["Linetype"]["tooltip"] and props["Weight"]["tooltip"]


def test_weight_row_shows_resolved_by_linetype(qapp):
    pd.set_model_blocks_weight(None)
    ms = Model_Space(scene_role="block_editor")
    lt = hidden(ms, weight="Thinner")
    ln = _line(ms)
    w = ln.get_properties()["Weight"]
    assert w["options"][0] == "By Linetype (Thinnest)" == w["value"]
    ln.style["linetype"] = lt
    w = ln.get_properties()["Weight"]
    assert w["options"][0] == "By Linetype (Thinner)" == w["value"]


def test_picking_by_linetype_label_stores_by_linetype(qapp):
    ms = Model_Space(scene_role="block_editor")
    ln = _line(ms)
    ln.set_property("Weight", "Thin")
    assert ln.style["weight"] == "Thin"
    ln.set_property("Weight", "By Linetype (Thinnest)")
    assert ln.style["weight"] == ss.BY_LINETYPE


def test_selected_primitive_edit_does_not_move_current(qapp):
    ms = Model_Space(scene_role="block_editor")
    _line(ms).set_property("Weight", "Thin")
    assert ss.current_style()["weight"] == ss.BY_LINETYPE


# -- GeometryTemplate = the current -----------------------------------------

def _tmpl(ms):
    return ms._get_geometry_template()


def test_template_rows_show_current(qapp):
    ms = Model_Space(scene_role="block_editor")
    props = _tmpl(ms).get_properties()
    assert props["Linetype"]["value"] == "Continuous"
    assert props["Weight"]["value"].startswith("By Linetype (")
    assert "By Block" not in props["Linetype"]["options"]
    assert props["Linetype"]["tooltip"] and props["Weight"]["tooltip"]


def test_template_pick_sets_current(qapp):
    ms = Model_Space(scene_role="block_editor")
    lt = hidden(ms)
    t = _tmpl(ms)
    t.set_property("Weight", "Thin")
    t.set_property("Linetype", "Hidden")
    assert ss.current_style() == {"linetype": lt, "weight": "Thin"}
    t.set_property("Weight", t.get_properties()["Weight"]["options"][0])
    assert ss.current_style()["weight"] == ss.BY_LINETYPE


def test_template_unresolvable_current_shows_continuous(qapp):
    ss.set_current(linetype="from-another-project")
    props = _tmpl(Model_Space(scene_role="block_editor")).get_properties()
    assert props["Linetype"]["value"] == "Continuous"
    assert ss.current_style()["linetype"] == ss.CONTINUOUS


def test_template_folder_pick_loads_and_becomes_current(qapp, tmp_path):
    from PyQt6.QtCore import QSettings
    from firepro3d import app_data, block_library
    from tests.lt3_support import make_linetype
    root = tmp_path / "lts"; root.mkdir()
    QSettings("GV", "FirePro3D").setValue(app_data.LINETYPE_DIR_KEY, str(root))
    lt = make_linetype(name="Center"); lt.series = "Linetypes"
    block_library.save_to_library(lt, root=str(root))
    ms = Model_Space(scene_role="block_editor")
    _tmpl(ms).set_property("Linetype", "Center")
    assert ms.block_registry.get(lt.id) is not None
    assert ss.current_style()["linetype"] == lt.id


# -- the 8 draw tools stamp the current; imports don't -----------------------

@pytest.fixture
def heavy_hidden(qapp):
    ms = Model_Space(scene_role="block_editor")
    lt = hidden(ms)
    ss.set_current(linetype=lt, weight="Thin")
    return ms, lt


def _assert_current(item, lt):
    assert item.style["linetype"] == lt and item.style["weight"] == "Thin"


def test_draw_line_takes_current(heavy_hidden):
    ms, lt = heavy_hidden
    ms.set_mode("draw_line")
    ms._make_line_like(QPointF(0, 0), QPointF(100, 0))
    _assert_current(ms._draw_lines[-1], lt)


def test_draw_circle_takes_current(heavy_hidden):
    ms, lt = heavy_hidden
    ms.set_mode("draw_circle")
    ms._draw_circle_center = QPointF(0, 0)
    assert ms._commit_draw_circle_at(QPointF(120.0, 0.0)) is True
    _assert_current(ms._draw_circles[-1], lt)


def test_polyline_takes_current(heavy_hidden):
    from tests.test_dynamic_input_parity import _FakeEvent
    ms, lt = heavy_hidden
    ms.set_mode("select"); ms.set_mode("polyline")
    p = QPointF(0, 0)
    ms._press_polyline(_FakeEvent(), p, p, None, None, None)
    _assert_current(ms._polyline_active, lt)


def test_rectangle_takes_current(heavy_hidden):
    from tests.test_dynamic_input_parity import _FakeEvent
    ms, lt = heavy_hidden
    ms.set_mode("draw_rectangle")
    for p in (QPointF(0, 0), QPointF(300, 0), QPointF(0, -400)):
        ms._press_draw_rectangle(_FakeEvent(), None, p, None, None, None)
    _assert_current(ms._draw_rects[-1], lt)


def test_ellipse_takes_current(heavy_hidden):
    ms, lt = heavy_hidden
    ms.set_mode("draw_ellipse")
    ctl = ms._geom_ctl
    for p in (QPointF(0, 0), QPointF(100, 0), QPointF(0, -40)):
        ctl._press_draw_ellipse(None, p, p, None, None, None)
    _assert_current(ms._draw_ellipses[-1], lt)


def test_spline_takes_current(heavy_hidden):
    ms, lt = heavy_hidden
    ms.set_mode("draw_spline")
    ctl = ms._geom_ctl
    for p in (QPointF(0, 0), QPointF(10, 20), QPointF(30, -10), QPointF(40, 5)):
        ctl._press_draw_spline(None, p, p, None, None, None)
    ctl._finish_draw_spline()
    _assert_current(ms._draw_splines[-1], lt)


def test_arc_and_polygon_take_current(shown_model_view):
    from tests.test_arc_polygon_slice_parity import _press_at
    view, ms = shown_model_view
    ms.scene_role = "block_editor"       # containment C1: plan refuses raw drawing
    lt = hidden(ms)
    ss.set_current(linetype=lt, weight="Thin")
    ms.set_mode("draw_arc")
    for p in (QPointF(0, 0), QPointF(400, 0), QPointF(0, -400)):
        _press_at(view, p)
    _assert_current(ms._draw_arcs[-1], lt)
    ms.set_mode("polygon")
    for p in (QPointF(0, 0), QPointF(400, 0), QPointF(0, -400)):
        _press_at(view, p)
    _assert_current(ms._draw_polygons[-1], lt)


def test_import_does_not_take_current(heavy_hidden):
    from firepro3d.geometry_import import geom_dicts_to_primitives
    items, _skipped = geom_dicts_to_primitives(
        [{"kind": "line", "x1": 0, "y1": 0, "x2": 10, "y2": 0}])
    assert items and all(it.style["weight"] == ss.BY_LINETYPE for it in items)
