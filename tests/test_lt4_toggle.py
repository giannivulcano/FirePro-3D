"""LT4 toggle / refusals / save (A4, LT4-6, LT4-11a-d)."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d import stroke_style as ss
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_editor import BlockEditorWidget
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import hidden, make_linetype


def _w(proj=None, defn=None):
    proj = proj or Model_Space()
    w = BlockEditorWidget(proj, block_id=defn.id if defn else None)
    if defn is not None:
        w.seed_from_definition(defn)
    msgs = []
    w.editor_scene._show_status = lambda m, t=5000: msgs.append(m)
    return proj, w, msgs


def _axis(sc):
    return sorted((l._pt1.x(), l._pt2.x()) for l in sc._draw_lines)


def test_on_empty_seeds_dash6_gap3_drafting_one_step(qapp):
    _, w, _ = _w()
    sc = w.editor_scene
    n = len(sc._undo_stack)
    assert w.toggle_capability("repeat")
    assert sc.block_repeat == {"length": 9.0, "size": "drafting"}
    assert _axis(sc) == [(0.0, 6.0)]
    assert len(sc._undo_stack) == n + 1
    sc.undo()
    assert sc.block_capability is None and _axis(sc) == []


def test_on_reads_content_and_converts_with_count(qapp):
    proj, w, msgs = _w()
    lt = hidden(proj)
    for a, b in ((0, 4), (6, 7)):
        it = LineItem(QPointF(a, 0), QPointF(b, 0))
        it.style["linetype"] = lt
        w._add_primitive(it)
    assert w.toggle_capability("repeat")
    sc = w.editor_scene
    assert sc.block_repeat["length"] == 7.0
    assert {l.style["linetype"] for l in sc._draw_lines} == {ss.CONTINUOUS}
    assert msgs[-1] == "2 lines set to Continuous"


def test_a4_on_refused_while_placed_as_symbol(qapp):
    proj = Model_Space()
    d = BlockDefinition.new(name="Sym", library="L", series="S", origin=(0, 0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(5, 0)).to_dict()])
    proj.register_block_definition(d)
    proj.place_block_instance(d.id, (0.0, 0.0))
    _, w, msgs = _w(proj, d)
    assert w.toggle_capability("repeat") is False
    assert w.editor_scene.block_capability is None
    assert msgs == ["Used as a symbol (1 placed) — remove those before "
                    "making it a linetype"]


def test_a4_exclusive_with_pattern_tile(qapp):
    _, w, msgs = _w()
    w._add_primitive(LineItem(QPointF(0, 0), QPointF(5, 0)))
    assert w.toggle_capability("tile")
    assert w.toggle_capability("repeat") is False
    assert msgs[-1] == ("Turn Pattern tile off first — a block is a pattern "
                        "or a linetype, not both")
    assert w.editor_scene.block_tile is not None


@pytest.mark.xfail(reason="LT4 Task 9 wording", strict=True)
def test_a4_off_refused_while_used(qapp):
    proj = Model_Space()
    lt_def = make_linetype("Hidden")
    proj.register_block_definition(lt_def)
    user_line = LineItem(QPointF(0, 0), QPointF(5, 0))
    user_line.style["linetype"] = lt_def.id
    riser = BlockDefinition.new(name="Riser", library="L", series="S",
                                origin=(0, 0), primitives=[user_line.to_dict()])
    proj.register_block_definition(riser)
    _, w, msgs = _w(proj, lt_def)
    assert w.toggle_capability("repeat") is False
    assert w.editor_scene.block_repeat is not None
    assert msgs[-1] == ("“Hidden” is used by lines inside: Riser — change "
                        "their linetype first.")


def test_save_as_keeps_the_linetype_and_new_is_never_placed(qapp):
    proj, w, msgs = _w()
    w.toggle_capability("repeat")
    d1 = w.commit_block("Hidden", "L", "Linetypes")
    assert d1.repeat == {"length": 9.0, "size": "drafting"}
    assert proj.instance_count(d1.id) == 0
    w._edit_block_id = None                                 # Save As path
    d2 = w.commit_block("Hidden 2", "L", "Linetypes")
    assert d2.id != d1.id and d2.repeat == d1.repeat


def test_reopen_loads_capability_into_the_baseline(qapp):
    proj = Model_Space()
    d = make_linetype("Hidden")
    proj.register_block_definition(d)
    _, w, _ = _w(proj, d)
    sc = w.editor_scene
    assert sc.block_repeat == d.repeat
    sc.undo()
    assert sc.block_repeat == d.repeat


def test_reopen_baseline_is_not_mutated_by_the_hook(qapp):
    """The pre-capture hook skips the re-baseline push: reopening a linetype
    whose unit runs past its Length neither grows it nor adds a step."""
    proj = Model_Space()
    d = make_linetype("Long", dashes=((0.0, 12.0),), length=9.0)
    proj.register_block_definition(d)
    _, w, _ = _w(proj, d)
    sc = w.editor_scene
    assert sc.block_repeat == {"length": 9.0, "size": "drafting"}
    assert len(sc._undo_stack) == 1 and not w.is_dirty()
