"""Pipe labels in sections and elevations (R-8, R-9)."""
import pytest

from tests.test_section_classification import _placed_scene
from tests.test_section_pipe_symbols import _lines, _pipe


def _labels(sec, pipe):
    from firepro3d.section_scene import _ElevPipeLabel
    return [i for i in sec.items() if isinstance(i, _ElevPipeLabel) and i.host is pipe]


def _scene(section_scene_for):
    """A section over a model holding the shipped PipeLabel block: the fixture's
    isolated library has no System tier, so a label would be the placeholder."""
    import os
    import firepro3d
    from firepro3d import block_library
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    ms.register_block_definition(block_library.load_block_file(os.path.join(
        os.path.dirname(firepro3d.__file__), "system_blocks", "Tags", "PipeLabel.fpdb")))
    return ms, sec


def test_line_pipe_gets_a_centred_block_label(qapp, section_scene_for):
    """AC6 / R-8: the plan's block, centred, annotation band."""
    from firepro3d.constants import Z_ANNOT_TAG
    ms, sec = _scene(section_scene_for)
    pipe = _pipe(ms, (2000.0, -1000.0, 2500.0), (6000.0, -1000.0, 2500.0))
    sec.rebuild()
    (lab,) = _labels(sec, pipe)
    assert lab.definition().id == "system-tags-pipelabel"
    assert lab.paints()
    assert (lab.pos().x(), lab.pos().y()) == pytest.approx((4000.0, -2500.0))
    assert lab.rotation() == pytest.approx(0.0)
    assert lab.zValue() == Z_ANNOT_TAG


@pytest.mark.parametrize("flip", [False, True])
def test_vertical_pipe_label_reads_along_the_pipe(qapp, section_scene_for, flip):
    """AC6: real stacked nodes; either node order reads bottom to top."""
    ms, sec = _scene(section_scene_for)
    a, b = (3000.0, -1000.0, 0.0), (3000.0, -1000.0, 3000.0)
    pipe = _pipe(ms, *((b, a) if flip else (a, b)))
    assert pipe._is_vertical()
    sec.rebuild()
    (lab,) = _labels(sec, pipe)
    assert lab.rotation() == pytest.approx(-90.0)
    assert (lab.pos().x(), lab.pos().y()) == pytest.approx((3000.0, -1500.0))


def test_show_label_off_means_no_label(qapp, section_scene_for):
    """AC6 / R-9."""
    ms, sec = _scene(section_scene_for)
    pipe = _pipe(ms, (2000.0, -1000.0, 2500.0), (6000.0, -1000.0, 2500.0))
    pipe._properties["Show Label"]["value"] = "False"
    sec.rebuild()
    assert not _labels(sec, pipe)


def test_symbols_get_no_label(qapp, section_scene_for):
    """R-8: perpendicular cut and end-on."""
    ms, sec = _scene(section_scene_for)
    cut = _pipe(ms, (3000.0, -1000.0, 2500.0), (3000.0, 1000.0, 2500.0))
    end = _pipe(ms, (5000.0, -1000.0, 2500.0), (5000.0, -3000.0, 2500.0))
    sec.rebuild()
    assert not _labels(sec, cut) and not _labels(sec, end)


def test_line_trimmed_away_keeps_no_label(qapp, section_scene_for):
    """A short pipe wholly inside a symbol's circle leaves no ink, so no label."""
    ms, sec = _scene(section_scene_for)
    _pipe(ms, (3000.0, -500.0, 2500.0), (3000.0, -1500.0, 2500.0))        # C at d=500
    short = _pipe(ms, (3020.0, -1000.0, 2500.0), (3040.0, -1000.0, 2500.0))
    sec.rebuild()
    assert _lines(sec, short)
    assert not _labels(sec, short)


def test_clipped_pipe_label_centres_on_the_visible_part(qapp, section_scene_for):
    """P2."""
    ms, sec = _scene(section_scene_for)
    pipe = _pipe(ms, (8000.0, -1000.0, 2500.0), (14000.0, -1000.0, 2500.0))
    sec.rebuild()
    (lab,) = _labels(sec, pipe)
    assert lab.pos().x() == pytest.approx(9000.0)


def test_label_is_not_selectable_or_framed(qapp, section_scene_for):
    """AC6."""
    from PyQt6.QtWidgets import QGraphicsItem
    ms, sec = _scene(section_scene_for)
    pipe = _pipe(ms, (2000.0, -1000.0, 2500.0), (6000.0, -1000.0, 2500.0))
    sec.rebuild()
    (lab,) = _labels(sec, pipe)
    assert not lab.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
    assert sec._manip_exclude(lab)


def test_hide_takes_the_label_with_the_line(qapp, section_scene_for):
    ms, sec = _scene(section_scene_for)
    pipe = _pipe(ms, (2000.0, -1000.0, 2500.0), (6000.0, -1000.0, 2500.0))
    sec.rebuild()
    (lab,) = _labels(sec, pipe)
    sec._hide_elev_items(_lines(sec, pipe))
    assert not lab.isVisible()


def test_refresh_annotation_tags_reshapes_the_label(qapp, section_scene_for):
    """A drawing scale change resizes it (bounds are cached)."""
    ms, sec = _scene(section_scene_for)
    pipe = _pipe(ms, (2000.0, -1000.0, 2500.0), (6000.0, -1000.0, 2500.0))
    sec.rebuild()
    (lab,) = _labels(sec, pipe)
    before = lab.boundingRect().width()
    ms.scale_manager.drawing_scale = ms.scale_manager.drawing_scale * 2
    sec.refresh_annotation_tags()
    assert lab.boundingRect().width() == pytest.approx(before * 2, rel=0.05)


def test_plan_label_pose_is_unchanged(qapp, section_scene_for):
    """GENERALIZE parity: sloped plan pipes keep the rotation base 6af322cc gave
    (literals read from its update_label mapping, not the shared helper)."""
    ms, _ = section_scene_for("north")
    a = ms.add_node(0.0, 0.0); b = ms.add_node(-1000.0, -1000.0)
    pipe = ms.add_pipe(a, b)                     # leftward, turned to read: down-right
    assert pipe.label.rotation() == pytest.approx(45.0)
    assert (pipe.label.pos().x(), pipe.label.pos().y()) == pytest.approx((-500.0, -500.0))
    c = ms.add_node(0.0, 3000.0); d = ms.add_node(1000.0, 2000.0)
    assert ms.add_pipe(c, d).label.rotation() == pytest.approx(-45.0)   # up-right


SCALE = 0.02


def _plan_label_hooks(sec, pipe):
    """What the plan Pipe branch sets on the same pipe's plan label."""
    from firepro3d.paper_display import apply_paper_overrides, restore_model_display
    ms = sec._ms
    saved = apply_paper_overrides(ms, ms.sceneRect(), SCALE)
    lab = pipe.label
    hooks = (lab._paper_scale, lab._paper_pen_width, lab._paper_pen_color)
    restore_model_display(saved)
    return hooks


def _ink_colours(sec, rect):
    """Colours of the fully opaque pixels rendered in *rect*."""
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QImage, QPainter
    w, h = int(rect.width()) + 1, int(rect.height()) + 1
    img = QImage(w * 4, h * 4, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    sec.render(p, QRectF(img.rect()), rect)
    p.end()
    return {img.pixelColor(i, j).name() for i in range(img.width()) for j in range(img.height())
            if img.pixelColor(i, j).alpha() == 255}


def _paper_scene(section_scene_for):
    ms, sec = _scene(section_scene_for)
    pipe = _pipe(ms, (2000.0, -1000.0, 2500.0), (6000.0, -1000.0, 2500.0))
    sec.rebuild()
    (lab,) = _labels(sec, pipe)
    return sec, pipe, lab


def test_pipe_row_prints_the_label_and_restores(qapp, section_scene_for):
    """AC6: the row reaches the label through _apply_block, then restore."""
    from firepro3d import paper_display as pd
    from firepro3d.paper_display import (PaperColorMode, apply_paper_overrides,
                                         restore_model_display, save_paper_color_mode)
    save_paper_color_mode(PaperColorMode.CUSTOM)
    cats = pd.load_paper_categories()
    cats["Pipe"]["color"] = "#0000ff"
    pd.save_paper_categories(cats)
    sec, pipe, lab = _paper_scene(section_scene_for)
    screen = lab.boundingRect().width()
    plan = _plan_label_hooks(sec, pipe)
    saved = apply_paper_overrides(sec, sec.sceneRect(), SCALE)
    assert lab._paper_scale == SCALE
    assert lab._paper_pen_color.name() == "#0000ff"
    assert lab._paper_pen_width == pytest.approx(
        pd.resolve_line_weight_mm(cats["Pipe"]["line_weight"]) / SCALE)
    assert (lab._paper_scale, lab._paper_pen_width, lab._paper_pen_color) == plan
    assert _ink_colours(sec, lab.sceneBoundingRect()) == {"#0000ff"}
    restore_model_display(saved)
    assert (lab._paper_scale, lab._paper_pen_color, lab._paper_pen_width) == (None, None, None)
    assert lab.boundingRect().width() == pytest.approx(screen)


def test_full_colour_prints_the_label_at_the_row_weight_keeping_its_colour(qapp, section_scene_for):
    """AC6: Full Colour sets scale and weight, no colour override, like plan."""
    from firepro3d import paper_display as pd
    from firepro3d.paper_display import (PaperColorMode, apply_paper_overrides,
                                         restore_model_display, save_paper_color_mode)
    save_paper_color_mode(PaperColorMode.FULL_COLOR)
    cats = pd.load_paper_categories()
    sec, pipe, lab = _paper_scene(section_scene_for)
    plan = _plan_label_hooks(sec, pipe)
    saved = apply_paper_overrides(sec, sec.sceneRect(), SCALE)
    assert lab._paper_pen_color is None
    assert lab._paper_pen_width == pytest.approx(
        pd.resolve_line_weight_mm(cats["Pipe"]["line_weight"]) / SCALE)
    assert (lab._paper_scale, lab._paper_pen_width, lab._paper_pen_color) == plan
    restore_model_display(saved)


def test_hidden_pipe_row_hides_the_label_and_restores(qapp, section_scene_for):
    from firepro3d import paper_display as pd
    from firepro3d.paper_display import apply_paper_overrides, restore_model_display
    cats = pd.load_paper_categories()
    cats["Pipe"]["visible"] = False
    pd.save_paper_categories(cats)
    sec, _pipe_item, lab = _paper_scene(section_scene_for)
    saved = apply_paper_overrides(sec, sec.sceneRect(), SCALE)
    assert not lab.isVisible()
    restore_model_display(saved)
    assert lab.isVisible()


def _two_level_pipe(section_scene_for):
    ms, sec = _scene(section_scene_for)
    lm = ms._level_manager
    lm.add_level("Level 2", elevation=3000.0)
    pipe = _pipe(ms, (2000.0, -1000.0, 0.0), (2000.0, -2000.0, 0.0))
    pipe.node2.ceiling_level = "Level 2"
    lm.update_elevations(ms)
    return ms, sec, lm, pipe


def test_level_change_refreshes_the_plan_label_bounds(qapp, section_scene_for):
    """AC7 / B12: the plan label's cached bounds follow the new Length."""
    ms, _sec, lm, pipe = _two_level_pipe(section_scene_for)
    pipe.update_label()
    lab = pipe.label
    before = lab.host_values({"Length"})["Length"].raw
    stale = lab.boundingRect()
    lm.get("Level 2").elevation = 90000.0
    lm.update_elevations(ms)
    assert lab.host_values({"Length"})["Length"].raw != before
    fresh = lab._compute_rect()
    assert fresh != stale                       # the longer value is wider
    assert lab.boundingRect() == fresh


def test_level_change_reaches_an_open_section_label(qapp, section_scene_for):
    """AC7: the section label reads the new Length after the rebuild. The
    rebuild reads host values live, so this holds without the level_manager
    change; the plan-bounds test above is the B12 guard."""
    ms, sec, lm, pipe = _two_level_pipe(section_scene_for)
    lm.get("Level 2").elevation = 90000.0
    lm.update_elevations(ms)
    sec.rebuild()                               # levelsChanged -> rebuild_all in the app
    (lab,) = _labels(sec, pipe)
    assert lab.host_values({"Length"})["Length"].raw == pytest.approx(
        pipe.label.host_values({"Length"})["Length"].raw)
    assert lab.boundingRect() == lab._compute_rect()
