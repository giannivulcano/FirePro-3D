"""A migrated item (implements manip_handles) is skipped by BOTH legacy grip
paths; an un-migrated item is still served by them."""
from PyQt6.QtCore import QPointF
from firepro3d.selection_manipulator import _item_uses_manip_handles
from firepro3d.manip_handle import GripHandle


class _Migrated:
    def grip_points(self):
        return [QPointF(0, 0), QPointF(10, 0)]
    def manip_handles(self):
        return [GripHandle(self, i) for i in range(2)]


class _Legacy:
    def grip_points(self):
        return [QPointF(0, 0)]


def test_gate_true_for_migrated():
    assert _item_uses_manip_handles(_Migrated()) is True


def test_gate_false_for_legacy():
    assert _item_uses_manip_handles(_Legacy()) is False


def test_gate_false_when_manip_handles_empty():
    class _Empty:
        def grip_points(self): return []
        def manip_handles(self): return []
    assert _item_uses_manip_handles(_Empty()) is False
