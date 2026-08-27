"""Tests for the paper-space display data module."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtCore import QSettings, QRectF, QPointF
from PyQt6.QtGui import QPen, QColor

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
    validate_line_weight_name,
    validate_line_weight_width,
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
    def test_factory_defaults_all_15_categories(self):
        # 14 model-mirrored categories + the paper-only "Construction" category
        # (bug #3: construction/draw geometry plots via a pen-only paper category).
        cats = FACTORY_PAPER_CATEGORIES
        assert len(cats) == 15

    def test_factory_construction_pen_only(self):
        """Construction is a paper-only, pen-only category (color #000000, no fill)."""
        c = FACTORY_PAPER_CATEGORIES["Construction"]
        assert c["color"] == "#000000"
        assert c["fill"] is None
        assert c["section_color"] is None
        assert c["line_weight"] == "Light"
        assert c["visible"] is True

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

    def test_factory_grid_medium(self):
        # Grid Line factory weight upgraded to Medium (Task 2: bubble-label true-scale)
        assert FACTORY_PAPER_CATEGORIES["Grid Line"]["line_weight"] == "Medium"

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


class TestRoomPaperNoFill:
    """Rooms plot as boundary + tag only — no fill — in paper viewports (#1)."""

    @pytest.fixture
    def scene_with_room(self, qapp):
        from firepro3d.room import Room
        scene = QGraphicsScene()
        pts = [QPointF(0, 0), QPointF(1000, 0),
               QPointF(1000, 1000), QPointF(0, 1000)]
        room = Room(boundary=pts, color="#4488cc")
        scene.addItem(room)
        return scene, room

    def test_apply_sets_no_fill_flag_and_restore_clears(self, scene_with_room):
        scene, room = scene_with_room
        saved = apply_paper_overrides(scene, QRectF(0, 0, 1000, 1000))
        assert getattr(room, "_paper_no_fill", False) is True, (
            "apply_paper_overrides must flag rooms as no-fill for paper"
        )
        restore_model_display(saved)
        assert not hasattr(room, "_paper_no_fill"), (
            "_paper_no_fill must be cleaned up on restore (round-trip)"
        )

    def _render_interior_pixel(self, scene):
        from PyQt6.QtGui import QImage, QPainter
        img = QImage(100, 100, QImage.Format.Format_ARGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        scene.render(p, target=QRectF(0, 0, 100, 100),
                     source=QRectF(0, 0, 1000, 1000))
        p.end()
        # (25,25) px → model (250,250): room interior, clear of the centroid tag.
        return img.pixelColor(25, 25)

    def test_room_interior_unfilled_in_paper(self, scene_with_room):
        scene, room = scene_with_room
        room._paper_no_fill = True
        assert self._render_interior_pixel(scene) == QColor("white"), (
            "room interior must render unfilled (background) in paper viewports"
        )

    def test_room_interior_filled_on_model_canvas(self, scene_with_room):
        scene, room = scene_with_room
        # No flag = model canvas: the alpha-50 wash tints the interior.
        assert self._render_interior_pixel(scene) != QColor("white"), (
            "room interior must stay filled on the model canvas (no regression)"
        )


class TestRoomLabelPaperHeight:
    """Room tag labels plot at a fixed on-paper cap height (§9.9), not the
    model-unit size that shrinks to invisible at architectural plot scale."""

    @pytest.fixture
    def scene_with_room(self, qapp):
        from firepro3d.room import Room
        scene = QGraphicsScene()
        pts = [QPointF(0, 0), QPointF(6000, 0),
               QPointF(6000, 4000), QPointF(0, 4000)]
        room = Room(boundary=pts, color="#4488cc")
        room._tag = "R101"
        room._show_label = True
        scene.addItem(room)
        if hasattr(room, "_update_label"):
            room._update_label()
        return scene, room

    def test_room_category_has_label_height(self):
        assert FACTORY_PAPER_CATEGORIES["Room"].get("label_height_mm") == 2.5

    def test_label_font_scaled_to_paper_then_restored(self, scene_with_room):
        scene, room = scene_with_room
        orig = room._label_font_size
        # 1:100 viewport → paper_scale 0.01. A 2.5 mm paper cap must map to a
        # model font of 2.5 / 0.01 = 250 units so it renders at 2.5 mm on paper.
        saved = apply_paper_overrides(scene, QRectF(0, 0, 6000, 4000),
                                      paper_scale=0.01)
        assert room._label_font_size == pytest.approx(2.5 / 0.01)
        assert room._label_font_size > orig, (
            "at plot scale the paper-height font must be larger than the "
            "model-unit font (otherwise it shrinks to sub-pixel)"
        )
        restore_model_display(saved)
        assert room._label_font_size == pytest.approx(orig), (
            "the model-unit font size must be restored after the render"
        )

    def test_label_paper_height_independent_of_scale(self, scene_with_room):
        """The on-paper size (font × paper_scale) is constant across scales."""
        scene, room = scene_with_room
        for S in (0.005, 0.01, 0.05):
            saved = apply_paper_overrides(scene, QRectF(0, 0, 6000, 4000),
                                          paper_scale=S)
            on_paper = room._label_font_size * S
            assert on_paper == pytest.approx(2.5, abs=1e-6)
            restore_model_display(saved)

    def test_light_label_forced_dark_on_bw_paper_then_restored(self, scene_with_room):
        """A light model label colour (readable on the dark canvas) must become
        the paper category colour on B&W paper — else it's white-on-white."""
        scene, room = scene_with_room
        room._label_font_color = "#ffffff"   # light model colour
        save_paper_color_mode(PaperColorMode.BW)
        saved = apply_paper_overrides(scene, QRectF(0, 0, 6000, 4000),
                                      paper_scale=0.01)
        assert room._label_font_color == FACTORY_PAPER_CATEGORIES["Room"]["color"]
        assert str(room._label_font_color).lstrip("#").lower() == "000000"
        restore_model_display(saved)
        assert room._label_font_color == "#ffffff", "model label colour not restored"

    def test_fullcolor_keeps_authored_label_color(self, scene_with_room):
        scene, room = scene_with_room
        room._label_font_color = "#123456"
        save_paper_color_mode(PaperColorMode.FULL_COLOR)
        saved = apply_paper_overrides(scene, QRectF(0, 0, 6000, 4000),
                                      paper_scale=0.01)
        assert room._label_font_color == "#123456", "full-colour must keep authored colour"
        restore_model_display(saved)


class TestResolveLineWeight:
    def test_known_weight(self):
        mm = resolve_line_weight_mm("Medium")
        assert mm == 0.25

    def test_unknown_weight_returns_default(self):
        mm = resolve_line_weight_mm("Nonexistent")
        assert mm == 0.25


class TestLineWeightValidation:
    def test_reject_empty_name(self):
        existing = [LineWeightDef("Light", 0.18)]
        assert validate_line_weight_name("", existing) is False

    def test_reject_duplicate_name(self):
        existing = [LineWeightDef("Light", 0.18)]
        assert validate_line_weight_name("Light", existing) is False

    def test_accept_unique_name(self):
        existing = [LineWeightDef("Light", 0.18)]
        assert validate_line_weight_name("Heavy", existing) is True

    def test_reject_zero_width(self):
        assert validate_line_weight_width(0.0) is False

    def test_reject_negative_width(self):
        assert validate_line_weight_width(-0.1) is False

    def test_reject_over_max(self):
        assert validate_line_weight_width(3.01) is False

    def test_accept_valid_width(self):
        assert validate_line_weight_width(0.25) is True

    def test_accept_max_width(self):
        assert validate_line_weight_width(3.00) is True


class TestViewportIntegration:
    """Integration tests for viewport rendering with paper display overrides."""

    @pytest.fixture
    def scene_with_wall(self, qapp):
        from firepro3d.wall import WallSegment
        scene = QGraphicsScene()
        wall = WallSegment(QPointF(0, 0), QPointF(200, 0), thickness_mm=100)
        scene.addItem(wall)
        wall._display_color = "#666666"
        return scene, wall

    def test_bw_mode_sets_wall_black(self, scene_with_wall):
        scene, wall = scene_with_wall
        save_paper_color_mode(PaperColorMode.BW)
        source_rect = QRectF(-10, -60, 220, 120)
        saved = apply_paper_overrides(scene, source_rect)
        assert wall._display_color == "#000000"
        restore_model_display(saved)
        assert wall._display_color == "#666666"

    def test_line_weight_applied(self, scene_with_wall):
        scene, wall = scene_with_wall
        cats = load_paper_categories()
        cats["Wall"]["line_weight"] = "Heavy"
        save_paper_categories(cats)
        source_rect = QRectF(-10, -60, 220, 120)
        saved = apply_paper_overrides(scene, source_rect)
        pen = wall.pen()
        assert pen.widthF() == pytest.approx(0.35, abs=0.01)
        assert pen.isCosmetic() is False
        restore_model_display(saved)

    def test_full_color_preserves_model_colors(self, scene_with_wall):
        scene, wall = scene_with_wall
        save_paper_color_mode(PaperColorMode.FULL_COLOR)
        source_rect = QRectF(-10, -60, 220, 120)
        saved = apply_paper_overrides(scene, source_rect)
        assert wall._display_color == "#666666"  # unchanged
        restore_model_display(saved)

    def test_opacity_applied(self, scene_with_wall):
        scene, wall = scene_with_wall
        cats = load_paper_categories()
        cats["Wall"]["opacity"] = 50
        save_paper_categories(cats)
        source_rect = QRectF(-10, -60, 220, 120)
        saved = apply_paper_overrides(scene, source_rect)
        assert wall.opacity() == pytest.approx(0.5, abs=0.01)
        restore_model_display(saved)
        assert wall.opacity() == pytest.approx(1.0, abs=0.01)

    def test_per_instance_override_ignored_in_paper_space(self, scene_with_wall):
        """Paper-space category settings override model per-instance overrides."""
        scene, wall = scene_with_wall
        wall._display_overrides = {"color": "#ff0000"}
        wall._display_color = "#ff0000"
        save_paper_color_mode(PaperColorMode.BW)
        source_rect = QRectF(-10, -60, 220, 120)
        saved = apply_paper_overrides(scene, source_rect)
        assert wall._display_color == "#000000"
        restore_model_display(saved)
        assert wall._display_color == "#ff0000"


class TestProjectRoundTrip:
    def test_save_load_round_trip(self):
        """Verify paper display survives project save -> load cycle."""
        save_paper_color_mode(PaperColorMode.CUSTOM)
        cats = load_paper_categories()
        cats["Pipe"]["line_weight"] = "Heavy"
        cats["Pipe"]["opacity"] = 75
        save_paper_categories(cats)

        saved_data = get_paper_display_for_save()

        save_paper_color_mode(PaperColorMode.BW)
        save_paper_categories(FACTORY_PAPER_CATEGORIES)

        apply_paper_display_from_project(saved_data)
        assert load_paper_color_mode() == PaperColorMode.CUSTOM
        loaded = load_paper_categories()
        assert loaded["Pipe"]["line_weight"] == "Heavy"
        assert loaded["Pipe"]["opacity"] == 75
