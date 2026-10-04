"""LT2-7 / H-f -- editable Linetype / Weight / Colour rows, undoable."""
from PyQt6.QtCore import QPointF

from firepro3d import paper_display as pd
from firepro3d.geometry_2d import LineItem, RegularPolygonItem
from firepro3d.model_space import Model_Space


def _editor_with_line():
    ms = Model_Space(scene_role="block_editor")
    ln = LineItem(QPointF(0, 0), QPointF(100, 0))
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    ms.push_undo_state()
    return ms, ln


def test_rows_present_with_options(qapp):
    _ms, ln = _editor_with_line()
    props = ln.get_properties()
    assert props["Linetype"]["options"] == ["Continuous", "By Block"]
    assert props["Linetype"]["value"] == "Continuous"
    assert props["Weight"]["options"] == ["By Block", *pd.weight_names()]
    assert props["Weight"]["value"] == "By Block"
    assert props["Colour"]["type"] == "color"
    assert "Line Weight" not in props


def test_polygon_gains_rows(qapp):
    poly = RegularPolygonItem(QPointF(0, 0), sides=6, radius_mm=10.0)
    props = poly.get_properties()
    assert {"Linetype", "Weight", "Colour"} <= set(props)


def test_weight_edit_applies_undoes_and_persists(qapp):
    ms, ln = _editor_with_line()
    n0, pos0 = len(ms._undo_stack), ms._undo_pos
    with ms.deferred_undo_push():
        ln.set_property("Weight", "Heavy")
    assert len(ms._undo_stack) == n0 + 1           # exactly one step pushed
    assert ms._undo_pos == pos0 + 1
    assert ln.style["weight"] == "Heavy"
    assert ln.to_dict()["style"]["weight"] == "Heavy"
    ms.undo()
    assert ms._draw_lines[0].style["weight"] == "by_block"


def test_linetype_and_colour_edits(qapp):
    ms, ln = _editor_with_line()
    ln.set_property("Linetype", "By Block")
    ln.set_property("Colour", "#123456")
    assert ln.style["linetype"] == "by_block"
    assert ln.style["colour"] == "#123456"
