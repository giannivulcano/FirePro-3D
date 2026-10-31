"""Paste mints a fresh Mark for each pasted floor void (floor-opening A2, AC7).
Mirrors tests/test_sb2b_paste_l1410.py (wall + door).  Raw: "O{n}" (DEFAULT_PATTERNS)."""
from PyQt6.QtCore import QPointF

from firepro3d import marks
from firepro3d.floor_opening import FloorOpening
from firepro3d.floor_slab import FloorSlab

SQ = [QPointF(0, 0), QPointF(3000, 0), QPointF(3000, 2000), QPointF(0, 2000)]
HOLE = [QPointF(1000, 500), QPointF(2000, 500), QPointF(2000, 1500), QPointF(1000, 1500)]


def test_paste_slab_with_void_mints_a_fresh_opening_mark(qapp, shown_model_view):
    """GUARD AC7: RED without the paste mint (the copy keeps the source's O1)."""
    view, scene = shown_model_view
    slab = FloorSlab(list(SQ))
    slab._top_level = scene.active_level
    scene.addItem(slab)
    scene._floor_slabs.append(slab)
    op = FloorOpening([QPointF(p) for p in HOLE], slab)
    slab.add_opening(op)
    if op.scene() is not scene:
        scene.addItem(op)
    assert marks.mint(scene, op) == "O1"
    scene.clearSelection()
    slab.setSelected(True)
    scene.copy_selected_items()
    scene.paste_items(QPointF(0, 5000))
    assert len(scene._floor_slabs) == 2
    copy = scene._floor_slabs[1]
    assert len(copy.openings) == 1
    pasted = copy.openings[0]
    assert pasted is not op and pasted.host is copy
    assert marks.get_mark(pasted) == "O2"
    assert marks.get_mark(op) == "O1"
    assert pasted.points[0].y() == op.points[0].y() + 5000     # rode the translated slab
