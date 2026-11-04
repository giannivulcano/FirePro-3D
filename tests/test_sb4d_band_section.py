"""SB4d guard 2 (section half): 12,000 projected items never reach the
gridline / datum / hosted-block z (D5: GRID / GRID / TAG band)."""
from PyQt6.QtWidgets import QGraphicsRectItem

from firepro3d.constants import Z_ANNOT_GRID, Z_ANNOT_TAG, Z_ANNOT_TEXT
from tests._hosted_blocks_helpers import defn, gridline
from tests.test_section_classification import _placed_scene


def _host(ms, gl, **kw):
    h = {"gridline": gl._uid, "offset_mm": 0.0, "along_mm": 1000.0,
         "elevation_mm": 500.0, "facing": 1}
    h.update(kw)
    return ms.place_block_instance(defn(ms).id, (0, 0), host=h)


def test_guard2_twelve_thousand_projected_items_stay_below_every_annotation(qapp, section_scene_for):
    from firepro3d.section_scene import ElevDatumItem, ElevGridlineItem, _HostedBlockCopy
    ms, sec = _placed_scene(section_scene_for, (0, 0), (10000, 0), 8000.0)
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    gridline(ms, (5000, -3000), (5000, 3000), "X")                # crosses the cut: an ElevGridlineItem
    near = _host(ms, gl, offset_mm=0.0, along_mm=1000.0)          # d = 3000
    far = _host(ms, gl, offset_mm=2000.0, along_mm=2000.0)        # d = 5000
    sec.rebuild()
    grids = [i for i in sec.items() if isinstance(i, (ElevGridlineItem, ElevDatumItem))]
    copies = {c.data(0x0100): (c.parentItem() or c) for c in sec.items()
              if isinstance(c, _HostedBlockCopy)}
    assert any(isinstance(i, ElevGridlineItem) for i in grids)
    assert any(isinstance(i, ElevDatumItem) for i in grids)
    assert set(copies) == {near, far}
    filler = [QGraphicsRectItem(0.0, 0.0, 1.0, 1.0) for _ in range(12_000)]
    for i, it in enumerate(filler):
        sec.addItem(it)
        sec._register_depth_item(float(i), it)
    sec._assign_depth_z_values()
    top_depth = max(it.zValue() for it in filler)
    assert top_depth < Z_ANNOT_TEXT
    assert {it.zValue() for it in grids} == {Z_ANNOT_GRID}
    for top in copies.values():
        assert Z_ANNOT_TAG <= top.zValue() < Z_ANNOT_GRID
        assert top.zValue() > top_depth
    assert copies[far].zValue() < copies[near].zValue()            # near over far, inside the band
