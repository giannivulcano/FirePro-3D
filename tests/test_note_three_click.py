"""Notes design N20 to N24: the Note tool places by tip, elbow, box edge."""
import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsRectItem

from firepro3d import text_leader as _tl
from firepro3d.constants import TEXT_LEADER_MIN_SHOULDER_MM
from firepro3d.system_blocks import NOTE_BLOCK_ID
from firepro3d.text_item import editing_text_item
from firepro3d.text_leader import attach_and_knee, box_from_clicks
from tests._note_helpers import click, key, mouse
from tests.test_note_instance import leader_op

W, H, MIN = 6000.0, 700.0, 200.0
K = QPointF(1000.0, 500.0)


@pytest.mark.parametrize("click, edge, want_attach", [
    (QPointF(1800.0, 700.0), "L", (1800.0, 500.0)),       # right of the elbow: the box's left edge
    (QPointF(200.0, 300.0), "R", (200.0, 500.0)),         # left of it: the right edge
    (QPointF(1100.0, 1400.0), "T", (1000.0, 1400.0)),     # below: the top edge
    (QPointF(900.0, -300.0), "B", (1000.0, -300.0)),      # above: the bottom edge
])
def test_the_click_names_the_edge_and_only_its_axis_counts(click, edge, want_attach):
    box, rec = box_from_clicks(K, click, W, H, MIN)
    assert rec["edge"] == edge
    a, k = attach_and_knee(box, rec)
    assert (a.x(), a.y()) == pytest.approx(want_attach)
    assert (k.x(), k.y()) == pytest.approx((K.x(), K.y()))       # the record lands on the elbow


def test_a_diagonal_tie_takes_a_side_edge():
    assert box_from_clicks(K, QPointF(1300.0, 800.0), W, H, MIN)[1]["edge"] == "L"
    assert box_from_clicks(K, QPointF(700.0, 200.0), W, H, MIN)[1]["edge"] == "R"


@pytest.mark.parametrize("click, edge, far", [
    (QPointF(1050.0, 510.0), "L", "left"),
    (QPointF(950.0, 490.0), "R", "right"),
    (QPointF(1010.0, 550.0), "T", "top"),
    (QPointF(990.0, 450.0), "B", "bottom"),
    (K, "L", "left"),                                     # a click on the elbow itself
])
def test_a_short_click_lands_at_the_minimum_shoulder(click, edge, far):
    box, rec = box_from_clicks(K, click, W, H, MIN)
    assert rec["edge"] == edge and rec["shoulder_mm"] == MIN
    a, k = attach_and_knee(box, rec)
    assert (k.x(), k.y()) == pytest.approx((K.x(), K.y()))
    assert abs(a.x() - k.x()) + abs(a.y() - k.y()) == pytest.approx(MIN)


@pytest.mark.parametrize("click", [QPointF(1800.0, 500.0), QPointF(200.0, 500.0),
                                   QPointF(1000.0, 1400.0), QPointF(1000.0, -300.0)])
def test_the_box_keeps_its_size_and_extends_away_from_the_elbow(click):
    box, _rec = box_from_clicks(K, click, W, H, MIN)
    assert (box.width(), box.height()) == (W, H)
    assert not box.contains(K)


# -- G4: posted clicks through a shown view ---------------------------------------

PLAN, DETAIL = "plan:Plan: Level 1", "detail:D1"
TIP, KNEE = QPointF(-1400.0, -1000.0), QPointF(-500.0, -300.0)
THIRD = {"L": QPointF(100.0, -100.0), "R": QPointF(-1200.0, -100.0),
         "T": QPointF(-400.0, 800.0), "B": QPointF(-600.0, -1100.0)}


def landed(view, pt):
    """Where a click at *pt* really lands: the view rounds to a whole pixel."""
    return view.mapToScene(view.mapFromScene(pt))


def px(view):
    """Scene mm of one view pixel: the tolerance of a posted click."""
    return 1.0 / view.transform().m11()


def three_clicks(view, scene, tip=TIP, knee=KNEE, third=THIRD["L"]):
    click(view, tip)
    click(view, knee)
    click(view, third)


def assert_drawn_on_clicks(view, drawn_tip, drawn_knee, drawn_attach, edge, third):
    """The drawn leader against the clicks, not against the tool's own record."""
    tol = px(view) * 1.5
    want_tip, want_knee = landed(view, TIP), landed(view, KNEE)
    want = landed(view, third)
    assert (drawn_tip.x(), drawn_tip.y()) == pytest.approx((want_tip.x(), want_tip.y()), abs=tol)
    assert (drawn_knee.x(), drawn_knee.y()) == pytest.approx((want_knee.x(), want_knee.y()), abs=tol)
    if edge in ("L", "R"):
        assert drawn_attach.x() == pytest.approx(want.x(), abs=tol)      # the click's axis
        assert drawn_attach.y() == pytest.approx(drawn_knee.y(), abs=1e-6)   # perpendicular
    else:
        assert drawn_attach.y() == pytest.approx(want.y(), abs=tol)
        assert drawn_attach.x() == pytest.approx(drawn_knee.x(), abs=1e-6)


@pytest.mark.parametrize("edge", ["L", "R", "T", "B"])
@pytest.mark.parametrize("key_", [PLAN, DETAIL], ids=["plan", "detail"])
def test_g4_three_posted_clicks_draw_tip_knee_and_edge_where_they_landed(
        shown_model_view, real_system_library, key_, edge):
    view, scene = shown_model_view
    scene.active_view_key = key_
    scene.set_mode("note")
    three_clicks(view, scene, third=THIRD[edge])
    inst = scene._block_instances[-1]
    assert inst.block_id == NOTE_BLOCK_ID and inst.note["view"] == key_
    assert editing_text_item(scene) is scene._note_ctl.overlay      # the editor opens at once
    scene._note_ctl.overlay.setPlainText("Hold")
    scene._text_edit_ctl.commit()
    op = leader_op(inst)
    pose = inst.pose_transform()
    a, k, tip = (pose.map(QPointF(op.pieces[0].x0, op.pieces[0].y0)),
                 pose.map(QPointF(op.pieces[0].x1, op.pieces[0].y1)),
                 pose.map(QPointF(op.pieces[1].x1, op.pieces[1].y1)))
    assert_drawn_on_clicks(view, tip, k, a, edge, THIRD[edge])
    box, tol = inst.note_box_scene(), px(view) * 1.5
    side = {"L": box.left(), "R": box.right(), "T": box.top(), "B": box.bottom()}[edge]
    want = landed(view, THIRD[edge])
    assert side == pytest.approx(want.x() if edge in "LR" else want.y(), abs=tol)
    assert box.contains(k) is False                                 # extends away from the elbow


def test_the_box_starts_60_printed_wide_and_one_line_tall(shown_model_view, real_system_library):
    view, scene = shown_model_view
    scene.active_view_key = PLAN
    scene.set_mode("note")
    three_clicks(view, scene)
    inst = scene._block_instances[-1]
    k = scene.scale_manager.drawing_scale
    box = inst.note_box_scene()
    assert box.width() == pytest.approx(60.0 * k)
    # One 3 mm Arial line plus 1 mm padding each way: about 7.2 printed mm, under the old 10 floor.
    scene._note_ctl.overlay.setPlainText("Hold")
    scene._text_edit_ctl.commit()
    assert inst.note_box_scene().height() == pytest.approx(box.height())   # one typed line fits
    assert 5.0 * k < box.height() < 9.0 * k


def test_a_short_third_click_lands_at_the_minimum_shoulder_in_printed_mm(
        shown_model_view, real_system_library):
    view, scene = shown_model_view
    scene.active_view_key = PLAN
    scene.set_mode("note")
    three_clicks(view, scene, third=KNEE + QPointF(40.0, 0.0))
    inst = scene._block_instances[-1]
    assert inst.note["leader"]["shoulder_mm"] == TEXT_LEADER_MIN_SHOULDER_MM
    k = scene.scale_manager.drawing_scale
    box = inst.note_box_scene()
    assert box.left() - landed(view, KNEE).x() == pytest.approx(
        TEXT_LEADER_MIN_SHOULDER_MM * k, abs=px(view) * 1.5)


@pytest.mark.parametrize("step", [0, 1, 2])
def test_g4_esc_before_the_third_click_leaves_nothing(shown_model_view, real_system_library, step):
    view, scene = shown_model_view
    scene.active_view_key = PLAN
    before = set(scene.items())
    depth = len(scene._undo_stack)
    scene.set_mode("note")
    for pt in (TIP, KNEE)[:step]:
        click(view, pt)
    key(view, Qt.Key.Key_Escape)
    assert scene.mode != "note"
    assert not [i for i in scene._block_instances if i.note]
    assert not [i for i in set(scene.items()) - before
                if isinstance(i, (QGraphicsPathItem, QGraphicsRectItem)) and i.isVisible()]
    assert len(scene._undo_stack) == depth


def test_g4_esc_in_the_empty_editor_leaves_nothing(shown_model_view, real_system_library):
    view, scene = shown_model_view
    scene.active_view_key = PLAN
    depth = len(scene._undo_stack)
    scene.set_mode("note")
    three_clicks(view, scene)
    assert editing_text_item(scene) is not None
    key(view, Qt.Key.Key_Escape)
    assert editing_text_item(scene) is None
    assert not [i for i in scene._block_instances if i.note]
    assert len(scene._undo_stack) == depth


def test_snap_applies_at_each_click(shown_model_view, real_system_library):
    view, scene = shown_model_view
    scene.active_view_key = PLAN
    tip_node, knee_node = scene.add_node(-1400.0, -1000.0), scene.add_node(-500.0, -300.0)
    edge_node = scene.add_node(300.0, -100.0)
    scene.set_mode("note")
    click(view, tip_node.scenePos() + QPointF(24.0, 16.0))      # inside the 80 mm aperture
    click(view, knee_node.scenePos() + QPointF(-16.0, 24.0))
    click(view, edge_node.scenePos() + QPointF(20.0, -20.0))
    inst = scene._block_instances[-1]
    tip = inst.note_tip_scene()
    assert (tip.x(), tip.y()) == pytest.approx((-1400.0, -1000.0), abs=1e-6)  # exact, not the click
    knee = inst._note_knee_scene()
    assert (knee.x(), knee.y()) == pytest.approx((-500.0, -300.0), abs=1e-6)
    assert inst.note_box_scene().left() == pytest.approx(300.0, abs=1e-6)
    scene._text_edit_ctl.commit()


# -- N24: preview and per-step anchor ---------------------------------------------

def _move(view, pt):
    mouse(view, QEvent.Type.MouseMove, pt, buttons=Qt.MouseButton.NoButton,
          button=Qt.MouseButton.NoButton)


def test_the_preview_runs_tip_to_cursor_then_tip_elbow_attach_with_the_box(
        shown_model_view, real_system_library):
    view, scene = shown_model_view
    scene.active_view_key = PLAN
    scene.set_mode("note")
    ctl = scene._note_ctl
    click(view, TIP)
    cursor = QPointF(-300.0, 200.0)
    _move(view, cursor)
    path, tol = ctl._tool_line.path(), px(view) * 1.5
    assert path.elementCount() == 2
    assert path.elementAt(1).x == pytest.approx(landed(view, cursor).x(), abs=tol)
    assert ctl._tool_box is None
    click(view, KNEE)
    third = THIRD["L"]
    _move(view, third)
    path = ctl._tool_line.path()
    assert path.elementCount() == 3
    assert path.elementAt(1).x == pytest.approx(landed(view, KNEE).x(), abs=tol)
    assert path.elementAt(2).x == pytest.approx(landed(view, third).x(), abs=tol)     # the attach
    assert path.elementAt(2).y == pytest.approx(path.elementAt(1).y)                  # perpendicular
    r = ctl._tool_box.rect()
    assert r.left() == pytest.approx(landed(view, third).x(), abs=tol)
    assert r.width() == pytest.approx(60.0 * scene.scale_manager.drawing_scale)
    scene.set_mode(None)


def test_a_project_reset_mid_note_leaves_no_preview_and_no_clicks(
        shown_model_view, real_system_library):
    view, scene = shown_model_view
    scene.active_view_key = PLAN
    scene.set_mode("note")
    click(view, TIP)
    click(view, KNEE)
    _move(view, THIRD["L"])
    line, box = scene._note_ctl._tool_line, scene._note_ctl._tool_box
    scene._clear_scene()
    assert scene._note_ctl.tool_anchor() is None and scene._note_ctl._tool_line is None
    assert line.scene() is None and box.scene() is None


def test_the_anchor_follows_the_step(shown_model_view, real_system_library):
    view, scene = shown_model_view
    scene.active_view_key = PLAN
    scene.set_mode("note")
    assert scene.get_placement_anchor() is None
    click(view, TIP)
    assert scene.get_placement_anchor() == landed(view, TIP)
    click(view, KNEE)
    assert scene.get_placement_anchor() == landed(view, KNEE)
    scene.set_mode(None)
    assert scene.get_placement_anchor() is None


def test_the_step_prompts_name_the_next_click(shown_model_view, real_system_library):
    view, scene = shown_model_view
    scene.active_view_key = PLAN
    seen = []
    scene.instructionChanged.connect(seen.append)
    scene.set_mode("note")
    click(view, TIP)
    click(view, KNEE)
    assert seen[-3:] == ["Pick arrow tip", "Pick elbow", "Pick box edge"]
    scene.set_mode(None)


# -- N23: while typing -------------------------------------------------------------

def _type_lines(view, scene, n):
    """Type *n* lines through the live editor's real key path."""
    for i in range(n):
        if i:
            key(view, Qt.Key.Key_Return)
        for k in (Qt.Key.Key_H, Qt.Key.Key_O, Qt.Key.Key_L, Qt.Key.Key_D):
            key(view, k)


@pytest.mark.parametrize("edge", ["L", "R"])
def test_n23_a_side_edge_keeps_the_shoulder_on_the_first_line_as_the_box_grows(
        shown_model_view, real_system_library, edge):
    view, scene = shown_model_view
    scene.active_view_key = PLAN
    scene.set_mode("note")
    three_clicks(view, scene, third=THIRD[edge])
    inst = scene._block_instances[-1]
    ov = scene._note_ctl.overlay
    one_line = inst.note_box_scene()
    _type_lines(view, scene, 3)
    assert ov.toPlainText().count("\n") == 2
    live = _tl.box_frame_points(ov)
    want_y = landed(view, KNEE).y()
    assert _tl._to_parent(ov, live[1]).y() == pytest.approx(want_y, abs=px(view) * 1.5)   # live
    scene._text_edit_ctl.commit()
    box = inst.note_box_scene()
    assert box.height() > one_line.height() * 2.0            # the box grew
    assert box.top() == pytest.approx(one_line.top())        # downward
    op = leader_op(inst)
    pose = inst.pose_transform()
    a = pose.map(QPointF(op.pieces[0].x0, op.pieces[0].y0))
    k = pose.map(QPointF(op.pieces[0].x1, op.pieces[0].y1))
    assert k.y() == pytest.approx(want_y, abs=px(view) * 1.5)     # the drawn shoulder did not leave
    assert a.y() == pytest.approx(k.y(), abs=1e-6)                # and it is still perpendicular
    assert a.y() - box.top() == pytest.approx(one_line.height() / 2.0, abs=px(view) * 1.5)


def test_n23_a_top_edge_stays_put_and_the_box_grows_away(shown_model_view, real_system_library):
    view, scene = shown_model_view
    scene.active_view_key = PLAN
    scene.set_mode("note")
    three_clicks(view, scene, third=THIRD["T"])
    inst = scene._block_instances[-1]
    _type_lines(view, scene, 3)
    scene._text_edit_ctl.commit()
    k = inst._note_knee_scene()
    want = landed(view, KNEE)
    assert (k.x(), k.y()) == pytest.approx((want.x(), want.y()), abs=px(view) * 1.5)


def test_n23_a_re_edit_holds_a_dragged_shoulder_too(shown_model_view, real_system_library):
    view, scene = shown_model_view
    scene.active_view_key = PLAN
    scene.set_mode("note")
    three_clicks(view, scene)
    inst = scene._block_instances[-1]
    scene._note_ctl.overlay.setPlainText("Hold")
    scene._text_edit_ctl.commit()
    before = inst._note_knee_scene()
    scene._note_ctl.begin(inst)
    scene._note_ctl.overlay.setPlainText("one\ntwo\nthree")
    scene._text_edit_ctl.commit()
    assert inst._note_knee_scene().y() == pytest.approx(before.y(), abs=1e-3)


def test_a_multi_line_note_saves_the_followed_fraction(shown_model_view, real_system_library):
    view, scene = shown_model_view
    scene.active_view_key = PLAN
    scene.set_mode("note")
    three_clicks(view, scene)
    inst = scene._block_instances[-1]
    _type_lines(view, scene, 3)
    scene._text_edit_ctl.commit()
    rec = inst.to_dict()["note"]["leader"]
    assert rec["t"] < 0.3                                          # no longer mid-height
    scene.undo()
    scene.redo()
    again = [i for i in scene._block_instances if i.note][-1]
    assert again.note["leader"]["t"] == rec["t"]


def test_the_hud_measures_each_step_from_its_own_point_and_a_typed_step_places(
        shown_model_view, real_system_library):
    view, scene = shown_model_view
    scene.active_view_key = PLAN
    scene.set_mode("note")
    _move(view, TIP)
    assert scene.dynamic_input is None                  # the first click has nothing to measure from
    click(view, TIP)
    _move(view, QPointF(-1000.0, -600.0))                # off the ALIGN rays: the line schema
    tip = landed(view, TIP)
    assert scene.dynamic_input is not None
    scene.begin_dynamic_input()
    scene.dynamic_input.set_values({"Length": 900.0, "Angle": 0.0})
    scene.dynamic_input._accept()
    knee = scene.get_placement_anchor()
    assert (knee.x(), knee.y()) == pytest.approx((tip.x() + 900.0, tip.y()))
    _move(view, knee + QPointF(400.0, 250.0))
    scene.begin_dynamic_input()
    scene.dynamic_input.set_values({"Length": 700.0, "Angle": 0.0})
    scene.dynamic_input._accept()
    inst = scene._block_instances[-1]
    assert inst.note_box_scene().left() == pytest.approx(knee.x() + 700.0)
    assert editing_text_item(scene) is scene._note_ctl.overlay
    assert scene.dynamic_input is None
    key(view, Qt.Key.Key_H)                             # the keyboard reached the editor
    assert scene._note_ctl.overlay.toPlainText().lower() == "h"
    scene._text_edit_ctl.commit()
