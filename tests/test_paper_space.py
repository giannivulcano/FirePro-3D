"""Unit tests for the Paper Space system (firepro3d/paper_space.py)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtCore import QRectF, QPointF, Qt

from firepro3d.paper_space import (
    PAPER_SIZES, MARGIN, INNER_MARGIN, TITLE_H,
    TitleBlockItem, PaperViewport, PaperScene, PaperSpaceWidget,
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
# PaperViewport
# ─────────────────────────────────────────────────────────────────────────────

class TestPaperViewport:
    """Tests for the PaperViewport item."""

    def test_rect_matches_constructor(self, model_scene):
        vp = PaperViewport(model_scene, 10, 20, 300, 200)
        r = vp.rect()
        assert r.x() == pytest.approx(10)
        assert r.y() == pytest.approx(20)
        assert r.width() == pytest.approx(300)
        assert r.height() == pytest.approx(200)

    def test_source_rect_default_none(self, model_scene):
        vp = PaperViewport(model_scene, 0, 0, 100, 100)
        assert vp.source_rect is None

    def test_source_rect_setter(self, model_scene):
        vp = PaperViewport(model_scene, 0, 0, 100, 100)
        src = QRectF(50, 50, 200, 200)
        vp.source_rect = src
        assert vp.source_rect == src

    def test_source_rect_reset_to_none(self, model_scene):
        vp = PaperViewport(model_scene, 0, 0, 100, 100)
        vp.source_rect = QRectF(0, 0, 50, 50)
        vp.source_rect = None
        assert vp.source_rect is None

    def test_is_movable(self, model_scene):
        vp = PaperViewport(model_scene, 0, 0, 100, 100)
        flags = vp.flags()
        assert flags & vp.GraphicsItemFlag.ItemIsMovable

    def test_is_selectable(self, model_scene):
        vp = PaperViewport(model_scene, 0, 0, 100, 100)
        flags = vp.flags()
        assert flags & vp.GraphicsItemFlag.ItemIsSelectable

    def test_z_value(self, model_scene):
        vp = PaperViewport(model_scene, 0, 0, 100, 100)
        assert vp.zValue() == 5

    def test_white_brush(self, model_scene):
        vp = PaperViewport(model_scene, 0, 0, 100, 100)
        assert vp.brush().color() == Qt.GlobalColor.white


# ─────────────────────────────────────────────────────────────────────────────
# PaperScene
# ─────────────────────────────────────────────────────────────────────────────

class TestPaperScene:
    """Tests for PaperScene setup and API."""

    def test_default_paper_size(self, model_scene):
        ps = PaperScene(model_scene)
        assert ps.paper_size == "ANSI D"

    def test_custom_paper_size(self, model_scene):
        ps = PaperScene(model_scene, paper_size="A4")
        assert ps.paper_size == "A4"

    def test_paper_size_setter(self, model_scene):
        ps = PaperScene(model_scene, paper_size="ANSI D")
        ps.paper_size = "A3"
        assert ps.paper_size == "A3"

    def test_invalid_paper_size_ignored(self, model_scene):
        ps = PaperScene(model_scene, paper_size="ANSI D")
        ps.paper_size = "NONEXISTENT"
        assert ps.paper_size == "ANSI D"

    def test_title_block_not_none(self, model_scene):
        ps = PaperScene(model_scene)
        assert ps.title_block is not None
        assert isinstance(ps.title_block, TitleBlockItem)

    def test_scene_rect_larger_than_paper(self, model_scene):
        ps = PaperScene(model_scene, paper_size="ANSI D")
        w, h = PAPER_SIZES["ANSI D"]
        sr = ps.sceneRect()
        # Scene rect should include 20 mm padding on each side
        assert sr.width() == pytest.approx(w + 40)
        assert sr.height() == pytest.approx(h + 40)
        assert sr.x() == pytest.approx(-20)
        assert sr.y() == pytest.approx(-20)

    def test_scene_has_items(self, model_scene):
        ps = PaperScene(model_scene)
        # Should have at least: background rect, border rect, title block, viewport
        assert len(ps.items()) >= 4

    def test_paper_size_change_rebuilds(self, model_scene):
        """Changing paper size triggers a full rebuild."""
        ps = PaperScene(model_scene, paper_size="A4")
        sr_a4 = ps.sceneRect()
        ps.paper_size = "ANSI D"
        sr_ansi = ps.sceneRect()
        assert sr_a4 != sr_ansi

    def test_refresh_viewport_no_crash(self, model_scene):
        """refresh_viewport() should not raise."""
        ps = PaperScene(model_scene)
        ps.refresh_viewport()  # should succeed silently

    def test_viewport_exists_after_setup(self, model_scene):
        ps = PaperScene(model_scene)
        assert ps._viewport is not None
        assert isinstance(ps._viewport, PaperViewport)

    def test_viewport_inside_margins(self, model_scene):
        """Viewport rect should sit within the border margins."""
        ps = PaperScene(model_scene, paper_size="ANSI D")
        vp = ps._viewport
        r = vp.rect()
        w, h = PAPER_SIZES["ANSI D"]
        # Viewport x must be >= MARGIN + INNER_MARGIN
        assert r.x() >= MARGIN + INNER_MARGIN - 1
        # Viewport right edge must be <= w - MARGIN - INNER_MARGIN
        assert r.x() + r.width() <= w - MARGIN - INNER_MARGIN + 1
        # Viewport y must be >= MARGIN + INNER_MARGIN
        assert r.y() >= MARGIN + INNER_MARGIN - 1

    def test_all_paper_sizes_construct(self, model_scene):
        """PaperScene can be constructed for every size in the catalogue."""
        for name in PAPER_SIZES:
            ps = PaperScene(model_scene, paper_size=name)
            assert ps.paper_size == name


# ─────────────────────────────────────────────────────────────────────────────
# PaperSpaceWidget
# ─────────────────────────────────────────────────────────────────────────────

class TestPaperSpaceWidget:
    """Tests for the PaperSpaceWidget toolbar and integration."""

    def test_widget_creates(self, model_scene):
        widget = PaperSpaceWidget(model_scene)
        assert widget is not None

    def test_default_combo_value(self, model_scene):
        widget = PaperSpaceWidget(model_scene)
        assert widget._size_combo.currentText() == "ANSI D"

    def test_combo_has_all_sizes(self, model_scene):
        widget = PaperSpaceWidget(model_scene)
        items = [widget._size_combo.itemText(i)
                 for i in range(widget._size_combo.count())]
        for name in PAPER_SIZES:
            assert name in items

    def test_change_paper_updates_scene(self, model_scene):
        widget = PaperSpaceWidget(model_scene)
        widget.change_paper("A3")
        assert widget.paper_scene.paper_size == "A3"
        assert widget._size_combo.currentText() == "A3"

    def test_paper_scene_is_set(self, model_scene):
        widget = PaperSpaceWidget(model_scene)
        assert widget.paper_scene is not None
        assert isinstance(widget.paper_scene, PaperScene)

    def test_view_exists(self, model_scene):
        widget = PaperSpaceWidget(model_scene)
        assert widget.view is not None
        assert widget.view.scene() is widget.paper_scene

    def test_refresh_no_crash(self, model_scene):
        widget = PaperSpaceWidget(model_scene)
        widget._refresh()  # should not raise


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

    def test_to_dict_keys(self):
        from firepro3d.paper_space import SheetViewData
        svd = SheetViewData("plan", "Level 1", "Level 1", 0.01, 0, 0, 100, 100)
        d = svd.to_dict()
        assert set(d.keys()) == {
            "source_view_type", "source_view_name", "title",
            "scale", "x", "y", "w", "h",
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

    def test_dirty_flag_initial(self, qapp):
        vp, _, _, _ = self._make_viewport(qapp)
        assert vp._dirty is True

    def test_mark_dirty(self, qapp):
        vp, _, _, _ = self._make_viewport(qapp)
        vp._dirty = False
        vp.mark_dirty()
        assert vp._dirty is True

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

    def test_dirty_flag_on_source_change(self, qapp):
        vp, _, _, model_scene = self._make_viewport(qapp)
        vp._dirty = False
        model_scene.addRect(500, 500, 100, 100)
        qapp.processEvents()
        assert vp._dirty is True


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
