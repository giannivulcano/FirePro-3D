"""Slice 4 guard — reference-graphic unification: Underlay re-homed on a definition.

The `Underlay` record is re-homed onto a shared reference `BlockDefinition` that
OWNS the geometry (R3/RD2). The existing batched builder + snap index + freeze
machinery is kept, repointed at the definition — so this is zero-UX: the group
renders identically, but the geoms now have a real home.

These guards lock:
  * building an underlay group sets ``record.definition`` (a reference
    BlockDefinition) whose ``geoms`` are the built geometry;
  * the snap index is built FROM ``record.definition.geoms`` (single owner);
  * text is preserved in the definition (geom-dict model).

See docs/specs/reference-graphic-model.md → Implementation (Option A re-home).
"""

from __future__ import annotations

from firepro3d.block_definition import BlockDefinition
from firepro3d.model_space import Model_Space
from firepro3d.underlay import Underlay
from firepro3d.underlay_snap_index import UnderlaySnapIndex


def _geoms():
    return [
        {"kind": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 100, "layer": "A-WALL"},
        {"kind": "line", "x1": 0, "y1": 50, "x2": 100, "y2": 50, "layer": "A-DOOR"},
        {"kind": "text", "x": 10, "y": 10, "text": "N1", "size": 2.5, "layer": "A-TEXT"},
    ]


def _record(**kw):
    kw.setdefault("type", "dxf")
    kw.setdefault("path", "x.dxf")
    return Underlay(**kw)


def test_building_group_sets_reference_definition(qapp):
    scene = Model_Space()
    rec = _record()
    assert rec.definition is None
    group, _layers = scene._build_batched_underlay_group(_geoms(), rec)
    assert group is not None
    assert isinstance(rec.definition, BlockDefinition)
    assert rec.definition.render_mode == "reference"


def test_definition_owns_the_geometry_including_text(qapp):
    scene = Model_Space()
    rec = _record()
    scene._build_batched_underlay_group(_geoms(), rec)
    kinds = [g["kind"] for g in rec.definition.geoms]
    assert kinds == ["line", "line", "text"]        # nothing dropped; text kept


def test_snap_index_built_from_definition_geoms(qapp):
    """The snap index (data(4)) references the definition's geoms — one owner."""
    scene = Model_Space()
    rec = _record()
    group, _ = scene._build_batched_underlay_group(_geoms(), rec)
    scene._attach_snap_index(group, _geoms(), rec)
    index = group.data(4)
    assert isinstance(index, UnderlaySnapIndex)
    assert index._geom_list is rec.definition.geoms


def test_empty_vector_import_builds_no_group(qapp):
    """An empty geom list builds no group (raster PDFs never reach this builder
    and so stay definition-less)."""
    scene = Model_Space()
    rec = _record()
    result = scene._build_batched_underlay_group([], rec)
    assert result is None
