"""LT5 D4 / Q10 -- Start End / Finish End + Start / Finish Visible (+ ET1
Scale) rows on
open primitives only; one undo step per edit; folder pick loads first and a
failed load restores; template and placement rows carry no end rows."""
import pytest
from PyQt6.QtCore import QPointF, QSettings

from firepro3d import app_data, block_library
from firepro3d import stroke_style as ss
from firepro3d.geometry_2d import (ArcItem, CircleItem, GeometryTemplate,
                                   LineItem, PolylineItem, RectangleItem,
                                   SplineItem)
from firepro3d.model_space import Model_Space
from tests.lt3_support import make_linetype
from tests.lt5_support import end_id, scene_line, v_end

_KEYS = ("Start End", "Finish End", "Start Visible", "Finish Visible",
         "Start Scale", "Finish Scale")                    # ET1 Q10-b


@pytest.fixture
def end_dir(qapp, tmp_path):
    root = tmp_path / "ends_root"
    root.mkdir()
    QSettings("GV", "FirePro3D").setValue(app_data.END_DIR_KEY, str(root))
    return root


def _add(ms, item, list_attr):
    ms.addItem(item)
    getattr(ms, list_attr).append(item)
    return item


def _poly(closed):
    p = PolylineItem(QPointF(0, 0))
    p.append_point(QPointF(10, 0))
    p.append_point(QPointF(10, 10))
    if closed:
        p.close()
    return p


def test_rows_on_open_items_only(qapp):
    ms = Model_Space()
    open_items = [_add(ms, LineItem(QPointF(0, 0), QPointF(10, 0)), "_draw_lines"),
                  _add(ms, _poly(False), "_polylines"),
                  _add(ms, ArcItem(QPointF(0, 0), 10.0, 0.0, 90.0), "_draw_arcs"),
                  _add(ms, SplineItem([QPointF(0, 0), QPointF(10, 10), QPointF(20, 0),
                                       QPointF(30, 10)]), "_draw_splines")]
    closed = [_add(ms, _poly(True), "_polylines"),
              _add(ms, RectangleItem(QPointF(0, 0), QPointF(10, 10)), "_draw_rects"),
              _add(ms, CircleItem(QPointF(0, 0), 5.0), "_draw_circles"),
              _add(ms, ArcItem(QPointF(0, 0), 10.0, 0.0, 360.0), "_draw_arcs")]
    for it in open_items:
        props = it.get_properties()
        assert all(k in props for k in _KEYS), type(it).__name__
        keys = list(props)
        assert keys.index("Start End") > keys.index("Weight")
        for k in _KEYS:
            assert props[k].get("tooltip"), k
    for it in closed:
        assert not any(k in it.get_properties() for k in _KEYS), type(it).__name__


def test_defaults_and_by_linetype_head_shows_the_linetype_default(qapp):
    ms = Model_Space()
    a = end_id(ms, name="Arrow")
    lt = make_linetype("Hidden")
    rep = lt.repeat
    rep["ends"] = {"start": a}
    lt.set_repeat(rep)
    ms.register_block_definition(lt)
    ln = scene_line(ms, linetype=lt.id)
    p = ln.get_properties()
    assert p["Start End"]["value"] == "By Linetype (Arrow)"
    assert p["Finish End"]["value"] == "By Linetype (None)"
    assert p["Finish End"]["options"] == ["By Linetype (None)", "None", "Arrow"]
    assert p["Start Visible"]["value"] is True
    assert p["Finish Visible"]["type"] == "bool"


def test_project_pick_none_and_visible_are_one_undo_step_each(qapp):
    ms = Model_Space()
    a = end_id(ms, name="Arrow")
    ln = scene_line(ms)
    pos0 = ms._undo_pos
    ln.set_property("Finish End", "Arrow")
    assert ln.style["finish"]["end"] == a and ms._undo_pos == pos0 + 1
    ln.set_property("Finish End", "Arrow")                 # re-commit: no step
    assert ms._undo_pos == pos0 + 1
    ln.set_property("Finish Visible", False)
    assert ln.style["finish"] == {"end": a, "visible": False}   # keeps the pick
    assert ms._undo_pos == pos0 + 2
    ln.set_property("Start End", "None")
    assert ln.style["start"]["end"] == ss.NONE and ms._undo_pos == pos0 + 3
    ms.undo()
    ms.undo()
    ms.undo()
    (ln2,) = ms._draw_lines
    assert ln2.style["finish"]["end"] == ss.BY_LINETYPE
    assert ln2.style["start"]["end"] == ss.BY_LINETYPE


def test_pick_through_the_property_panel(qapp):
    from PyQt6.QtWidgets import QApplication
    from firepro3d.property_manager import PropertyManager
    ms = Model_Space()
    a = end_id(ms, name="Arrow")
    ln = scene_line(ms)
    pm = PropertyManager()
    pm.show_properties([ln])
    QApplication.processEvents()
    combo = pm._prop_widgets["Start End"]
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "By Linetype (None)", "None", "Arrow"]
    pos0 = ms._undo_pos
    combo.setCurrentText("Arrow")
    QApplication.processEvents()
    assert ln.style["start"]["end"] == a and ms._undo_pos == pos0 + 1
    pm._prop_widgets["Start Visible"].click()
    QApplication.processEvents()
    assert ln.style["start"]["visible"] is False and ms._undo_pos == pos0 + 2


def test_missing_and_non_end_ids_show_missing_and_never_rewrite(qapp):
    ms = Model_Space()
    lt = make_linetype("Hidden")
    ms.register_block_definition(lt)
    ln = scene_line(ms, finish={"end": "deadbeef", "visible": True},
                    start={"end": lt.id, "visible": True})
    p = ln.get_properties()
    assert p["Finish End"]["value"] == "Missing: deadbeef"
    assert p["Finish End"]["options"][0] == "Missing: deadbeef"
    assert p["Start End"]["value"] == "Missing: Hidden"
    pos0 = ms._undo_pos
    ln.set_property("Finish End", "Missing: deadbeef")
    ln.set_property("Finish End", "No such end")
    assert ln.style["finish"]["end"] == "deadbeef" and ms._undo_pos == pos0


def test_folder_pick_loads_in_one_step_and_failure_restores(end_dir, monkeypatch):
    from firepro3d import themed_message
    shown = []
    monkeypatch.setattr(themed_message, "themed_info",
                        lambda *a, **k: shown.append(a))
    ms = Model_Space()
    good = v_end(name="Tick")
    block_library.save_to_library(good, root=str(end_dir))
    bad = v_end(name="Dot")
    block_library.save_to_library(bad, root=str(end_dir))
    ms.register_block_definition(v_end(name="Dot"))      # load clash
    ln = scene_line(ms)
    pos0 = ms._undo_pos
    ln.set_property("Finish End", "Tick")
    assert ln.style["finish"]["end"] == good.id
    assert ms.get_block_definition(good.id) is not None
    assert ms._undo_pos == pos0 + 1                          # the load's batch
    ms.undo()
    assert ms.get_block_definition(good.id) is None
    assert ms._draw_lines[0].style["finish"]["end"] == ss.BY_LINETYPE
    ln = ms._draw_lines[0]
    pos1 = ms._undo_pos
    label = next(o for o in ln.get_properties()["Start End"]["options"]
                 if o.startswith("Dot ("))
    ln.set_property("Start End", label)
    assert ln.style["start"]["end"] == ss.BY_LINETYPE         # restored
    assert ms._undo_pos == pos1 and shown


def test_folder_pick_inside_a_block_editor_is_one_editor_step(end_dir):
    from firepro3d.block_editor import BlockEditorWidget
    proj = Model_Space()
    good = v_end(name="Tick")
    block_library.save_to_library(good, root=str(end_dir))
    w = BlockEditorWidget(proj)
    sc = w.editor_scene
    ln = LineItem(QPointF(0, 0), QPointF(30, 0))
    w._add_primitive(ln)
    sc.push_undo_state()
    pos0 = sc._undo_pos
    ln.set_property("Finish End", "Tick")
    assert proj.get_block_definition(good.id) is not None    # loaded into project
    assert ln.style["finish"]["end"] == good.id
    assert sc._undo_pos == pos0 + 1
    sc.undo()
    assert sc._draw_lines[0].style["finish"]["end"] == ss.BY_LINETYPE


def test_template_and_placement_rows_carry_no_end_rows(qapp):
    from firepro3d.block_definition import BlockDefinition
    ms = Model_Space()
    end_id(ms, name="Arrow")
    assert not any(k in GeometryTemplate(ms).get_properties() for k in _KEYS)
    d = BlockDefinition.new(name="Sym", library="L", series="S", origin=(0, 0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(5, 0)).to_dict()])
    ms.register_block_definition(d)
    inst = ms.place_block_instance(d.id, (0.0, 0.0))
    assert not any(k in inst.get_properties() for k in _KEYS)


def test_multi_target_folder_pick_is_one_undo_step(end_dir):
    """Two selected lines + a not-yet-loaded folder end through the real
    panel: ONE step that both re-points the lines and loads the end."""
    from PyQt6.QtWidgets import QApplication
    from firepro3d.property_manager import PropertyManager
    ms = Model_Space()
    good = v_end(name="Tick")
    block_library.save_to_library(good, root=str(end_dir))
    a = scene_line(ms)
    b = scene_line(ms, p1=(0.0, 10.0), p2=(30.0, 10.0))
    pm = PropertyManager()
    pm.show_properties([a, b])
    QApplication.processEvents()
    pos0 = ms._undo_pos
    pm._prop_widgets["Finish End"].setCurrentText("Tick")
    QApplication.processEvents()
    assert [ln.style["finish"]["end"] for ln in (a, b)] == [good.id] * 2
    assert ms.get_block_definition(good.id) is not None
    assert ms._undo_pos == pos0 + 1
    ms.undo()
    assert [ln.style["finish"]["end"] for ln in ms._draw_lines] == [ss.BY_LINETYPE] * 2
    assert ms.get_block_definition(good.id) is None
