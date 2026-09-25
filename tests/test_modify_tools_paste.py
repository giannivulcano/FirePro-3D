"""D5/D13: ghost on cursor, one click commits one paste; refusals are clean."""
import json
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from tests._modify_tools_helpers import PRIMITIVES, add_primitive, grips
from tests._snap_polish_helpers import click, close_view, make_view, move


def _esc(view):
    """The real Escape path: a key event to the view -> scene keyPressEvent."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    QTest.keyClick(view.viewport(), Qt.Key.Key_Escape)


def _copy_at(view, scene, base=QPointF(0, 0)):
    scene._modify_ctl.start("copy")
    click(view, base)


@pytest.mark.parametrize("name", list(PRIMITIVES))
def test_paste_one_click_translates_by_cursor_minus_base(qapp, name):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, name)
        before = grips(item)
        _copy_at(view, scene)
        base = QPointF(*json.loads(QApplication.clipboard().text())["base"])
        p0 = scene._undo_pos
        assert scene._modify_ctl.start("paste") is True
        assert scene.mode == "paste"
        assert scene._move_ghost_base                       # ghost armed at once
        move(view, QPointF(400, 300))
        assert scene._move_ghost                            # ghost rides the cursor
        click(view, QPointF(400, 300))
        lst = getattr(scene, attr)
        assert len(lst) == 2
        new = lst[-1]
        dx, dy = 400 - base.x(), 300 - base.y()
        exp = [(x + dx, y + dy) for (x, y) in before]
        assert grips(new) == pytest.approx(exp, abs=0.5)   # [RED]
        assert grips(item) == before                       # original untouched
        assert scene._undo_pos == p0 + 1
        assert new.isSelected() and not item.isSelected()
        assert scene.mode in (None, "select")
        assert scene._move_ghost == [] and scene._paste_payload is None
    finally:
        close_view(view, scene)


def test_paste_text(qapp):
    from firepro3d.text_item import TextAnnotationData, TextItem
    view, scene = make_view(scale=1.0)
    try:
        t = TextItem(TextAnnotationData(text="T", x=0.0, y=0.0, height_mm=20.0))
        scene.addItem(t); scene._texts.append(t); scene.push_undo_state()
        t.setSelected(True)
        scene._modify_ctl.write_clipboard([t], QPointF(0, 0))
        assert scene._modify_ctl.start("paste") is True
        move(view, QPointF(400, 300)); click(view, QPointF(400, 300))
        assert len(scene._texts) == 2
        d = scene._texts[-1].to_dict()
        assert (d["x"], d["y"]) == pytest.approx((400.0, 300.0), abs=0.5)
    finally:
        close_view(view, scene)


def test_paste_esc_cancels(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")
        _copy_at(view, scene)
        p0 = scene._undo_pos
        assert scene._modify_ctl.start("paste") is True
        _esc(view)                                          # real Esc path
        assert scene.mode in (None, "select")
        assert len(getattr(scene, attr)) == 1
        assert scene._undo_pos == p0
        assert scene._move_ghost == [] and scene._move_ghost_base == []
    finally:
        close_view(view, scene)


def test_paste_empty_clipboard_is_a_message(qapp):
    view, scene = make_view(scale=1.0)
    try:
        msgs = []
        scene._show_status = lambda m, timeout=5000: msgs.append(m)
        QApplication.clipboard().setText("")
        assert scene._modify_ctl.start("paste") is False    # [RED] (was TypeError)
        assert scene.mode in (None, "select")
        assert msgs and msgs[-1] == "Nothing to paste"
    finally:
        close_view(view, scene)


def test_paste_foreign_text_is_refused(qapp):
    view, scene = make_view(scale=1.0)
    try:
        QApplication.clipboard().setText(json.dumps([{"type": "draw_line"}]))
        assert scene._modify_ctl.start("paste") is False
        assert scene.mode in (None, "select")
    finally:
        close_view(view, scene)


def test_paste_2d_geometry_into_plan_is_refused(qapp):
    view, scene = make_view(role="block_editor", scale=1.0)
    plan_view, plan = make_view(role="plan", scale=1.0)
    try:
        add_primitive(scene, "line")
        _copy_at(view, scene)
        assert plan._modify_ctl.start("paste") is False     # [RED] C1
        assert plan.mode in (None, "select")
        assert plan._draw_lines == []
    finally:
        close_view(view, scene); close_view(plan_view, plan)


def test_paste_plan_entity_into_block_editor_is_refused(qapp):
    view, scene = make_view(role="block_editor", scale=1.0)
    try:
        QApplication.clipboard().setText(json.dumps(
            {"fp3d_clipboard": 1, "base": [0, 0], "scene_role": "plan",
             "items": [{"type": "node", "x": 0.0, "y": 0.0, "pipes": []}]}))
        assert scene._modify_ctl.start("paste") is False
        assert scene.mode in (None, "select")
    finally:
        close_view(view, scene)


def test_paste_hud_dx_dy(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")
        _copy_at(view, scene)
        scene._modify_ctl.start("paste")
        move(view, QPointF(5, 5))
        assert scene.begin_dynamic_input() is True
        scene.dynamic_input.editor("dX").setText("1000")
        scene.dynamic_input.editor("dY").setText("0")
        scene.dynamic_input._accept()
        assert len(getattr(scene, attr)) == 2
        new = getattr(scene, attr)[-1]
        assert grips(new)[0] == pytest.approx((1000.0, 0.0), abs=0.01)
        assert scene.mode in (None, "select")
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("kind", ["door", "wall"])
def test_paste_real_plan_record_into_block_editor_is_refused(qapp, kind):
    """D13 allow-list: a real plan record (not in the 2D registry) is refused
    in the Block Editor — no mode, no undo, the refusal message."""
    from firepro3d.geometry_2d import LineItem
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import DoorOpening
    rec = (DoorOpening().to_dict() if kind == "door"
           else WallSegment(QPointF(0, 0), QPointF(1000, 0)).to_dict())
    view, scene = make_view(role="block_editor", scale=1.0)
    try:
        msgs = []
        scene._show_status = lambda m, timeout=5000: msgs.append(m)
        QApplication.clipboard().setText(json.dumps(
            {"fp3d_clipboard": 1, "base": [0, 0], "scene_role": "plan",
             "items": [LineItem(QPointF(0, 0), QPointF(1, 0)).to_dict(), rec]}))
        p0 = scene._undo_pos
        assert scene._modify_ctl.start("paste") is False          # [RED]
        assert scene.mode in (None, "select")
        assert scene._undo_pos == p0
        assert msgs[-1] == "Plan elements can't be pasted into the Block Editor"
    finally:
        close_view(view, scene)


def test_paste_ghost_is_on_the_cursor_at_entry(qapp):
    """D5 'immediately': entering Paste after the cursor has moved shows the
    ghost at the cursor — no extra mouse move needed."""
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")                 # (0,0)-(100,0)
        scene._modify_ctl.write_clipboard([item], QPointF(0, 0))
        move(view, QPointF(400, 300))                             # cursor parked
        assert scene._modify_ctl.start("paste") is True
        assert scene._move_ghost                                  # [RED]
        br = scene._move_ghost[0].boundingRect()
        assert br.center().x() == pytest.approx(450.0, abs=2.0)
        assert br.center().y() == pytest.approx(300.0, abs=2.0)
    finally:
        close_view(view, scene)
