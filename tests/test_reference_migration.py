"""Slice 5 guard — reference-graphic unification: migration (R8, migrate-not-drop).

Existing underlays are real imported content, not clean-dropped. On project load
each underlay's reference ``BlockDefinition`` is reconstructed transparently: the
cache-load and source-reimport paths both run through the batched builder (Slice
4 seam), so ``record.definition`` materializes automatically. Because the
definition is NOT serialized, the on-disk ``.fpd`` format is byte-identical — no
SAVE_VERSION bump, zero migration risk for existing projects.

These guards lock:
  * cache-load reconstructs a reference definition (the common project-open path);
  * source-missing + cache-present falls back to the cached geometry as a locked
    reference (R8 fallback), definition still reconstructed;
  * a legacy record (old .fpd, no definition key) deserializes to definition=None
    and to_dict still omits it (format unchanged).

See docs/specs/reference-graphic-model.md → Implementation (Migration, R8).
"""

from __future__ import annotations

import os

from firepro3d.block_definition import BlockDefinition
from firepro3d.model_space import Model_Space
from firepro3d.underlay import Underlay
from firepro3d.underlay_cache import cache_dir_for_project, write_cache


def _cache_geoms():
    return [
        {"kind": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 100, "layer": "A"},
        {"kind": "text", "x": 10, "y": 10, "text": "N", "size": 2.5, "layer": "T"},
    ]


def _scene_with_cache(tmp_path, record, source_mtime, geoms):
    """A Model_Space whose project has a populated underlay cache for *record*."""
    scene = Model_Space()
    project = tmp_path / "proj.fpd"
    project.touch()
    scene._project_path = str(project)
    write_cache(cache_dir_for_project(str(project)), record.cache_key(),
                geoms, source_mtime)
    return scene


def test_cache_load_reconstructs_reference_definition(qapp, tmp_path):
    """The common project-open path: a cache hit re-homes onto a definition."""
    src = tmp_path / "floor.dxf"
    src.write_text("dummy")
    rec = Underlay(type="dxf", path=str(src))
    mtime = os.path.getmtime(src)
    scene = _scene_with_cache(tmp_path, rec, mtime, _cache_geoms())

    ok = scene._underlay_ctl._load_underlay_from_cache(rec, mtime)
    assert ok is True
    assert isinstance(rec.definition, BlockDefinition)
    assert rec.definition.render_mode == "reference"
    # Text preserved through migration (geom-dict model).
    assert [g["kind"] for g in rec.definition.geoms] == ["line", "text"]


def test_source_missing_falls_back_to_cached_reference(qapp, tmp_path):
    """R8 fallback: source gone, cache present -> definition from cached geoms."""
    rec = Underlay(type="dxf", path=str(tmp_path / "gone.dxf"))  # never created
    # Cache was written earlier when the source existed (mtime 123.0).
    scene = _scene_with_cache(tmp_path, rec, 123.0, _cache_geoms())

    # Load with source_mtime=None (resolve_path failed -> file missing).
    ok = scene._underlay_ctl._load_underlay_from_cache(rec, None)
    assert ok is True                       # cached fallback engaged
    assert rec.definition is not None       # reference reconstructed
    assert rec.definition.geoms             # locked reference has geometry


def test_legacy_record_deserializes_without_definition(qapp):
    """An old .fpd underlay dict carried no definition; format is unchanged."""
    rec = Underlay.from_dict({"type": "dxf", "path": "x.dxf"})
    assert rec.definition is None
    assert "definition" not in rec.to_dict()


def test_definition_survives_a_record_to_from_dict_roundtrip_as_none(qapp, tmp_path):
    """to_dict/from_dict never carry the definition (cache-backed, reconstructed)."""
    src = tmp_path / "f.dxf"
    src.write_text("dummy")
    rec = Underlay(type="dxf", path=str(src))
    mtime = os.path.getmtime(src)
    scene = _scene_with_cache(tmp_path, rec, mtime, _cache_geoms())
    scene._underlay_ctl._load_underlay_from_cache(rec, mtime)
    assert rec.definition is not None            # set at runtime
    reserialized = Underlay.from_dict(rec.to_dict())
    assert reserialized.definition is None       # not persisted; reconstructs on load
