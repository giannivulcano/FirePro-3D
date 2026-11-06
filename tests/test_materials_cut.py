"""Every cut draws its element's material (AC1, AC2, AC3, AC9). Ground truth = pixels."""
from collections import Counter

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d import fill_types as ft
from firepro3d import materials as mt
from firepro3d import paper_display as pd
from firepro3d.constants import TOKEN_ELEMENT
from firepro3d.fill_layers import BackgroundLayer, FillLayers, PatternLayer
from firepro3d.floor_slab import FloorSlab
from firepro3d.hatch_patterns import BUILTIN_DIAGONAL
from firepro3d.wall import WallSegment
from tests.test_section_classification import _placed_scene, _source_rects, _wall as _section_wall


@pytest.fixture(autouse=True)
def _fresh_tables():
    ft.reset_project_table()
    mt.reset_project_table()
    yield
    ft.reset_project_table()
    mt.reset_project_table()


def _mat(name, colour=None, ref=None):
    """A material on a new Fill Type: a *colour* body and / or a *ref* hatch."""
    bg = BackgroundLayer(colour, 1.0) if colour else None
    pat = PatternLayer(ref, TOKEN_ELEMENT) if ref else None
    t = ft.project_table().add(ft.FillType(ft.new_id(), name, FillLayers(bg, pat)))
    return mt.project_table().add(mt.Material(ft.new_id(), name, t.id))


def _cut_wall(ms, y=0.0, m=None):
    w = WallSegment(QPointF(0, y), QPointF(4000, y), thickness_mm=300.0)
    ms.addItem(w)
    ms._walls.append(w)
    w._is_section_cut = True
    if m is not None:
        w.material_id = m.id
    return w


def _colours(scene, rect, scale=1.0):
    """Colour counts of *rect* inset 30 %, clear of the outline."""
    r = QRectF(rect).adjusted(rect.width() * .3, rect.height() * .3,
                              -rect.width() * .3, -rect.height() * .3)
    w, h = max(int(r.width() * scale), 4), max(int(r.height() * scale), 4)
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, w, h), r)
    p.end()
    return Counter(QColor(img.pixel(x, y)).name() for x in range(w) for y in range(h))


def _body(scene, rect):
    return _colours(scene, rect).most_common(1)[0][0]


def test_two_walls_in_one_section_draw_their_own_material(qapp, section_scene_for):
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    a, b = _section_wall(ms, (3000.0, -1000.0), (3000.0, 1000.0)), \
        _section_wall(ms, (7000.0, -1000.0), (7000.0, 1000.0))
    a.material_id, b.material_id = _mat("R", "#ff0000").id, _mat("B", "#0000ff").id
    sec.rebuild()
    ra, rb = _source_rects(sec, a)[0], _source_rects(sec, b)[0]
    assert _body(sec, ra.sceneBoundingRect()) == "#ff0000"
    assert _body(sec, rb.sceneBoundingRect()) == "#0000ff"


def test_a_slab_in_a_section_draws_its_material(qapp, section_scene_for):
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    s = FloorSlab([QPointF(1000, -1000), QPointF(9000, -1000),
                   QPointF(9000, 1000), QPointF(1000, 1000)])
    ms.addItem(s)
    ms._floor_slabs.append(s)
    s.material_id = _mat("G", "#00ff00").id
    sec.rebuild()
    assert _body(sec, _source_rects(sec, s)[0].sceneBoundingRect()) == "#00ff00"


def test_two_walls_in_a_plan_cut_draw_their_own_material(qapp, model_space):
    a = _cut_wall(model_space, 0.0, _mat("R", "#ff0000"))
    b = _cut_wall(model_space, 2000.0, _mat("B", "#0000ff"))
    assert _body(model_space, a.sceneBoundingRect()) == "#ff0000"
    assert _body(model_space, b.sceneBoundingRect()) == "#0000ff"


def test_a_slab_plan_cut_draws_its_material(qapp, model_space):
    s = FloorSlab([QPointF(0, 0), QPointF(2000, 0), QPointF(2000, 2000), QPointF(0, 2000)])
    model_space.addItem(s)
    model_space._floor_slabs.append(s)
    s._is_section_cut = True
    s.material_id = _mat("G", "#00ff00").id
    assert _body(model_space, s.sceneBoundingRect()) == "#00ff00"


def test_none_draws_nothing_in_plan_and_section(qapp, section_scene_for):
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    w = _section_wall(ms, (3000.0, -1000.0), (3000.0, 1000.0))
    w._is_section_cut = True
    sec.rebuild()
    assert set(_colours(sec, _source_rects(sec, w)[0].sceneBoundingRect())) == {"#ffffff"}
    assert set(_colours(ms, w.sceneBoundingRect())) == {"#ffffff"}


def test_a_none_material_set_to_solid_draws_solid(qapp, model_space):
    w = _cut_wall(model_space)
    t = ft.project_table().add(ft.FillType("t", "Solid", FillLayers(BackgroundLayer("#ff0000", 1.0))))
    table = mt.project_table()
    none = table.get(w.material_id)
    table.replace(mt.Material(none.id, none.name, t.id))
    assert _body(model_space, w.sceneBoundingRect()) == "#ff0000"


def test_fill_mode_section_shows_the_material_on_an_uncut_wall(qapp, model_space):
    w = _cut_wall(model_space, m=_mat("R", "#ff0000"))
    w._is_section_cut = False
    w.set_property("Fill Mode", "Section")
    assert _body(model_space, w.sceneBoundingRect()) == "#ff0000"


def test_a_table_edit_reaches_the_next_repaint_with_no_rebuild(qapp, section_scene_for):
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    w = _section_wall(ms, (3000.0, -1000.0), (3000.0, 1000.0))
    m = _mat("R", "#ff0000")
    w.material_id = m.id
    sec.rebuild()
    r = _source_rects(sec, w)[0]
    assert _body(sec, r.sceneBoundingRect()) == "#ff0000"
    other = ft.project_table().add(ft.FillType("g", "G", FillLayers(BackgroundLayer("#00ff00", 1.0))))
    mt.project_table().replace(mt.Material(m.id, m.name, other.id))        # re-point
    assert _body(sec, r.sceneBoundingRect()) == "#00ff00"
    ft.project_table().replace(ft.FillType("g", "G", FillLayers(BackgroundLayer("#0000ff", 1.0))))  # restyle
    assert _body(sec, r.sceneBoundingRect()) == "#0000ff"


PAPER_SCALE = 0.01      # 1:100, as a real viewport passes (hatch lines scale off it)


def _paper_render(ms, item):
    """Render through the real paper pass (B&W is the default colour mode)."""
    saved = pd.apply_paper_overrides(ms, item.sceneBoundingRect().adjusted(-500, -500, 500, 500),
                                     PAPER_SCALE)
    try:
        return _colours(ms, item.sceneBoundingRect())
    finally:
        pd.restore_model_display(saved)


def test_paper_hatch_only_material_has_no_black_body(qapp, model_space, shipped_hatches):
    shipped_hatches(model_space)
    w = _cut_wall(model_space, m=_mat("H", ref=BUILTIN_DIAGONAL))
    seen = _paper_render(model_space, w)
    assert seen.most_common(1)[0][0] == "#ffffff"       # the ground shows between lines
    assert len(seen) > 1                                # and the hatch printed


def test_paper_material_with_a_body_keeps_the_paper_section_colour(qapp, model_space):
    w = _cut_wall(model_space, m=_mat("S", "#ff0000"))
    assert _paper_render(model_space, w).most_common(1)[0][0] != "#ffffff"


def test_paper_none_prints_nothing(qapp, model_space):
    w = _cut_wall(model_space)
    assert set(_paper_render(model_space, w)) == {"#ffffff"}


def test_a_section_rect_on_paper_follows_the_same_rule(qapp, section_scene_for, shipped_hatches):
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    shipped_hatches(ms)
    w = _section_wall(ms, (3000.0, -1000.0), (3000.0, 1000.0))
    w.material_id = _mat("H", ref=BUILTIN_DIAGONAL).id
    sec.rebuild()
    r = _source_rects(sec, w)[0]
    saved = pd.apply_paper_overrides(sec, sec.itemsBoundingRect(), PAPER_SCALE)
    try:
        seen = _colours(sec, r.sceneBoundingRect())
    finally:
        pd.restore_model_display(saved)
    assert seen.most_common(1)[0][0] == "#ffffff" and len(seen) > 1
