"""FIX 2: disabling HALO drops the highlight (no stale paint).

drawForeground gates the HALO paint on ``not scene._halo_suppressed()``, so a
disabled/suppressed HALO is not left painted. Disabling via the pill/_toggle
also clears the candidate list.
"""
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from firepro3d.model_space import Model_Space
from firepro3d.node import Node


def test_disable_suppresses_and_clears(qapp):
    sc = Model_Space()
    sc.addItem(Node(0.0, 0.0))
    sc.halo_update(QPointF(0.0, 0.0), 8.0, QTransform())
    assert sc.halo_item() is not None
    assert not sc._halo_suppressed()

    # Disable HALO (pill off) -> suppression is on
    sc.halo_enabled = False
    assert sc._halo_suppressed() is True


def test_toggle_off_clears_candidates(qapp):
    # Drive the contract _toggle_halo relies on: after disabling + clearing,
    # halo_item() is None so drawForeground has nothing to paint.
    sc = Model_Space()
    sc.addItem(Node(0.0, 0.0))
    sc.halo_update(QPointF(0.0, 0.0), 8.0, QTransform())
    assert sc.halo_item() is not None
    sc.halo_enabled = False
    sc.halo_clear()
    assert sc.halo_item() is None


def _edge_pt(item):
    """A point on the rectangle's left edge (an unfilled rect hits on its outline)."""
    b = item.sceneBoundingRect()
    return QPointF(b.left() + 1.0, b.center().y())


def _hovered_moved_rect():
    """A tracked rectangle, hovered (HALO) after being moved by +500 in x."""
    from firepro3d.geometry_2d import RectangleItem
    sc = Model_Space(scene_role="block_editor")
    r = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    sc.addItem(r)
    sc._draw_rects.append(r)
    sc.push_undo_state()
    r.translate(500, 0)
    sc.push_undo_state()
    sc.halo_update(_edge_pt(r), 8.0, QTransform())
    assert sc.halo_item() is r
    return sc


def test_undo_drops_stale_halo_highlight(qapp):
    """Undo rebuilds every item from the snapshot; the hovered item is now a
    detached object still at its pre-undo (moved) position, so a kept HALO
    candidate would paint a ghost outline there (user smoke 2026-09-23)."""
    sc = _hovered_moved_rect()
    sc.undo()
    assert sc.halo_item() is None


def test_redo_drops_stale_halo_highlight(qapp):
    sc = _hovered_moved_rect()
    sc.undo()
    live = sc._draw_rects[0]
    sc.halo_update(_edge_pt(live), 8.0, QTransform())
    assert sc.halo_item() is live
    sc.redo()
    assert sc.halo_item() is None
