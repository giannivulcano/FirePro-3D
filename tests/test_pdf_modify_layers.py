"""Regression: PDF underlay Modify reload must filter the RENDER by the
record's ``selected_layers``.

Bug (smoke, 2026-09): on a PDF underlay Modify -> "Reuse existing" / "Insert
at origin", the canvas drew ALL layers of the PDF page regardless of the
dialog's layer selection. Those paths route
``model_space.replace_underlay`` -> ``refresh_underlay`` -> ``import_pdf``,
which RE-EXTRACTS the full page from disk. The DXF branch passes
``layers=record.selected_layers`` to the worker (worker filters); the PDF
branch never filtered the returned geom_list by ``record.selected_layers``,
so every layer drew.

Fix (Option B): extract/cache the FULL page (layer-agnostic), then filter the
geom_list by ``record.selected_layers`` at the point the render group is built
-- for BOTH the fresh-extract path (``_import_pdf_vectors``) AND the cache-hit
path (``_load_underlay_from_cache``). ``selected_layers is None`` = all layers.
The Manager's per-layer ``hidden_layers`` still composes on top.
"""
from PyQt6.QtCore import QPointF

from firepro3d.dwg_converter import filter_geoms_by_layers
from firepro3d.model_space import Model_Space
from firepro3d.underlay import Underlay
from firepro3d.underlay_cache import (
    cache_dir_for_project,
    write_cache,
)


# ---------------------------------------------------------------------------
# Step 2 — helper unit tests
# ---------------------------------------------------------------------------

def _line(layer):
    """A real-shaped stroked line geom dict on *layer*."""
    return {"kind": "line", "x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 0.0,
            "width": 0.0, "layer": layer}


def test_filter_subset_keeps_only_matching():
    geoms = [_line("A"), _line("B"), _line("C")]
    kept = filter_geoms_by_layers(geoms, ["A", "C"])
    assert [g["layer"] for g in kept] == ["A", "C"]


def test_filter_none_keeps_all():
    geoms = [_line("A"), _line("B")]
    kept = filter_geoms_by_layers(geoms, None)
    assert kept == geoms
    assert kept is not geoms  # returns a copy, not the input list


def test_filter_empty_layers_keeps_nothing():
    geoms = [_line("A"), _line("B")]
    assert filter_geoms_by_layers(geoms, []) == []


def test_filter_missing_layer_key_treated_as_zero():
    g_default = {"kind": "line", "x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 0.0}
    geoms = [g_default, _line("A")]
    # keep "0": only the layer-less geom survives
    assert filter_geoms_by_layers(geoms, ["0"]) == [g_default]
    # keep "A": only the tagged geom survives
    assert filter_geoms_by_layers(geoms, ["A"]) == [_line("A")]


# ---------------------------------------------------------------------------
# helpers for the integration tests
# ---------------------------------------------------------------------------

def _multi_layer_geoms():
    """Full-page geom_list spanning three distinct layers A/B/C."""
    return [_line("A"), _line("B"), _line("C")]


def _rendered_layers(group):
    """The distinct source layers carried by a built underlay group's
    child path items (each item tags its layer via ``data(1)``)."""
    layers = set()
    for child in group.childItems():
        ln = child.data(1)
        if ln is not None:
            layers.add(ln)
    return layers


# ---------------------------------------------------------------------------
# Step 3/4 — fresh-extract reload path (_import_pdf_vectors)
# ---------------------------------------------------------------------------

def test_fresh_reload_renders_only_selected_layers(qapp):
    """The fresh-extract PDF build path (``_import_pdf_vectors``, reached by
    refresh_underlay -> import_pdf on a PDF Modify) must render only the
    record's selected layers even though the full page was extracted.

    RED-VERIFY: with the ``filter_geoms_by_layers`` call removed from
    ``_import_pdf_vectors``, ``_rendered_layers`` is {A, B, C} and this fails.
    """
    scene = Model_Space()
    record = Underlay(
        type="pdf", path="dummy.pdf", page=0,
        import_mode="vectors",
        selected_layers=["A", "C"],   # dialog selection: drop layer B
    )

    scene._import_pdf_vectors(
        "dummy.pdf", _multi_layer_geoms(),
        x=0.0, y=0.0, _record=record, import_mode="vectors",
    )

    assert scene.underlays, "reload should append an underlay group"
    _rec, group = scene.underlays[-1]
    assert _rendered_layers(group) == {"A", "C"}


def test_fresh_reload_none_selected_renders_all(qapp):
    """``selected_layers is None`` means 'all layers' — no filter applied."""
    scene = Model_Space()
    record = Underlay(
        type="pdf", path="dummy.pdf", page=0,
        import_mode="vectors", selected_layers=None,
    )

    scene._import_pdf_vectors(
        "dummy.pdf", _multi_layer_geoms(),
        x=0.0, y=0.0, _record=record, import_mode="vectors",
    )

    _rec, group = scene.underlays[-1]
    assert _rendered_layers(group) == {"A", "B", "C"}


def test_fresh_reload_hidden_layers_compose_on_top(qapp):
    """The Manager's per-layer ``hidden_layers`` still applies on top of the
    now layer-filtered render set: selecting A/C but hiding C leaves only A
    visible (C's child items exist but are hidden)."""
    scene = Model_Space()
    record = Underlay(
        type="pdf", path="dummy.pdf", page=0,
        import_mode="vectors",
        selected_layers=["A", "C"],
        hidden_layers=["C"],
    )

    scene._import_pdf_vectors(
        "dummy.pdf", _multi_layer_geoms(),
        x=0.0, y=0.0, _record=record, import_mode="vectors",
    )

    _rec, group = scene.underlays[-1]
    # B was filtered out entirely; C is present but hidden; A visible.
    assert _rendered_layers(group) == {"A", "C"}
    visible_layers = {c.data(1) for c in group.childItems()
                      if c.isVisible() and c.data(1) is not None}
    assert visible_layers == {"A"}


# ---------------------------------------------------------------------------
# Step 3/4 — cache-hit reload path (_load_underlay_from_cache)
# ---------------------------------------------------------------------------

def test_cache_hit_renders_only_selected_layers(qapp, tmp_path):
    """A cache HIT for a PDF underlay must ALSO filter by ``selected_layers``.

    The cache holds the FULL page (this reproduces the poisoned-cache case:
    the full page stored under the subset key). Without the cache-hit filter,
    ALL layers render on reload.

    RED-VERIFY: removing the ``filter_geoms_by_layers`` call from
    ``_load_underlay_from_cache`` makes ``_rendered_layers`` == {A, B, C}.
    """
    # A real project path so the cache dir resolves. The source file need not
    # exist: read_cache is called with source_mtime=None (source missing),
    # which skips the freshness check and still returns cached geoms.
    project = tmp_path / "proj.fpd"
    project.write_text("{}", encoding="utf-8")
    src = str(tmp_path / "sheet.pdf")   # not created on disk on purpose

    scene = Model_Space()
    scene._project_path = str(project)

    record = Underlay(
        type="pdf", path=src, page=0,
        import_mode="vectors",
        selected_layers=["A", "C"],
    )

    # Seed the cache with the FULL page under the record's own key.
    cache_dir = cache_dir_for_project(str(project))
    write_cache(cache_dir, record.cache_key(),
                _multi_layer_geoms(), source_mtime=1234.0)

    # source_mtime=None => skip freshness check, force the cache hit.
    ok = scene._load_underlay_from_cache(record, source_mtime=None)
    assert ok is True, "cache should hit and build the group"

    _rec, group = scene.underlays[-1]
    assert _rendered_layers(group) == {"A", "C"}


def test_cache_hit_none_selected_renders_all(qapp, tmp_path):
    """Cache hit with ``selected_layers is None`` renders every cached layer."""
    project = tmp_path / "proj.fpd"
    project.write_text("{}", encoding="utf-8")
    src = str(tmp_path / "sheet.pdf")

    scene = Model_Space()
    scene._project_path = str(project)

    record = Underlay(
        type="pdf", path=src, page=0,
        import_mode="vectors", selected_layers=None,
    )
    cache_dir = cache_dir_for_project(str(project))
    write_cache(cache_dir, record.cache_key(),
                _multi_layer_geoms(), source_mtime=1234.0)

    ok = scene._load_underlay_from_cache(record, source_mtime=None)
    assert ok is True
    _rec, group = scene.underlays[-1]
    assert _rendered_layers(group) == {"A", "B", "C"}
