"""Unit tests for the Underlay data model."""
import os
import tempfile

import pytest
from firepro3d.underlay import Underlay
from firepro3d.constants import DEFAULT_LEVEL, DEFAULT_USER_LAYER


class TestUnderlayFields:
    """New fields exist with correct defaults."""

    def test_default_level(self):
        u = Underlay(type="dxf", path="test.dxf")
        assert u.level == DEFAULT_LEVEL

    def test_default_visible(self):
        u = Underlay(type="dxf", path="test.dxf")
        assert u.visible is True

    def test_default_hidden_layers(self):
        u = Underlay(type="dxf", path="test.dxf")
        assert u.hidden_layers == []

    def test_default_import_mode(self):
        u = Underlay(type="pdf", path="test.pdf")
        assert u.import_mode == "auto"

    def test_hidden_layers_not_shared(self):
        """Each instance gets its own list (field default_factory)."""
        a = Underlay(type="dxf", path="a.dxf")
        b = Underlay(type="dxf", path="b.dxf")
        a.hidden_layers.append("Layer0")
        assert b.hidden_layers == []

    def test_default_import_scale(self):
        u = Underlay(type="dxf", path="test.dxf")
        assert u.import_scale == 1.0

    def test_default_import_base_x(self):
        u = Underlay(type="dxf", path="test.dxf")
        assert u.import_base_x == 0.0

    def test_default_import_base_y(self):
        u = Underlay(type="dxf", path="test.dxf")
        assert u.import_base_y == 0.0

    def test_default_selected_layers(self):
        u = Underlay(type="dxf", path="test.dxf")
        assert u.selected_layers is None


class TestUnderlaySerialization:
    """to_dict / from_dict round-trip and backward compat."""

    def test_round_trip_dxf(self):
        u = Underlay(
            type="dxf", path="plans/floor1.dxf",
            x=10.0, y=20.0, scale=2.5, rotation=45.0, opacity=0.8,
            locked=True, colour="#ff0000", line_weight=0.5,
            user_layer="Underlay",
            level="Level 2", visible=False,
            hidden_layers=["A-FURN", "A-ELEC"], import_mode="auto",
        )
        d = u.to_dict()
        u2 = Underlay.from_dict(d)
        assert u2.type == "dxf"
        assert u2.path == "plans/floor1.dxf"
        assert u2.level == "Level 2"
        assert u2.visible is False
        assert u2.hidden_layers == ["A-FURN", "A-ELEC"]
        assert u2.import_mode == "auto"
        assert u2.colour == "#ff0000"
        assert u2.line_weight == 0.5

    def test_round_trip_pdf(self):
        u = Underlay(
            type="pdf", path="plans/sheet.pdf",
            page=2, dpi=300, import_mode="raster",
            level="*", visible=True,
        )
        d = u.to_dict()
        u2 = Underlay.from_dict(d)
        assert u2.page == 2
        assert u2.dpi == 300
        assert u2.import_mode == "raster"
        assert u2.level == "*"

    def test_backward_compat_missing_new_fields(self):
        """Old project files lack level/visible/hidden_layers/import_mode."""
        old_dict = {
            "type": "dxf", "path": "old.dxf",
            "x": 0.0, "y": 0.0, "scale": 1.0,
            "rotation": 0.0, "opacity": 1.0, "locked": False,
            "colour": "#ffffff", "line_weight": 0.0,
            "user_layer": "Default",
        }
        u = Underlay.from_dict(old_dict)
        assert u.level == DEFAULT_LEVEL
        assert u.visible is True
        assert u.hidden_layers == []
        assert u.import_mode == "auto"

    def test_to_dict_includes_new_fields(self):
        u = Underlay(type="dxf", path="test.dxf", level="Level 3",
                     visible=False, hidden_layers=["X"], import_mode="auto")
        d = u.to_dict()
        assert d["level"] == "Level 3"
        assert d["visible"] is False
        assert d["hidden_layers"] == ["X"]
        assert d["import_mode"] == "auto"

    def test_round_trip_import_params(self):
        u = Underlay(
            type="dxf", path="plans/floor1.dxf",
            import_scale=25.4, import_base_x=100.0, import_base_y=200.0,
            selected_layers=["A-WALL", "A-DOOR"],
        )
        d = u.to_dict()
        u2 = Underlay.from_dict(d)
        assert u2.import_scale == 25.4
        assert u2.import_base_x == 100.0
        assert u2.import_base_y == 200.0
        assert u2.selected_layers == ["A-WALL", "A-DOOR"]

    def test_round_trip_selected_layers_none(self):
        u = Underlay(type="dxf", path="test.dxf", selected_layers=None)
        d = u.to_dict()
        u2 = Underlay.from_dict(d)
        assert u2.selected_layers is None

    def test_backward_compat_missing_import_params(self):
        """Old project files lacking the new import-param fields get defaults."""
        old_dict = {
            "type": "dxf", "path": "old.dxf",
            "x": 0.0, "y": 0.0, "scale": 1.0,
            "rotation": 0.0, "opacity": 1.0, "locked": False,
            "colour": "#ffffff", "line_weight": 0.0,
            "user_layer": "Default",
        }
        u = Underlay.from_dict(old_dict)
        assert u.import_scale == 1.0
        assert u.import_base_x == 0.0
        assert u.import_base_y == 0.0
        assert u.selected_layers is None

    def test_to_dict_includes_import_params(self):
        u = Underlay(
            type="dxf", path="test.dxf",
            import_scale=2.0, import_base_x=50.0, import_base_y=75.0,
            selected_layers=["A-WALL"],
        )
        d = u.to_dict()
        assert d["import_scale"] == 2.0
        assert d["import_base_x"] == 50.0
        assert d["import_base_y"] == 75.0
        assert d["selected_layers"] == ["A-WALL"]

    def test_to_dict_selected_layers_none(self):
        u = Underlay(type="dxf", path="test.dxf", selected_layers=None)
        d = u.to_dict()
        assert d["selected_layers"] is None


class TestPathResolution:
    """Path relativize / resolve helpers."""

    def test_relativize_same_dir(self):
        project_dir = "/projects/building"
        abs_path = "/projects/building/plans/floor1.dxf"
        result = Underlay.relativize_path(abs_path, project_dir)
        assert result == os.path.join("plans", "floor1.dxf")

    def test_relativize_one_level_up(self):
        project_dir = "/projects/building"
        abs_path = "/projects/shared/floor1.dxf"
        result = Underlay.relativize_path(abs_path, project_dir)
        assert ".." in result
        assert result.endswith("floor1.dxf")

    def test_relativize_deep_traversal_returns_absolute(self, tmp_path):
        project_dir = str(tmp_path / "a" / "b" / "c")
        abs_path = str(tmp_path.parent / "other" / "deep" / "file.dxf")
        result = Underlay.relativize_path(abs_path, project_dir)
        assert os.path.isabs(result)

    def test_resolve_relative_path(self, tmp_path):
        plans = tmp_path / "plans"
        plans.mkdir()
        dxf = plans / "floor1.dxf"
        dxf.write_text("dummy")
        result = Underlay.resolve_path("plans/floor1.dxf", str(tmp_path))
        assert result is not None
        assert os.path.exists(result)

    def test_resolve_absolute_path(self, tmp_path):
        dxf = tmp_path / "floor1.dxf"
        dxf.write_text("dummy")
        result = Underlay.resolve_path(str(dxf), str(tmp_path))
        assert result == str(dxf)

    def test_resolve_missing_returns_none(self, tmp_path):
        result = Underlay.resolve_path("nonexistent.dxf", str(tmp_path))
        assert result is None

    def test_resolve_relative_fallback_to_absolute(self, tmp_path):
        """Relative resolution fails but stored path exists as absolute."""
        dxf = tmp_path / "floor1.dxf"
        dxf.write_text("dummy")
        result = Underlay.resolve_path(str(dxf), "/some/other/dir")
        assert result == str(dxf)
