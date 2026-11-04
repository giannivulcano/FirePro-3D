"""Seam fix item 7: guards the acceptance sweep found missing (tests only)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt

from firepro3d import text_leader as _tl
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_editor import BlockEditorWidget
from firepro3d.manip_handle import GripHandle
from firepro3d.model_space import Model_Space
from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
from firepro3d.render_op import STROKE
from firepro3d.text_item import TextAnnotationData, TextItem
from tests.test_text_leader_fixes import _lit_scene_rect

LEADER = {"edge": "R", "t": 0.5, "shoulder_mm": 6.0, "tip_x": 200.0, "tip_y": 60.0,
          "end": "none", "weight": ""}


def _text(**kw):
    return TextItem(TextAnnotationData(text="n", wrap_width_mm=30.0, box_height_mm=10.0,
                                       height_mm=3.0, color="#ffffff", **kw))


def _editor(kind, scale=100.0):
    proj = Model_Space()
    w = BlockEditorWidget(proj, kind=kind)
    w.editor_scene.scale_manager.drawing_scale = scale
    return proj, w, w.editor_scene


# -- the Leader row, reached through the real panel, on the editor canvases --------

@pytest.mark.parametrize("kind", ["block", "schematic"])
def test_the_leader_row_toggled_through_the_panel_draws_in_the_editor(
        qapp, real_system_library, kind):
    """Build > Text with Leader on: the row is reachable on a Block Editor and a
    Schematic canvas and the toggle draws shoulder, leader and the End (D12)."""
    proj, w, sc = _editor(kind)
    try:
        item = _text()
        sc.addItem(item)
        sc._texts.append(item)
        assert "Leader" in item.get_properties() and "Leader End" not in item.get_properties()
        area = QRectF(-60, -60, 700, 700)
        before = _lit_scene_rect(sc, area)
        item.set_property("Leader", True)                  # the panel's own commit path
        assert item.data.leader and "Leader End" in item.get_properties()
        after = _lit_scene_rect(sc, area)
        assert after.width() > before.width() + 20 or after.height() > before.height() + 20
        assert [o for o in _stroke_ops(item)]              # and the shared stroke op exists
    finally:
        sc.cleanup()


def _stroke_ops(item):
    from firepro3d.block_definition import text_box_ops
    from PyQt6.QtGui import QTransform
    _under, over = text_box_ops(item, QTransform())
    return [o for o in over if o.kind == STROKE and len(o.pieces) == 2]


# -- grip drags undo ------------------------------------------------------------------

def _drag(m, handle, target):
    start = handle.scene_position(m._rect)
    m._begin_handle(handle, start, QPointF(0, 0))
    m._moved = True
    handle.on_drag(m, target, Qt.KeyboardModifier.NoModifier)
    handle.on_release(m, target, Qt.KeyboardModifier.NoModifier)


@pytest.mark.parametrize("grip", ["LEADER_TIP_GRIP", "LEADER_KNEE_GRIP"])
def test_a_block_editor_text_leader_grip_drag_is_one_undo_step_and_undoes(qapp, grip):
    proj, w, sc = _editor("block")
    try:
        item = _text(leader=dict(LEADER))
        sc.addItem(item)
        sc._texts.append(item)
        sc.push_undo_state()                                 # baseline
        before = dict(item.data.leader)
        depth = len(sc._undo_stack)
        item.setSelected(True)
        m = sc._live_manip()
        m.rebake()
        idx = getattr(TextItem, grip)
        h = next(h for h in m._active_handles()
                 if isinstance(h, GripHandle) and h.item is item and h.index == idx)
        _drag(m, h, QPointF(150.0, 80.0))
        assert item.data.leader != before
        assert len(sc._undo_stack) == depth + 1
        sc.undo()
        back = sc._texts[0]
        assert back.data.leader == before
    finally:
        sc.cleanup()


def test_a_note_knee_grip_drag_is_one_undo_step_and_undoes(shown_model_view, real_system_library):
    from firepro3d.system_blocks import NOTE_BLOCK_ID
    from tests.test_note_edit import LEADER as NLEADER, _drag as _ndrag, _grip_handle, _note
    view, ms = shown_model_view
    inst = _note(ms, leader=NLEADER)
    before = dict(inst.note["leader"])
    depth = len(ms._undo_stack)
    m, h = _grip_handle(ms, inst, "knee")
    _ndrag(m, h, QPointF(0.0, -700.0))
    assert inst.note["leader"]["edge"] == "T"
    assert len(ms._undo_stack) == depth + 1
    ms.undo()
    again = next(i for i in ms._block_instances if i.note)
    assert again.note["leader"] == before


# -- file save and reload ---------------------------------------------------------------

def test_a_definition_leader_survives_a_file_save_and_reload_and_still_draws(qapp, tmp_path):
    rec = _text(leader=dict(LEADER)).to_dict()
    d = BlockDefinition.new(name="T", library="L", series="S", origin=(0.0, 0.0),
                            primitives=[rec])
    ms = Model_Space()
    ms.register_block_definition(d)
    ms.place_block_instance(d.id, (0.0, 0.0))
    path = str(tmp_path / "def.FPD")
    assert ms.save_to_file(path)
    back = Model_Space()
    back.load_from_file(path)
    (inst,) = back._block_instances
    assert back.get_block_definition(d.id).primitives[0]["leader"] == LEADER
    strokes = [o for o in inst.render_ops() if o.kind == STROKE and len(o.pieces) == 2]
    assert len(strokes) == 1
    tip = strokes[0].pieces[-1]
    assert (tip.x1, tip.y1) == pytest.approx((LEADER["tip_x"], LEADER["tip_y"]))


def test_a_sheet_text_leader_survives_a_file_save_and_reload_and_still_draws(qapp, tmp_path):
    ms = Model_Space()
    sheet = Sheet.create_default()
    ms._sheets = [sheet]
    sheet.annotations.append(TextAnnotationData(
        text="s", x=20.0, y=20.0, wrap_width_mm=40.0, box_height_mm=12.0, height_mm=3.0,
        leader=dict(LEADER, tip_x=90.0, tip_y=60.0)))
    path = str(tmp_path / "sheet.FPD")
    assert ms.save_to_file(path)
    back = Model_Space()
    back.load_from_file(path)
    (ann,) = back._sheets[0].annotations
    assert ann.leader["tip_x"] == 90.0 and ann.leader["edge"] == "R"
    paper = PaperScene(back._sheets[0], ViewResolver(back, None, None, None))
    items = [i for i in paper.items() if isinstance(i, TextItem) and i.data.leader]
    assert len(items) == 1
    assert len(_tl.leader_pieces(items[0])) == 2             # shoulder and leader still resolve
    assert len(_stroke_ops(items[0])) == 1                   # and the shared stroke op is built
