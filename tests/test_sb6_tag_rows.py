"""SB6 AC6 / AC3 (Aligned) -- the panel's Tag row swaps among same-category blocks in
one undoable step; a host category change re-resolves to the new default and drops the
swap (R8); the Orientation row turns a tag with its host and keep_upright keeps the
Mark readable. Raw sources: block ids in firepro3d/system_blocks/Tags/*.fpdb, the
feature id "window_900" (feature.py), the raw wall endpoints."""
import copy

import pytest
from PyQt6.QtCore import QPointF

from tests._sb6_helpers import (LEADER, add_door, add_wall, drop_panel, expected_pose, panel_for,
                                place_tag, pose_of, tags_of)
from tests._snap_polish_helpers import close_view, make_view


def _alt(ms, cat, name):
    """A project copy of the shipped *cat* tag under a new id (an eligible swap)."""
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


def test_ac6_tag_row_swaps_undoably_and_a_category_change_re_resolves(qapp, tmp_path, real_system_library):
    view, scene = make_view(role="plan", scale=0.1)
    pm = None
    try:
        w = add_wall(scene)
        add_door(scene, w)
        scene.push_undo_state()
        tag = place_tag(scene, w.openings[0])
        assert tag.block_id == "system-tags-doortag"
        alt = _alt(scene, "Door", "DoorTagAlt")
        pm = panel_for(tag, tmp_path)
        props = tag.get_properties()
        assert "DoorTagAlt (Project)" in props["Tag"]["options"]
        assert "Rotation" not in props and "Mirrored" not in props
        p0 = scene._undo_pos
        pm._apply_property("Tag", "DoorTagAlt (Project)")
        assert scene._undo_pos == p0 + 1                                   # one undoable step
        assert tag.block_id == alt.id and tag.tag["block"] == alt.id      # [RED]
        pm.show_properties(None)
        scene.undo()
        (t,) = tags_of(scene)
        assert t.block_id == "system-tags-doortag" and t.tag["block"] is None
        scene.redo()
        (t,) = tags_of(scene)
        assert t.block_id == alt.id
        scene._walls[0].openings[0].set_property("Feature", "window_900")   # door -> window; pushes
        assert t.block_id == "system-tags-windowtag"                       # [RED: re-resolve]
        assert t.tag["block"] is None                                      # the Door swap is dropped (R8)
    finally:
        drop_panel(pm)
        close_view(view, scene)


def _scene_glyphs(inst):
    """Every TEXT op's glyph path in the scene, as paint draws it."""
    from firepro3d.render_op import TEXT
    xf = inst.pose_transform()
    return [xf.map(inst._text_path(op)) for op in inst.render_ops() if op.kind == TEXT]


def _same(paths_a, paths_b, tol):
    if len(paths_a) != len(paths_b) or not paths_a:
        return False
    for a, b in zip(paths_a, paths_b):
        if a.elementCount() != b.elementCount():
            return False
        for i in range(a.elementCount()):
            ea, eb = a.elementAt(i), b.elementAt(i)
            if abs(ea.x - eb.x) > tol or abs(ea.y - eb.y) > tol:
                return False
    return True


def test_ac3_aligned_row_turns_with_the_host_and_reads_upright(qapp, tmp_path, real_system_library):
    view, scene = make_view(role="plan", scale=0.1)
    pm = None
    try:
        # a = atan2(2000, -4000) = 153.43 deg (scene): an Aligned tag would read upside down
        w = add_wall(scene, p1=(2000.0, -1000.0), p2=(-2000.0, 1000.0))
        scene.push_undo_state()
        tag = place_tag(scene, w)
        pm = panel_for(tag, tmp_path)
        p0 = scene._undo_pos
        pm._apply_property("Orientation", "Aligned to host")
        assert scene._undo_pos == p0 + 1
        x, y, rot = expected_pose(w, "aligned")
        assert pose_of(tag) == pytest.approx((x, y, rot), abs=1e-6)       # [RED: rotation()]
        # keep_upright: the Mark is turned 180 deg about its centred box, so it draws
        # exactly as an upright placement at rot + 180 (whose text needs no flip)
        ref = scene.place_block_instance(tag.block_id, (x, y), rotation=rot + 180.0)
        ref.set_attributes({"Mark": "W1"})
        assert _same(_scene_glyphs(tag), _scene_glyphs(ref), tol=1e-3)   # [RED: keep_upright]
    finally:
        drop_panel(pm)
        close_view(view, scene)


def test_leader_row_toggles_the_record_in_one_step(qapp, tmp_path, real_system_library):
    view, scene = make_view(role="plan", scale=0.1)
    pm = None
    try:
        w = add_wall(scene)
        scene.push_undo_state()
        tag = place_tag(scene, w)
        pm = panel_for(tag, tmp_path)
        p0 = scene._undo_pos
        pm._apply_property("Leader", True)
        assert tag.tag["leader"] == LEADER and scene._undo_pos == p0 + 1
        pm._apply_property("Leader", False)
        assert tag.tag["leader"] is None and scene._undo_pos == p0 + 2
    finally:
        drop_panel(pm)
        close_view(view, scene)


def _reading_angle_deg(inst, op):
    """Effective reading direction (Y-up degrees, scene) of a TEXT op as paint draws it:
    the vector from the first glyph to the last glyph, both laid out and posed in the
    scene. First / last come from the op's authored (unflipped) outline, so a 180 turn
    shows up as a reversed vector."""
    import math
    from PyQt6.QtCore import QPointF
    def centre(poly):
        r = poly.boundingRect()
        return QPointF(r.center())
    authored = [centre(p) for p in op.path.toSubpathPolygons()]
    drawn = inst._text_path(op).toSubpathPolygons()
    assert len(authored) == len(drawn) and len(drawn) >= 2
    first = min(range(len(authored)), key=lambda i: authored[i].x())
    last = max(range(len(authored)), key=lambda i: authored[i].x())
    xf = inst.pose_transform()
    a = xf.map(centre(drawn[first]))
    b = xf.map(centre(drawn[last]))
    return math.degrees(math.atan2(-(b.y() - a.y()), b.x() - a.x()))


def test_aligned_tag_on_a_right_to_left_wall_reads_upright(qapp, tmp_path, real_system_library):
    """Review (a): an Aligned tag on a right-to-left wall (~153 deg) reads upright --
    asserted on the laid-out text in the scene (keep_upright), not on the stored
    rotation: the first -> last glyph reading vector points to the right half-plane
    (effective angle in (-90, 90]) while the tag itself is turned ~-153 deg."""
    import math
    from firepro3d.render_op import TEXT
    view, scene = make_view(role="plan", scale=0.1)
    pm = None
    try:
        w = add_wall(scene, p1=(2000.0, -1000.0), p2=(-2000.0, 1000.0), mark="W12")
        scene.push_undo_state()
        tag = place_tag(scene, w)
        pm = panel_for(tag, tmp_path)
        pm._apply_property("Orientation", "Aligned to host")
        a = math.degrees(math.atan2(2000.0, -4000.0))
        assert a == pytest.approx(153.43, abs=0.01)
        assert tag.block_rotation() == pytest.approx(-a, abs=1e-6)        # turned with the wall
        ops = [op for op in tag.render_ops() if op.kind == TEXT]
        assert ops
        for op in ops:
            assert -90.0 < _reading_angle_deg(tag, op) <= 90.0
    finally:
        drop_panel(pm)
        close_view(view, scene)


def test_tag_panel_has_no_scale_row_but_a_plain_block_does(qapp, real_system_library):
    view, scene = make_view(role="plan", scale=0.1)
    try:
        w = add_wall(scene)
        scene.push_undo_state()
        tag = place_tag(scene, w)
        plain = scene.place_block_instance(tag.block_id, (0.0, 0.0))
        assert "Scale" in plain.get_properties()
        assert "Scale" not in tag.get_properties()                          # [RED: _tag_rows]
        assert "Rotation" not in tag.get_properties()
    finally:
        close_view(view, scene)


def test_orientation_row_on_a_door_poses_the_tag_along_the_sloped_wall(qapp, tmp_path, real_system_library):
    """M3: Aligned on a door in a sloped wall -- raw pose from the wall endpoints +
    the door's offset_along; rotation = -degrees(wall angle); the Mark reads upright."""
    import math
    from firepro3d.render_op import TEXT
    view, scene = make_view(role="plan", scale=0.1)
    pm = None
    try:
        w = add_wall(scene, p1=(2000.0, -1000.0), p2=(-2000.0, 1000.0))   # a ~153.43 deg
        door = add_door(scene, w, along=1200.0)
        scene.push_undo_state()
        tag = place_tag(scene, door)
        pm = panel_for(tag, tmp_path)
        pm._apply_property("Orientation", "Aligned to host")
        a = math.atan2(2000.0, -4000.0)
        x1, y1 = 2000.0, -1000.0
        ax, ay = x1 + 1200.0 * math.cos(a), y1 + 1200.0 * math.sin(a)
        ex = ax + 500.0 * math.cos(a) - (-800.0) * math.sin(a)
        ey = ay + 500.0 * math.sin(a) + (-800.0) * math.cos(a)
        assert pose_of(tag) == pytest.approx((ex, ey, -math.degrees(a)), abs=1e-6)
        ops = [op for op in tag.render_ops() if op.kind == TEXT]
        assert ops
        for op in ops:
            assert -90.0 < _reading_angle_deg(tag, op) <= 90.0
    finally:
        drop_panel(pm)
        close_view(view, scene)
