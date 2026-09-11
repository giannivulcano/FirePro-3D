"""Stage 1: DetailMarker behaves like RectangleItem in the plan — box-native
(frame-redundant crop outline + 8 rigid SQUARE resize handles) + a round bubble
extra grip; axis-aligned (no rotate)."""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from firepro3d.detail_view import DetailMarker
from firepro3d.selection_manipulator import (
    item_capabilities, _item_uses_manip_handles, SelectionManipulator,
)
from firepro3d.manip_handle import GripHandle
from firepro3d.manip_math import _RESIZE_ROLES, HandleRole


def _make():
    return DetailMarker("Detail 1", QRectF(0, 0, 200, 100))


def test_box_native_caps(qapp):
    dm = _make()
    assert item_capabilities(dm) == {"translate", "scale"}   # no rotate
    assert _item_uses_manip_handles(dm) is True              # coexistence gate on


def test_manip_scale_resizes_crop_about_anchor(qapp):
    dm = _make()
    dm.manip_scale(2.0, 2.0, QPointF(0, 0))                  # x2 about top-left
    r = dm._crop_rect
    assert r.left() == 0 and r.top() == 0                    # anchor held fixed
    assert abs(r.width() - 400) < 1e-6
    assert abs(r.height() - 200) < 1e-6


def test_manip_translate_moves_crop_and_bubble(qapp):
    dm = _make()
    b0 = QPointF(dm._bubble_pos)
    dm.manip_translate(50, 30)
    assert dm._crop_rect.topLeft() == QPointF(50, 30)
    assert dm._bubble_pos == QPointF(b0.x() + 50, b0.y() + 30)


def test_selected_shows_rigid_resize_plus_round_bubble(qapp):
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(500, 500); view.show()
    qapp.processEvents()
    dm = _make(); scene.addItem(dm)
    m = SelectionManipulator(scene)
    dm.setSelected(True); qapp.processEvents()
    assert dm in m.selection_items()
    assert m.provides_handles_for(dm) is True                # box-native
    assert m._frame_is_redundant() is True                   # crop outline IS the box
    handles = m._active_handles()
    resize = [h for h in handles if h.role in _RESIZE_ROLES]
    assert len(resize) == 8                                   # corners + midpoints
    extra = [h for h in handles if isinstance(h, GripHandle)]
    assert len(extra) == 1                                    # the bubble
    assert extra[0].index == 8 and extra[0].circular is True  # round move grip
    # no rotate knob is active for an axis-aligned crop
    assert not any(h.role is HandleRole.ROTATE and h.visible(m) for h in handles)
