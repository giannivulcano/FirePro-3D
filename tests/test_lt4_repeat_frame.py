"""LT4 H4-b: shared capability frame; the repeat frame."""
from PyQt6.QtCore import QPointF

from firepro3d.block_editor import BlockEditorWidget
from firepro3d.capability_frame import CAPABILITY_FRAME_TAG, CapabilityFrameItem
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.repeat_frame import RepeatFrame
from firepro3d.tile_frame import TILE_FRAME_TAG, TileFrame, TileFrameItem


def _editor(*lines):
    w = BlockEditorWidget(Model_Space())
    for a, b in lines:
        w._add_primitive(LineItem(QPointF(a, 0), QPointF(b, 0)))
    return w, w.editor_scene


def test_both_frames_share_the_base_and_tag(qapp):
    assert TileFrameItem is TileFrame and TILE_FRAME_TAG == CAPABILITY_FRAME_TAG
    _, sc = _editor()
    sc.set_block_capability(("repeat", {"length": 9.0, "size": "drafting"}))
    f = sc.capability_frame_item()
    assert isinstance(f, RepeatFrame) and isinstance(f, CapabilityFrameItem)
    assert f.data(0) == CAPABILITY_FRAME_TAG
    sc.set_block_capability(("tile", {"w": 5.0, "h": 5.0, "row_shift": 0.0,
                                      "size": "model"}))
    assert isinstance(sc.capability_frame_item(), TileFrame)


def test_repeat_grip_sets_trailing_gap_and_clamps(qapp):
    _, sc = _editor((0, 6))
    sc.set_block_capability(("repeat", {"length": 9.0, "size": "drafting"}))
    f = sc.capability_frame_item()
    assert f.grip_points() == [QPointF(9.0, 0.0)]
    f.apply_grip(0, QPointF(14.0, 3.0))           # X only
    assert sc.block_repeat["length"] == 14.0
    f.apply_grip(0, QPointF(2.0, 0.0))            # below the content end (6)
    assert sc.block_repeat["length"] == 6.0


def test_frame_is_not_deletable_nor_a_snap_target(qapp):
    from firepro3d import snap_engine
    _, sc = _editor((0, 6))
    sc.set_block_capability(("repeat", {"length": 9.0, "size": "drafting"}))
    f = sc.capability_frame_item()
    sc.delete_items([f])
    assert f.scene() is sc
    assert CAPABILITY_FRAME_TAG in snap_engine._NON_TARGET_TAGS


def test_ring_paints_dashes_outside_the_frame(qapp):
    from PyQt6.QtGui import QImage, QPainter, QColor
    _, sc = _editor((0, 6))
    sc.set_block_capability(("repeat", {"length": 9.0, "size": "drafting"}))
    f = sc.capability_frame_item()
    img = QImage(400, 40, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.translate(100, 20)
    p.scale(10, 10)                               # 10 px / mm; frame x 0..9 -> px 100..190
    f.paint(p, None)
    p.end()
    # Left ring cell = x -9..0 mm -> px 10..100: its dash (-9..-3 mm) covers
    # px 10..70, its gap (-3..0 mm) px 70..100. Row 20 is the axis; px ~100 is
    # the frame's left edge (excluded). Rows 19/20 both checked (AA spread).
    def lit(x0, x1):
        return any(img.pixelColor(x, y).alpha() > 0
                   for x in range(x0, x1) for y in (19, 20))
    assert lit(15, 65)                            # ring dash painted
    assert not lit(75, 95)                        # ring gap empty
