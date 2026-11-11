"""Elevation parity area C: the section is a modify host (design D2).

Hosted-block copies in a section are write-back copies of plan-store model
blocks; the section's modify tools change the MODEL block (pose + host
record). Fixture: ``test_hosted_blocks_edit._setup`` -- placed section
(0,0)-(10000,0), depth 8000; gridline B (0,-3000)-(6000,-3000); block "A"
placed at section (2500, -1200) -> host along 2500, elevation 1200.
"""
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d import hosted_blocks as hb
from firepro3d.section_marker import SectionMarker
from tests._modify_tools_helpers import ignore_os_mouse
from tests._snap_polish_helpers import click, move
from tests.test_hosted_blocks_edit import _setup

PLACED_ALONG, PLACED_ELEV = 2500.0, 1200.0        # _setup's QPointF(2500, -1200)


def _section(ms, a, b, look, depth=8000.0, name="S2"):
    """Another section over the same model, rebuilt once."""
    from firepro3d.section_scene import SectionScene
    m = SectionMarker(name, QPointF(*a), QPointF(*b), look, depth)
    s = SectionScene(m, ms, ms._level_manager, ms.scale_manager)
    s.rebuild()
    return s


def _same_side(ms):
    """Parallel section, same side as _setup's (gridline B 2000 mm deep)."""
    return _section(ms, (0, -1000), (10000, -1000), 1, name="Same")


def _far_side(ms):
    """Parallel section looking from gridline B's other side (3000 mm deep)."""
    return _section(ms, (0, -6000), (10000, -6000), -1, name="Far")


def _pose(cp):
    return (round(cp.block_pos()[0], 3), round(cp.block_pos()[1], 3),
            round(cp.block_rotation(), 3), cp.block_mirrored(),
            round(cp.block_scale(), 6))


def _inverse(sec, cp, src, old_xy):
    """The candidate write-back (probe only): inverse of section_pose."""
    gl = sec._ms.gridline_by_uid(src.host["gridline"])
    back = hb.facing_of(sec._basis, gl) != int(src.host.get("facing", 1))
    x, y = cp.block_pos()
    src.host["along_mm"] = (float(src.host["along_mm"])
                            + (x - old_xy[0]) * hb.h_sign(sec._basis, gl))
    src.host["elevation_mm"] = -y
    rot = cp.block_rotation()
    src.set_block_rotation(-rot if back else rot)
    src.set_block_mirrored(cp.block_mirrored() != back)
    src.set_block_scale(cp.block_scale() * sec._ppm())
    sec._ms._sync_hosted_blocks(gl)


def test_probe_hosted_pose_is_the_in_plane_pose(qapp, section_scene_for):
    """D2 step-1 probe: the model block's pose IS its pose in the host
    gridline's plane (front: as is; far side: rotation negated, mirror
    toggled -- hosted-blocks D4), and the inverse of that projection is
    exact for a rotate about an off-origin pivot, a mirror (front and far
    side) and a scale. So rotate / mirror / scale in a section are
    expressible in ``_pose_rot`` / ``_pose_mirrored`` / ``_pose_scale``.
    RED when: ``hosted_blocks.section_pose`` stops negating the far-side
    rotation (``-rotation if back else rotation`` -> ``rotation``)."""
    ms, sec, gl, inst = _setup(section_scene_for)
    same, far = _same_side(ms), _far_side(ms)
    inst.set_block_rotation(30.0)
    for s in (sec, same, far):
        s.rebuild()
    f, p, b = (s._hosted_copies[id(inst)] for s in (sec, same, far))
    assert (f.block_rotation(), f.block_mirrored()) == (30.0, False)
    assert (p.block_rotation(), p.block_mirrored()) == (30.0, False)
    assert (b.block_rotation(), b.block_mirrored()) == (-30.0, True)

    old = f.block_pos()                       # rotate 90 about 500 mm left
    f.manip_rotate(90.0, QPointF(old[0] - 500.0, old[1]))
    want = _pose(f)
    assert want[:3] == (2000.0, -1700.0, 120.0)      # 30 + 90; (500,0) turned up
    _inverse(sec, f, inst, old)
    for s in (sec, same, far):
        s.rebuild()
    f, p, b = (s._hosted_copies[id(inst)] for s in (sec, same, far))
    assert _pose(f) == want and _pose(p) == want
    assert b.block_rotation() == pytest.approx(-120.0) and b.block_mirrored()

    old = b.block_pos()                       # mirror in the FAR section
    b.manip_reflect(QPointF(old[0] + 100.0, 0.0), QPointF(old[0] + 100.0, -1000.0))
    want_far = _pose(b)
    _inverse(far, b, inst, old)
    for s in (sec, far):
        s.rebuild()
    assert _pose(far._hosted_copies[id(inst)]) == want_far

    f = sec._hosted_copies[id(inst)]           # scale x2 about an off-origin base
    old = f.block_pos()
    f.manip_scale_about(QPointF(old[0] - 100.0, old[1] + 100.0), 2.0)
    want = _pose(f)
    _inverse(sec, f, inst, old)
    sec.rebuild()
    assert _pose(sec._hosted_copies[id(inst)]) == want
    assert inst.block_scale() == pytest.approx(2.0)
