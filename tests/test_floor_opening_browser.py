"""Model Browser: a floor void is a child row of its host slab (floor-opening A8)."""
from PyQt6.QtCore import QPointF

from firepro3d.floor_opening import FloorOpening
from firepro3d.floor_slab import FloorSlab
from firepro3d.model_browser import ModelBrowser, _ROLE_ENTITY

SQ = [QPointF(0, 0), QPointF(3000, 0), QPointF(3000, 2000), QPointF(0, 2000)]


def _void(scene, slab, x0, mark):
    op = FloorOpening([QPointF(x0, 500), QPointF(x0 + 500, 500),
                       QPointF(x0 + 500, 1000), QPointF(x0, 1000)], slab, mark=mark)
    slab.add_opening(op)
    if op.scene() is not scene:
        scene.addItem(op)
    return op


def _browser(model_scene):
    scene = model_scene()
    slab = FloorSlab(list(SQ))
    slab.name = "Slab A"
    scene.addItem(slab)
    scene._floor_slabs.append(slab)
    v1 = _void(scene, slab, 500, "O7")
    v2 = _void(scene, slab, 1500, "")
    b = ModelBrowser()
    b.set_scene(scene)
    b.refresh()
    return b, scene, slab, v1, v2


def _floors_root(b):
    t = b._tree
    return next(t.topLevelItem(i) for i in range(t.topLevelItemCount())
                if t.topLevelItem(i).text(0).startswith("Floors ("))


def test_void_rows_nest_under_the_host_slab_row(qapp, model_scene):
    """GUARD AC6: label = Mark or "Opening"; voids are not counted as floors."""
    b, scene, slab, v1, v2 = _browser(model_scene)
    root = _floors_root(b)
    assert root.text(0) == "Floors (1)"
    slab_row = root.child(0)
    assert slab_row.text(0) == "Slab A"
    assert slab_row.data(0, _ROLE_ENTITY) == id(slab)
    assert [slab_row.child(i).text(0) for i in range(slab_row.childCount())] == ["O7", "Opening"]
    assert [slab_row.child(i).data(0, _ROLE_ENTITY)
            for i in range(slab_row.childCount())] == [id(v1), id(v2)]
    assert b._find_entity_by_id(id(v1)) is v1


def test_selecting_a_void_row_selects_the_void(qapp, model_scene):
    """GUARD: a void row is a plain row, not a gridline-hosted block row."""
    b, scene, slab, v1, v2 = _browser(model_scene)
    _floors_root(b).child(0).child(0).setSelected(True)   # itemSelectionChanged
    assert v1.isSelected() and not slab.isSelected()


def test_show_rereveals_a_hidden_void(qapp, model_scene):
    """GUARD: Show (Model_Space._show_items) re-shows a hidden void."""
    b, scene, slab, v1, v2 = _browser(model_scene)
    scene._hide_items([v1])
    assert not v1.isVisible()
    scene._show_items([v1])
    assert v1.isVisible()
    assert "visible" not in v1._display_overrides
