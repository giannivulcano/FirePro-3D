"""Unit tests for the Underlay data model."""
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
