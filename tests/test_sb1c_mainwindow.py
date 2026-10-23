"""SB1c D7 -- a project drawing-scale change re-prepares annotative
instances on the plan. Runs in its OWN pytest process (module MainWindow)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from tests.test_constraint_pick_ribbon import mw  # noqa: F401


def test_scale_change_reprepares_annotative_instances(mw, qapp):
    ms = mw.scene
    ln = LineItem(QPointF(-3.0, 0.0), QPointF(3.0, 0.0))
    d = BlockDefinition.new(name="SB1c-D7", library="L", series="S",
                            primitives=[ln.to_dict()], origin=(0.0, 0.0))
    d.scale_mode = "annotative"
    ms.register_block_definition(d)
    inst = ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
    old = ms.scale_manager.drawing_scale
    probe = QPointF(800.0, 0.0)       # outside the 1:100 extent, inside 1:200
    damaged = []
    ms.changed.connect(lambda rects: damaged.extend(rects))
    qapp.processEvents()
    try:
        damaged.clear()
        ms.scale_manager.drawing_scale = 200.0
        mw._on_project_settings_changed()
        qapp.processEvents()
        # 6 printed mm x 200 = 1200 scene mm, centred on the origin.
        assert inst.geometric_rect().width() == pytest.approx(1200.0, rel=1e-6)
        # The scene must have been told to repaint the grown extent.
        assert any(r.contains(probe) for r in damaged),             "no repaint was scheduled over the new extent"
    finally:
        ms.scale_manager.drawing_scale = old
        mw._on_project_settings_changed()
        ms.remove_block_instance(inst)
        qapp.processEvents()
