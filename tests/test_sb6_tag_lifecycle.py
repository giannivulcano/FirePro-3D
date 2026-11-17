"""SB6 AC3 / AC4 / AC7 (paste) -- G4 host lifecycle through the real tools (Move,
Rotate, the wall's endpoint grip, Delete, Ctrl+Z, the property panel, Copy -> Paste).
Expected poses come from tests/_sb6_helpers.expected_pose: re-derived from the raw
wall endpoints and the door's stored offset_along, never from firepro3d.hosted_tag."""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from tests._ph1_helpers import ph1_cleanup  # noqa: F401
from tests._sb5_helpers import managed_scene
from tests._sb6_helpers import (U, V, add_door, add_wall, drop_panel, expected_pose,
                                panel_for, place_tag, pose_of, tags_of)
from tests._snap_polish_helpers import click, close_view, make_view, move

KINDS = ["wall", "door"]
ORIENTS = ["horizontal", "aligned"]


def _setup(kind, orient="horizontal"):
    view, scene = make_view(role="plan", scale=0.1)
    w = add_wall(scene)
    host = w if kind == "wall" else add_door(scene, w)
    scene.push_undo_state()
    return view, scene, w, host, place_tag(scene, host, orient)


def _type_angle(scene, text):
    assert scene.begin_dynamic_input() is True
    scene.dynamic_input.editor("Angle").setText(text)
    scene.dynamic_input._accept()


@pytest.mark.parametrize("orient", ORIENTS)
@pytest.mark.parametrize("kind", KINDS)
def test_g4_placed_pose_is_anchor_plus_offset(qapp, real_system_library, kind, orient):
    view, scene, w, host, tag = _setup(kind, orient)
    try:
        assert pose_of(tag) == pytest.approx(expected_pose(host, orient), abs=1e-6)   # [RED]
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("orient", ORIENTS)
@pytest.mark.parametrize("kind", KINDS)
def test_g4_move_tool_carries_the_tag(qapp, real_system_library, kind, orient):
    view, scene, w, host, tag = _setup(kind, orient)
    try:
        scene.clearSelection()
        w.setSelected(True)
        p0 = scene._undo_pos
        scene._modify_ctl.start("move")
        click(view, QPointF(0.0, 0.0))
        move(view, QPointF(300.0, 700.0))
        click(view, QPointF(300.0, 700.0))
        assert scene._undo_pos == p0 + 1
        assert (w.pt1.x(), w.pt1.y()) != (-2000.0, 0.0)             # the wall really moved
        assert pose_of(tag) == pytest.approx(expected_pose(host, orient), abs=1e-6)   # [RED]
        assert tag.tag["offset"] == pytest.approx([U, V])           # host frame kept (D2)
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("orient", ORIENTS)
@pytest.mark.parametrize("kind", KINDS)
def test_g4_rotate_tool_carries_the_tag(qapp, real_system_library, kind, orient):
    view, scene, w, host, tag = _setup(kind, orient)
    try:
        scene.clearSelection()
        w.setSelected(True)
        scene._modify_ctl.start("rotate")
        click(view, QPointF(-2000.0, 0.0))                          # pivot: the wall's start
        _type_angle(scene, "30")
        assert abs(w.pt2.y()) > 1.0                                  # really turned
        assert pose_of(tag) == pytest.approx(expected_pose(host, orient), abs=1e-6)   # [RED]
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("orient", ORIENTS)
@pytest.mark.parametrize("kind", KINDS)
def test_g4_wall_endpoint_grip_carries_the_tag(qapp, real_system_library, kind, orient):
    view, scene, w, host, tag = _setup(kind, orient)
    try:
        scene.clearSelection()
        w.setSelected(True)
        QApplication.processEvents()
        m = scene._live_manip()
        p0 = scene._undo_pos
        handle = w.manip_handles()[1]                                # pt2 endpoint grip
        g0, g1 = QPointF(w.grip_points()[1]), QPointF(2000.0, -1500.0)
        m._begin_handle(handle, g0, g0)
        m._update(g1, Qt.KeyboardModifier.NoModifier, g1)
        m._finish(g1, Qt.KeyboardModifier.NoModifier)
        assert scene._undo_pos == p0 + 1
        assert abs(w.pt2.y()) > 1.0
        assert pose_of(tag) == pytest.approx(expected_pose(host, orient), abs=1e-6)   # [RED]
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("kind", KINDS)
def test_g4_delete_cascades_in_one_step_and_one_undo_relinks(qapp, real_system_library, kind):
    view, scene, w, host, tag = _setup(kind)
    try:
        uid = host._uid
        scene.clearSelection()
        w.setSelected(True)
        p0 = scene._undo_pos
        QTest.keyClick(view.viewport(), Qt.Key.Key_Delete)
        assert scene._undo_pos == p0 + 1                             # one step
        assert tags_of(scene) == []                                  # [RED: cascade]
        QTest.keyClick(view.viewport(), Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        (t2,) = tags_of(scene)
        h2 = t2.element_host
        assert h2 is not None and h2._uid == uid and h2.scene() is scene
        assert pose_of(t2) == pytest.approx(expected_pose(h2), abs=1e-6)
    finally:
        close_view(view, scene)


def test_g4_mark_edit_through_the_panel_updates_the_tag_text(qapp, tmp_path, real_system_library):
    from tests.test_sb2a_binding import _painted_as
    view, scene, w, host, tag = _setup("door")
    pm = None
    try:
        pm = panel_for(host, tmp_path)
        p0 = scene._undo_pos
        r0 = tag.sceneBoundingRect()
        pm._apply_property("Mark", "D77777777")
        assert scene._undo_pos == p0 + 1
        ref = scene.place_block_instance(tag.block_id, tag.block_pos(), rotation=tag.block_rotation())
        assert _painted_as(tag, ref, {"Mark": "D77777777"})
        r1, rr = tag.sceneBoundingRect(), ref.sceneBoundingRect()
        assert (r1.x(), r1.y(), r1.width(), r1.height()) == pytest.approx(
            (rr.x(), rr.y(), rr.width(), rr.height()), abs=1e-6)       # the tag re-shaped to the new Mark
        assert r1.width() != pytest.approx(r0.width(), abs=1e-6)
    finally:
        drop_panel(pm)
        close_view(view, scene)


def test_g4_paste_alone_keeps_where_it_lands_on_the_original_host(qapp, real_system_library):
    view, scene, w, host, tag = _setup("wall")
    try:
        ctl = scene._modify_ctl
        assert ctl.write_clipboard([tag], QPointF(0.0, 0.0))
        assert ctl.begin_paste()
        ctl.commit_paste(QPointF(0.0, 8000.0))
        scene.push_undo_state()                                      # a further committed step re-poses
        new = [t for t in tags_of(scene) if t is not tag]
        assert len(new) == 1 and new[0]._host_uid == w._uid         # SB5 Q9: the live original host
        # raw: the original pose (U, V) on a horizontal wall through (0, 0), plus the (0, 8000) paste offset
        assert pose_of(new[0]) == pytest.approx((U, V + 8000.0, 0.0), abs=1e-6)       # [RED: rebase]
        assert new[0].tag["offset"] == pytest.approx([U, V + 8000.0])
        assert pose_of(tag) == pytest.approx(expected_pose(w), abs=1e-6)
    finally:
        close_view(view, scene)


def test_g4_paste_with_its_host_rebinds_to_the_copy(qapp, real_system_library):
    view, scene, w, host, tag = _setup("wall")
    try:
        ctl = scene._modify_ctl
        assert ctl.write_clipboard([w, tag], QPointF(0.0, 0.0))
        assert ctl.begin_paste()
        ctl.commit_paste(QPointF(0.0, 8000.0))
        scene.push_undo_state()
        (w2,) = [x for x in scene._walls if x is not w]
        (t2,) = [t for t in tags_of(scene) if t is not tag]
        assert t2._host_uid == w2._uid and t2._host_uid != w._uid
        assert t2.tag["offset"] == pytest.approx([U, V])
        assert pose_of(t2) == pytest.approx(expected_pose(w2), abs=1e-6)
    finally:
        close_view(view, scene)


def test_push_reposes_the_hosts_tags(qapp, real_system_library):
    from firepro3d import hosted_dependents
    ms = managed_scene()
    w = add_wall(ms)
    tag = place_tag(ms, w)
    w.translate(100.0, 250.0)
    hosted_dependents.push(ms, w)
    assert pose_of(tag) == pytest.approx(expected_pose(w), abs=1e-6)   # [RED: push branch]


def _swap_alt(ms, cat, name):
    """A project copy of the shipped *cat* tag under a new id (an eligible swap)."""
    import copy
    from firepro3d import block_library
    from firepro3d.assets import system_blocks_path
    from firepro3d.block_attributes import normalise_attr
    from firepro3d.block_definition import BlockDefinition
    src = block_library.load_block_file(system_blocks_path("Tags", f"{cat}Tag.fpdb"))
    d = BlockDefinition.new(name=name, library="", series="", origin=(0.0, 0.0),
                            primitives=copy.deepcopy(src.primitives))
    d.scale_mode = "annotative"
    d.host_category = cat
    d.attributes = [normalise_attr({"key": "Mark", "source": "host", "host_key": "Mark"})]
    ms.register_block_definition(d)
    return d


def test_swapped_block_survives_save_load_and_undo_redo(qapp, tmp_path, real_system_library):
    """Review (b): ``hosted_tag.resolve`` drops a swap whose definition is not yet
    registered -- load and undo restore must register definitions before the tags
    resolve, so a non-default swap is kept through both."""
    from tests._sb5_helpers import save_load
    ms = managed_scene()
    w = add_wall(ms)
    ms.push_undo_state()
    tag = place_tag(ms, w)
    alt = _swap_alt(ms, "Wall", "WallTagAlt")
    tag.tag["block"] = alt.id
    ms.push_undo_state()
    assert tag.block_id == alt.id
    ms.push_undo_state()                       # a no-op step: resolve must keep the swap
    (t,) = tags_of(ms)
    assert t.tag["block"] == alt.id and t.block_id == alt.id
    ms.undo()
    ms.redo()
    (t,) = tags_of(ms)
    assert t.tag["block"] == alt.id and t.block_id == alt.id      # undo -> redo keeps the swap
    out, _raw = save_load(ms, tmp_path)
    out.push_undo_state()                      # the first committed step after Open re-resolves
    (t,) = tags_of(out)
    assert t.tag["block"] == alt.id and t.block_id == alt.id      # save -> load keeps the swap


def test_i1_paste_of_a_leader_tag_loads_its_end_into_a_fresh_project(qapp, make_model_space,
                                                                     real_system_library):
    """VC9 I1: copy a wall + a leader tag, paste into a project that lacks the End definition
    -- the paste loads it, so the pasted leader's End is not an orphan."""
    from firepro3d.level_manager import LevelManager
    src = make_model_space()
    src._level_manager = LevelManager()
    w = add_wall(src)
    src.push_undo_state()
    tag = place_tag(src, w, leader=True)
    records = src._clipboard_item_dicts([w, tag])
    dst = make_model_space()
    dst._level_manager = LevelManager()
    assert dst.annotation_block("Wall") is not None               # the tag block is there (embedded on demand)
    end = tag.tag["leader"]["end"]
    assert end == "system-endtypes-arrow"                          # the tag's own End (D10)
    assert dst.get_block_definition(end) is None                     # the fresh project lacks the End
    dst.paste_items(QPointF(0.0, 8000.0), data=records)
    (t2,) = tags_of(dst)
    assert t2.tag["leader"] is not None
    assert dst.get_block_definition(end) is not None                 # [RED: ensure_end_available on paste]
