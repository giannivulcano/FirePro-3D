"""P4 probes for gridline-hosted blocks (design D8/D9)."""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsRectItem

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_instance import BlockInstance


def _defn(ms):
    d = BlockDefinition.new(name="A", library="L", series="S",
        primitives=[{"type": "draw_line", "pt1": [0, 0], "pt2": [100, 0],
                     "color": "#ffffff", "lineweight": 1.0}], origin=(0.0, 0.0))
    ms.register_block_definition(d)
    return d


def test_block_instance_lives_in_section_scene(qapp, section_scene_for):
    """D8: a BlockInstance resolves + paints inside a SectionScene."""
    ms, sec = section_scene_for("north")
    d = _defn(ms)
    inst = BlockInstance(block_id=d.id, resolver=ms.get_block_definition)
    inst.set_block_pos(500.0, -1000.0)
    sec.addItem(inst)
    br = inst.boundingRect()
    assert br.width() > 50.0                        # the 100 mm line resolved
    assert inst.z_range_mm() is None or isinstance(inst.z_range_mm(), tuple)
    from PyQt6.QtGui import QImage, QPainter
    img = QImage(400, 400, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    sec.render(p, QRectF(0, 0, 400, 400), QRectF(0, -1200, 800, 400))
    p.end()                                       # no exception = paints


def test_paper_category_under_clip_parent(qapp, section_scene_for):
    """D8: paper_display categorises a clipped child BlockInstance as Blocks."""
    from firepro3d import paper_display
    ms, sec = section_scene_for("north")
    d = _defn(ms)
    clip = QGraphicsRectItem(QRectF(0, -5000, 300, 10000))
    clip.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, True)
    sec.addItem(clip)
    inst = BlockInstance(block_id=d.id, resolver=ms.get_block_definition)
    inst.setParentItem(clip)
    found = [it for it in sec.items(QRectF(-10, -5000, 400, 10000))
             if isinstance(it, BlockInstance)]
    assert found == [inst]
    assert paper_display._category_for_item(inst) == "Blocks"
    print("CLIP_PARENT_CATEGORY", paper_display._category_for_item(clip))


def test_snap_engine_on_section_lines(qapp, section_scene_for):
    """D9: does the plan snap engine see ElevGridlineItem / ElevDatumItem?"""
    ms, sec = section_scene_for("north")
    sec.rebuild()
    from firepro3d.section_scene import ElevDatumItem
    from firepro3d import snap_engine as se
    datums = [it for it in sec.items() if isinstance(it, ElevDatumItem)]
    assert datums, "the default level must project a datum"
    eng = se.SnapEngine()
    dat = datums[0]
    cands = eng._collect(dat)
    print("SNAP_COLLECT_DATUM", [(t, round(p.x(), 1), round(p.y(), 1)) for t, p, _ in cands])
    print("SNAP_IS_TARGET", se.is_snap_target(dat, skip_pipes=False))
    ln = dat.line()
    tip = dat.mapToScene(ln.p1())
    res = eng.find(tip + QPointF(1.0, 1.0), sec, QTransform())
    print("SNAP_FIND_RESULT", res)
