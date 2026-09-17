"""Slice 3 guard — reference-graphic unification: unified import -> definition.

A vector import (DXF/DWG/PDF) becomes a reference ``BlockDefinition`` that owns
the curve-preserving, layer-tagged import geom-dict list (``geoms``). This is the
convergence point of the two pipelines (R1).

Design decision (2026-09-17, /todo Slice 3 grill): the reference definition stores
the *import geom-dict* form (not geometry_2d primitive dicts) so the existing
batched builder + snap-index + freeze machinery renders it verbatim in Slice 4,
and TEXT (which has no geometry_2d primitive yet) is preserved. ``geoms`` is
cache-backed (Slice 5) and deliberately absent from ``to_dict`` to keep ``.fpd``
lean.

See docs/specs/reference-graphic-model.md → Implementation.
"""

from __future__ import annotations

from firepro3d.block_definition import BlockDefinition


def _import_geoms():
    """Import geoms across 2 geometry layers + a text glyph on a third layer.

    The arc is PARAMETRIC (kind='arc') — curve fidelity must survive (the factory
    must not flatten).
    """
    return [
        {"kind": "line", "layer": "A", "color": "#fff",
         "x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 0.0},
        {"kind": "arc", "layer": "A", "color": "#fff",
         "rx": 0.0, "ry": 0.0, "rw": 4.0, "rh": 4.0, "start": 0.0, "span": 90.0},
        {"kind": "circle", "layer": "B", "color": "#fff",
         "x": 0.0, "y": 0.0, "w": 2.0, "h": 2.0},
        {"kind": "text", "layer": "NOTES", "color": "#fff",
         "x": 1.0, "y": 1.0, "text": "N1", "size": 2.5},
    ]


def test_factory_builds_reference_definition(qapp):
    d = BlockDefinition.reference_from_geoms(_import_geoms(), name="ref")
    assert d.render_mode == "reference"
    assert d.name == "ref"
    # Geometry lives in geoms; primitives stays empty for a reference def.
    assert d.primitives == []


def test_geoms_preserved_including_text_and_curves(qapp):
    d = BlockDefinition.reference_from_geoms(_import_geoms())
    kinds = [g["kind"] for g in d.geoms]
    assert kinds == ["line", "arc", "circle", "text"]      # nothing dropped
    assert "arc" in kinds                                   # curve NOT flattened
    assert any(g["kind"] == "text" for g in d.geoms)        # text preserved


def test_reference_render_ops_batch_per_geometry_layer(qapp):
    """render_ops batches geometry per layer; text is excluded from ops (rendered
    by the batched group in Slice 4) but stays in geoms."""
    d = BlockDefinition.reference_from_geoms(_import_geoms())
    ops = d.render_ops()
    # geometry layers = {A, B}; NOTES holds only text -> no geometry op.
    assert len(ops) == 2
    for _pen, path in ops:
        assert not path.boundingRect().isNull()


def test_geoms_absent_from_to_dict(qapp):
    """Cache-backed: geoms must NOT bloat the .fpd via to_dict."""
    d = BlockDefinition.reference_from_geoms(_import_geoms())
    assert "geoms" not in d.to_dict()


def test_empty_import_yields_empty_reference(qapp):
    """A raster/empty import (no geoms) yields a valid empty reference def."""
    d = BlockDefinition.reference_from_geoms([])
    assert d.render_mode == "reference"
    assert d.geoms == []
    assert d.render_ops() == []
