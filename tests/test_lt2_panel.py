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
    # WM-4/WM-5 (retired LT2-7 By Block options): Continuous only, and the
    # weight row opens with By Linetype showing what it resolves to.
    assert props["Linetype"]["options"] == ["Continuous"]
    assert props["Linetype"]["value"] == "Continuous"
    by_lt = f"By Linetype ({pd.model_blocks_weight()})"
    assert props["Weight"]["options"] == [by_lt, *pd.weight_names()]
    assert props["Weight"]["value"] == by_lt
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
    assert ms._draw_lines[0].style["weight"] == "by_linetype"   # WM-10 default


def test_linetype_and_colour_edits(qapp):
    ms, ln = _editor_with_line()
    ln.style["linetype"] = "x-unresolved"       # WM-4: no By Block to pick
    ln.set_property("Linetype", "Continuous")
    ln.set_property("Colour", "#123456")
    assert ln.style["linetype"] == "continuous"
    assert ln.style["colour"] == "#123456"


def test_weight_row_shows_and_sets_by_linetype(qapp):
    """LT3-8 / WM-5: the row shows By Linetype with its resolved weight and a
    pick of that label stores ``by_linetype`` (one undo step)."""
    ms, ln = _editor_with_line()
    by_lt = f"By Linetype ({pd.model_blocks_weight()})"
    assert ln.get_properties()["Weight"]["value"] == by_lt
    ln.style["weight"] = "Heavy"
    n0 = len(ms._undo_stack)
    with ms.deferred_undo_push():
        ln.set_property("Weight", by_lt)
    assert ln.style["weight"] == "by_linetype"
    assert len(ms._undo_stack) == n0 + 1
    assert ln.get_properties()["Weight"]["value"] == by_lt
