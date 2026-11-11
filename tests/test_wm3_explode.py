"""WM3 G6 -- Explode bakes the resolved placement Colour, look unchanged
(WM-11, design D6, AC7)."""
from firepro3d import paper_display as pd
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_explode import explode_instances
from firepro3d.model_space import Model_Space
from firepro3d.text_item import TextItem
from tests.test_lt1_block_paper import _render_model
from tests.wm2_support import nested_record
from tests.wm3_support import AUTHORED, OVR, composite_defs, lit_outside_origin


def _editor(shipped_hatches, defs):
    """The Block Editor scene Explode runs in (C1), D39 tint off (it sits
    above the override and treats a block's border op and an exploded
    TextItem's border differently -- pre-existing)."""
    from firepro3d.block_editor import BlockEditorWidget
    proj = Model_Space()
    for d in defs:
        proj.register_block_definition(d)
    shipped_hatches(proj)
    w = BlockEditorWidget(proj)
    ms = w.editor_scene
    ms.constraint_ctl.enabled = False
    return w, ms


def _diff(a, b):
    """Every pixel compared (VC2): count of positions that differ."""
    assert (a.width(), a.height()) == (b.width(), b.height())
    return sum(1 for x in range(a.width()) for y in range(a.height())
               if a.pixel(x, y) != b.pixel(x, y))


def _place(ms, d, ov):
    return ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level,
                                   overrides=ov)


def test_g6_explode_bakes_colour_pixel_identical(qapp, shipped_hatches):
    defs = composite_defs(leader=False)
    w, ms = _editor(shipped_hatches, defs)
    inst = _place(ms, defs[2], {"colour": OVR})
    before = _render_model(ms)
    assert lit_outside_origin(before) == {OVR, AUTHORED["textfill"]}
    created = explode_instances(ms, [inst], flatten=False)
    assert len(created) == 9
    # R3: the exploded "H" keeps its box fill verbatim (only it has one).
    assert sorted(c.data.fill_color for c in created if isinstance(c, TextItem)) == [
        "", AUTHORED["textfill"]]
    assert _diff(before, _render_model(ms)) == 0


def test_g6_explode_by_category_bakes_the_current_dm_colour(qapp, shipped_hatches):
    pd.set_model_blocks_colour("#808000")
    defs = composite_defs(leader=False)
    w, ms = _editor(shipped_hatches, defs)
    inst = _place(ms, defs[2], {"colour": "by_category"})
    before = _render_model(ms)
    created = explode_instances(ms, [inst], flatten=False)
    texts = [c for c in created if isinstance(c, TextItem)]
    styled = [c for c in created if getattr(c, "style", None) is not None]
    assert len(texts) == 2 and len(styled) == 7
    assert {t.data.color for t in texts} == {"#808000"}        # concrete, not by_category
    assert {t.data.fill_color for t in texts} == {"", AUTHORED["textfill"]}   # R3
    assert {s.style["colour"] for s in styled} == {"#808000"}
    layers = [lay for c in styled for lay in (c.fill_layers.background,
                                              c.fill_layers.pattern) if lay is not None]
    assert len(layers) == 2 and {lay.color for lay in layers} == {"#808000"}
    assert _diff(before, _render_model(ms)) == 0
    pd.set_model_blocks_colour(OVR)               # baked: a DM change no longer reaches them
    assert lit_outside_origin(_render_model(ms)) == {"#808000", AUTHORED["textfill"]}


def test_g6_as_authored_explodes_verbatim(qapp, shipped_hatches):
    defs = composite_defs(leader=False)
    w, ms = _editor(shipped_hatches, defs)
    inst = _place(ms, defs[2], None)
    created = explode_instances(ms, [inst], flatten=False)
    lines = sorted(c.style["colour"] for c in created if type(c).__name__ == "LineItem")
    assert lines == sorted(AUTHORED[k] for k in ("circle", "cross", "deflector",
                                                 "end", "dots"))
    texts = sorted(c.data.color for c in created if isinstance(c, TextItem))
    assert texts == sorted((AUTHORED["text"], AUTHORED["bound"]))


def test_g6_explode_composes_nested_colour_per_axis(qapp, shipped_hatches):
    end, lt, d = composite_defs(leader=False)
    h = BlockDefinition.new(name="Host", library="L", series="S",
                            primitives=[nested_record(d.id, {"colour": "#808000"})],
                            origin=(0.0, 0.0))
    w, ms = _editor(shipped_hatches, [end, lt, d, h])
    inst = _place(ms, h, {"linetype": "continuous"})
    (child,) = explode_instances(ms, [inst], flatten=False)
    assert child.overrides == {"weight": "as_authored", "linetype": "continuous",
                               "colour": "#808000"}
    explode_instances(ms, [child], flatten=True)
    assert lit_outside_origin(_render_model(ms)) == {"#808000", AUTHORED["textfill"]}
