"""Slice 2 guard — reference-graphic unification: batched-per-layer compile.

The R4 perf spike's binding constraint #1: a reference definition MUST render as
batched-per-layer cosmetic paths, never one scene object per primitive (individual
scene items made a single snap take 11-18 s on the Sleeman 437k-geom DXF).

``BlockDefinition`` grows a ``render_mode``:
  * ``"default"`` — unchanged: one render op per primitive (authored small blocks,
    non-goal #9).
  * ``"reference"`` — one render op per distinct source ``layer`` tag.

These guards lock the op-shape invariant (mutation-tested: if reference compile
regresses to per-primitive, ``len(render_ops) == n_layers`` goes RED):

See docs/specs/reference-graphic-model.md → Implementation → "Reference-mode compile".
"""

from __future__ import annotations

from firepro3d.block_definition import BlockDefinition


def _prims_across_layers():
    """5 primitives spanning 3 distinct layers (A, A, B, C, C)."""
    return [
        {"type": "draw_line", "pt1": [0, 0], "pt2": [10, 0],
         "color": "#ffffff", "lineweight": 1.0, "layer": "A"},
        {"type": "draw_line", "pt1": [0, 5], "pt2": [10, 5],
         "color": "#ffffff", "lineweight": 1.0, "layer": "A"},
        {"type": "draw_circle", "cx": 5, "cy": 5, "radius": 2.0,
         "color": "#ffffff", "lineweight": 1.0, "layer": "B"},
        {"type": "draw_line", "pt1": [0, 10], "pt2": [10, 10],
         "color": "#ffffff", "lineweight": 1.0, "layer": "C"},
        {"type": "draw_circle", "cx": 8, "cy": 8, "radius": 1.0,
         "color": "#ffffff", "lineweight": 1.0, "layer": "C"},
    ]


def _make(render_mode, primitives):
    return BlockDefinition(
        id="ref-test", version=1, name="ref", library="", series="",
        scale_mode="real_size", origin=(0.0, 0.0), attributes=[],
        primitives=primitives, render_mode=render_mode)


def test_reference_mode_emits_one_op_per_layer(qapp):
    """Reference compile batches: exactly one render op per distinct layer."""
    d = _make("reference", _prims_across_layers())
    ops = d.render_ops()
    assert len(ops) == 3          # 3 distinct layers, NOT 5 primitives
    # And each op has real geometry (union path non-empty).
    for _pen, path in ops:
        assert not path.boundingRect().isNull()


def test_default_mode_emits_one_op_per_primitive(qapp):
    """Default compile is unchanged: one op per primitive (authored blocks)."""
    d = _make("default", _prims_across_layers())
    assert len(d.render_ops()) == 5


def test_reference_batches_strictly_fewer_than_primitives(qapp):
    """The whole point: reference ops << primitives (batching, not per-item)."""
    d = _make("reference", _prims_across_layers())
    assert len(d.render_ops()) < len(d.primitives)


def test_untagged_primitives_collapse_to_single_layer(qapp):
    """Untagged (layer='') primitives batch into one op, not N."""
    prims = [
        {"type": "draw_line", "pt1": [0, 0], "pt2": [1, 1],
         "color": "#ffffff", "lineweight": 1.0},
        {"type": "draw_line", "pt1": [1, 1], "pt2": [2, 2],
         "color": "#ffffff", "lineweight": 1.0},
    ]
    d = _make("reference", prims)
    assert len(d.render_ops()) == 1


def test_render_mode_roundtrips_through_to_from_dict(qapp):
    """render_mode survives serialization; default stays 'default'."""
    d = _make("reference", _prims_across_layers())
    restored = BlockDefinition.from_dict(d.to_dict())
    assert restored.render_mode == "reference"
    # A definition built without render_mode defaults to 'default'.
    legacy = BlockDefinition.from_dict({
        "id": "x", "version": 1, "primitives": [], "origin": [0, 0]})
    assert legacy.render_mode == "default"


def test_default_is_the_unchanged_default(qapp):
    """A definition constructed the old way (no render_mode) is 'default'."""
    d = BlockDefinition.new(name="a", library="", series="",
                            primitives=_prims_across_layers(), origin=(0.0, 0.0))
    assert d.render_mode == "default"
    assert len(d.render_ops()) == 5
