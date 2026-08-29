"""End-to-end round-trip test for underlay multi-level assignment.

Proves the headline feature: an underlay assigned to MULTIPLE levels
survives save → reload with its .levels list intact.

Path used: raster PDF (synchronous import via import_pdf).
Save/load API: Model_Space.save_to_file / Model_Space.load_from_file.
"""

from __future__ import annotations

import shutil

import pytest
import fitz  # PyMuPDF — already a project dependency

from firepro3d.model_space import Model_Space
from firepro3d.level_manager import LevelManager
from firepro3d.scale_manager import ScaleManager


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_blank_pdf(path) -> None:
    """Write a minimal single-page PDF to *path* using PyMuPDF."""
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    doc.save(str(path))
    doc.close()


def _make_scene(qapp) -> Model_Space:
    """Fresh Model_Space with a LevelManager (Level 1-3) and ScaleManager."""
    scene = Model_Space()
    lm = LevelManager()   # seeds Level 1, Level 2, Level 3 (and more) by default
    scene._level_manager = lm
    scene.scale_manager = ScaleManager()
    return scene


# ── the gate test ─────────────────────────────────────────────────────────────

def test_import_assign_two_levels_save_reload(qapp, tmp_path):
    """Underlay assigned to 2 levels survives save → reload.

    Steps
    -----
    1. Build a real Model_Space with LevelManager (Level 1, 2, 3 available).
    2. Import a raster PDF synchronously via import_pdf().
    3. Assign record.levels = ["Level 1", "Level 3"].
    4. Save to tmp_path/proj.fpd  (path is resolvable because the PDF lives
       in the same tmp_path directory, so the stored relative path is valid).
    5. Reload into a fresh Model_Space via load_from_file().
    6. Assert the reloaded underlay's .levels == ["Level 1", "Level 3"].
    """
    # ── 1. Scene setup ─────────────────────────────────────────────────────
    scene = _make_scene(qapp)

    # Verify the default LevelManager has Level 1, Level 2, Level 3.
    level_names = [lvl.name for lvl in scene._level_manager.levels]
    assert "Level 1" in level_names, f"Expected 'Level 1' in {level_names}"
    assert "Level 2" in level_names, f"Expected 'Level 2' in {level_names}"
    assert "Level 3" in level_names, f"Expected 'Level 3' in {level_names}"

    # ── 2. Import a tiny raster PDF synchronously ──────────────────────────
    pdf_path = tmp_path / "underlay.pdf"
    _make_blank_pdf(pdf_path)

    # Force raster path (import_mode="raster") so the import is fully
    # synchronous even if PDF vector extraction is available.
    scene.import_pdf(str(pdf_path), dpi=72, page=0, import_mode="raster")

    assert len(scene.underlays) == 1, (
        f"Expected 1 underlay after import_pdf, got {len(scene.underlays)}"
    )

    # ── 3. Assign to two levels ────────────────────────────────────────────
    record, _item = scene.underlays[0]
    record.levels = ["Level 1", "Level 3"]

    # ── 4. Save ────────────────────────────────────────────────────────────
    project_file = str(tmp_path / "proj.fpd")
    ok = scene.save_to_file(project_file)
    assert ok is True, "save_to_file returned False"

    # Sanity-check the raw JSON so we can diagnose serialisation failures
    # independently of the reload machinery.
    import json
    with open(project_file) as fh:
        payload = json.load(fh)
    raw_underlays = payload.get("underlays", [])
    assert len(raw_underlays) == 1, (
        f"Expected 1 underlay in JSON, got {len(raw_underlays)}"
    )
    assert raw_underlays[0].get("levels") == ["Level 1", "Level 3"], (
        f"Serialised levels mismatch: {raw_underlays[0].get('levels')}"
    )

    # ── 5. Reload into a fresh scene ───────────────────────────────────────
    scene2 = _make_scene(qapp)
    scene2.load_from_file(project_file)

    # ── 6. Assert multi-level assignment survived ──────────────────────────
    assert len(scene2.underlays) == 1, (
        f"Expected 1 underlay after reload, got {len(scene2.underlays)}"
    )
    record2, _item2 = scene2.underlays[0]
    assert record2.levels == ["Level 1", "Level 3"], (
        f"Reloaded levels mismatch: expected ['Level 1', 'Level 3'], "
        f"got {record2.levels!r}"
    )
