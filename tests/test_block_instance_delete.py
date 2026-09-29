"""AC1 — Delete removes a selected BlockInstance (plan + Block Editor), one undo."""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.scale_manager import ScaleManager


def _line_def(name):
    return BlockDefinition.new(
        name=name, library="L", series="S", origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict()])


@pytest.mark.parametrize("role", [None, "block_editor"])
def test_delete_key_removes_block_instance_and_undo_restores(qapp, role):
    sc = Model_Space(scene_role=role) if role else Model_Space()
    sc.scale_manager = ScaleManager()
    v = Model_View(sc)
    v.resize(800, 600)
    v.show()
    QTest.qWaitForWindowExposed(v)
    try:
        d = _line_def("B")
        sc.register_block_definition(d)
        inst = sc.place_block_instance(d.id, (10.0, 10.0))
        sc.push_undo_state()
        inst.setSelected(True)
        v.setFocus()
        QTest.keyClick(v.viewport(), Qt.Key.Key_Delete)
        QApplication.processEvents()
        assert inst.scene() is None
        assert inst not in sc._block_instances
        assert inst not in d._instances
        sc.undo()
        QApplication.processEvents()
        assert len(sc._block_instances) == 1
        assert sc._block_instances[0].block_pos() == (10.0, 10.0)
    finally:
        sc.cleanup()
        v.close()
        v.deleteLater()
        QApplication.processEvents()
