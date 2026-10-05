"""WM1 G3/G4 -- panel pickers without By Block, the GeometryTemplate rows,
the draw tools stamping the current, imports not (linetypes.md WM-5/WM-10)."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d import paper_display as pd
from firepro3d import stroke_style as ss
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import hidden


def _line(ms):
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ms.addItem(ln); ms._draw_lines.append(ln)
    ms.push_undo_state()
    return ln


def test_primitive_rows_have_no_by_block(qapp):
    ms = Model_Space(scene_role="block_editor")
    props = _line(ms).get_properties()
    assert "By Block" not in props["Linetype"]["options"]
    assert not any(o.startswith("By Block") for o in props["Weight"]["options"])
    assert props["Linetype"]["tooltip"] and props["Weight"]["tooltip"]


def test_weight_row_shows_resolved_by_linetype(qapp):
    pd.set_model_blocks_weight(None)
    ms = Model_Space(scene_role="block_editor")
    lt = hidden(ms, weight="Medium")
    ln = _line(ms)
    w = ln.get_properties()["Weight"]
    assert w["options"][0] == "By Linetype (Light)" == w["value"]
    ln.style["linetype"] = lt
    w = ln.get_properties()["Weight"]
    assert w["options"][0] == "By Linetype (Medium)" == w["value"]


def test_picking_by_linetype_label_stores_by_linetype(qapp):
    ms = Model_Space(scene_role="block_editor")
    ln = _line(ms)
    ln.set_property("Weight", "Heavy")
    assert ln.style["weight"] == "Heavy"
    ln.set_property("Weight", "By Linetype (Light)")
    assert ln.style["weight"] == ss.BY_LINETYPE


def test_selected_primitive_edit_does_not_move_current(qapp):
    ms = Model_Space(scene_role="block_editor")
    _line(ms).set_property("Weight", "Heavy")
    assert ss.current_style()["weight"] == ss.BY_LINETYPE
