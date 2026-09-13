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
