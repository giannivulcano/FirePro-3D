"""SB4d D5 (plan): LevelManager.apply_to_scene puts every annotation holder
in its sub-band; symbols stay elevation-ordered model geometry."""
import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.constants import (Z_ANNOT_GRID, Z_ANNOT_MARKER, Z_ANNOT_TAG,
                                 Z_ANNOT_TEXT, Z_CAT_CONSTRUCTION, Z_CAT_NODE,
                                 Z_CAT_PIPE, Z_ELEV_SCALE)
from tests._sb4d_helpers import dispose, plan_scene, tag_def, wall


def test_tag_block_joins_the_tag_band_and_a_symbol_block_stays_model(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        tall = wall(ms, top_offset=20000.0)                 # 20 m: 20000 * 0.01 + 0.3 = 200.3
        tag = ms.place_block_instance(tag_def(ms).id, (4000.0, 0.0))
        sym = ms.place_block_instance(tag_def(ms, category="", name="Sym").id, (2000.0, 0.0))
        ms._level_manager.apply_to_scene(ms)
        assert tag.zValue() == Z_ANNOT_TAG
        assert sym.zValue() == pytest.approx(0.0 * Z_ELEV_SCALE + Z_CAT_CONSTRUCTION)   # Level 1 at 0 mm
        assert ms.items(QPointF(4000.0, 0.0))[0] is tag      # Qt's own stacking: the tag over the wall
        assert tall.zValue() < tag.zValue()
    finally:
        dispose(ms, sec, tabs)


def test_text_is_born_in_the_text_band(qapp):
    from firepro3d.text_item import TextAnnotationData, TextItem
    t = TextItem(TextAnnotationData(text="NOTE"))
    assert t.zValue() == Z_ANNOT_TEXT


def test_gridline_and_both_markers_take_their_bands_after_the_walk(qapp):
    from firepro3d.gridline import GridlineItem
    ms, sec, det, tabs = plan_scene()
    try:
        gl = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 9000.0), label="1")
        ms._gridlines.append(gl)
        ms.addItem(gl)
        dmk = det.create_detail("Detail 1", QRectF(0.0, 0.0, 2000.0, 2000.0))
        smk = sec.place_section(QPointF(0.0, -2000.0), QPointF(6000.0, -2000.0))
        smk.setZValue(0.0)                     # the walk, not the constructor, must set it
        dmk.setZValue(0.0)
        ms._level_manager.apply_to_scene(ms)
        assert gl.zValue() == Z_ANNOT_GRID
        assert dmk.zValue() == Z_ANNOT_MARKER
        assert smk.zValue() == Z_ANNOT_MARKER
    finally:
        dispose(ms, sec, tabs)


def test_water_supply_is_elevation_ordered_just_above_node(qapp):
    from firepro3d.water_supply import WaterSupply
    from firepro3d.constants import Z_CAT_SYMBOL
    ms, sec, det, tabs = plan_scene()
    try:
        ws = WaterSupply(1000.0, 1000.0)
        ws.level = "Level 2"                            # 3048 mm (DEFAULT_LEVEL_GAP_MM)
        ms.addItem(ws)
        ms.water_supply_node = ws
        ms._level_manager.apply_to_scene(ms)
        assert ws.zValue() == pytest.approx(3048.0 * Z_ELEV_SCALE + Z_CAT_SYMBOL)   # 31.03
        assert Z_CAT_NODE < Z_CAT_SYMBOL < Z_CAT_CONSTRUCTION                        # 0.5 < 0.55 < 0.6
    finally:
        dispose(ms, sec, tabs)


def test_riser_symbol_pins_just_above_its_pipe(qapp):
    from firepro3d.constants import Z_CAT_SYMBOL
    ms, sec, det, tabs = plan_scene()
    try:
        from firepro3d.node import Node
        top, bot = Node(500.0, 500.0), Node(500.0, 500.0)   # ms.add_node would merge two coincident nodes
        for n in (top, bot):
            ms.addItem(n)
            ms.sprinkler_system.add_node(n)
        p = ms.add_pipe(top, bot)          # add_pipe propagates the ceiling: set the heights after it
        for n, z in ((top, 3000.0), (bot, 0.0)):
            n.ceiling_level, n.ceiling_offset = "Level 1", z    # apply_to_scene re-derives z_pos from these
            n.z_pos = z
        p.update_label()
        assert p._riser_symbol is not None
        ms._level_manager.apply_to_scene(ms)
        assert p.zValue() == pytest.approx(3000.0 * Z_ELEV_SCALE + Z_CAT_PIPE)   # 30.4
        assert p._riser_symbol.zValue() == pytest.approx(p.zValue() + (Z_CAT_SYMBOL - Z_CAT_PIPE))
    finally:
        dispose(ms, sec, tabs)


@pytest.mark.parametrize("z_mm", [0.0, 25000.0])
def test_pipe_label_takes_the_tag_band_at_any_elevation(qapp, z_mm):
    ms, sec, det, tabs = plan_scene()
    try:
        p = ms.add_pipe(ms.add_node(0.0, 0.0), ms.add_node(3000.0, 0.0))
        for n in (p.node1, p.node2):
            n.ceiling_level, n.ceiling_offset = "Level 1", z_mm   # apply_to_scene re-derives z_pos from these
            n.z_pos = z_mm
        ms._level_manager.apply_to_scene(ms)
        assert p.label.zValue() == Z_ANNOT_TAG
        assert p.label.zValue() > p.zValue()
    finally:
        dispose(ms, sec, tabs)
