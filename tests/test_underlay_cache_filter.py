"""Area-selection (import_bounds) must survive the geometry-cache round-trip.

Bug (found live 2026-08-30): the PDF import/reload paths wrote the FULL page
extraction into the cache under a key that claims the area-selected variant,
and the cache-load path trusted cache content — so an area-filtered underlay
(e.g. 4.9k geoms / 10 layers) bloated back to the full sheet (20.5k geoms /
85 layers) on every project load, making live repaints ~10x slower.
"""
import os

import pytest

from firepro3d.model_space import Model_Space
from firepro3d.underlay import Underlay
from firepro3d.underlay_cache import cache_dir_for_project, write_cache

BOUNDS = [0.0, 0.0, 100.0, 100.0]


def _geoms(n_inside=5, n_outside=15):
    inside = [{"kind": "path_points", "layer": f"IN{i}", "closed": False,
               "width": 0.0, "points": [[10.0 + i, 10.0], [50.0, 50.0]]}
              for i in range(n_inside)]
    outside = [{"kind": "path_points", "layer": f"OUT{i}", "closed": False,
                "width": 0.0, "points": [[500.0 + i, 500.0], [600.0, 600.0]]}
               for i in range(n_outside)]
    return inside + outside


def test_cache_load_reapplies_import_bounds(qapp, tmp_path):
    """A poisoned (unfiltered) cache entry must be filtered on load and the
    group marked dirty so the next save rewrites the cache healed."""
    scene = Model_Space()
    src = tmp_path / "plan.pdf"
    src.write_bytes(b"x")
    proj = tmp_path / "proj.fpd"
    proj.write_text("{}")
    scene._project_path = str(proj)

    record = Underlay(type="pdf", path=str(src), import_bounds=list(BOUNDS))
    mtime = os.path.getmtime(src)
    write_cache(cache_dir_for_project(str(proj)), record.cache_key(),
                _geoms(), source_mtime=mtime)

    assert scene._load_underlay_from_cache(record, mtime) is True
    rec, grp = scene.underlays[-1]
    raw = grp.data(5)
    assert len(raw) == 5, (
        f"cache-load kept {len(raw)} geoms - import_bounds filter not applied")
    assert grp.data(6) is True, (
        "healed group must be dirty so the next save rewrites the cache")


def test_cache_load_clean_cache_stays_clean(qapp, tmp_path):
    """A correctly-filtered cache entry loads unchanged and stays non-dirty."""
    scene = Model_Space()
    src = tmp_path / "plan.pdf"
    src.write_bytes(b"x")
    proj = tmp_path / "proj.fpd"
    proj.write_text("{}")
    scene._project_path = str(proj)

    record = Underlay(type="pdf", path=str(src), import_bounds=list(BOUNDS))
    mtime = os.path.getmtime(src)
    write_cache(cache_dir_for_project(str(proj)), record.cache_key(),
                _geoms(n_inside=5, n_outside=0), source_mtime=mtime)

    assert scene._load_underlay_from_cache(record, mtime) is True
    rec, grp = scene.underlays[-1]
    assert len(grp.data(5)) == 5
    assert grp.data(6) is False


def test_import_pdf_vectors_filters_by_bounds(qapp, tmp_path):
    """The PDF reload path must filter build + cache snapshot by
    import_bounds (parity with the DXF _on_dxf_finished path)."""
    scene = Model_Space()
    src = tmp_path / "plan.pdf"
    src.write_bytes(b"x")

    record = Underlay(type="pdf", path=str(src), import_bounds=list(BOUNDS))
    scene._import_pdf_vectors(str(src), _geoms(), _record=record)

    rec, grp = scene.underlays[-1]
    assert len(grp.data(5)) == 5, (
        f"_import_pdf_vectors kept {len(grp.data(5))} geoms - unfiltered")


def test_v4_cache_rejected(qapp, tmp_path):
    """Old-extractor caches (v4) must be invalidated: they carry 10-20x
    over-extracted geometry (the 2026-08-30 live-lag root cause)."""
    import json as _json

    from firepro3d.underlay_cache import read_cache

    cache_dir = tmp_path / "c"
    cache_dir.mkdir()
    key = "somekey.json"
    payload = {"version": 4, "source_mtime": 123.0,
               "geom_count": 1,
               "geoms": [{"kind": "path_points", "layer": "L", "width": 0.0,
                          "closed": False, "points": [[0, 0], [1, 1]]}]}
    (cache_dir / key).write_text(_json.dumps(payload))
    assert read_cache(str(cache_dir), key, source_mtime=123.0) is None
