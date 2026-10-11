"""Flip / Mirror / Scale act on block instances (design DD8, AC1/AC2)."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from tests._snap_polish_helpers import click, close_view
from tests.test_modify_tools_flip_mirror import (AXIS_X, _axis_line,
                                                 _capture_status, _hover_and_click)
from tests.test_modify_tools_scale import _type_factor, make_view


def _block(scene, at=(-150.0, -150.0)):
    d = BlockDefinition.new(name="B", library="L", series="S", origin=(0.0, 0.0),
                            primitives=[{"type": "draw_line", "pt1": [0, 0], "pt2": [40, 0],
                                         "color": "#ffffff", "lineweight": 1.0},
                                        {"type": "draw_line", "pt1": [0, 0], "pt2": [0, -20],
                                         "color": "#ffffff", "lineweight": 1.0}])
    scene.register_block_definition(d)
    return scene.place_block_instance(d.id, at)


def _ends(scene, inst):
    return sorted({(round(p.x(), 3), round(p.y(), 3))
                   for k, p, _n in scene._snap_engine._collect(inst) if k == "endpoint"})


@pytest.mark.parametrize("role", ["plan", "block_editor"])
def test_flip_reflects_a_block_instance(qapp, role):
    view, scene = make_view(role=role, scale=1.0)
    try:
        _axis_line(scene)
        inst = _block(scene)
        scene.push_undo_state()         # baseline holds the placed block
        scene.clearSelection()
        inst.setSelected(True)
        msgs = _capture_status(scene)
        assert scene._modify_ctl.start("flip") is True                        # [RED] refused today
        _hover_and_click(view)
        mx = lambda x: 2 * AXIS_X - x
        assert _ends(scene, inst) == sorted([(mx(-150.0), -150.0), (mx(-110.0), -150.0),
                                             (mx(-150.0), -170.0)])
        assert "Flipped 1 item(s)" in msgs[-1] and "skipped" not in msgs[-1]
        scene.undo()                    # one step; restore rebuilds the instances
        (back,) = scene._block_instances
        assert back.block_mirrored() is False
    finally:
        close_view(view, scene)


def test_mirror_makes_a_posed_copy(qapp):
    view, scene = make_view(role="plan", scale=1.0)
    try:
        _axis_line(scene)
        inst = _block(scene)
        scene.clearSelection()
        inst.setSelected(True)
        scene._modify_ctl.start("mirror")
        _hover_and_click(view)
        assert len(scene._block_instances) == 2                               # [RED]
        copy = [i for i in scene._block_instances if i is not inst][0]
        assert copy.block_mirrored() and not inst.block_mirrored()
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("role", ["plan", "block_editor"])
def test_scale_scales_a_block_instance(qapp, role):
    view, scene = make_view(role=role, scale=1.0)
    try:
        inst = _block(scene, at=(10.0, 0.0))
        scene.clearSelection()
        inst.setSelected(True)
        assert scene._modify_ctl.start("scale") is True                       # [RED]
        click(view, QPointF(0, 0))
        _type_factor(scene, "2")
        assert inst.block_pos() == pytest.approx((20.0, 0.0))
        assert _ends(scene, inst) == sorted([(20.0, 0.0), (100.0, 0.0), (20.0, -40.0)])
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
        ctl = _forced_rollback(scene, monkeypatch)
        with ctl.edit([inst]):
            inst.manip_reflect(QPointF(50, -1), QPointF(50, 1))
        assert (inst.block_pos(), inst.block_mirrored(), inst.block_rotation()) == \
            ((10.0, 0.0), False, 0.0)                                              # [RED]
    finally:
        close_view(view, scene)


def test_rolled_back_scale_restores_the_scale(qapp, monkeypatch):
    view, scene = make_view(role="block_editor", scale=1.0)
    try:
        inst = _block(scene, at=(10.0, 0.0))
        ctl = _forced_rollback(scene, monkeypatch)
        with ctl.edit([inst]):
            inst.manip_scale_about(QPointF(0, 0), 2.0)
        assert inst.block_scale() == 1.0 and inst.block_pos() == (10.0, 0.0)       # [RED]
    finally:
        close_view(view, scene)
