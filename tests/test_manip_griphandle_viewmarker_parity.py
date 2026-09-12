"""U3 migration of ViewMarkerArrow onto manip_handles(): the elevation marker
forwards 8 SQUARE crop grips to the shared SharedCropBox, is resizable + movable
via the manipulator, and the legacy grip paths skip it. Mirrors DetailMarker
(detail_view.py) — a parametric crop, not box-native. Grips are state-dependent:
present only when the marker is selected and the crop box is visible.
"""
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtWidgets import QApplication

from firepro3d.view_marker import ViewMarkerManager, ViewMarkerArrow
from firepro3d.manip_handle import GripHandle
from firepro3d.manip_math import HandleRole


def _add_markers(scene):
    """Create real N/S/E/W markers + shared crop box in the scene (gridline
    bbox falls back to a fixed rect when the scene has no gridlines)."""
    mgr = ViewMarkerManager(scene)
    mgr.create_elevation_markers()
    scene._view_marker_mgr = mgr          # keep a ref so it isn't GC'd
    return mgr


def _select(scene, mgr, direction="north"):
    marker = mgr.get_marker(direction)
    scene.set_mode("select")
    marker.setSelected(True)              # itemChange -> box.setVisible(True)
    QApplication.processEvents()
    return marker


def test_selected_marker_has_8_square_crop_grips(qapp, shown_model_view):
    _, scene = shown_model_view
    mgr = _add_markers(scene)
    marker = _select(scene, mgr)
    hs = marker.manip_handles()
    assert len(hs) == 8
    assert all(type(h) is GripHandle for h in hs)
    assert all(h.role is HandleRole.GRIP for h in hs)
    assert all(h.circular is False for h in hs)      # resize grips -> square
    # grip 2 (bottomRight) maps to the box's bottomRight in scene coords
    assert hs[2].index == 2
    assert hs[2].scene_position(None) == marker.grip_points()[2]


def test_manip_bounds_is_crop_box_rect(qapp, shown_model_view):
    _, scene = shown_model_view
    mgr = _add_markers(scene)
    marker = _select(scene, mgr)
    box = mgr._crop_box
    assert marker.manip_bounds() == box.mapRectToScene(box.rect())


def test_unselected_marker_exposes_no_grips_and_gate_off(qapp, shown_model_view):
    from firepro3d.selection_manipulator import _item_uses_manip_handles
    _, scene = shown_model_view
    mgr = _add_markers(scene)
    marker = mgr.get_marker("north")     # not selected -> box hidden
    assert marker.grip_points() == []
    assert marker.manip_handles() == []
    assert _item_uses_manip_handles(marker) is False


def test_selected_marker_gate_on(qapp, shown_model_view):
    from firepro3d.selection_manipulator import _item_uses_manip_handles
    _, scene = shown_model_view
    mgr = _add_markers(scene)
    marker = _select(scene, mgr)
    assert _item_uses_manip_handles(marker) is True
