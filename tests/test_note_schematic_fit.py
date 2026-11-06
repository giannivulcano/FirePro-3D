"""Notes reaching a sheet: the user's rulings of 2026-11-05 on the three-click Note. A
bottom-edge box grows upward, a Real size schematic sizes a Note by the project scale, a
leader counts toward the schematic's extent, and a Note placed by clicks prints true."""
import pytest

from firepro3d import text_leader as _tl
from firepro3d.block_definition import BlockDefinition
from firepro3d.paper_export import export_pdf
from firepro3d.schematic_scene import SchematicSceneManager
from firepro3d.text_leader import normalise
from tests.test_note_instance import leader_op
from tests.test_note_three_click import (KNEE, PLAN, SCHEMATIC_SCALE, THIRD, TIP, _type_lines,
                                         landed, px, schematic, three_clicks)  # noqa: F401
from tests.test_printed_text_pdf import _MM_PER_PT, _cap_mm, _editor, _fills, _sheet, _strokes


def _note_on_plan(shown_model_view, edge):
    view, scene = shown_model_view
    scene.active_view_key = PLAN
    scene.set_mode("note")
    three_clicks(view, scene, third=THIRD[edge])
    return view, scene, scene._block_instances[-1]


def test_a_plan_note_on_its_bottom_edge_grows_up_and_keeps_its_elbow(
        shown_model_view, real_system_library):
    view, scene, inst = _note_on_plan(shown_model_view, "B")
    one_line = inst.note_box_scene()
    ov = scene._note_ctl.overlay
    _type_lines(view, scene, 3)
    live = _tl.box_frame_points(ov)
    want = landed(view, KNEE)
    assert _tl._to_parent(ov, live[1]).y() == pytest.approx(want.y(), abs=px(view) * 1.5)
    scene._text_edit_ctl.commit()
    box = inst.note_box_scene()
    assert box.height() > one_line.height() * 2.0
    assert box.bottom() == pytest.approx(one_line.bottom(), abs=px(view))
    assert box.top() < one_line.top() - one_line.height()
    op, pose = leader_op(inst), inst.pose_transform()
    k = pose.map(_knee_of(op))
    assert (k.x(), k.y()) == pytest.approx((want.x(), want.y()), abs=px(view) * 1.5)
    tip = inst.note_tip_scene()
    t = landed(view, TIP)
    assert (tip.x(), tip.y()) == pytest.approx((t.x(), t.y()), abs=px(view) * 1.5)


def _knee_of(op):
    from PyQt6.QtCore import QPointF
    return QPointF(op.pieces[0].x1, op.pieces[0].y1)


def test_a_plan_note_on_its_top_edge_still_grows_down(shown_model_view, real_system_library):
    view, scene, inst = _note_on_plan(shown_model_view, "T")
    one_line = inst.note_box_scene()
    _type_lines(view, scene, 3)
    scene._text_edit_ctl.commit()
    box = inst.note_box_scene()
    assert box.height() > one_line.height() * 2.0
    assert box.top() == pytest.approx(one_line.top(), abs=px(view))


def _schematic_note(schematic, edge):
    w, view, scene, proj = schematic
    scene.set_mode("note")
    assert scene.mode == "note"
    three_clicks(view, scene, third=THIRD[edge])
    return w, view, scene, proj, scene._texts[-1]


def test_a_schematic_note_on_its_bottom_edge_grows_up_and_keeps_its_elbow(schematic):
    _w, view, scene, _proj, item = _schematic_note(schematic, "B")
    one_line = item.manip_bounds()
    _type_lines(view, scene, 3)
    scene._text_edit_ctl.commit()
    box = item.manip_bounds()
    assert box.height() > one_line.height() * 2.0
    assert box.bottom() == pytest.approx(one_line.bottom(), abs=px(view))
    k, want = _tl._to_parent(item, _tl.box_frame_points(item)[1]), landed(view, KNEE)
    assert (k.x(), k.y()) == pytest.approx((want.x(), want.y()), abs=px(view) * 1.5)
    assert item.to_dict()["y"] == pytest.approx(box.top(), abs=1e-6)     # the save sees it


def test_a_printed_schematic_note_sizes_by_its_own_scale(schematic):
    _w, _view, _scene, _proj, item = _schematic_note(schematic, "L")
    assert item.data.wrap_width_mm == pytest.approx(60.0 * SCHEMATIC_SCALE)
    assert item.data.height_mm == pytest.approx(3.0 * SCHEMATIC_SCALE)


def test_a_real_size_schematic_note_sizes_by_the_project_scale(schematic):
    """60 mm printed is 2400 mm at the project's 1:40, with 120 mm text beside it."""
    w, view, scene, _proj = schematic
    scene.set_block_meta({k: v for k, v in scene.block_meta.items()
                          if k not in ("text_sizing", "text_scale")}, push_undo=False)
    scene.scale_manager.drawing_scale = 40.0
    _w, _view, _scene, _proj2, item = _schematic_note(schematic, "L")
    assert item.data.wrap_width_mm == pytest.approx(60.0 * 40.0)
    assert item.data.height_mm == pytest.approx(3.0 * 40.0)


LEADER = {"edge": "R", "t": 0.5, "shoulder_mm": 40.0, "tip_x": -900.0, "tip_y": 700.0,
          "end": "none", "weight": ""}


def _schematic_with(proj, data):
    prims = [{"type": "line", "x1": 0.0, "y1": 0.0, "x2": 200.0, "y2": 0.0},
             {"type": "text", "text": "N", "x": 0.0, "y": 0.0, "height_mm": 10.0, **data}]
    d = BlockDefinition.new(name="S", library="", series="", origin=(0.0, 0.0),
                            primitives=prims, kind="schematic")
    proj.register_block_definition(d)
    return d


def _proj():
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_space import Model_Space
    from firepro3d.scale_manager import ScaleManager
    proj = Model_Space()
    proj._level_manager = LevelManager()
    proj.scale_manager = ScaleManager()
    return proj


def test_the_extent_holds_a_leader_past_the_drawing(qapp):
    proj = _proj()
    d = _schematic_with(proj, {"wrap_width_mm": 80.0, "box_height_mm": 20.0,
                               "leader": normalise(dict(LEADER))})
    mgr = SchematicSceneManager(proj)
    mgr.scene_for(d.id)
    r = mgr.extent(d.id)
    assert r.contains(-900.0, 700.0)


def test_a_text_with_no_leader_keeps_the_extent_it_had(qapp):
    proj = _proj()
    d = _schematic_with(proj, {"wrap_width_mm": 80.0, "box_height_mm": 20.0})
    mgr = SchematicSceneManager(proj)
    mgr.scene_for(d.id)
    r = mgr.extent(d.id)
    assert r.width() < 400.0 and r.height() < 200.0


@pytest.mark.parametrize("scale", [10.0, 0.0])
def test_a_note_placed_by_clicks_prints_at_its_printed_height(schematic, tmp_path, scale):
    """The whole path: three clicks in a Printed schematic, saved, on a sheet, in a PDF.
    Scale 0 is an NTS viewport. Cap height read from the PDF, 3 mm authored."""
    w, view, scene, proj, item = _schematic_note(schematic, "L")
    item.setPlainText("H")
    scene._text_edit_ctl.commit()
    item.data.color = "#000000"
    item.data.leader["end"] = "none"                     # glyph ink only in the fill scan
    defn = w.commit_block("Noted", "", "")
    sheet, res, _mgr, data = _sheet(proj, defn, scale)
    path = tmp_path / f"note_{scale}.pdf"
    export_pdf([sheet], res, str(path))
    assert _cap_mm(path, data) == pytest.approx(3.0, abs=0.15)


def test_middle_ink_is_centred_in_the_exported_pdf(qapp, tmp_path):
    """AC3's PDF half: glyph ink against the box border, both read from the file. A 3 mm text
    with a descender in a 20 mm box, printed at 1:10 from a 1:20 schematic."""
    proj = _proj()
    proj.scale_manager.drawing_scale = 20.0
    w, _t = _editor(proj, "printed", text="Hgy", height_mm=60.0, valign="M", color="#000000",
                    wrap_width_mm=800.0, box_height_mm=400.0, border=True, x=0.0, y=0.0)
    defn = w.commit_block("Centred", "", "")
    sheet, res, _mgr, data = _sheet(proj, defn, 10.0)
    path = tmp_path / "centred.pdf"
    export_pdf([sheet], res, str(path))
    ink = _fills(path, data)
    assert ink
    top, bottom = min(d["rect"].y0 for d in ink), max(d["rect"].y1 for d in ink)
    frame = max(_strokes(path, data), key=lambda d: d["rect"].height)["rect"]
    above, below = (top - frame.y0) * _MM_PER_PT, (frame.y1 - bottom) * _MM_PER_PT
    assert above > 0.5 and above == pytest.approx(below, abs=0.15)
