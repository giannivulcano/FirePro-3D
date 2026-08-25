"""Design-area pick routes through SnapEngine but stays sprinkler-centers-only."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform


def _install_view_scale(ms, scale):
    t = QTransform()
    t.scale(scale, scale)
    for v in ms.views():
        v.setTransform(t)


def test_design_area_snaps_only_to_sprinkler_center(qapp, make_model_space):
    ms = make_model_space()
    ms.mode = "design_area"
    from firepro3d.construction_geometry import LineItem
    ms.addItem(LineItem(QPointF(0.0, 0.0), QPointF(100.0, 0.0)))  # endpoint at (0,0) — must be IGNORED
    node = ms.add_node(50.0, 0.0)
    ms.add_sprinkler(node)
    _install_view_scale(ms, 1.0)
    res = ms.get_effective_position(QPointF(52.0, 2.0))
    assert abs(res.x() - 50.0) < 1.0 and abs(res.y()) < 1.0, \
        "must snap to the sprinkler center, not the line endpoint"
    assert ms._snap_result is not None and ms._snap_result.snap_type == "center"


def test_design_area_pick_works_when_center_snap_disabled(qapp, make_model_space):
    """Fix 1 parity: design-area pick must work even when the user has unchecked
    'Center' in SNAP prefs (snap_center=False), and the flag must be restored after."""
    ms = make_model_space()
    ms.mode = "design_area"
    node = ms.add_node(50.0, 0.0)
    ms.add_sprinkler(node)
    ms._snap_engine.snap_center = False   # user unchecked "Center" in SNAP prefs
    _install_view_scale(ms, 1.0)
    res = ms.get_effective_position(QPointF(52.0, 2.0))
    assert ms._snap_result is not None and ms._snap_result.snap_type == "center", \
        "design-area pick must work even when Center snap is disabled in prefs"
    # snap_center pref must be restored, not clobbered:
    assert ms._snap_engine.snap_center is False, \
        "get_effective_position must restore snap_center to the user's pre-call value"
