"""Flip / Mirror / Scale act on block instances (design DD8, AC1/AC2)."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.transform_ghost import reflect_transform
from tests._modify_tools_helpers import add_primitive, grips
from tests._snap_polish_helpers import click, close_view
from tests.test_modify_tools_flip_mirror import (AXIS_X, _axis_line,
                                                 _capture_status, _hover_and_click)
from tests.test_modify_tools_scale import _type_factor, make_view


def _block(scene, at=(-150.0, -150.0), **kw):
    d = BlockDefinition.new(name="B", library="L", series="S", origin=(0.0, 0.0),
                            primitives=[{"type": "draw_line", "pt1": [0, 0], "pt2": [40, 0],
                                         "color": "#ffffff", "lineweight": 1.0},
                                        {"type": "draw_line", "pt1": [0, 0], "pt2": [0, -20],
                                         "color": "#ffffff", "lineweight": 1.0}])
    scene.register_block_definition(d)
    return scene.place_block_instance(d.id, at, **kw)


def _ends(scene, inst):
    return sorted({(round(p.x(), 3), round(p.y(), 3))
                   for k, p, _n in scene._snap_engine._collect(inst) if k == "endpoint"})


def _reflected(ends):
    """*ends* mapped across the ``_axis_line`` (x = AXIS_X) by the ghost's own
    ``reflect_transform`` -- the reflection the commit must reproduce."""
    t = reflect_transform(QPointF(AXIS_X, -500), QPointF(AXIS_X, 500))
    return sorted({(round(q.x(), 3), round(q.y(), 3))
                   for q in (t.map(QPointF(x, y)) for x, y in ends)})


@pytest.mark.parametrize("role", ["plan", "block_editor"])
def test_flip_reflects_a_block_instance(qapp, role):
    view, scene = make_view(role=role, scale=1.0)
    try:
        _axis_line(scene)
        inst = _block(scene)
        inst.set_block_rotation(30.0)
        scene.push_undo_state()         # baseline holds the placed block
        before = inst.to_dict()
        src_ends = _ends(scene, inst)           # rotated 30: reflect, don't hand-compute
        p0 = scene._undo_pos
        scene.clearSelection()
        inst.setSelected(True)
        msgs = _capture_status(scene)
        assert scene._modify_ctl.start("flip") is True                        # [RED] refused today
        _hover_and_click(view)
        assert _ends(scene, inst) == _reflected(src_ends)
        assert "Flipped 1 item(s)" in msgs[-1] and "skipped" not in msgs[-1]
        assert scene._undo_pos == p0 + 1        # exactly one undo step
        scene.undo()                    # one step; restore rebuilds the instances
        (back,) = scene._block_instances
        assert back.to_dict() == before         # pos, rotation, mirrored restored
    finally:
        close_view(view, scene)


def _mirror_via_tool(view, scene, inst, at=None):
    scene.clearSelection()
    inst.setSelected(True)
    assert scene._modify_ctl.start("mirror") is True
    _hover_and_click(view) if at is None else _hover_and_click(view, at)


@pytest.mark.parametrize("role", ["plan", "block_editor"])
def test_mirror_makes_a_posed_copy(qapp, role):
    """Mirror copies the WHOLE pose through ``place_kwargs`` (DD7) and then
    reflects the copy: a mirrored, rotated, scaled, offset source on its own
    level gives a new-uid copy that is unmirrored, keeps level / offset /
    scale, and whose posed endpoints are the source's reflection."""
    view, scene = make_view(role=role, scale=1.0)
    try:
        _axis_line(scene)
        inst = _block(scene, level="Level 2", level_offset_mm=300.0)
        inst.set_block_rotation(30.0)
        inst.set_block_mirrored(True)           # mirrored source -> unmirrored copy
        inst.set_block_scale(2.0)
        scene.active_level = "Level 3"          # the copy must NOT adopt this
        scene.push_undo_state()                 # baseline holds the posed source
        before = inst.to_dict()
        src_ends = _ends(scene, inst)
        p0 = scene._undo_pos
        _mirror_via_tool(view, scene, inst)
        assert scene._undo_pos == p0 + 1        # exactly one undo step
        assert len(scene._block_instances) == 2
        copy = [i for i in scene._block_instances if i is not inst][0]
        assert copy._uid != inst._uid
        # place_kwargs must carry mirrored=True so the reflect toggles it OFF (M2a)
        assert copy.block_mirrored() is False and inst.block_mirrored() is True
        assert copy.level == "Level 2"
        assert copy.to_dict()["level_offset_mm"] == pytest.approx(300.0)
        assert copy.block_scale() == pytest.approx(2.0)
        assert _ends(scene, copy) == _reflected(src_ends)   # posed endpoints (M2a)
        assert inst.to_dict() == before         # the source is untouched
        scene.undo()                            # one step removes only the copy
        (back,) = scene._block_instances
        assert back.to_dict() == before
    finally:
        close_view(view, scene)


def test_mirroring_a_mirrored_block_gives_an_unmirrored_copy(qapp):
    view, scene = make_view(role="plan", scale=1.0)
    try:
        _axis_line(scene)
        inst = _block(scene)
        inst.set_block_mirrored(True)
        _mirror_via_tool(view, scene, inst)
        copy = [i for i in scene._block_instances if i is not inst][0]
        assert inst.block_mirrored() is True and copy.block_mirrored() is False
    finally:
        close_view(view, scene)


def _ground(scene, inst):
    c = scene.constraint_ctl.add("coincident", [{"uid": inst._uid, "h": "ins"},
                                                {"ref": "origin"}])
    assert c is not None
    return (inst.block_pos(), inst.block_mirrored(), inst.block_rotation())


def test_flip_refuses_a_grounded_block(qapp):
    """A fully defined block refuses Flip the way it refuses Scale / Rotate
    (D17): the WHOLE commit is refused -- a free line selected alongside is
    not flipped either -- with no undo step and the selection kept."""
    from firepro3d.constraint_controller import GROUNDED_STATUS
    view, scene = make_view(role="block_editor", scale=1.0)
    try:
        _axis_line(scene)
        inst = _block(scene, at=(10.0, 0.0))
        pose = _ground(scene, inst)
        line, _ = add_primitive(scene, "line")            # (0,0)-(100,0), free
        line_grips = grips(line)
        scene.push_undo_state()
        p0 = scene._undo_pos
        scene.clearSelection()
        inst.setSelected(True)
        line.setSelected(True)
        msgs = _capture_status(scene)
        assert scene._modify_ctl.start("flip") is True
        _hover_and_click(view)
        assert GROUNDED_STATUS in msgs                                        # [RED]
        assert (inst.block_pos(), inst.block_mirrored(), inst.block_rotation()) == pose
        assert grips(line) == line_grips        # the free line is refused too
        assert scene._undo_pos == p0 and scene.mode in (None, "select")
        assert inst.isSelected() and line.isSelected()
    finally:
        close_view(view, scene)


def test_mirror_of_a_grounded_block_still_copies(qapp):
    view, scene = make_view(role="block_editor", scale=1.0)
    try:
        _axis_line(scene)
        inst = _block(scene, at=(10.0, 0.0))
        pose = _ground(scene, inst)
        _mirror_via_tool(view, scene, inst)
        assert len(scene._block_instances) == 2
        copy = [i for i in scene._block_instances if i is not inst][0]
        assert copy.block_mirrored()
        assert (inst.block_pos(), inst.block_mirrored(), inst.block_rotation()) == pose
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("axis_kind, kept", [("vertical", True), ("diagonal", False)])
def test_mirror_remaps_a_block_line_horizontal_and_keeps_the_d30_rule(qapp, axis_kind, kept):
    """A Horizontal between a block's insertion point and a line follows the
    copies across a vertical axis and is dropped across a 45 degree one (D30)."""
    from firepro3d.geometry_2d import ReferenceLineItem
    from tests._modify_tools_helpers import add_primitive
    view, scene = make_view(role="block_editor", scale=1.0)
    try:
        if axis_kind == "vertical":
            _axis_line(scene)
            at = None
        else:
            rl = ReferenceLineItem(QPointF(0, 100), QPointF(200, 300))
            scene.addItem(rl)
            scene._reference_lines.append(rl)
            at = QPointF(100, 200)
        inst = _block(scene, at=(-150.0, 0.0))
        line, _ = add_primitive(scene, "line")            # (0,0)-(100,0), selected
        ctl = scene.constraint_ctl
        assert ctl.add("horizontal", [{"uid": inst._uid, "h": "ins"},
                                      {"uid": line._uid, "h": "p1"}]) is not None
        scene.clearSelection()
        inst.setSelected(True)
        line.setSelected(True)
        assert scene._modify_ctl.start("mirror") is True
        _hover_and_click(view) if at is None else _hover_and_click(view, at)
        copy = [i for i in scene._block_instances if i is not inst][0]
        types = [c.type for c in ctl.constraints_on(copy)]
        assert types == (["horizontal"] if kept else [])                      # [RED]
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("role", ["plan", "block_editor"])
def test_scale_scales_a_block_instance(qapp, role):
    view, scene = make_view(role=role, scale=1.0)
    try:
        inst = _block(scene, at=(10.0, 0.0))
        scene.push_undo_state()
        before = inst.to_dict()
        p0 = scene._undo_pos
        scene.clearSelection()
        inst.setSelected(True)
        assert scene._modify_ctl.start("scale") is True                       # [RED]
        click(view, QPointF(0, 0))
        _type_factor(scene, "2")
        assert inst.block_pos() == pytest.approx((20.0, 0.0))
        assert _ends(scene, inst) == sorted([(20.0, 0.0), (100.0, 0.0), (20.0, -40.0)])
        assert scene._undo_pos == p0 + 1
        scene.undo()
        (back,) = scene._block_instances
        assert back.block_scale() == 1.0 and back.block_pos() == (10.0, 0.0)
        assert back.to_dict() == before
    finally:
        close_view(view, scene)


def test_scale_by_one_on_a_block_is_a_no_op(qapp):
    view, scene = make_view(role="plan", scale=1.0)
    try:
        inst = _block(scene, at=(10.0, 0.0))
        scene.push_undo_state()
        p0, n0 = scene._undo_pos, len(scene._undo_stack)
        scene.clearSelection()
        inst.setSelected(True)
        msgs = _capture_status(scene)
        scene._modify_ctl.start("scale")
        click(view, QPointF(0, 0))
        _type_factor(scene, "1")
        assert msgs[-1] == "Scale factor is 1 — nothing changed"
        assert (scene._undo_pos, len(scene._undo_stack)) == (p0, n0)
        assert inst.block_scale() == 1.0 and inst.block_pos() == (10.0, 0.0)
    finally:
        close_view(view, scene)


def _forced_rollback(scene, monkeypatch):
    ctl = scene.constraint_ctl
    monkeypatch.setattr(ctl, "enabled", True)
    monkeypatch.setattr(ctl, "touches", lambda items: True)
    monkeypatch.setattr(ctl, "_solve", lambda **kw: False)       # force the D10 rollback
    return ctl


def test_rolled_back_flip_restores_the_whole_pose(qapp, monkeypatch):
    view, scene = make_view(role="block_editor", scale=1.0)
    try:
        inst = _block(scene, at=(10.0, 0.0))
        inst.set_block_rotation(30.0)
        ctl = _forced_rollback(scene, monkeypatch)
        with ctl.edit([inst]):
            inst.manip_reflect(QPointF(50, -1), QPointF(50, 1))
        assert (inst.block_pos(), inst.block_mirrored(), inst.block_rotation()) == \
            ((10.0, 0.0), False, 30.0)                                              # [RED]
    finally:
        close_view(view, scene)


def test_rolled_back_scale_restores_the_scale(qapp, monkeypatch):
    view, scene = make_view(role="block_editor", scale=1.0)
    try:
        inst = _block(scene, at=(10.0, 0.0))
        inst.set_block_rotation(30.0)
        ctl = _forced_rollback(scene, monkeypatch)
        with ctl.edit([inst]):
            inst.manip_scale_about(QPointF(0, 0), 2.0)
        assert inst.block_scale() == 1.0 and inst.block_pos() == (10.0, 0.0)
        assert inst.block_rotation() == 30.0       # [RED]
    finally:
        close_view(view, scene)
