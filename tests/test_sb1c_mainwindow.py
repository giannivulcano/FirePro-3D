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


def test_scale_change_reprepares_hosted_copies_in_open_sections(mw, qapp):
    """The gridline-hosted copy in a live section scene follows the project
    drawing scale without a rebuild (SB1c D7 / VC9 I1)."""
    from firepro3d.gridline import GridlineItem
    from firepro3d.section_scene import _HostedBlockCopy

    ms = mw.scene
    ln = LineItem(QPointF(-3.0, 0.0), QPointF(3.0, 0.0))
    d = BlockDefinition.new(name="SB1c-D7-sec", library="L", series="S",
                            primitives=[ln.to_dict()], origin=(0.0, 0.0))
    d.scale_mode = "annotative"
    ms.register_block_definition(d)
    gl = GridlineItem(QPointF(0.0, -3000.0), QPointF(6000.0, -3000.0), label="B")
    ms._gridlines.append(gl)
    ms.addItem(gl)
    host = {"gridline": gl._uid, "offset_mm": 0.0, "along_mm": 1000.0,
            "elevation_mm": 500.0, "facing": 1}
    inst = ms.place_block_instance(d.id, (0, 0), host=host)
    sec = mw.section_manager.get_or_build_scene("north")
    # Project Settings edits the model's ScaleManager. The section's own _sm is
    # the SectionManager's construction-time one (stale after a load / clear),
    # so the copy must follow the model's, not _sm.
    ssm = ms.scale_manager
    old = ssm.drawing_scale
    try:
        sec.rebuild()
        qapp.processEvents()
        cp = sec._hosted_copies[id(inst)]
        assert isinstance(cp, _HostedBlockCopy)
        assert sec in mw.section_manager.open_scenes
        r0 = cp.mapRectToScene(cp.boundingRect())
        w0 = r0.width()
        # outside the old extent, inside the doubled one
        probe = QPointF(r0.center().x() + 0.75 * w0, r0.center().y())
        damaged = []
        sec.changed.connect(lambda rects: damaged.extend(rects))
        qapp.processEvents()
        damaged.clear()
        ssm.drawing_scale = old * 2.0
        mw._on_project_settings_changed()
        qapp.processEvents()
        assert sec._hosted_copies[id(inst)] is cp      # re-prepared, not rebuilt
        w1 = cp.mapRectToScene(cp.boundingRect()).width()
        assert w1 / w0 == pytest.approx(2.0, rel=0.02)
        # prepareGeometryChange ran: the scene index and the repaint region
        # both cover the grown extent (a bare boundingRect query would not tell).
        assert cp in sec.items(probe), "scene index still holds the old extent"
        assert any(r.contains(probe) for r in damaged), "no repaint over the new extent"
    finally:
        ssm.drawing_scale = old
        mw._on_project_settings_changed()
        ms.remove_block_instance(inst)
        ms._gridlines.remove(gl)
        ms.removeItem(gl)
        qapp.processEvents()
