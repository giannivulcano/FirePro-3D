"""Integration tests for underlay file-not-found, refresh, and scene-level behavior.

Covers:
  1. File-not-found handling and placeholder creation
  2. Placeholder item properties (data tag, position, child label)
  3. Refresh-from-disk behavior (file missing -> placeholder)
  4. Underlay group creation and Z-ordering
  5. Underlay group is NOT selectable/movable after _apply_underlay_display
  6. DXF underlay layer visibility toggling (_apply_underlay_hidden_layers)
  7. remove_underlay cleanup
"""

from __future__ import annotations

import os

import pytest
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPen, QColor, QBrush, QPainterPath
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
)

from firepro3d.underlay import Underlay
from firepro3d.constants import Z_UNDERLAY, DEFAULT_LEVEL
from firepro3d.model_space import Model_Space


# ── helpers ────────────────────────────────────────────────────────────────

def _make_scene(qapp) -> Model_Space:
    """Create a fresh Model_Space for testing."""
    return Model_Space()


def _build_layer_path_item(layer: str = "0") -> QGraphicsPathItem:
    """Create a batched path item tagged by layer.

    Mirrors the per-layer QPainterPathItems created by
    _build_batched_underlay_group in production code.
    """
    path = QPainterPath()
    path.moveTo(0, 0)
    path.lineTo(100, 100)
    item = QGraphicsPathItem(path)
    pen = QPen(QColor("#c0c0c0"), 1.5)
    pen.setCosmetic(True)
    item.setPen(pen)
    item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    item.setZValue(Z_UNDERLAY)
    item.setData(1, layer)
    return item


def _build_underlay_group(
    scene: Model_Space,
    layers: list[str] | None = None,
    x: float = 0.0,
    y: float = 0.0,
) -> QGraphicsItemGroup:
    """Build a DXF-like underlay group with batched path items per layer.

    Mirrors the structure created by _build_batched_underlay_group.
    """
    if layers is None:
        layers = ["A-WALL", "A-DOOR", "A-FURN"]

    items = []
    for layer_name in layers:
        item = _build_layer_path_item(layer=layer_name)
        scene.addItem(item)
        items.append(item)

    group = scene.createItemGroup(items)
    group.setZValue(Z_UNDERLAY)
    group.setPos(x, y)
    group.setData(0, "DXF Underlay")
    group.setData(2, sorted(set(layers)))
    return group


# =====================================================================
# 1. Placeholder creation for missing underlays
# =====================================================================

class TestPlaceholderCreation:
    """_create_underlay_placeholder produces the right scene item."""

    def test_placeholder_added_to_scene(self, qapp):
        scene = _make_scene(qapp)
        data = Underlay(type="dxf", path="missing/floor.dxf", x=50.0, y=75.0)

        item = scene._create_underlay_placeholder(data)

        assert item.scene() is scene

    def test_placeholder_position_matches_record(self, qapp):
        scene = _make_scene(qapp)
        data = Underlay(type="dxf", path="gone.dxf", x=123.0, y=456.0)

        item = scene._create_underlay_placeholder(data)

        assert item.pos().x() == pytest.approx(123.0)
        assert item.pos().y() == pytest.approx(456.0)

    def test_placeholder_data_tag(self, qapp):
        scene = _make_scene(qapp)
        data = Underlay(type="dxf", path="gone.dxf")

        item = scene._create_underlay_placeholder(data)

        assert item.data(0) == "missing_underlay"

    def test_placeholder_is_selectable_but_not_movable(self, qapp):
        scene = _make_scene(qapp)
        data = Underlay(type="dxf", path="gone.dxf")

        item = scene._create_underlay_placeholder(data)

        flags = item.flags()
        assert flags & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        assert not (flags & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    def test_placeholder_registered_in_underlays_list(self, qapp):
        scene = _make_scene(qapp)
        data = Underlay(type="dxf", path="gone.dxf")

        item = scene._create_underlay_placeholder(data)

        assert len(scene.underlays) == 1
        rec, scn_item = scene.underlays[0]
        assert rec is data
        assert scn_item is item

    def test_placeholder_has_red_dashed_outline(self, qapp):
        scene = _make_scene(qapp)
        data = Underlay(type="dxf", path="gone.dxf")

        item = scene._create_underlay_placeholder(data)

        pen = item.pen()
        assert pen.style() == Qt.PenStyle.DashLine
        assert pen.color().red() == 255

    def test_placeholder_has_child_label_with_filename(self, qapp):
        scene = _make_scene(qapp)
        data = Underlay(type="dxf", path="plans/floor1.dxf")

        item = scene._create_underlay_placeholder(data)

        children = item.childItems()
        assert len(children) == 1
        label_text = children[0].text()
        assert "floor1.dxf" in label_text
        assert "Missing" in label_text

    def test_placeholder_for_pdf_type(self, qapp):
        """Placeholder works for PDF underlays too."""
        scene = _make_scene(qapp)
        data = Underlay(type="pdf", path="sheets/A1.pdf", x=10.0, y=20.0)

        item = scene._create_underlay_placeholder(data)

        assert item.data(0) == "missing_underlay"
        children = item.childItems()
        assert any("A1.pdf" in c.text() for c in children)


# =====================================================================
# 2. Underlay group Z-ordering
# =====================================================================

class TestUnderlayGroupZOrdering:
    """Underlay groups get the correct Z value."""

    def test_group_z_value(self, qapp):
        scene = _make_scene(qapp)
        group = _build_underlay_group(scene)

        assert group.zValue() == Z_UNDERLAY

    def test_child_items_z_value(self, qapp):
        """Each child item inside a group also has Z_UNDERLAY."""
        scene = _make_scene(qapp)
        group = _build_underlay_group(scene)

        for child in group.childItems():
            assert child.zValue() == Z_UNDERLAY

    def test_z_underlay_is_minus_79(self, qapp):
        """Sanity: Z_UNDERLAY is the expected constant value."""
        assert Z_UNDERLAY == -79


# =====================================================================
# 3. _apply_underlay_display — transform, visibility, lock
# =====================================================================

class TestApplyUnderlayDisplay:
    """_apply_underlay_display sets scale/rotation/opacity/visibility/lock."""

    def test_scale_applied(self, qapp):
        scene = _make_scene(qapp)
        group = _build_underlay_group(scene)
        record = Underlay(type="dxf", path="a.dxf", scale=2.5)

        scene._apply_underlay_display(group, record)

        assert group.scale() == pytest.approx(2.5)

    def test_rotation_applied(self, qapp):
        scene = _make_scene(qapp)
        group = _build_underlay_group(scene)
        record = Underlay(type="dxf", path="a.dxf", rotation=45.0)

        scene._apply_underlay_display(group, record)

        assert group.rotation() == pytest.approx(45.0)

    def test_opacity_applied(self, qapp):
        scene = _make_scene(qapp)
        group = _build_underlay_group(scene)
        record = Underlay(type="dxf", path="a.dxf", opacity=0.3)

        scene._apply_underlay_display(group, record)

        assert group.opacity() == pytest.approx(0.3)

    def test_hidden_when_not_visible(self, qapp):
        scene = _make_scene(qapp)
        group = _build_underlay_group(scene)
        record = Underlay(type="dxf", path="a.dxf", visible=False)

        scene._apply_underlay_display(group, record)

        assert group.isVisible() is False

    def test_visible_by_default(self, qapp):
        scene = _make_scene(qapp)
        group = _build_underlay_group(scene)
        record = Underlay(type="dxf", path="a.dxf", visible=True)

        scene._apply_underlay_display(group, record)

        assert group.isVisible() is True

    def test_locked_disables_selectable_and_movable(self, qapp):
        """Locked underlay should have selectable and movable flags cleared."""
        scene = _make_scene(qapp)
        group = _build_underlay_group(scene)
        # Pre-set the flags so we can confirm they get cleared
        group.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        group.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        record = Underlay(type="dxf", path="a.dxf", locked=True)

        scene._apply_underlay_display(group, record)

        flags = group.flags()
        assert not (flags & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        assert not (flags & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)


# =====================================================================
# 4. DXF layer visibility toggling
# =====================================================================

class TestUnderlayHiddenLayers:
    """_apply_underlay_hidden_layers toggles child visibility by layer."""

    def test_hide_single_layer(self, qapp):
        scene = _make_scene(qapp)
        group = _build_underlay_group(scene, layers=["A-WALL", "A-DOOR", "A-FURN"])
        record = Underlay(type="dxf", path="a.dxf", hidden_layers=["A-FURN"])

        scene._apply_underlay_hidden_layers(group, record)

        for child in group.childItems():
            if child.data(1) == "A-FURN":
                assert child.isVisible() is False
            else:
                assert child.isVisible() is True

    def test_hide_multiple_layers(self, qapp):
        scene = _make_scene(qapp)
        group = _build_underlay_group(scene, layers=["A-WALL", "A-DOOR", "A-FURN"])
        record = Underlay(type="dxf", path="a.dxf",
                          hidden_layers=["A-WALL", "A-FURN"])

        scene._apply_underlay_hidden_layers(group, record)

        for child in group.childItems():
            layer = child.data(1)
            if layer in ("A-WALL", "A-FURN"):
                assert child.isVisible() is False
            else:
                assert child.isVisible() is True

    def test_stale_layer_names_pruned(self, qapp):
        """Layer names not present in the group are silently dropped."""
        scene = _make_scene(qapp)
        group = _build_underlay_group(scene, layers=["A-WALL", "A-DOOR"])
        record = Underlay(type="dxf", path="a.dxf",
                          hidden_layers=["A-WALL", "NONEXISTENT"])

        scene._apply_underlay_hidden_layers(group, record)

        # Stale name removed from record
        assert "NONEXISTENT" not in record.hidden_layers
        assert "A-WALL" in record.hidden_layers

    def test_empty_hidden_layers_no_effect(self, qapp):
        scene = _make_scene(qapp)
        group = _build_underlay_group(scene, layers=["A-WALL", "A-DOOR"])
        record = Underlay(type="dxf", path="a.dxf", hidden_layers=[])

        scene._apply_underlay_hidden_layers(group, record)

        for child in group.childItems():
            assert child.isVisible() is True

    def test_all_layers_hidden(self, qapp):
        scene = _make_scene(qapp)
        layers = ["A-WALL", "A-DOOR", "A-FURN"]
        group = _build_underlay_group(scene, layers=layers)
        record = Underlay(type="dxf", path="a.dxf", hidden_layers=list(layers))

        scene._apply_underlay_hidden_layers(group, record)

        for child in group.childItems():
            assert child.isVisible() is False


# =====================================================================
# 5. remove_underlay cleanup
# =====================================================================

class TestRemoveUnderlay:
    """remove_underlay removes the item from both the scene and tracking list."""

    def test_group_removed_from_scene(self, qapp):
        scene = _make_scene(qapp)
        group = _build_underlay_group(scene)
        record = Underlay(type="dxf", path="a.dxf")
        scene.underlays.append((record, group))

        scene.remove_underlay(record, group)

        # Group is destroyed; children should not be in the scene either
        assert len(scene.underlays) == 0

    def test_tracking_list_cleared(self, qapp):
        scene = _make_scene(qapp)
        group = _build_underlay_group(scene)
        record = Underlay(type="dxf", path="a.dxf")
        scene.underlays.append((record, group))

        scene.remove_underlay(record, group)

        assert (record, group) not in scene.underlays

    def test_remove_placeholder(self, qapp):
        """Placeholders (QGraphicsRectItem, not groups) are also removed."""
        scene = _make_scene(qapp)
        data = Underlay(type="dxf", path="missing.dxf")
        placeholder = scene._create_underlay_placeholder(data)
        assert len(scene.underlays) == 1

        scene.remove_underlay(data, placeholder)

        assert len(scene.underlays) == 0
        assert placeholder.scene() is None

    def test_remove_only_target(self, qapp):
        """Removing one underlay does not affect others."""
        scene = _make_scene(qapp)
        group1 = _build_underlay_group(scene, layers=["L1"])
        rec1 = Underlay(type="dxf", path="a.dxf")
        scene.underlays.append((rec1, group1))

        group2 = _build_underlay_group(scene, layers=["L2"])
        rec2 = Underlay(type="dxf", path="b.dxf")
        scene.underlays.append((rec2, group2))

        scene.remove_underlay(rec1, group1)

        assert len(scene.underlays) == 1
        assert scene.underlays[0][0] is rec2


# =====================================================================
# 6. Refresh with missing file -> placeholder
# =====================================================================

class TestRefreshUnderlayMissing:
    """refresh_underlay replaces with placeholder when file is gone."""

    def test_refresh_missing_creates_placeholder(self, qapp):
        scene = _make_scene(qapp)
        group = _build_underlay_group(scene, x=10.0, y=20.0)
        record = Underlay(
            type="dxf", path="/nonexistent/path/floor.dxf",
            x=10.0, y=20.0,
        )
        scene.underlays.append((record, group))

        scene.refresh_underlay(record, group)

        # Should now have exactly one underlay entry (the placeholder)
        assert len(scene.underlays) == 1
        _, new_item = scene.underlays[0]
        assert new_item.data(0) == "missing_underlay"

    def test_refresh_missing_preserves_position_in_record(self, qapp):
        scene = _make_scene(qapp)
        group = _build_underlay_group(scene, x=100.0, y=200.0)
        record = Underlay(type="dxf", path="/no/such/file.dxf")
        scene.underlays.append((record, group))

        scene.refresh_underlay(record, group)

        # record.x and record.y are synced from item.scenePos() before
        # the file-not-found check
        assert record.x == pytest.approx(100.0)
        assert record.y == pytest.approx(200.0)

    def test_refresh_missing_old_group_removed(self, qapp):
        scene = _make_scene(qapp)
        group = _build_underlay_group(scene, layers=["A-WALL"])
        record = Underlay(type="dxf", path="/no/file.dxf")
        scene.underlays.append((record, group))

        scene.refresh_underlay(record, group)

        # The original group should no longer be in the scene
        assert group.scene() is None


# =====================================================================
# 7. Refresh with existing file (DXF, via tmp_path)
# =====================================================================

class TestRefreshUnderlayFromDisk:
    """refresh_underlay re-imports when the file exists on disk.

    DXF import is async (worker thread), but we can verify the old
    entry is removed and a worker is started.
    """

    def test_refresh_existing_dxf_removes_old_entry(self, qapp, tmp_path):
        """Old underlay entry is removed before async re-import begins."""
        dxf_file = tmp_path / "test.dxf"
        # Create a minimal valid DXF file
        import ezdxf
        doc = ezdxf.new()
        msp = doc.modelspace()
        msp.add_line((0, 0), (100, 100))
        doc.saveas(str(dxf_file))

        scene = _make_scene(qapp)
        group = _build_underlay_group(scene, layers=["0"])
        record = Underlay(type="dxf", path=str(dxf_file), x=5.0, y=10.0)
        scene.underlays.append((record, group))

        scene.refresh_underlay(record, group)

        # The old entry should be removed. A DXF worker is now running;
        # we clean it up to avoid dangling threads.
        assert all(d is not record for d, _ in scene.underlays
                   if _.data(0) != "DXF Underlay"
                   or d.path != str(dxf_file))
        # Clean up the worker thread
        if hasattr(scene, "_dxf_worker") and scene._dxf_worker is not None:
            scene._dxf_worker.cancel()
            scene._dxf_worker.quit()
            scene._dxf_worker.wait(2000)

    def test_refresh_syncs_transform_before_reimport(self, qapp, tmp_path):
        """Position/scale/rotation/opacity are synced from the scene item."""
        dxf_file = tmp_path / "test.dxf"
        import ezdxf
        doc = ezdxf.new()
        msp = doc.modelspace()
        msp.add_line((0, 0), (50, 50))
        doc.saveas(str(dxf_file))

        scene = _make_scene(qapp)
        group = _build_underlay_group(scene, x=77.0, y=88.0)
        group.setScale(3.0)
        group.setRotation(15.0)
        group.setOpacity(0.6)
        record = Underlay(type="dxf", path=str(dxf_file))
        scene.underlays.append((record, group))

        scene.refresh_underlay(record, group)

        assert record.x == pytest.approx(77.0)
        assert record.y == pytest.approx(88.0)
        assert record.scale == pytest.approx(3.0)
        assert record.rotation == pytest.approx(15.0)
        assert record.opacity == pytest.approx(0.6)

        # Clean up
        if hasattr(scene, "_dxf_worker") and scene._dxf_worker is not None:
            scene._dxf_worker.cancel()
            scene._dxf_worker.quit()
            scene._dxf_worker.wait(2000)


# =====================================================================
# 8. refresh_all_underlays
# =====================================================================

class TestRefreshAllUnderlays:
    """refresh_all_underlays iterates the snapshot and refreshes each."""

    def test_all_missing_become_placeholders(self, qapp):
        scene = _make_scene(qapp)

        groups = []
        records = []
        for i in range(3):
            g = _build_underlay_group(scene, layers=[f"L{i}"])
            r = Underlay(type="dxf", path=f"/no/file_{i}.dxf")
            scene.underlays.append((r, g))
            groups.append(g)
            records.append(r)

        scene.refresh_all_underlays()

        # All three should now be placeholders
        assert len(scene.underlays) == 3
        for _, item in scene.underlays:
            assert item.data(0) == "missing_underlay"

    def test_empty_underlays_no_error(self, qapp):
        scene = _make_scene(qapp)
        assert len(scene.underlays) == 0

        scene.refresh_all_underlays()  # should not raise

        assert len(scene.underlays) == 0


# =====================================================================
# 9. find_underlay_for_item
# =====================================================================

class TestFindUnderlayForItem:
    """find_underlay_for_item returns correct tuple or None."""

    def test_find_existing(self, qapp):
        scene = _make_scene(qapp)
        group = _build_underlay_group(scene)
        record = Underlay(type="dxf", path="a.dxf")
        scene.underlays.append((record, group))

        result = scene.find_underlay_for_item(group)

        assert result is not None
        assert result[0] is record
        assert result[1] is group

    def test_find_nonexistent_returns_none(self, qapp):
        scene = _make_scene(qapp)
        group = _build_underlay_group(scene)
        # Not registered in underlays list

        result = scene.find_underlay_for_item(group)

        assert result is None

    def test_find_placeholder(self, qapp):
        scene = _make_scene(qapp)
        data = Underlay(type="dxf", path="missing.dxf")
        placeholder = scene._create_underlay_placeholder(data)

        result = scene.find_underlay_for_item(placeholder)

        assert result is not None
        assert result[0] is data


# =====================================================================
# 10. _geom_to_item produces correctly tagged items
# =====================================================================

# =====================================================================
# 11. PDF import_pdf — file-not-found early return
# =====================================================================

class TestImportPdfNotFound:
    """import_pdf returns early when file does not exist."""

    def test_pdf_not_found_no_underlay_added(self, qapp):
        scene = _make_scene(qapp)

        scene.import_pdf("/nonexistent/path/sheet.pdf")

        assert len(scene.underlays) == 0

    def test_pdf_not_found_no_scene_items_added(self, qapp):
        scene = _make_scene(qapp)
        initial_count = len(scene.items())

        scene.import_pdf("/nonexistent/path/sheet.pdf")

        assert len(scene.items()) == initial_count
