"""The scene Rotate tool rotates placed block instances (pre-merge fix).

Convention (observable screen truth): scene Y is down, angles are Y-up CCW+.
A +X point rotated +90 about the origin lands at scene (0, -100) — visually UP.
Rendered pixels (the item's own ``paint``) are the ground truth, not the
stored pose numbers.
"""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QStyleOptionGraphicsItem

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_instance import BlockInstance
from firepro3d.geometry_2d import LineItem
from tests._snap_polish_helpers import click, close_view, make_view


def _def(name, prims, origin=(0.0, 0.0)):
    return BlockDefinition.new(name=name, library="L", series="S",
                               primitives=prims, origin=origin)


def _line(x0, y0, x1, y1):
    return LineItem(QPointF(x0, y0), QPointF(x1, y1)).to_dict()


def _l_shape():
    """Asymmetric L: a 100 mm +X leg and a 40 mm visually-up leg."""
    return _def("L", [_line(0, 0, 100, 0), _line(0, 0, 0, -40)])


def _ink(item, pad=20):
    """Scene-space bbox (x0, y0, x1, y1) of the pixels ``item.paint`` inks."""
    r = item.sceneBoundingRect().adjusted(-pad, -pad, pad, pad)
    w, h = int(r.width()) + 1, int(r.height()) + 1
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    p.translate(-r.left(), -r.top())
    item.paint(p, QStyleOptionGraphicsItem(), None)
    p.end()
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            if (img.pixel(x, y) >> 24) & 0xFF:
                xs.append(x)
                ys.append(y)
    assert xs, "item painted nothing"
    return (r.left() + min(xs), r.top() + min(ys),
            r.left() + max(xs), r.top() + max(ys))


def _type_angle(scene, text):
    assert scene.begin_dynamic_input() is True
    scene.dynamic_input.editor("Angle").setText(text)
    scene.dynamic_input._accept()


# ── Unit: manip_rotate contract ──────────────────────────────────────────

def test_manip_rotate_90_about_origin_matches_fresh_render(qapp):
    d = _l_shape()
    reg = {d.id: d}.get
    inst = BlockInstance(block_id=d.id, resolver=reg)
    inst.set_block_pos(100.0, 0.0)
    inst.manip_rotate(90.0, QPointF(0.0, 0.0))
    assert inst.block_pos() == pytest.approx((0.0, -100.0), abs=1e-9)
    assert inst.block_rotation() == pytest.approx(90.0)
    fresh = BlockInstance(block_id=d.id, resolver=reg)
    fresh.set_block_pos(0.0, -100.0)
    fresh.set_block_rotation(90.0)
    got = _ink(inst)
    assert got == pytest.approx(_ink(fresh), abs=1.0)
    # Visual truth: the +X leg now points UP from (0,-100) to (0,-200); the
    # up leg now points LEFT (-X) 40 mm.
    assert got == pytest.approx((-40.0, -200.0, 0.0, -100.0), abs=2.0)


def test_manip_rotate_about_own_insertion_point_only_turns(qapp):
    d = _l_shape()
    inst = BlockInstance(block_id=d.id, resolver={d.id: d}.get)
    inst.set_block_pos(30.0, 40.0)
    inst.set_block_rotation(15.0)
    inst.manip_rotate(30.0, QPointF(30.0, 40.0))
    assert inst.block_pos() == pytest.approx((30.0, 40.0), abs=1e-9)
    assert inst.block_rotation() == pytest.approx(45.0)


# ── Real path: Modify > Rotate in a shown view (plan + Block Editor) ─────

@pytest.mark.parametrize("role", ["plan", "block_editor"])
def test_modify_rotate_tool_rotates_a_placed_block(qapp, role):
    view, scene = make_view(role=role, scale=1.0)
    try:
        d = _l_shape()
        scene.register_block_definition(d)
        inst = scene.place_block_instance(d.id, (100.0, 0.0))
        scene.push_undo_state()
        ink0 = _ink(inst)
        scene.clearSelection()
        inst.setSelected(True)
        p0 = scene._undo_pos
        scene._modify_ctl.start("rotate")
        click(view, QPointF(0, 0))                    # pivot
        click(view, QPointF(100, 0))                  # start ray (0 deg)
        click(view, QPointF(0, -100))                 # end ray (+90 Y-up)
        assert scene._undo_pos == p0 + 1              # exactly one undo step
        assert scene.mode in (None, "select")
        (inst,) = scene._block_instances
        assert inst.block_pos() == pytest.approx((0.0, -100.0), abs=1e-6)
        assert inst.block_rotation() == pytest.approx(90.0)
        assert _ink(inst) == pytest.approx((-40.0, -200.0, 0.0, -100.0), abs=2.0)
        # Ctrl+Z restores the original pose (item refs die on undo restore).
        view.setFocus(Qt.FocusReason.OtherFocusReason)
        QApplication.processEvents()
        QTest.keyClick(view.viewport(), Qt.Key.Key_Z,
                       Qt.KeyboardModifier.ControlModifier)
        QApplication.processEvents()
        assert scene._undo_pos == p0
        (inst,) = scene._block_instances
        assert inst.block_pos() == pytest.approx((100.0, 0.0), abs=1e-6)
        assert inst.block_rotation() == pytest.approx(0.0)
        assert _ink(inst) == pytest.approx(ink0, abs=1.0)
    finally:
        close_view(view, scene)


def test_typed_rotate_hud_rotates_a_placed_block(qapp):
    view, scene = make_view(role="plan", scale=1.0)
    try:
        d = _l_shape()
        scene.register_block_definition(d)
        inst = scene.place_block_instance(d.id, (100.0, 0.0))
        scene.push_undo_state()
        scene.clearSelection()
        inst.setSelected(True)
        p0 = scene._undo_pos
        scene._modify_ctl.start("rotate")
        click(view, QPointF(0, 0))
        _type_angle(scene, "90")
        assert scene._undo_pos == p0 + 1
        (inst,) = scene._block_instances
        assert _ink(inst) == pytest.approx((-40.0, -200.0, 0.0, -100.0), abs=2.0)
    finally:
        close_view(view, scene)


def test_rotating_a_nesting_parent_turns_the_nested_pixels(qapp):
    """A nests only B (a 40 mm visually-up leg at A-local (50, 0))."""
    view, scene = make_view(role="plan", scale=1.0)
    try:
        b = _def("B", [_line(0, 0, 0, -40)])
        scene.register_block_definition(b)
        a = _def("A", [{"type": "block_instance", "block_id": b.id,
                        "pos": [50.0, 0.0], "rotation": 0.0}])
        scene.register_block_definition(a)
        inst = scene.place_block_instance(a.id, (100.0, 0.0))
        # B leg before: x = 150, y in [-40, 0]
        assert _ink(inst) == pytest.approx((150.0, -40.0, 150.0, 0.0), abs=2.0)
        scene.push_undo_state()
        scene.clearSelection()
        inst.setSelected(True)
        scene._modify_ctl.start("rotate")
        click(view, QPointF(0, 0))
        _type_angle(scene, "90")
        (inst,) = scene._block_instances
        # (150, 0) -> (0, -150); the up leg now points LEFT: x in [-40, 0]
        assert _ink(inst) == pytest.approx((-40.0, -150.0, 0.0, -150.0), abs=2.0)
    finally:
        close_view(view, scene)
