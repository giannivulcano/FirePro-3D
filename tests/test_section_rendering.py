"""Cut vs behind rendering (spec s5): cut wall = Section colour + pattern,
behind wall = today's Fill; a crossing inside an opening leaves the head;
cut pipe = the plan riser symbol."""
import pytest
from PyQt6.QtCore import QPointF, QSettings
from PyQt6.QtGui import QColor

from firepro3d.section_marker import SectionMarker
from tests.test_section_classification import _placed_scene, _wall, _source_rects


def _cut_items(sec, src):
    from firepro3d.section_scene import _ElevCutRect, _ElevCutEllipse, _ROLE_SOURCE
    return [it for it in sec.items() if isinstance(it, (_ElevCutRect, _ElevCutEllipse))
            and it.data(_ROLE_SOURCE) is src]


def test_cut_wall_rect_uses_section_colour_and_pattern(qapp, section_scene_for):
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Wall/color", "#004400")
    from firepro3d import fill_types, materials
    from firepro3d.constants import TOKEN_ELEMENT
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    w = _wall(ms, (3000.0, -1000.0), (3000.0, 1000.0))
    # The wall's material draws the cut (body = #aa0000, pattern By element at scale 2).
    t = fill_types.project_table().add(fill_types.FillType(
        fill_types.new_id(), f"Cut look {fill_types.new_id()}", fill_types.legacy_section_layers("#aa0000", "crosshatch", 2.0)))
    w.material_id = materials.project_table().add(
        materials.Material(fill_types.new_id(), t.name, t.id)).id
    sec.rebuild()
    (item,) = _cut_items(sec, w)
    lay = fill_types.project_table().get(materials.fill_type_of(item._section_element)).layers
    assert lay.background.color == "#aa0000"
    assert lay.pattern.ref == "crosshatch" and lay.pattern.color == TOKEN_ELEMENT
    assert lay.pattern.scale == 2.0
    assert item.resolved_pen_brush()[0].color().name() == "#004400"
    # Geometry: width = the chord of the cut through the mitered quad = wall thickness.
    assert item.rect().width() == pytest.approx(2.0 * w.half_thickness_scene(), abs=1e-6)
    assert item.rect().height() == pytest.approx(w._height_mm, abs=1e-6)
    # It paints the hatch: a QPainter pass on the item calls draw_section_type.
    from unittest.mock import patch
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QStyleOptionGraphicsItem
    img = QImage(64, 64, QImage.Format.Format_ARGB32); img.fill(0)
    p = QPainter(img)
    with patch("firepro3d.section_scene.draw_section_type") as hatch:
        item.paint(p, QStyleOptionGraphicsItem(), None)
    p.end()
    assert hatch.call_count == 1
    assert hatch.call_args.args[4] == t.id                    # the material's Fill Type id
    assert hatch.call_args.args[5].name() == "#004400"       # By element = the cut's pen colour


def test_cut_hatch_is_drawn_against_the_section_scene(qapp, section_scene_for):
    """The renderer reads the paper override off the scene it is handed
    (paper_display sets it on the viewport's source = the SectionScene)."""
    from unittest.mock import patch
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QStyleOptionGraphicsItem
    from firepro3d.hatch_render import drafting_factor
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    w = _wall(ms, (3000.0, -1000.0), (3000.0, 1000.0))
    sec.rebuild()
    (item,) = _cut_items(sec, w)
    sec._hatch_paper_scale = 0.02
    img = QImage(64, 64, QImage.Format.Format_ARGB32); img.fill(0)
    p = QPainter(img)
    with patch("firepro3d.section_scene.draw_section_type") as hatch:
        item.paint(p, QStyleOptionGraphicsItem(), None)
    p.end()
    assert hatch.call_args.args[2] is sec
    with_override = drafting_factor(sec)
    sec._hatch_paper_scale = None
    assert with_override != drafting_factor(sec)
    assert with_override == pytest.approx(50.0)


def test_token_bg_has_no_picker_label():
    from firepro3d.colour_tokens import token_label
    from firepro3d.constants import TOKEN_BG
    assert token_label(TOKEN_BG) is None


def test_behind_wall_keeps_todays_fill(qapp, section_scene_for):
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Wall/fill", "#123456")
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    w = _wall(ms, (1000.0, -2000.0), (6000.0, -2000.0))
    sec.rebuild()
    (r,) = _source_rects(sec, w)
    assert r._brush_src == "#123456" and not _cut_items(sec, w)


def test_cut_through_window_leaves_head_and_sill(qapp, section_scene_for):
    from firepro3d.wall_opening import WallOpening
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    w = _wall(ms, (3000.0, -3000.0), (3000.0, 3000.0))       # 6 m wall crossing at its midpoint
    op = WallOpening(w, offset_along=3000.0, width_mm=1200.0, height_mm=1500.0,
                     sill_mm=900.0, feature_id="window_900")
    w.openings.append(op)
    sec.rebuild()
    items = _cut_items(sec, w)
    assert len(items) == 2
    spans = sorted((-it.rect().bottom(), -it.rect().top()) for it in items)   # (z0, z1) pairs
    assert spans[0] == pytest.approx((0.0, 900.0))              # below the sill
    assert spans[1] == pytest.approx((2400.0, w._height_mm))    # above the head


def test_cut_pipe_symbol_is_the_plan_size(qapp, section_scene_for):
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    n1 = ms.add_node(3000.0, -1000.0); n2 = ms.add_node(3000.0, 1000.0)
    pipe = ms.add_pipe(n1, n2)
    n1.z_pos = 2000.0; n2.z_pos = 3000.0     # after add_pipe: it recomputes z_pos from the level
    pipe._display_scale = 2.0                # the plan riser ignores it (fixed size)
    sec.rebuild()
    (c,) = _cut_items(sec, pipe)
    assert c.rect().width() == pytest.approx(pipe._RISER_SIZE_MM)
    assert c.rect().center().x() == pytest.approx(3000.0) and c.rect().center().y() == pytest.approx(-2500.0)
