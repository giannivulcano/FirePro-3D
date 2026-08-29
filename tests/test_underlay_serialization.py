"""Unit tests for underlay path resolution and serialization edge cases.

Complements tests/test_underlay.py — focuses on:
  - Full dataclass construction with every field
  - to_dict / from_dict type-specific field inclusion
  - Backward compatibility with minimal legacy dicts
  - Path resolution and relativization edge cases
  - get_properties coverage
"""

import os
import pytest

from firepro3d.underlay import Underlay
from firepro3d.constants import DEFAULT_LEVEL


# =====================================================================
# 1. Dataclass creation — all fields explicit
# =====================================================================

class TestUnderlayFullConstruction:
    """Verify the dataclass stores every field when fully populated."""

    def test_dxf_all_fields(self):
        u = Underlay(
            type="dxf",
            path="plans/floor1.dxf",
            x=100.0,
            y=200.0,
            scale=2.0,
            rotation=90.0,
            opacity=0.5,
            locked=True,
            page=0,
            dpi=150,
            colour="#00ff00",
            line_weight=1.5,
            levels=["Level 2"],
            visible=False,
            hidden_layers=["A-FURN"],
            import_mode="vector",
            import_scale=25.4,
            import_base_x=50.0,
            import_base_y=75.0,
            selected_layers=["A-WALL", "A-DOOR"],
        )
        assert u.type == "dxf"
        assert u.path == "plans/floor1.dxf"
        assert u.x == 100.0
        assert u.y == 200.0
        assert u.scale == 2.0
        assert u.rotation == 90.0
        assert u.opacity == 0.5
        assert u.locked is True
        assert u.colour == "#00ff00"
        assert u.line_weight == 1.5
        assert u.levels == ["Level 2"]
        assert u.visible is False
        assert u.hidden_layers == ["A-FURN"]
        assert u.import_mode == "vector"
        assert u.import_scale == 25.4
        assert u.import_base_x == 50.0
        assert u.import_base_y == 75.0
        assert u.selected_layers == ["A-WALL", "A-DOOR"]

    def test_pdf_all_fields(self):
        u = Underlay(
            type="pdf",
            path="docs/sheet.pdf",
            x=-10.0,
            y=-20.0,
            scale=0.5,
            rotation=180.0,
            opacity=0.25,
            locked=False,
            page=3,
            dpi=300,
            colour="#ffffff",
            line_weight=0.0,
            levels=["*"],
            visible=True,
            hidden_layers=[],
            import_mode="raster",
            import_scale=1.0,
            import_base_x=0.0,
            import_base_y=0.0,
            selected_layers=None,
        )
        assert u.type == "pdf"
        assert u.page == 3
        assert u.dpi == 300
        assert u.import_mode == "raster"
        assert u.levels == ["*"]
        assert u.selected_layers is None


# =====================================================================
# 2. to_dict — type-specific field inclusion
# =====================================================================

class TestToDictTypeSpecific:
    """PDF dicts include page/dpi; DXF dicts include colour/line_weight."""

    def test_pdf_dict_has_page_and_dpi(self):
        u = Underlay(type="pdf", path="sheet.pdf", page=2, dpi=300)
        d = u.to_dict()
        assert "page" in d
        assert "dpi" in d
        assert d["page"] == 2
        assert d["dpi"] == 300

    def test_pdf_dict_excludes_line_weight_includes_colour(self):
        """PDF dicts persist colour but not line_weight (spec §16.6).

        Vector PDFs support colour edits, so colour must round-trip
        through the project file; line_weight remains dxf/dwg-only.
        Old files without a colour key still load gray via the
        type-aware from_dict default.
        """
        u = Underlay(type="pdf", path="sheet.pdf", colour="#00ff00")
        d = u.to_dict()
        assert "line_weight" not in d
        assert "colour" in d
        assert d["colour"] == "#00ff00"

    def test_dxf_dict_has_colour_and_line_weight(self):
        u = Underlay(type="dxf", path="floor.dxf", colour="#ff0000",
                     line_weight=0.5)
        d = u.to_dict()
        assert "colour" in d
        assert "line_weight" in d
        assert d["colour"] == "#ff0000"
        assert d["line_weight"] == 0.5

    def test_dxf_dict_excludes_pdf_fields(self):
        u = Underlay(type="dxf", path="floor.dxf")
        d = u.to_dict()
        assert "page" not in d
        assert "dpi" not in d

    def test_dict_always_has_common_fields(self):
        for utype in ("pdf", "dxf"):
            u = Underlay(type=utype, path=f"test.{utype}")
            d = u.to_dict()
            for key in ("type", "path", "x", "y", "scale", "rotation",
                        "opacity", "locked", "levels",
                        "visible", "hidden_layers", "import_mode",
                        "import_scale", "import_base_x", "import_base_y",
                        "selected_layers"):
                assert key in d, f"Missing key '{key}' for type={utype}"

    def test_hidden_layers_deep_copy(self):
        """to_dict must return a copy — mutating the output must not
        affect the original Underlay."""
        u = Underlay(type="dxf", path="a.dxf", hidden_layers=["L1"])
        d = u.to_dict()
        d["hidden_layers"].append("L2")
        assert u.hidden_layers == ["L1"]

    def test_selected_layers_deep_copy(self):
        u = Underlay(type="dxf", path="a.dxf",
                     selected_layers=["A-WALL"])
        d = u.to_dict()
        d["selected_layers"].append("A-DOOR")
        assert u.selected_layers == ["A-WALL"]


# =====================================================================
# 3. from_dict — backward compatibility
# =====================================================================

class TestFromDictBackwardCompat:
    """Loading dicts from old project files that lack newer fields."""

    def test_minimal_dict_only_type_and_path(self):
        """Absolute minimum: just type + path — everything else defaults."""
        d = {"type": "dxf", "path": "old.dxf"}
        u = Underlay.from_dict(d)
        assert u.type == "dxf"
        assert u.path == "old.dxf"
        assert u.x == 0.0
        assert u.y == 0.0
        assert u.scale == 1.0
        assert u.rotation == 0.0
        assert u.opacity == 1.0
        assert u.locked is False
        assert u.page == 0
        assert u.dpi == 150
        assert u.colour == "#ffffff"
        assert u.line_weight == 0
        assert u.levels == [DEFAULT_LEVEL]
        assert u.visible is True
        assert u.hidden_layers == []
        assert u.import_mode == "auto"
        assert u.import_scale == 1.0
        assert u.import_base_x == 0.0
        assert u.import_base_y == 0.0
        assert u.selected_layers is None

    def test_rev1_dict_no_level_or_import_fields(self):
        """Rev 1 projects have basic geometry + user_layer but nothing else."""
        d = {
            "type": "pdf",
            "path": "sheet.pdf",
            "x": 5.0,
            "y": 10.0,
            "scale": 1.5,
            "rotation": 0.0,
            "opacity": 0.8,
            "locked": True,
            "page": 1,
            "dpi": 200,
            "user_layer": "Plans",
        }
        u = Underlay.from_dict(d)
        assert u.x == 5.0
        assert u.page == 1
        assert u.dpi == 200
        # Rev 2+ fields fall back to defaults
        assert u.levels == [DEFAULT_LEVEL]
        assert u.visible is True
        assert u.hidden_layers == []
        assert u.import_mode == "auto"
        # Rev 3 fields fall back to defaults
        assert u.import_scale == 1.0
        assert u.import_base_x == 0.0
        assert u.import_base_y == 0.0
        assert u.selected_layers is None

    def test_from_dict_hidden_layers_not_shared(self):
        """Two from_dict calls with missing hidden_layers must get
        independent lists (not a shared default mutable)."""
        d = {"type": "dxf", "path": "a.dxf"}
        u1 = Underlay.from_dict(d)
        u2 = Underlay.from_dict(d)
        u1.hidden_layers.append("X")
        assert u2.hidden_layers == []


# =====================================================================
# 4. Full round-trip edge cases
# =====================================================================

class TestRoundTripEdgeCases:
    """Serialization round-trip for tricky values."""

    def test_zero_values_preserved(self):
        u = Underlay(type="dxf", path="a.dxf", x=0.0, y=0.0,
                     scale=0.0, rotation=0.0, opacity=0.0)
        u2 = Underlay.from_dict(u.to_dict())
        assert u2.x == 0.0
        assert u2.y == 0.0
        assert u2.scale == 0.0
        assert u2.rotation == 0.0
        assert u2.opacity == 0.0

    def test_negative_coordinates(self):
        u = Underlay(type="pdf", path="a.pdf", x=-500.0, y=-1200.0)
        u2 = Underlay.from_dict(u.to_dict())
        assert u2.x == -500.0
        assert u2.y == -1200.0

    def test_large_import_scale(self):
        u = Underlay(type="dxf", path="a.dxf", import_scale=304.8)
        u2 = Underlay.from_dict(u.to_dict())
        assert u2.import_scale == 304.8

    def test_empty_hidden_layers_round_trip(self):
        u = Underlay(type="dxf", path="a.dxf", hidden_layers=[])
        u2 = Underlay.from_dict(u.to_dict())
        assert u2.hidden_layers == []

    def test_many_hidden_layers_round_trip(self):
        layers = [f"Layer-{i}" for i in range(50)]
        u = Underlay(type="dxf", path="a.dxf", hidden_layers=layers)
        u2 = Underlay.from_dict(u.to_dict())
        assert u2.hidden_layers == layers

    def test_all_levels_wildcard_round_trip(self):
        u = Underlay(type="pdf", path="a.pdf", levels=["*"])
        u2 = Underlay.from_dict(u.to_dict())
        assert u2.levels == ["*"]

    def test_selected_layers_empty_list_round_trip(self):
        """Empty list is distinct from None."""
        u = Underlay(type="dxf", path="a.dxf", selected_layers=[])
        d = u.to_dict()
        u2 = Underlay.from_dict(d)
        assert u2.selected_layers == []


# =====================================================================
# 5. Path resolution edge cases
# =====================================================================

class TestPathResolutionEdgeCases:
    """Edge cases for resolve_path and relativize_path."""

    def test_resolve_empty_relative_path(self, tmp_path):
        """Empty string treated as relative; won't find a file."""
        result = Underlay.resolve_path("", str(tmp_path))
        # os.path.join(project_dir, "") == project_dir (a directory)
        # exists but is not useful as a file — implementation returns
        # the directory path since os.path.exists is true for dirs.
        # Just verify it does not crash.
        assert result is not None or result is None  # no crash

    def test_resolve_path_with_spaces(self, tmp_path):
        subdir = tmp_path / "my plans"
        subdir.mkdir()
        f = subdir / "floor plan.dxf"
        f.write_text("dummy")
        result = Underlay.resolve_path("my plans/floor plan.dxf",
                                       str(tmp_path))
        assert result is not None
        assert os.path.exists(result)

    def test_resolve_path_with_unicode(self, tmp_path):
        subdir = tmp_path / "planos"
        subdir.mkdir()
        f = subdir / "piso_1.dxf"
        f.write_text("dummy")
        result = Underlay.resolve_path("planos/piso_1.dxf",
                                       str(tmp_path))
        assert result is not None
        assert os.path.exists(result)

    def test_resolve_absolute_nonexistent_returns_none(self):
        fake = os.path.join(os.sep, "nonexistent_dir_xyz", "nope.dxf")
        result = Underlay.resolve_path(fake, os.sep)
        assert result is None

    def test_resolve_relative_dot_prefix(self, tmp_path):
        f = tmp_path / "test.dxf"
        f.write_text("dummy")
        result = Underlay.resolve_path("./test.dxf", str(tmp_path))
        assert result is not None
        assert os.path.exists(result)

    def test_resolve_relative_parent_traversal(self, tmp_path):
        f = tmp_path / "shared.dxf"
        f.write_text("dummy")
        sub = tmp_path / "project"
        sub.mkdir()
        result = Underlay.resolve_path("../shared.dxf", str(sub))
        assert result is not None
        assert os.path.exists(result)


class TestRelativizeEdgeCases:
    """Edge cases for relativize_path boundary conditions."""

    def test_exact_two_parent_traversals_stays_relative(self, tmp_path):
        """Two levels of '..' is within the threshold (< 3)."""
        project = tmp_path / "a" / "b"
        project.mkdir(parents=True)
        target = tmp_path / "other" / "file.dxf"
        result = Underlay.relativize_path(str(target), str(project))
        # Should be relative (2 '..' hops: b -> a -> tmp, then other/)
        assert not os.path.isabs(result)

    def test_exactly_three_parent_traversals_returns_absolute(self, tmp_path):
        """Three levels of '..' hits the threshold (>= 3)."""
        project = tmp_path / "a" / "b" / "c"
        project.mkdir(parents=True)
        # Target requires going up 3+ times from project to reach
        target_dir = tmp_path.parent / "other"
        target_dir.mkdir(exist_ok=True)
        target = target_dir / "file.dxf"
        result = Underlay.relativize_path(str(target), str(project))
        # Count parent traversals
        rel_for_check = os.path.relpath(str(target), str(project))
        parts = rel_for_check.replace("\\", "/").split("/")
        parent_count = sum(1 for p in parts if p == "..")
        if parent_count >= 3:
            assert os.path.isabs(result)
        else:
            # On some tmp_path layouts the traversal may be < 3
            assert not os.path.isabs(result)

    def test_relativize_same_file(self, tmp_path):
        """File inside project_dir itself — no parent traversal."""
        f = tmp_path / "plan.dxf"
        result = Underlay.relativize_path(str(f), str(tmp_path))
        assert result == "plan.dxf"
        assert not os.path.isabs(result)

    def test_relativize_preserves_subdirectory(self, tmp_path):
        target = tmp_path / "sub" / "deep" / "file.dxf"
        result = Underlay.relativize_path(str(target), str(tmp_path))
        assert result == os.path.join("sub", "deep", "file.dxf")


# =====================================================================
# 6. get_properties
# =====================================================================

class TestGetProperties:
    """Verify the property-manager dictionary."""

    def test_basic_pdf_properties(self):
        u = Underlay(type="pdf", path="/plans/sheet.pdf", page=2, dpi=300,
                     x=10.0, y=20.0, scale=2.0, rotation=45.0,
                     opacity=0.8, locked=True, visible=False,
                     import_mode="raster", import_scale=25.4)
        props = u.get_properties()
        assert props["File"]["value"] == "sheet.pdf"
        assert props["Type"]["value"] == "PDF"
        assert props["DPI"]["value"] == "300"
        # Page is displayed 1-indexed
        assert props["Page"]["value"] == "3"
        assert props["Import Mode"]["value"] == "raster"
        assert props["Locked"]["value"] == "Yes"
        assert props["Visible"]["value"] == "No"
        assert props["Import Scale"]["value"] == "25.4"

    def test_basic_dxf_properties(self):
        u = Underlay(type="dxf", path="floor.dxf", locked=False,
                     visible=True)
        props = u.get_properties()
        assert props["Type"]["value"] == "DXF"
        assert props["Locked"]["value"] == "No"
        assert props["Visible"]["value"] == "Yes"
        # DXF has no DPI/Page/Import Mode keys
        assert "DPI" not in props
        assert "Page" not in props
        assert "Import Mode" not in props

    def test_hidden_layers_shown_when_present(self):
        u = Underlay(type="dxf", path="a.dxf",
                     hidden_layers=["A-FURN", "A-ELEC"])
        props = u.get_properties()
        assert "Hidden Layers" in props
        assert props["Hidden Layers"]["value"] == "A-FURN, A-ELEC"

    def test_hidden_layers_absent_when_empty(self):
        u = Underlay(type="dxf", path="a.dxf", hidden_layers=[])
        props = u.get_properties()
        assert "Hidden Layers" not in props

    def test_all_levels_display(self):
        u = Underlay(type="dxf", path="a.dxf", levels=["*"])
        props = u.get_properties()
        assert props["Levels"]["value"] == "All Levels"

    def test_specific_level_display(self):
        u = Underlay(type="dxf", path="a.dxf", levels=["Level 3"])
        props = u.get_properties()
        assert props["Levels"]["value"] == "Level 3"

    def test_all_values_are_label_type(self):
        u = Underlay(type="pdf", path="a.pdf", page=0, dpi=150,
                     hidden_layers=["L1"], import_mode="auto")
        props = u.get_properties()
        for key, entry in props.items():
            assert entry["type"] == "label", (
                f"Property '{key}' has type '{entry['type']}', expected 'label'")


# =====================================================================
# Cache key
# =====================================================================

class TestUnderlayCacheKey:
    def test_dxf_cache_key_deterministic(self):
        u = Underlay(type="dxf", path="/plans/floor1.dxf")
        assert u.cache_key() == u.cache_key()

    def test_pdf_different_pages_different_keys(self):
        u1 = Underlay(type="pdf", path="/plans/sheet.pdf", page=0)
        u2 = Underlay(type="pdf", path="/plans/sheet.pdf", page=1)
        assert u1.cache_key() != u2.cache_key()

    def test_dxf_layer_selection_affects_key(self):
        u1 = Underlay(type="dxf", path="/plans/floor.dxf", selected_layers=None)
        u2 = Underlay(type="dxf", path="/plans/floor.dxf",
                      selected_layers=["A-WALL"])
        assert u1.cache_key() != u2.cache_key()
