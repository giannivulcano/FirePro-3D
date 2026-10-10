"""ET1 Q10-a/b -- end-type editor rows On screen / Trim / Preview (Size gone),
line rows Start End / Visible / Scale, one undo step per edit, bad input
reverts, locked in capability editors, no rows on closed / template /
placement."""
from PyQt6.QtCore import QPointF

from firepro3d.capability_panel import capability_rows, set_capability_property
from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.model_space import Model_Space
from tests.lt5_support import end_id, scene_line
from tests.test_lt5_authoring import _end_editor


def test_end_editor_rows_on_screen_trim_preview(qapp):
    _, w, sc, _ = _end_editor()
    assert sc.block_end == {"trim": 0.0, "screen": "fixed"}          # SEED (Q6)
    r = capability_rows(sc)
    assert "Size" not in r
    assert list(k for k in r if k in ("On screen", "Trim", "Preview")) == ["On screen", "Trim", "Preview"]
    assert r["On screen"]["options"] == ["Fixed size", "Scale with zoom"]
    assert r["On screen"]["value"] == "Fixed size"
    assert r["Trim"]["type"] == "dimension"
    for k in ("On screen", "Trim", "Preview swatch"):
        assert "\n" in r[k]["tooltip"] or len(r[k]["tooltip"]) < 60, k
    pos0 = sc._undo_pos
    set_capability_property(sc, w, "On screen", "Scale with zoom")
    assert sc.block_end == {"trim": 0.0} and sc._undo_pos == pos0 + 1
    assert capability_rows(sc)["On screen"]["value"] == "Scale with zoom"
    set_capability_property(sc, w, "On screen", "Scale with zoom")   # no-op
    assert sc._undo_pos == pos0 + 1
    set_capability_property(sc, w, "On screen", "Fixed size")
    assert sc.block_end == {"trim": 0.0, "screen": "fixed"} and sc._undo_pos == pos0 + 2
    set_capability_property(sc, w, "Trim", 2.5)
    assert sc.block_end["trim"] == 2.5 and sc._undo_pos == pos0 + 3
    sc.undo()
    assert sc.block_end == {"trim": 0.0, "screen": "fixed"}


def test_line_scale_rows_order_edit_revert_and_round_trip(qapp):
    proj = Model_Space()
    end_id(proj)
    ln = scene_line(proj)
    ln.set_property("Finish End", "Arrow")
    keys = [k for k in ln.get_properties() if k.endswith((" End", " Visible", " Scale"))]
    assert keys == ["Start End", "Start Visible", "Start Scale",
                    "Finish End", "Finish Visible", "Finish Scale"]
    r = ln.get_properties()["Finish Scale"]
    assert (r["type"], r["value"], r["suffix"]) == ("string", "1", "×")
    assert "\n" in r["tooltip"]
    n = len(proj._undo_stack)
    ln.set_property("Finish Scale", "2")
    assert ln.style["finish"]["scale"] == 2.0 and len(proj._undo_stack) == n + 1
    assert ln.get_properties()["Finish Scale"]["value"] == "2"
    ln.set_property("Finish Scale", "12")                       # out of range: reverts
    assert ln.style["finish"]["scale"] == 2.0 and len(proj._undo_stack) == n + 1
    ln.set_property("Finish Scale", "abc")
    assert ln.style["finish"]["scale"] == 2.0 and len(proj._undo_stack) == n + 1
    ln.set_property("Finish Scale", "1")
    assert "scale" not in ln.style["finish"] and len(proj._undo_stack) == n + 2
    proj.undo()                                   # undo rebuilds the items
    assert proj._draw_lines[-1].style["finish"]["scale"] == 2.0


def test_scale_rows_hidden_on_closed_template_and_placement_and_locked_in_editors(qapp):
    proj = Model_Space()
    rect = RectangleItem(QPointF(0, 0), QPointF(10, 10))
    proj.addItem(rect)
    assert "Start Scale" not in rect.get_properties()
    _, w, sc, _ = _end_editor()
    ln = next(it for it in sc.items() if isinstance(it, LineItem))
    r = ln.get_properties()
    assert r["Start Scale"]["disabled"] is True
    assert r["Start Scale"]["tooltip"] == r["Start End"]["tooltip"]
    pos0 = sc._undo_pos
    ln.set_property("Start Scale", "2")                         # locked: refused
    assert "scale" not in ln.style["start"] and sc._undo_pos == pos0
