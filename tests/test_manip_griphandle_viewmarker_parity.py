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


def test_unselected_marker_exposes_no_grips(qapp, shown_model_view):
    _, scene = shown_model_view
    mgr = _add_markers(scene)
    marker = mgr.get_marker("north")     # not selected -> box hidden
    # State-dependent empty is symmetric (grip_points and manip_handles both []).
    assert marker.grip_points() == []
    assert marker.manip_handles() == []


def test_selected_marker_exposes_grips(qapp, shown_model_view):
    _, scene = shown_model_view
    mgr = _add_markers(scene)
    marker = _select(scene, mgr)
    assert marker.manip_handles()


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
    # Both managers share this scene; the fixture has no gridlines, so each
    # create_elevation_markers() falls through _gridline_bbox() to the SAME fixed
    # rect -> identical starting crop boxes, which makes the parity comparison sound.
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


# --------------------------------------------------------------------------
# Integration — real Model_Space + its live manipulator (driven lifecycle)
# --------------------------------------------------------------------------

def test_crop_grip_drag_resizes_one_commit(qapp, shown_model_view):
    _, scene = shown_model_view
    mgr = _add_markers(scene)
    marker = _select(scene, mgr)
    box = mgr._crop_box
    r0 = QRectF(box.rect())
    m = scene._live_manip()
    assert m is not None and m.wraps(marker)      # manipulator wrapped the marker
    calls = []
    m._commit_hook = lambda mode: calls.append(mode)
    h = marker.manip_handles()[2]                 # bottomRight corner
    start = QPointF(marker.grip_points()[2])
    target = QPointF(start.x() + 500, start.y() + 300)
    m._begin_handle(h, start, start)
    m._update(target, Qt.KeyboardModifier.NoModifier, target)
    m._finish(target, Qt.KeyboardModifier.NoModifier)
    assert box.rect() != r0                        # resized
    assert calls == ["grip"]                       # single undo commit


def test_crop_box_has_no_own_outline_keeps_fill(qapp, shown_model_view):
    # Unified chrome: the manipulator frame IS the crop outline; the box draws
    # only its faint fill (its own dashed outline is dropped -> no double rect).
    from PyQt6.QtGui import QBrush
    _, scene = shown_model_view
    mgr = _add_markers(scene)
    box = mgr._crop_box
    assert box.pen().style() == Qt.PenStyle.NoPen
    assert box.brush().style() != Qt.BrushStyle.NoBrush     # fill retained


def test_selection_renders_grip_hosts_no_manual_rebake(qapp, shown_model_view):
    """Regression: the manipulator must actually RENDER 8 grip hosts after the
    real selection path, with no manual rebake.

    The bug: grips gated on box.isVisible(), which the marker's itemChange sets
    during the SAME selectionChanged that drives rebake — so rebake read [] and
    built ZERO hosts (live: 'there are no handles'). This asserts the rendered
    host pool (NOT marker.manip_handles() directly, which the other tests call
    and which masked the bug). Goes RED if grip_points() re-couples to
    box.isVisible()."""
    _, scene = shown_model_view
    mgr = _add_markers(scene)
    marker = _select(scene, mgr)
    m = scene._live_manip()
    assert m is not None and m.wraps(marker)
    visible_hosts = [h for h in m._host_pool if h.isVisible()]
    assert len(visible_hosts) == 8            # 8 crop grips actually rendered
