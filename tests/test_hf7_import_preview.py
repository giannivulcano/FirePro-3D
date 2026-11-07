"""HF7: the import preview shows fills; the type dialog names them."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsPathItem

from firepro3d.constants import HATCH_LOD_TONE
from tests.test_import_dialog_preview import _prepped_dialog


def _fill():
    return {"kind": "fill", "layer": "0", "color": "#000000", "solid": True, "mask": False,
            "tone": False, "lines": [[1.0, 1.0, 9.0, 9.0]], "pattern": None,
            "loops": [[{"kind": "path_points", "layer": "0", "closed": True,
                        "points": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]}]]}


def test_preview_adds_a_filled_item_under_the_strokes(qapp):
    dialog = _prepped_dialog()
    dialog._all_geoms = [_fill()]
    dialog._rebuild_preview()
    items = [c for c in dialog._preview_geom_group.childItems()
             if isinstance(c, QGraphicsPathItem)]
    fill = [i for i in items if i.brush().style() != Qt.BrushStyle.NoBrush]
    stroke = [i for i in items if i.brush().style() == Qt.BrushStyle.NoBrush]
    assert len(fill) == 1 and fill[0].opacity() == HATCH_LOD_TONE
    assert fill[0].path().fillRule() == Qt.FillRule.WindingFill
    assert items.index(fill[0]) < items.index(stroke[0])
    assert not stroke[0].path().isEmpty()        # the pattern line went in the stroke path


def test_preview_skips_a_hatch_that_draws_nothing(qapp):
    """Empty pattern: not solid, no tone, no lines. No tone item, no crash."""
    inert = {**_fill(), "solid": False, "tone": False, "lines": [], "pattern": None}
    dialog = _prepped_dialog()
    dialog._all_geoms = [inert]
    dialog._rebuild_preview()
    group = dialog._preview_geom_group
    assert group is None or not [
        c for c in group.childItems()
        if isinstance(c, QGraphicsPathItem) and c.brush().style() != Qt.BrushStyle.NoBrush]
