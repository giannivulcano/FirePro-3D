"""Unit tests for the Paper Space system (firepro3d/paper_space.py)."""
from __future__ import annotations

import base64
import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtCore import QRectF, QPointF, Qt, QBuffer, QIODevice
from PyQt6.QtGui import QImage, QPainter

from firepro3d.paper_space import (
    PAPER_SIZES, MARGIN, INNER_MARGIN, TITLE_H,
    TitleBlockItem, PaperScene, PaperSpaceWidget,
    Sheet, ViewResolver, SheetViewData,
    TitleBlockTemplateItem, build_field_values,
)
from firepro3d.titleblock_template import (
    FieldDef, Slot, TemplateLayout, solve_layout, make_default_template,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def model_scene(qapp):
    """Minimal model-space QGraphicsScene used as viewport source."""
    scene = QGraphicsScene()
    scene.addRect(0, 0, 1000, 1000)
    return scene


@pytest.fixture
def paper_scene(qapp):
    """PaperScene with a default Sheet and mock resolver."""
    sheet = Sheet.create_default()
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.return_value = None  # no actual source views needed
    return PaperScene(sheet, resolver)


# ─────────────────────────────────────────────────────────────────────────────
# Paper sizes catalogue
# ─────────────────────────────────────────────────────────────────────────────

class TestPaperSizes:
    """Validate the PAPER_SIZES catalogue."""

    def test_all_sizes_have_positive_dimensions(self):
        for name, (w, h) in PAPER_SIZES.items():
            assert w > 0, f"{name} width must be positive"
            assert h > 0, f"{name} height must be positive"

    def test_ansi_d_dimensions(self):
        w, h = PAPER_SIZES["ANSI D"]
        assert w == pytest.approx(863.6, abs=0.1)
        assert h == pytest.approx(558.8, abs=0.1)

    def test_ansi_b_dimensions(self):
        w, h = PAPER_SIZES["ANSI B"]
        assert w == pytest.approx(431.8, abs=0.1)
        assert h == pytest.approx(279.4, abs=0.1)

    def test_a4_dimensions(self):
        w, h = PAPER_SIZES["A4"]
        assert w == 210.0
        assert h == 297.0

    def test_expected_sizes_present(self):
        expected = {"A4", "A3", "A2", "A1", "A0",
                    "ANSI B", "ANSI D", "Letter", "D-size"}
        assert expected.issubset(set(PAPER_SIZES.keys()))


# ─────────────────────────────────────────────────────────────────────────────
# TitleBlockItem (programmatic fallback)
# ─────────────────────────────────────────────────────────────────────────────

class TestTitleBlockItem:
    """Tests for the programmatic TitleBlockItem."""

    def test_default_fields(self, qapp):
        tb = TitleBlockItem(600, 400)
        assert "Company" in tb.fields
        assert "Project" in tb.fields
        assert "Scale" in tb.fields
        assert "Drawing No" in tb.fields
        assert "Rev" in tb.fields
        assert "Date" in tb.fields
        assert "Drawn By" in tb.fields
        assert "Checked By" in tb.fields

    def test_default_company(self, qapp):
        tb = TitleBlockItem(600, 400)
        assert tb.fields["Company"] == "Celerity Engineering Limited"

    def test_default_title(self, qapp):
        tb = TitleBlockItem(600, 400)
        assert tb.fields["Title"] == "Fire Suppression Layout"

    def test_fields_mutable(self, qapp):
        tb = TitleBlockItem(600, 400)
        tb.fields["Project"] = "My Project"
        assert tb.fields["Project"] == "My Project"

    def test_bounding_rect_position(self, qapp):
        """Title block sits at the bottom of the sheet inside margins."""
        w, h = 600.0, 400.0
        tb = TitleBlockItem(w, h)
        br = tb.boundingRect()
        expected_x = MARGIN + INNER_MARGIN
        expected_y = h - MARGIN - INNER_MARGIN - TITLE_H
        expected_w = w - 2 * (MARGIN + INNER_MARGIN)
        assert br.x() == pytest.approx(expected_x)
        assert br.y() == pytest.approx(expected_y)
        assert br.width() == pytest.approx(expected_w)
        assert br.height() == pytest.approx(TITLE_H)

    def test_bounding_rect_varies_with_sheet_size(self, qapp):
        tb1 = TitleBlockItem(600, 400)
        tb2 = TitleBlockItem(800, 600)
        assert tb1.boundingRect().width() != tb2.boundingRect().width()
        assert tb1.boundingRect().y() != tb2.boundingRect().y()

    def test_z_value(self, qapp):
        tb = TitleBlockItem(600, 400)
        assert tb.zValue() == 10


# ─────────────────────────────────────────────────────────────────────────────
# PaperScene
# ─────────────────────────────────────────────────────────────────────────────

class TestPaperScene:
    """Tests for PaperScene setup and API."""

    def _make_scene(self, paper_size="ANSI D"):
        """Helper: create a PaperScene with the given paper size."""
        sheet = Sheet.create_default()
        sheet.paper_size = paper_size
        resolver = MagicMock(spec=ViewResolver)
        resolver.resolve.return_value = None
        return PaperScene(sheet, resolver)

    def test_default_paper_size(self, paper_scene):
        assert paper_scene.paper_size == "ANSI D"

    def test_custom_paper_size(self, qapp):
        ps = self._make_scene("A4")
        assert ps.paper_size == "A4"

    def test_paper_size_setter(self, paper_scene):
        paper_scene.paper_size = "A3"
        assert paper_scene.paper_size == "A3"

    def test_invalid_paper_size_ignored(self, paper_scene):
        paper_scene.paper_size = "NONEXISTENT"
        assert paper_scene.paper_size == "ANSI D"

    def test_title_block_not_none(self, paper_scene):
        assert paper_scene.title_block is not None
        assert isinstance(paper_scene.title_block, TitleBlockItem)

    def test_scene_rect_larger_than_paper(self, paper_scene):
        w, h = PAPER_SIZES["ANSI D"]
        sr = paper_scene.sceneRect()
        # Scene rect should include 20 mm padding on each side
        assert sr.width() == pytest.approx(w + 40)
        assert sr.height() == pytest.approx(h + 40)
        assert sr.x() == pytest.approx(-20)
        assert sr.y() == pytest.approx(-20)

    def test_scene_has_items(self, paper_scene):
        # Should have at least: background rect, border rect, title block
        assert len(paper_scene.items()) >= 3

    def test_paper_size_change_rebuilds(self, qapp):
        """Changing paper size triggers a full rebuild."""
        ps = self._make_scene("A4")
        sr_a4 = ps.sceneRect()
        ps.paper_size = "ANSI D"
        sr_ansi = ps.sceneRect()
        assert sr_a4 != sr_ansi

    def test_refresh_viewport_no_crash(self, paper_scene):
        """refresh_viewport() should not raise."""
        paper_scene.refresh_viewport()  # should succeed silently

    def test_empty_viewports_after_setup(self, paper_scene):
        """No viewports when sheet has no sheet_views."""
        assert len(paper_scene.get_viewports()) == 0

    def test_sheet_property(self, paper_scene):
        assert paper_scene.sheet is not None
        assert isinstance(paper_scene.sheet, Sheet)

    def test_all_paper_sizes_construct(self, qapp):
        """PaperScene can be constructed for every size in the catalogue."""
        for name in PAPER_SIZES:
            ps = self._make_scene(name)
            assert ps.paper_size == name

    def test_add_and_remove_viewport(self, qapp):
        model_scene = QGraphicsScene()
        model_scene.addRect(0, 0, 10000, 8000)
        sheet = Sheet.create_default()
        resolver = MagicMock(spec=ViewResolver)
        resolver.resolve.return_value = (model_scene, QRectF(0, 0, 10000, 8000))
        ps = PaperScene(sheet, resolver)

        data = SheetViewData("plan", "Level 1", "Level 1", 0.01, 50, 50, 400, 300)
        vp = ps.add_viewport(data)
        assert len(ps.get_viewports()) == 1
        assert data in sheet.sheet_views

        ps.remove_viewport(vp)
        assert len(ps.get_viewports()) == 0
        assert data not in sheet.sheet_views


# ─────────────────────────────────────────────────────────────────────────────
# PaperSpaceWidget
# ─────────────────────────────────────────────────────────────────────────────

class TestPaperSpaceWidgetAPI:
    """PaperSpaceWidget public API (toolbar retired 2026-07-16 — ribbon owns commands)."""

    def _make_widget(self):
        """Helper: create a PaperSpaceWidget with default Sheet and mock resolver."""
        sheet = Sheet.create_default()
        resolver = MagicMock(spec=ViewResolver)
        resolver.resolve.return_value = None
        return PaperSpaceWidget(sheet, resolver)

    def test_widget_creates(self, qapp):
        widget = self._make_widget()
        assert widget is not None

    def test_default_paper_size(self, qapp):
        widget = self._make_widget()
        assert widget.paper_scene.sheet.paper_size == "ANSI D"

    def test_change_paper_public(self, qapp):
        widget = self._make_widget()
        widget.change_paper("A3")
        assert widget.paper_scene.sheet.paper_size == "A3"

    def test_no_toolbar_attributes(self, qapp):
        widget = self._make_widget()
        assert not hasattr(widget, "_size_combo")
        assert not hasattr(widget, "_add_text_btn")

    def test_set_add_text_mode_emits_signal(self, qapp):
        widget = self._make_widget()
        fired = []
        widget.add_text_mode_toggled.connect(fired.append)
        widget.set_add_text_mode(True)
        assert widget.view._add_text_mode is True
        assert fired == [True]
        widget.set_add_text_mode(False)
        assert fired == [True, False]

    def test_paper_scene_is_set(self, qapp):
        widget = self._make_widget()
        assert widget.paper_scene is not None
        assert isinstance(widget.paper_scene, PaperScene)

    def test_view_exists(self, qapp):
        widget = self._make_widget()
        assert widget.view is not None
        assert widget.view.scene() is widget.paper_scene

    def test_refresh_no_crash(self, qapp):
        widget = self._make_widget()
        widget.refresh_viewport()  # public API; should not raise

    def test_change_paper_accepts_all_named_sizes(self, qapp):
        widget = self._make_widget()
        for name in PAPER_SIZES:
            widget.change_paper(name)
            assert widget.paper_scene.sheet.paper_size == name


# ─────────────────────────────────────────────────────────────────────────────
# Margin / layout constants
# ─────────────────────────────────────────────────────────────────────────────

class TestLayoutConstants:
    """Sanity checks for paper layout constants."""

    def test_margin_positive(self):
        assert MARGIN > 0

    def test_inner_margin_positive(self):
        assert INNER_MARGIN > 0

    def test_title_height_positive(self):
        assert TITLE_H > 0

    def test_title_fits_inside_smallest_paper(self):
        """Title block + margins must fit inside the smallest paper size."""
        min_h = min(h for _, (_, h) in PAPER_SIZES.items())
        required = 2 * (MARGIN + INNER_MARGIN) + TITLE_H
        assert required < min_h, (
            f"Title block ({required:.1f} mm) exceeds smallest paper height "
            f"({min_h:.1f} mm)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Scale helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestScaleHelpers:
    def test_metric_scale_to_float(self):
        from firepro3d.paper_space import scale_to_float
        assert scale_to_float("1:100") == pytest.approx(0.01)
        assert scale_to_float("1:50") == pytest.approx(0.02)
        assert scale_to_float("1:1") == pytest.approx(1.0)
        assert scale_to_float("1:200") == pytest.approx(0.005)

    def test_imperial_scale_to_float(self):
        from firepro3d.paper_space import scale_to_float
        assert scale_to_float('1/4"=1\'-0"') == pytest.approx(1 / 48)
        assert scale_to_float('1/8"=1\'-0"') == pytest.approx(1 / 96)
        assert scale_to_float('1"=1\'-0"') == pytest.approx(1 / 12)
        assert scale_to_float('3/8"=1\'-0"') == pytest.approx(3 / 96)

    def test_custom_scale_to_float(self):
        from firepro3d.paper_space import scale_to_float
        assert scale_to_float("1:125") == pytest.approx(1 / 125)

    def test_invalid_scale_to_float(self):
        from firepro3d.paper_space import scale_to_float
        with pytest.raises(ValueError):
            scale_to_float("not a scale")

    def test_float_to_known_preset(self):
        from firepro3d.paper_space import float_to_scale_str
        assert float_to_scale_str(0.01) == "1:100"
        assert float_to_scale_str(0.02) == "1:50"
        assert float_to_scale_str(1.0) == "1:1"

    def test_float_to_imperial_preset(self):
        from firepro3d.paper_space import float_to_scale_str
        assert float_to_scale_str(1 / 48) == '1/4"=1\'-0"'

    def test_float_to_custom(self):
        from firepro3d.paper_space import float_to_scale_str
        assert float_to_scale_str(1 / 125) == "1:125"


# ─────────────────────────────────────────────────────────────────────────────
# SheetViewData
# ─────────────────────────────────────────────────────────────────────────────

class TestSheetViewData:
    def test_round_trip(self):
        from firepro3d.paper_space import SheetViewData
        svd = SheetViewData(
            source_view_type="plan", source_view_name="Level 1",
            title="Level 1 - Sprinkler Plan", scale=0.01,
            x=25.0, y=25.0, w=400.0, h=300.0,
        )
        d = svd.to_dict()
        restored = SheetViewData.from_dict(d)
        assert restored.source_view_type == "plan"
        assert restored.source_view_name == "Level 1"
        assert restored.title == "Level 1 - Sprinkler Plan"
        assert restored.scale == pytest.approx(0.01)
        assert restored.x == pytest.approx(25.0)
        assert restored.w == pytest.approx(400.0)

    def test_round_trip_new_fields(self):
        from firepro3d.paper_space import SheetViewData
        svd = SheetViewData(
            source_view_type="plan", source_view_name="Level 1",
            title="Level 1", scale=0.01,
            x=25.0, y=25.0, w=400.0, h=300.0,
            show_border=False, view_number="3",
        )
        d = svd.to_dict()
        restored = SheetViewData.from_dict(d)
        assert restored.show_border is False
        assert restored.view_number == "3"

    def test_backward_compat_missing_new_fields(self):
        from firepro3d.paper_space import SheetViewData
        d = {
            "source_view_type": "plan", "source_view_name": "Level 1",
            "title": "Level 1", "scale": 0.01,
            "x": 0, "y": 0, "w": 100, "h": 100,
        }
        restored = SheetViewData.from_dict(d)
        assert restored.show_border is True
        assert restored.view_number == ""

    def test_to_dict_keys(self):
        from firepro3d.paper_space import SheetViewData
        svd = SheetViewData("plan", "Level 1", "Level 1", 0.01, 0, 0, 100, 100)
        d = svd.to_dict()
        assert set(d.keys()) == {
            "source_view_type", "source_view_name", "title",
            "scale", "x", "y", "w", "h",
            "show_border", "view_number",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Sheet
# ─────────────────────────────────────────────────────────────────────────────

class TestSheet:
    def _make_sheet(self):
        from firepro3d.paper_space import Sheet, SheetViewData
        return Sheet(
            number="FP-1.0", name="Fire Suppression Layout",
            paper_size="ANSI D",
            title_block_fields={
                "Company": "Test Corp", "Project": "Test Project",
                "Title": "Level 1 Plan", "Scale": "1:100",
                "Drawing No": "FP-001", "Rev": "A",
                "Date": "10 May 2026", "Drawn By": "GV", "Checked By": "",
            },
            sheet_views=[
                SheetViewData("plan", "Level 1", "Level 1", 0.01, 25, 25, 400, 300),
            ],
        )

    def test_round_trip(self):
        from firepro3d.paper_space import Sheet
        sheet = self._make_sheet()
        d = sheet.to_dict()
        restored = Sheet.from_dict(d)
        assert restored.number == "FP-1.0"
        assert restored.name == "Fire Suppression Layout"
        assert restored.paper_size == "ANSI D"
        assert restored.title_block_fields["Company"] == "Test Corp"
        assert len(restored.sheet_views) == 1
        assert restored.sheet_views[0].source_view_name == "Level 1"

    def test_empty_sheet_views(self):
        from firepro3d.paper_space import Sheet
        sheet = Sheet("FP-1", "Test", "ANSI D", {}, [])
        d = sheet.to_dict()
        restored = Sheet.from_dict(d)
        assert restored.sheet_views == []

    def test_default_fields(self):
        from firepro3d.paper_space import Sheet, DEFAULT_TITLE_BLOCK_FIELDS
        sheet = Sheet.create_default()
        assert sheet.paper_size == "ANSI D"
        assert "Company" in sheet.title_block_fields
        assert sheet.sheet_views == []


# ─────────────────────────────────────────────────────────────────────────────
# ViewResolver
# ─────────────────────────────────────────────────────────────────────────────

class TestViewResolver:
    def _make_resolver(self, qapp):
        from firepro3d.paper_space import ViewResolver
        model_scene = QGraphicsScene()
        model_scene.addRect(0, 0, 10000, 8000)

        plan_mgr = MagicMock()
        plan_view = MagicMock()
        plan_view.view_height = 3000.0
        plan_view.view_depth = 0.0
        plan_mgr._views = {"Plan: Level 1": plan_view}
        plan_mgr.get.return_value = plan_view

        detail_mgr = MagicMock()
        detail_mgr.detail_names = ["Detail 1"]
        marker = MagicMock()
        marker.crop_rect = QRectF(100, 100, 2000, 1500)
        detail_mgr.get_marker.return_value = marker

        elev_mgr = MagicMock()
        elev_scene = QGraphicsScene()
        elev_scene.addRect(0, 0, 5000, 3000)
        elev_mgr.get_scene.return_value = elev_scene
        elev_mgr.open_directions = ["north", "east"]

        return ViewResolver(model_scene, plan_mgr, detail_mgr, elev_mgr)

    def test_available_views(self, qapp):
        resolver = self._make_resolver(qapp)
        views = resolver.available_views()
        assert "Floor Plans" in views
        assert "Plan: Level 1" in views["Floor Plans"]
        assert "Details" in views
        assert "Detail 1" in views["Details"]
        assert "Elevations" in views

    def test_resolve_plan(self, qapp):
        resolver = self._make_resolver(qapp)
        result = resolver.resolve("plan", "Plan: Level 1")
        assert result is not None
        scene, rect = result
        assert scene is not None
        assert not rect.isEmpty()

    def test_resolve_detail(self, qapp):
        resolver = self._make_resolver(qapp)
        result = resolver.resolve("detail", "Detail 1")
        assert result is not None
        scene, rect = result
        assert rect == QRectF(100, 100, 2000, 1500)

    def test_resolve_elevation(self, qapp):
        resolver = self._make_resolver(qapp)
        result = resolver.resolve("elevation", "North")
        assert result is not None

    def test_resolve_missing_returns_none(self, qapp):
        from firepro3d.paper_space import ViewResolver
        model_scene = QGraphicsScene()
        plan_mgr = MagicMock()
        plan_mgr._views = {}
        plan_mgr.get.return_value = None
        detail_mgr = MagicMock()
        detail_mgr.detail_names = []
        detail_mgr.get_marker.return_value = None
        elev_mgr = MagicMock()
        elev_mgr.get_scene.return_value = None
        resolver = ViewResolver(model_scene, plan_mgr, detail_mgr, elev_mgr)
        assert resolver.resolve("plan", "Nonexistent") is None
        assert resolver.resolve("detail", "Nonexistent") is None
        assert resolver.resolve("elevation", "Nonexistent") is None
        assert resolver.resolve("unknown_type", "Foo") is None


# ─────────────────────────────────────────────────────────────────────────────
# SheetViewport
# ─────────────────────────────────────────────────────────────────────────────

class TestSheetViewport:
    def _make_viewport(self, qapp):
        from firepro3d.paper_space import SheetViewData, SheetViewport
        data = SheetViewData("plan", "Level 1", "Level 1", 0.01, 50, 50, 400, 300)
        model_scene = QGraphicsScene()
        model_scene.addRect(0, 0, 40000, 30000)
        resolver = MagicMock()
        resolver.resolve.return_value = (model_scene, QRectF(0, 0, 40000, 30000))
        vp = SheetViewport(data, resolver)
        return vp, data, resolver, model_scene

    def test_rect_matches_data(self, qapp):
        vp, data, _, _ = self._make_viewport(qapp)
        assert vp.boundingRect().width() == pytest.approx(400, abs=20)
        assert vp.boundingRect().height() == pytest.approx(300, abs=20)

    def test_movable_and_selectable(self, qapp):
        vp, _, _, _ = self._make_viewport(qapp)
        flags = vp.flags()
        from PyQt6.QtWidgets import QGraphicsItem
        assert flags & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        assert flags & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable

    def test_mark_dirty_calls_update(self, qapp):
        """mark_dirty() triggers a repaint via update()."""
        from unittest.mock import patch
        vp, _, _, _ = self._make_viewport(qapp)
        with patch.object(vp, "update") as mock_update:
            vp.mark_dirty()
            mock_update.assert_called_once()

    def test_update_data_from_position(self, qapp):
        vp, data, _, _ = self._make_viewport(qapp)
        vp.setPos(100, 200)
        vp.sync_data_from_item()
        assert data.x == pytest.approx(100)
        assert data.y == pytest.approx(200)

    def test_placeholder_on_missing_view(self, qapp):
        from firepro3d.paper_space import SheetViewData, SheetViewport
        data = SheetViewData("plan", "Deleted View", "Deleted", 0.01, 50, 50, 400, 300)
        resolver = MagicMock()
        resolver.resolve.return_value = None
        vp = SheetViewport(data, resolver)
        assert vp._placeholder is True

    def test_source_change_triggers_update(self, qapp):
        """Source scene change triggers mark_dirty -> update()."""
        from unittest.mock import patch
        vp, _, _, model_scene = self._make_viewport(qapp)
        with patch.object(vp, "update") as mock_update:
            model_scene.addRect(500, 500, 100, 100)
            qapp.processEvents()
            assert mock_update.call_count >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Scale Auto-Population
# ─────────────────────────────────────────────────────────────────────────────

class TestScaleAutoPopulation:
    def test_single_viewport_scale(self):
        from firepro3d.paper_space import Sheet, SheetViewData, _compute_scale_field
        sheet = Sheet.create_default()
        sheet.sheet_views = [
            SheetViewData("plan", "L1", "L1", 0.01, 0, 0, 100, 100),
        ]
        assert _compute_scale_field(sheet) == "1:100"

    def test_multiple_same_scale(self):
        from firepro3d.paper_space import Sheet, SheetViewData, _compute_scale_field
        sheet = Sheet.create_default()
        sheet.sheet_views = [
            SheetViewData("plan", "L1", "L1", 0.01, 0, 0, 100, 100),
            SheetViewData("detail", "D1", "D1", 0.01, 200, 0, 100, 100),
        ]
        assert _compute_scale_field(sheet) == "1:100"

    def test_multiple_different_scales(self):
        from firepro3d.paper_space import Sheet, SheetViewData, _compute_scale_field
        sheet = Sheet.create_default()
        sheet.sheet_views = [
            SheetViewData("plan", "L1", "L1", 0.01, 0, 0, 100, 100),
            SheetViewData("detail", "D1", "D1", 0.02, 200, 0, 100, 100),
        ]
        assert _compute_scale_field(sheet) == "AS NOTED"

    def test_no_viewports(self):
        from firepro3d.paper_space import Sheet, _compute_scale_field
        sheet = Sheet.create_default()
        assert _compute_scale_field(sheet) == ""


# ─────────────────────────────────────────────────────────────────────────────
# Serialization (scene_io integration)
# ─────────────────────────────────────────────────────────────────────────────

class TestSerialization:
    def test_backward_compat_no_sheets_key(self):
        from firepro3d.paper_space import Sheet
        payload = {"version": 4}
        sheets = [Sheet.from_dict(d) for d in payload.get("sheets", [])]
        assert sheets == []

    def test_round_trip_via_payload(self):
        from firepro3d.paper_space import Sheet, SheetViewData
        sheet = Sheet(
            number="FP-1.0", name="Test Sheet",
            paper_size="ANSI D",
            title_block_fields={"Company": "Test", "Scale": "1:100"},
            sheet_views=[
                SheetViewData("plan", "Level 1", "Level 1", 0.01, 25, 25, 400, 300),
            ],
        )
        payload = {"sheets": [sheet.to_dict()]}
        loaded = [Sheet.from_dict(d) for d in payload["sheets"]]
        assert len(loaded) == 1
        assert loaded[0].number == "FP-1.0"
        assert len(loaded[0].sheet_views) == 1
        assert loaded[0].sheet_views[0].scale == pytest.approx(0.01)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures for TitleBlockTemplateItem tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tiny_png_b64(qapp):
    """A 4×4 solid-color PNG encoded as base64 ASCII."""
    img = QImage(4, 4, QImage.Format.Format_RGB32)
    img.fill(0xFF336699)
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return base64.b64encode(bytes(buf.data())).decode("ascii")


# ─────────────────────────────────────────────────────────────────────────────
# build_field_values seeding (DD-13)
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildFieldValuesSeeding:
    def test_standard_keys_seeded_empty(self, qapp):
        sheet = Sheet("", "", "ANSI D", {}, [])
        vals = build_field_values(sheet, {})
        for key in ("Title", "Drawing No", "Rev", "Date",
                    "Company", "Project", "Address",
                    "Drawn By", "Checked By"):
            assert key in vals
        assert vals["Title"] == ""

    def test_real_values_still_override(self, qapp):
        sheet = Sheet("", "", "ANSI D", {}, [])
        sheet.title_block_fields["Title"] = "Plan"
        vals = build_field_values(sheet, {"name": "Proj X"})
        assert vals["Title"] == "Plan"
        assert vals["Project"] == "Proj X"


# ─────────────────────────────────────────────────────────────────────────────
# TitleBlockTemplateItem rev-3 renderer
# ─────────────────────────────────────────────────────────────────────────────

class TestTemplateItemRev3:
    def _render(self, template, values=None):
        vals = values or {}
        lay = solve_layout(template.layout, 863.6, 558.8, vals)
        item = TitleBlockTemplateItem(lay, template.layout, vals)
        img = QImage(400, 300, QImage.Format.Format_RGB32)
        img.fill(Qt.GlobalColor.white)
        p = QPainter(img)
        p.scale(0.4, 0.4)
        item.paint(p, None)
        p.end()
        return img

    def _nonwhite(self, img):
        return any(img.pixel(x, y) != 0xFFFFFFFF
                   for x in range(0, 400, 10) for y in range(0, 300, 10))

    def test_default_template_paints(self, qapp):
        assert self._nonwhite(self._render(make_default_template()))

    def test_combined_image_and_text_cell_paints(self, qapp, tiny_png_b64):
        f = FieldDef(id="a", name="Co", label="Company",
                     text="Acme", image_data=tiny_png_b64)
        t = make_default_template()
        t.layout.fields = [f]
        t.layout.rows = [[Slot("a", 40.0)]]
        assert self._nonwhite(self._render(t))

    def test_bad_image_data_warns_not_crashes(self, qapp):
        f = FieldDef(id="a", name="Logo", image_data="not-base64!!!")
        t = make_default_template()
        t.layout.fields = [f]
        t.layout.rows = [[Slot("a", 30.0)]]
        lay = solve_layout(t.layout, 863.6, 558.8, {})
        item = TitleBlockTemplateItem(lay, t.layout, {})
        assert any("could not be decoded" in w for w in item.warnings)

    def test_empty_fields_bounding_rect_no_crash(self, qapp):
        lay0 = TemplateLayout(fields=[], rows=[])
        sol = solve_layout(lay0, 863.6, 558.8, {})
        item = TitleBlockTemplateItem(sol, lay0, {})
        item.boundingRect()          # must not raise on empty max()
