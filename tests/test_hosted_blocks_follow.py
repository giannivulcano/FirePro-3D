"""D5/D6: hosted blocks follow move/rotate/typed origin; grips 0/1/2/3 and
rename do not move them (G10)."""
import pytest
from PyQt6.QtCore import QPointF
from tests._hosted_blocks_helpers import gridline, defn


def _setup(ms):
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    d = defn(ms)
    inst = ms.place_block_instance(d.id, (0, 0), host={
        "gridline": gl._uid, "offset_mm": 200.0, "along_mm": 1500.0,
        "elevation_mm": 0.0, "facing": 1})
    return gl, inst


def test_translate_follows(qapp, make_model_space):
    ms = make_model_space(); gl, inst = _setup(ms)
    gl.translate(100.0, -50.0)
    assert inst.block_pos() == pytest.approx((1600.0, -3250.0))


def test_rotate_follows(qapp, make_model_space):
    ms = make_model_space(); gl, inst = _setup(ms)
    gl.manip_rotate(90.0, QPointF(0, -3000))
    assert inst.block_pos() == pytest.approx((-200.0, -4500.0))


def test_typed_origin_follows(qapp, make_model_space):
    ms = make_model_space(); gl, inst = _setup(ms)
    gl.set_property("Origin X", 300.0)
    assert inst.block_pos()[0] == pytest.approx(1800.0)


def test_typed_origin_y_and_angle_follow(qapp, make_model_space):
    ms = make_model_space(); gl, inst = _setup(ms)
    gl.set_property("Origin Y", 2000.0)          # world Y 3000 -> 2000
    assert inst.block_pos() == pytest.approx((1500.0, -2200.0))
    gl.set_property("Angle", 90.0)               # u=(0,1), n=(-1,0) about origin (0,2000)
    assert inst.block_pos() == pytest.approx((-200.0, -3500.0))


def test_perpendicular_moves_follow(qapp, make_model_space):
    ms = make_model_space(); gl, inst = _setup(ms)
    x0, y0 = inst.block_pos()
    gl.move_perpendicular(100.0)
    x1, y1 = inst.block_pos()
    assert (x1 - x0) ** 2 + (y1 - y0) ** 2 == pytest.approx(100.0 ** 2)
    assert x1 == pytest.approx(x0)               # horizontal line: perpendicular is vertical
    gl.set_perpendicular_position(-3000.0 * gl._perpendicular_vector()[1])
    assert inst.block_pos() == pytest.approx((1500.0, -3200.0))


def test_locked_gridline_keeps_blocks(qapp, make_model_space):
    ms = make_model_space(); gl, inst = _setup(ms)
    before = inst.block_pos()
    gl.locked = True
    gl.translate(100.0, 100.0)
    gl.manip_rotate(45.0, QPointF(0, 0))
    gl.set_property("Origin X", 999.0)
    gl.move_perpendicular(50.0)
    assert inst.block_pos() == pytest.approx(before)


@pytest.mark.parametrize("grip,pt", [(0, (-700, -3000)), (0, (900, -3000)),
                                     (1, (9000, -3000)), (2, (-500, -3000)),
                                     (3, (7000, -3000))])
def test_grips_do_not_move_blocks(qapp, make_model_space, grip, pt):
    ms = make_model_space(); gl, inst = _setup(ms)
    before = inst.block_pos()
    gl.apply_grip(grip, QPointF(*pt))
    assert inst.block_pos() == pytest.approx(before)


def test_rename_keeps_host(qapp, make_model_space):
    ms = make_model_space(); gl, inst = _setup(ms)
    gl.set_property("Label", "Z")
    assert ms.hosted_blocks_on(gl) == [inst]
    assert inst.block_pos() == pytest.approx((1500.0, -3200.0))
