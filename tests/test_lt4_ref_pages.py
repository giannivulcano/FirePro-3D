"""Seam review M2: the LT4 modules are in the API-reference module list.

The deliverable is the curated ``TIERS`` list itself, so the guard reads it
(via ``ast`` -- ``mkdocs_gen_files`` is a docs-only dependency).
"""
import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_LT4 = ("capability_frame", "repeat_frame", "capability_panel",
        "linetype_authoring", "linetype_pattern")


def _tiers() -> dict:
    tree = ast.parse((_ROOT / "docs" / "gen_ref_pages.py").read_text("utf-8"))
    for node in tree.body:
        if (isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) == "TIERS" for t in node.targets)):
            return ast.literal_eval(node.value)
    raise AssertionError("TIERS not found")


def test_lt4_modules_listed_beside_tile_frame():
    tiers = _tiers()
    home = next(t for t, mods in tiers.items() if "tile_frame" in mods)
    for name in _LT4:
        assert name in tiers[home], name
        # the generator skips a missing file silently -- each must exist
        assert (_ROOT / "firepro3d" / f"{name}.py").exists(), name
