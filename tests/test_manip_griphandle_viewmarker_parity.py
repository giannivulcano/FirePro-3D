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


# --------------------------------------------------------------------------
# Apply parity + coexistence
# --------------------------------------------------------------------------

class _StubScene:
    _tools = None
    _grip_item = None
    _grip_dragging = False

    def get_effective_position(self, p):
        return QPointF(p)


class _StubM:
    _commit_hook = None

    def __init__(self, sc):
        self._sc = sc

    def scene(self):
        return self._sc

    def _reflow_live(self):
        pass


def test_crop_grip_apply_matches_legacy(qapp, shown_model_view):
    _, scene = shown_model_view
    # Legacy path: drive apply_grip directly on the marker (forwards to box).
    mgr_l = _add_markers(scene)
    marker_l = _select(scene, mgr_l)
    target = QPointF(marker_l.grip_points()[2].x() + 800,
                     marker_l.grip_points()[2].y() + 600)
    marker_l.apply_grip(2, QPointF(target))
    legacy_rect = QRectF(mgr_l._crop_box.rect())
    legacy_south = QPointF(mgr_l.get_marker("south").pos())
    mgr_l.remove_all()

    # Migrated path: drive the GripHandle lifecycle to the same target.
    mgr_m = _add_markers(scene)
    marker_m = _select(scene, mgr_m)
    h = marker_m.manip_handles()[2]
    sc = _StubScene(); m = _StubM(sc)
    h.on_press(m)
    h.on_drag(m, QPointF(target), Qt.KeyboardModifier.NoModifier)
    assert mgr_m._crop_box.rect() == legacy_rect            # same resize
    assert mgr_m.get_marker("south").pos() == legacy_south  # markers repositioned


def test_legacy_grip_paths_skip_migrated_marker(qapp, shown_model_view):
    _, scene = shown_model_view
    mgr = _add_markers(scene)
    marker = _select(scene, mgr)
    hit = scene._tools._find_grip_hit(QPointF(marker.grip_points()[0]))
    assert hit is None or hit[0] is not marker


# --------------------------------------------------------------------------
# manip_translate (interior-drag move of the whole box) + caps + serialize
# --------------------------------------------------------------------------

def test_manip_translate_moves_box_and_markers(qapp, shown_model_view):
    _, scene = shown_model_view
    mgr = _add_markers(scene)
    marker = _select(scene, mgr)
    box = mgr._crop_box
    r0 = QRectF(box.rect())
    north0 = QPointF(mgr.get_marker("north").pos())
    marker.manip_translate(400.0, 250.0)
    assert box.rect() == r0.translated(400.0, 250.0)
    assert mgr.get_marker("north").pos() != north0     # repositioned to new edge


def test_capabilities_are_translate_only(qapp, shown_model_view):
    from firepro3d.selection_manipulator import item_capabilities
    _, scene = shown_model_view
    mgr = _add_markers(scene)
    marker = _select(scene, mgr)
    # translate (for wrap + interior move); NO scale (not box-native), NO rotate.
    assert item_capabilities(marker) == {"translate"}


def test_move_persists_in_serialization(qapp, shown_model_view):
    _, scene = shown_model_view
    mgr = _add_markers(scene)
    marker = _select(scene, mgr)
    marker.manip_translate(400.0, 250.0)
    data = mgr.to_dict()
    assert data["crop_rect"]["x"] == mgr._crop_box.rect().x()
    assert data["crop_rect"]["y"] == mgr._crop_box.rect().y()
