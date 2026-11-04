"""Smoke round 1: the knee snap (item 2), and a Note's Text rows at placement and
after it, with a border by default (items 3, 4). Design D8 as amended at smoke."""
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d import paper_display as pd
from firepro3d.block_instance import BlockInstance
from firepro3d.display_manager import DisplayManager
from firepro3d.paper_display import LineWeightDef
from firepro3d.text_item import TextAnnotationData, TextItem
from firepro3d.text_leader import solve_knee
from tests._note_helpers import click
from tests.test_note_ribbon import main_window  # noqa: F401  (module MainWindow fixture)

PLAN = "plan:Plan: Level 1"
A, B = QPointF(-1200.0, -800.0), QPointF(1200.0, 400.0)


def _note(shown_model_view):
    view, scene = shown_model_view
    scene.active_view_key = PLAN
    scene.set_mode("note")
    click(view, A)
    click(view, B)
    inst = scene._block_instances[-1]
    scene._note_ctl.overlay.setPlainText("Hold")
    scene._text_edit_ctl.commit()
    return view, scene, inst


def _edge_lit(scene, inst):
    """Lit pixels along the note's top edge, rendered through the real scene."""
    for it in getattr(scene, "_origin_cross_items", ()):
        it.setVisible(False)
    scene.clearSelection()
    box = inst.note_box_scene()
    area = box.adjusted(-200.0, -200.0, 200.0, 200.0)
    px = 0.25
    w, h = int(area.width() * px), int(area.height() * px)
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, w, h), area)
    p.end()
    y = int((box.top() - area.top()) * px)
    x0, x1 = int((box.left() + box.width() * .6 - area.left()) * px), int((box.right() - area.left()) * px) - 8
    return sum(any(QColor(img.pixel(x, yy)).lightness() > 60 for yy in range(y - 2, y + 3))
               for x in range(x0, x1)), x1 - x0


# -- item 2: the knee snaps to an edge midpoint ------------------------------

BOX = QRectF(0.0, 0.0, 100.0, 40.0)
REC = {"edge": "R", "t": 0.1, "shoulder_mm": 10.0}


@pytest.mark.parametrize("y, snapped", [(21.5, True), (18.5, True), (23.5, False), (5.0, False)])
def test_the_knee_lands_on_the_midpoint_inside_the_band(y, snapped):
    got = solve_knee(BOX, QPointF(120.0, y), REC, 2.0)
    assert got["edge"] == "R"
    assert got["t"] == (0.5 if snapped else pytest.approx(y / 40.0))


def test_no_band_means_no_snap():
    assert solve_knee(BOX, QPointF(120.0, 20.5), REC)["t"] == pytest.approx(20.5 / 40.0)


def test_a_note_knee_drag_snaps_at_the_screen_aperture_and_honours_the_toggle(
        shown_model_view, real_system_library):
    view, scene, inst = _note(shown_model_view)
    inst.set_property("Leader", True)
    box = inst.note_box_scene()
    px = 1.0 / view.transform().m11()                  # scene mm per screen px
    near = QPointF(box.right() + 400.0, box.center().y() + 8.0 * px)
    inst.apply_grip(inst.note_grip_index("knee"), near)
    assert inst.note["leader"]["t"] == 0.5
    far = QPointF(near.x(), box.center().y() + 60.0 * px)
    inst.apply_grip(inst.note_grip_index("knee"), far)
    assert inst.note["leader"]["t"] != 0.5
    scene._snap_engine.snap_midpoint = False
    try:
        inst.apply_grip(inst.note_grip_index("knee"), near)
        assert inst.note["leader"]["t"] != 0.5
    finally:
        scene._snap_engine.snap_midpoint = True


def test_a_text_knee_drag_snaps(qapp, shown_model_view):
    view, scene = shown_model_view
    item = TextItem(TextAnnotationData(
        text="n", wrap_width_mm=300.0, box_height_mm=200.0, height_mm=30.0,
        leader={"edge": "R", "t": 0.1, "shoulder_mm": 40.0, "tip_x": 900.0, "tip_y": 500.0}))
    scene.addItem(item)
    scene._texts.append(item)
    r = item.manip_bounds()
    px = 1.0 / view.transform().m11()
    item.apply_grip(item.LEADER_KNEE_GRIP, QPointF(r.right() + 80.0, r.center().y() + 8.0 * px))
    assert item.data.leader["t"] == 0.5


# -- item 4: a border by default, and a row for it ---------------------------

def test_a_new_note_draws_its_border_and_line_type_none_removes_it(
        shown_model_view, real_system_library):
    _view, scene, inst = _note(shown_model_view)
    lit, span = _edge_lit(scene, inst)
    assert lit > span * 0.9
    inst.set_property("Line Type", "none")
    lit, span = _edge_lit(scene, inst)
    assert lit == 0
    assert inst.note["style"] == {"border": False}


def test_a_note_carries_the_text_rows(shown_model_view, real_system_library):
    _view, _scene, inst = _note(shown_model_view)
    props = inst.get_properties()
    for k in ("Font", "Height", "Padding", "Style", "Alignment", "V Align", "Font Color",
              "Line Type", "Border Weight", "Corner", "Corner Radius",
              "Fill Color", "Fill Opacity", "Leader"):
        assert k in props, k
    assert props["Line Type"]["value"] == "solid"
    assert "pt" in props["Height"]["formatter"](3.0)   # printed text, as in an annotative block


def test_a_row_commit_undoes_in_one_step_and_survives_the_file_record(
        shown_model_view, real_system_library):
    _view, scene, inst = _note(shown_model_view)
    depth = len(scene._undo_stack)
    with scene.deferred_undo_push():
        inst.set_property("Line Type", "dashed")
    assert len(scene._undo_stack) == depth + 1
    rec = inst.to_dict()
    assert rec["note"]["style"] == {"border_line_type": "dashed"}
    assert BlockInstance.place_kwargs(rec)["note"]["style"] == {"border_line_type": "dashed"}
    scene.undo()
    assert not (scene._block_instances[-1].note.get("style"))


def test_only_the_overridden_field_stops_following_the_definition(
        shown_model_view, real_system_library):
    _view, _scene, inst = _note(shown_model_view)
    inst.set_property("Bold", True)
    assert inst.note["style"] == {"bold": True}
    inst.set_property("Bold", False)                   # back to the definition: nothing stored
    assert "style" not in inst.note
    inst.set_property("Fill Color", "#112233")
    prim = inst._note_prim()
    prim["height_mm"] = 5.0
    inst.note_changed()
    assert inst.get_properties()["Height"]["value_mm"] == 5.0    # untouched: follows the block
    assert inst.get_properties()["Fill Color"]["value"] == "#112233"
    prim["height_mm"] = 3.0


def test_the_box_memo_sees_a_style_change(shown_model_view, real_system_library):
    _view, _scene, inst = _note(shown_model_view)
    assert inst._note_geometry()[0].data.height_mm == 3.0
    inst.note["style"] = {"height_mm": 6.0}            # as an undo restore writes it
    assert inst._note_geometry()[0].data.height_mm == 6.0


def test_the_edit_overlay_wears_the_note_style(shown_model_view, real_system_library):
    _view, scene, inst = _note(shown_model_view)
    inst.set_property("Line Type", "dashed")
    scene._note_ctl.begin(inst)
    ov = scene._note_ctl.overlay
    assert ov.data.border_line_type == "dashed" and ov.data.border is True
    scene._text_edit_ctl.commit()


# -- item 3: the template panel while the Note tool is armed -----------------

def test_arming_note_shows_the_template_and_the_next_note_takes_it(
        main_window, real_system_library):
    win = main_window
    scene = win.scene
    view = scene._snap_view()
    tmpl = scene._note_ctl.template
    win._activate_note_tool()
    assert win.prop_manager._targets == [tmpl]
    for k in ("Line Type", "Border Weight", "Font", "Leader"):
        assert k in win.prop_manager._prop_widgets, k
    depth = len(scene._undo_stack)
    tmpl.set_property("Line Type", "dotted")
    tmpl.set_property("Bold", True)
    tmpl.set_property("Leader", True)
    assert len(scene._undo_stack) == depth             # the template is not the model
    assert "Leader End" in tmpl.get_properties()
    tmpl.set_property("Leader Weight", "Medium")
    vr = view.viewport().rect()
    a = view.mapToScene(int(vr.width() * .55), int(vr.height() * .3))
    b = view.mapToScene(int(vr.width() * .9), int(vr.height() * .7))
    click(view, a)
    click(view, b)
    inst = scene._block_instances[-1]
    assert inst.note["style"] == {"border_line_type": "dotted", "bold": True}
    assert inst.note["leader"]["weight"] == "Medium"
    assert inst.note["style"] is not tmpl.style
    scene._note_ctl.overlay.setPlainText("Hold")
    scene._text_edit_ctl.commit()
    tmpl.style, tmpl.leader = {}, None


def test_leaving_the_note_tool_clears_the_template(main_window, real_system_library):
    win = main_window
    win._activate_note_tool()
    win.scene.set_mode(None)
    assert win.prop_manager._targets == []


# -- the weight walker reaches the new field ---------------------------------

def test_a_note_border_weight_counts_and_follows_a_rename(shown_model_view, real_system_library):
    _view, scene, inst = _note(shown_model_view)
    pd.set_project_line_weights([*pd.project_line_weights(), LineWeightDef("Styleonly", 0.33)])
    d = DisplayManager(scene, active_context="paper")
    try:
        inst.note["style"] = {"border_weight": "Styleonly"}
        assert d._line_weight_in_use("Styleonly")
        d._propagate_lw_rename("Styleonly", "Renamed")
        assert inst.note["style"]["border_weight"] == "Renamed"
    finally:
        d.reject()
        pd.reset_project_line_weights()
