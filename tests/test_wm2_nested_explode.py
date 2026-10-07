"""WM2 G6 (outer wins) + G8 (Explode bakes, look unchanged)."""
from firepro3d import paper_display as pd
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_explode import explode_instances
from firepro3d.model_space import Model_Space
from firepro3d.stroke_style import canvas_px
from tests.test_lt1_block_paper import _render_model
from tests.test_lt2_canvas_paper import _run_near
from tests.wm2_support import (COL, ROWS, nested_record, scene_with,
                               sprinkler_def)


def _host(child, rec_ov=None):
    return BlockDefinition.new(name="Host", library="L", series="S",
                               primitives=[nested_record(child.id, rec_ov)],
                               origin=(0.0, 0.0))


def _runs(ms):
    img = _render_model(ms)
    return {c: _run_near(img, COL, r) for c, r in ROWS.items()}


def test_g6_outer_placement_beats_nested_record(qapp):
    s = sprinkler_def()
    h = _host(s, {"weight": "Thickest"})
    ms, _ = scene_with([s, h], h.id, {"weight": "Thinnest"})
    assert set(_runs(ms).values()) == {round(canvas_px("Thinnest"))}


def test_g6_as_authored_outer_shows_nested_record(qapp):
    s = sprinkler_def()
    h = _host(s, {"weight": "Thickest"})
    ms, _ = scene_with([s, h], h.id)
    assert set(_runs(ms).values()) == {round(canvas_px("Thickest"))}


def test_g6_outer_record_beats_inner_record(qapp):
    s = sprinkler_def()
    mid = _host(s, {"weight": "Thickest"})
    top = BlockDefinition.new(name="Top", library="L", series="S",
                              primitives=[nested_record(mid.id, {"weight": "Thinnest"})],
                              origin=(0.0, 0.0))
    ms, _ = scene_with([s, mid, top], top.id)
    assert set(_runs(ms).values()) == {round(canvas_px("Thinnest"))}


def test_g6_load_prim_normalises_nested_record_overrides(qapp):
    """A stored nested record's override is canonicalised on load and an
    As Authored one is dropped (H-g; keeps make-from-selection records lean)."""
    s = sprinkler_def()
    h = _host(s, {"weight": " Thinnest "})
    h2 = BlockDefinition.from_dict(h.to_dict())
    assert h2.primitives[0]["overrides"] == {"weight": "Thinnest",
                                             "linetype": "as_authored"}
    a = _host(s, {"weight": "as_authored"})
    assert "overrides" not in BlockDefinition.from_dict(a.to_dict()).primitives[0]


def _editor_scene(defs):
    """The Block Editor scene Explode runs in (C1): returns (widget, scene)."""
    from firepro3d.block_editor import BlockEditorWidget
    proj = Model_Space()
    for d in defs:
        proj.register_block_definition(d)
    w = BlockEditorWidget(proj)
    return w, w.editor_scene


def test_g8_explode_flat_bakes_and_looks_unchanged(qapp):
    pd.set_model_blocks_weight(None)
    s = sprinkler_def()
    w, ms = _editor_scene([s])
    inst = ms.place_block_instance(s.id, (0.0, 0.0), level=ms.active_level,
                                   overrides={"weight": "by_category"})
    before = _runs(ms)
    created = explode_instances(ms, [inst], flatten=False)
    assert {it.style["weight"] for it in created} == {pd.model_blocks_weight()}
    assert _runs(ms) == before


def test_g8_explode_composes_nested_per_axis(qapp):
    s = sprinkler_def()
    h = _host(s, {"weight": "Thickest", "linetype": "continuous"})
    w, ms = _editor_scene([s, h])
    inst = ms.place_block_instance(h.id, (0.0, 0.0), level=ms.active_level,
                                   overrides={"weight": "Thinnest"})
    before = _runs(ms)
    (child,) = explode_instances(ms, [inst], flatten=False)
    assert child.overrides == {"weight": "Thinnest", "linetype": "continuous"}
    assert _runs(ms) == before
    flat = explode_instances(ms, [child], flatten=True)
    assert {it.style["weight"] for it in flat} == {"Thinnest"}
    assert _runs(ms) == before
