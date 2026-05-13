"""Tests for the paper-space display data module."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtCore import QSettings, QRectF

from firepro3d.paper_display import (
    LineWeightDef,
    PaperColorMode,
    FACTORY_LINE_WEIGHTS,
    FACTORY_PAPER_CATEGORIES,
    load_line_weights,
    save_line_weights,
    load_paper_categories,
    save_paper_categories,
    load_paper_color_mode,
    save_paper_color_mode,
    get_paper_display_for_save,
    apply_paper_display_from_project,
    apply_paper_overrides,
    restore_model_display,
    resolve_line_weight_mm,
)


@pytest.fixture(autouse=True)
def _clean_settings():
    """Clear paper/* QSettings before each test."""
    s = QSettings("GV", "FirePro3D")
    s.remove("paper")
    s.sync()
    yield
    s.remove("paper")
    s.sync()


class TestLineWeightDefs:
    def test_factory_defaults_count(self):
        assert len(FACTORY_LINE_WEIGHTS) == 5

    def test_factory_names(self):
        names = [lw.name for lw in FACTORY_LINE_WEIGHTS]
        assert names == ["Very Light", "Light", "Medium", "Heavy", "Very Heavy"]

    def test_factory_widths(self):
        widths = [lw.width_mm for lw in FACTORY_LINE_WEIGHTS]
        assert widths == [0.13, 0.18, 0.25, 0.35, 0.50]

    def test_sorted_ascending(self):
        widths = [lw.width_mm for lw in FACTORY_LINE_WEIGHTS]
        assert widths == sorted(widths)

    def test_round_trip_qsettings(self):
        defs = [LineWeightDef("Thin", 0.10), LineWeightDef("Thick", 0.60)]
        save_line_weights(defs)
        loaded = load_line_weights()
        assert len(loaded) == 2
        assert loaded[0].name == "Thin"
        assert loaded[0].width_mm == 0.10
        assert loaded[1].name == "Thick"
        assert loaded[1].width_mm == 0.60

    def test_load_returns_factory_when_no_settings(self):
        loaded = load_line_weights()
        assert len(loaded) == 5
        assert loaded[0].name == "Very Light"


class TestPaperColorMode:
    def test_default_is_bw(self):
        assert load_paper_color_mode() == PaperColorMode.BW

    def test_round_trip(self):
        save_paper_color_mode(PaperColorMode.FULL_COLOR)
        assert load_paper_color_mode() == PaperColorMode.FULL_COLOR
        save_paper_color_mode(PaperColorMode.CUSTOM)
        assert load_paper_color_mode() == PaperColorMode.CUSTOM

    def test_invalid_value_returns_bw(self):
        s = QSettings("GV", "FirePro3D")
        s.setValue("paper/color_mode", "garbage")
        assert load_paper_color_mode() == PaperColorMode.BW


class TestPaperCategories:
    def test_factory_defaults_all_14_categories(self):
        cats = FACTORY_PAPER_CATEGORIES
        assert len(cats) == 14

    def test_factory_bw_colors(self):
        """Factory default is B&W -- all colors black, fills white."""
        for key, vals in FACTORY_PAPER_CATEGORIES.items():
            assert vals["color"] == "#000000", f"{key} color"
            if vals["fill"] is not None:
                assert vals["fill"] == "#ffffff", f"{key} fill"

    def test_factory_wall_heavy(self):
        assert FACTORY_PAPER_CATEGORIES["Wall"]["line_weight"] == "Heavy"

    def test_factory_pipe_medium(self):
        assert FACTORY_PAPER_CATEGORIES["Pipe"]["line_weight"] == "Medium"

    def test_factory_grid_very_light(self):
        assert FACTORY_PAPER_CATEGORIES["Grid Line"]["line_weight"] == "Very Light"

    def test_round_trip_qsettings(self):
        cats = load_paper_categories()
        cats["Pipe"]["line_weight"] = "Heavy"
        save_paper_categories(cats)
        loaded = load_paper_categories()
        assert loaded["Pipe"]["line_weight"] == "Heavy"

    def test_load_returns_factory_when_no_settings(self):
        loaded = load_paper_categories()
        assert loaded["Pipe"]["line_weight"] == "Medium"


class TestProjectPersistence:
    def test_get_paper_display_for_save(self):
        result = get_paper_display_for_save()
        assert "color_mode" in result
        assert "categories" in result
        assert "Pipe" in result["categories"]

    def test_apply_from_project_overrides_settings(self):
        project_data = {
            "color_mode": "full_color",
            "categories": {
                "Pipe": {
                    "color": "#ff0000",
                    "fill": None,
                    "section_color": None,
                    "line_weight": "Heavy",
                    "opacity": 80,
                },
            },
        }
        apply_paper_display_from_project(project_data)
        cats = load_paper_categories()
        assert cats["Pipe"]["line_weight"] == "Heavy"
        assert cats["Pipe"]["opacity"] == 80
        assert load_paper_color_mode() == PaperColorMode.FULL_COLOR

    def test_apply_from_project_missing_key_uses_factory(self):
        apply_paper_display_from_project({})
        cats = load_paper_categories()
        assert cats["Pipe"]["line_weight"] == "Medium"


class TestProjectFilePersistence:
    """Integration tests for project-file save/load round-trip."""

    def test_save_includes_paper_display(self):
        save_paper_color_mode(PaperColorMode.CUSTOM)
        cats = load_paper_categories()
        cats["Pipe"]["line_weight"] = "Heavy"
        save_paper_categories(cats)
        result = get_paper_display_for_save()
        assert result["color_mode"] == "custom"
        assert result["categories"]["Pipe"]["line_weight"] == "Heavy"

    def test_load_missing_paper_display_uses_factory(self):
        apply_paper_display_from_project({})
        assert load_paper_color_mode() == PaperColorMode.BW
        cats = load_paper_categories()
        assert cats["Pipe"]["line_weight"] == "Medium"

    def test_backward_compat_no_paper_display_key(self):
        """Simulates loading a project file that predates paper_display."""
        apply_paper_display_from_project(None)
        assert load_paper_color_mode() == PaperColorMode.BW


class TestApplyRestore:
    """Verify temporary mutation round-trips cleanly."""

    @pytest.fixture
    def scene_with_pipe(self, qapp):
        """Scene with a minimal Pipe mock."""
        from firepro3d.pipe import Pipe
        from firepro3d.node import Node
        scene = QGraphicsScene()
        n1 = Node(0, 0)
        n2 = Node(100, 0)
        scene.addItem(n1)
        scene.addItem(n2)
        pipe = Pipe(n1, n2)
        scene.addItem(pipe)
        pipe._display_color = "#4488ff"
        pipe._display_scale = 1.0
        return scene, pipe

    def test_apply_bw_changes_pipe_color(self, scene_with_pipe):
        scene, pipe = scene_with_pipe
        save_paper_color_mode(PaperColorMode.BW)
        source_rect = QRectF(0, 0, 200, 200)
        saved = apply_paper_overrides(scene, source_rect)
        assert pipe._display_color == "#000000"
        restore_model_display(saved)
        assert pipe._display_color == "#4488ff"

    def test_apply_full_color_keeps_model_colors(self, scene_with_pipe):
        scene, pipe = scene_with_pipe
        save_paper_color_mode(PaperColorMode.FULL_COLOR)
        source_rect = QRectF(0, 0, 200, 200)
        saved = apply_paper_overrides(scene, source_rect)
        assert pipe._display_color == "#4488ff"
        restore_model_display(saved)

    def test_restore_returns_exact_original_state(self, scene_with_pipe):
        scene, pipe = scene_with_pipe
        original_color = pipe._display_color
        original_opacity = pipe.opacity()
        save_paper_color_mode(PaperColorMode.BW)
        source_rect = QRectF(0, 0, 200, 200)
        saved = apply_paper_overrides(scene, source_rect)
        restore_model_display(saved)
        assert pipe._display_color == original_color
        assert pipe.opacity() == original_opacity


class TestResolveLineWeight:
    def test_known_weight(self):
        mm = resolve_line_weight_mm("Medium")
        assert mm == 0.25

    def test_unknown_weight_returns_default(self):
        mm = resolve_line_weight_mm("Nonexistent")
        assert mm == 0.25
