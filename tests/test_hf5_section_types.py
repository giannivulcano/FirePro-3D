"""HF5 Task 6 -- section cuts via Fill Types (R4/R7/R8)."""
import json
from collections import Counter

from PyQt6.QtCore import QPointF, QRectF, QSettings
from PyQt6.QtGui import QColor, QImage, QPainter

import pytest

from firepro3d import fill_types as ft
from firepro3d import materials as mt
from firepro3d.constants import TOKEN_ELEMENT
from firepro3d.fill_layers import BackgroundLayer, FillLayers, PatternLayer, to_record


def test_legacy_cell_converts_to_look_identical_layers():
    lay = ft.legacy_section_layers("#666666", "diagonal", 2.0)
    assert lay.background == BackgroundLayer("#666666", 1.0)
    assert lay.pattern.color == TOKEN_ELEMENT and lay.pattern.scale == 2.0
    assert lay.pattern.ref == "builtin-hatch-diagonal"
    assert ft.legacy_section_layers("", None, None).background is None
    assert ft.legacy_section_layers("hatch:#ff0000", None, None).background is None


def test_item_override_converts_and_distinct_looks_number():
    ft.set_project_table(ft.FillTypeTable())
    ft.project_table().ensure_look("Wall Section", ft.legacy_section_layers("#666666", "diagonal", 1.0))
    ov = {"section": "#ff0000", "section_pattern": "diagonal", "color": "#00ff00"}
    ft.convert_item_section_override("Wall", ov)
    assert set(ov) == {"color", "section_type"}
    assert ft.project_table().get(ov["section_type"]).name == "Wall Section 2"


def test_item_override_with_only_a_pattern_inherits_the_category_body():
    """Legacy per-key fallback: an override naming only a pattern kept the
    category's body colour and scale."""
    ft.set_project_table(ft.FillTypeTable())
    tid = ft.project_table().ensure_look(
        "Wall Section", ft.legacy_section_layers("#666666", "diagonal", 2.0)).id
    ov = {"section_pattern": "horizontal"}
    ft.convert_item_section_override("Wall", ov, ft.resolve(tid, None)[0])
    lay = ft.project_table().get(ov["section_type"]).layers
    assert lay.background.color == "#666666"
    assert lay.pattern.ref == "builtin-hatch-horizontal" and lay.pattern.scale == 2.0


def test_token_and_no_fill_bodies_survive_the_conversion():
    """The old dialog offered Automatic / Accent and No Fill for the body colour;
    both convert (token kept, '' = no body)."""
    from firepro3d.constants import TOKEN_ACCENT
    lay = ft.legacy_section_layers(TOKEN_ACCENT, "diagonal", 1.0)
    assert lay.background == BackgroundLayer(TOKEN_ACCENT, 1.0)
    assert ft.legacy_section_layers("", "diagonal", 1.0).background is None


# -- the real path: a cut draws its element's material (materials.md M3) -----------

@pytest.fixture(autouse=True)
def _fresh_tables():
    ft.reset_project_table()
    mt.reset_project_table()
    yield
    ft.reset_project_table()
    mt.reset_project_table()


def _give_material(item, layers, name="Cut look"):
    """Give *item* a material on a new Fill Type carrying *layers*; returns the type."""
    t = ft.project_table().add(ft.FillType(ft.new_id(), name, layers))
    item.material_id = mt.project_table().add(mt.Material(ft.new_id(), name, t.id)).id
    return t


def _factory_cut():
    """The retired factory Wall category look: #666666 body, By element diagonal."""
    return ft.legacy_section_layers("#666666", "diagonal", 1.0)


def _wall(ms, x0=0.0, x1=1200.0):
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(x0, 0.0), QPointF(x1, 0.0))
    ms._walls.append(w)
    ms.addItem(w)
    w._is_section_cut = True
    return w


def _apply_wall_category(ms):
    from firepro3d import display_manager as dm
    dm._apply_to_scene_items(ms, "Wall", dm._read_category_from_settings("Wall"),
                             respect_overrides=True)


def _render(ms, wall, scale=1.0):
    """The wall's interior (inset from its outline) rendered at *scale* px/scene unit."""
    r = wall.sceneBoundingRect().adjusted(-20, -20, 20, 20)
    w, h = int(r.width() * scale), int(r.height() * scale)
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, w, h), r)
    p.end()
    # the interior band: well inside the wall's outline
    b = wall.sceneBoundingRect()
    x0, x1 = int((b.left() + b.width() * 0.2 - r.left()) * scale), int((b.right() - b.width() * 0.2 - r.left()) * scale)
    c = int((b.center().y() - r.top()) * scale)
    half = int(b.height() * 0.25 * scale)
    return [QColor(img.pixel(x, y)) for x in range(x0, x1) for y in range(c - half, c + half)]


def _body(px):
    """The most common interior colour = the cut body (the hatch lines are sparser)."""
    return Counter(c.name() for c in px).most_common(1)[0][0]


def _near(c, rgb, tol=40):
    return all(abs(a - b) <= tol for a, b in zip((c.red(), c.green(), c.blue()), rgb))


def test_wall_cut_pixels_follow_type_and_element_colour(qapp, model_space, shipped_hatches):
    ms = model_space
    shipped_hatches(ms)
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Wall/color", "#00aa00")      # the wall line colour (green)
    w = _wall(ms)
    w._display_overrides["fill"] = ""                 # no element fill under the cut
    _apply_wall_category(ms)
    tid = _give_material(w, _factory_cut()).id
    assert ft.project_table().get(tid) is not None

    # 1. category default: body = the factory #666666, hatch lines = the wall line colour
    px = _render(ms, w)
    assert _body(px) == "#666666"
    green = [c for c in px if _near(c, (0, 170, 0), 30)]
    assert len(green) > 10, "By element hatch should draw in the wall line colour"

    # 2. a per-item line colour override recolours the hatch (R8)
    w._display_overrides["color"] = "#ff0000"
    _apply_wall_category(ms)
    px = _render(ms, w)
    assert len([c for c in px if _near(c, (255, 0, 0), 30)]) > 10
    assert not [c for c in px if _near(c, (0, 170, 0), 30)]
    del w._display_overrides["color"]
    _apply_wall_category(ms)

    # 3. restyle the type live: the body follows (G6), no re-apply
    t = ft.project_table().get(tid)
    ft.project_table().replace(ft.FillType(t.id, t.name, FillLayers(
        BackgroundLayer("#0000ff", 1.0), t.layers.pattern)))
    ft.notify_changed()
    assert _body(_render(ms, w)) == "#0000ff"

    # 4. a material whose Fill Type is gone draws the fallback grey
    w.material_id = mt.project_table().add(mt.Material(ft.new_id(), "Gone", "no-such-type")).id
    _apply_wall_category(ms)
    px = _render(ms, w)
    assert _near(QColor(_body(px)), (230, 230, 230), 3)     # #808080 at 20 % on white
    assert not [c for c in px if _near(c, (0, 0, 255), 30)]


def test_wall_with_a_hatch_only_material_draws_the_hatch_in_the_line_colour(
        qapp, model_space, shipped_hatches):
    """Materials M3 retired the category default look (an untyped cut drew a
    diagonal in the line colour); a hatch-only material keeps what it proved:
    By element hatch in the line colour, no body. None now draws nothing
    (tests/test_materials_cut.py)."""
    ms = model_space
    shipped_hatches(ms)
    w = _wall(ms)
    w._display_color = "#aa0000"
    _give_material(w, ft.legacy_section_layers("", "diagonal", 1.0), "Hatch only")
    px = _render(ms, w)
    assert _body(px) == "#ffffff"
    assert len([c for c in px if _near(c, (170, 0, 0), 30)]) > 10


def test_paper_body_colour_wins_over_the_type_background(qapp, model_space, shipped_hatches):
    """The paper pass's section colour is the only writer of _display_section_color
    now; '' (No Fill) is a value and removes the body."""
    ms = model_space
    shipped_hatches(ms)
    w = _wall(ms)
    w._display_overrides["fill"] = ""
    _apply_wall_category(ms)
    _give_material(w, _factory_cut())
    assert _body(_render(ms, w)) == "#666666"
    w._display_section_color = "#00ff00"
    assert _body(_render(ms, w)) == "#00ff00"
    w._display_section_color = ""
    assert _body(_render(ms, w)) == "#ffffff"


def test_floor_cut_follows_its_type(qapp, model_space, shipped_hatches):
    from firepro3d import display_manager as dm
    from firepro3d.floor_slab import FloorSlab
    ms = model_space
    shipped_hatches(ms)
    slab = FloorSlab(points=[QPointF(0, 0), QPointF(1200, 0), QPointF(1200, 800), QPointF(0, 800)])
    ms._floor_slabs.append(slab)
    ms.addItem(slab)
    slab._is_section_cut = True
    slab._display_fill_color = ""
    dm._apply_to_scene_items(ms, "Floor", dm._read_category_from_settings("Floor"))
    t = _give_material(slab, ft.legacy_section_layers("#8888cc", "diagonal", 1.0), "Floor cut look")
    ft.project_table().replace(ft.FillType(t.id, t.name, FillLayers(BackgroundLayer("#ff00ff", 1.0))))
    ft.notify_changed()
    r = slab.sceneBoundingRect().adjusted(-20, -20, 20, 20)
    img = QImage(int(r.width()), int(r.height()), QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, img.width(), img.height()), r)
    p.end()
    assert QColor(img.pixel(img.width() // 2, img.height() // 2)).name() == "#ff00ff"


# -- Display Manager data path ----------------------------------------------------

def test_category_settings_carry_no_section_cell_and_old_keys_are_ignored(qapp):
    """M5 / M8: the category has no section cell. A QSettings install holding the
    old keys reads without them, a write leaves them alone (no migration writes),
    and the project payload never carries one."""
    from firepro3d import display_manager as dm
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Wall/section", "#aa0000")             # a pre-HF5 install
    s.setValue("display/Wall/section_pattern", "diagonal")
    s.setValue("display/Wall/section_type", "Wall Section")   # an HF5 install
    s.setValue("display/Wall/section_look", json.dumps({"pattern": {"ref": "x"}}))
    try:
        vals = dm._read_category_from_settings("Wall")
        assert not {"section", "section_pattern", "section_type", "section_look"} & set(vals)
        dm._write_category_to_settings("Wall", vals)
        assert s.value("display/Wall/section_type") == "Wall Section"      # left as found
        assert s.value("display/Wall/section") == "#aa0000"
        entry = dm.get_display_settings_for_save()["Wall"]
        assert not {"section", "section_pattern", "section_scale",
                    "section_type", "section_look"} & set(entry)
    finally:
        for k in ("section", "section_pattern", "section_type", "section_look"):
            s.remove(f"display/Wall/{k}")


def test_project_payload_with_old_section_keys_loads_and_draws_none(qapp, model_space):
    """M8: an old project's category section keys (legacy colour / pattern, and the
    HF5 type + look) load without error, add no Fill Type, and the wall draws None."""
    from firepro3d import display_manager as dm
    from firepro3d import materials as mt
    before = {t.name for t in ft.project_table().all()}
    w = _wall(model_space)
    dm.apply_project_display_settings(model_space, {"Wall": {
        "color": "#666666", "section": "#abcdef", "section_pattern": "diagonal",
        "section_type": "Wall Section",
        "section_look": {"background": {"color": "#111111", "opacity": 1.0}}}})
    assert {t.name for t in ft.project_table().all()} == before
    assert mt.fill_type_of(w) is None
    assert not hasattr(w, "_display_section_type")


def test_floor_slab_and_wall_section_overrides_round_trip(qapp, model_space):
    """L283 (2026-10-29): a wall's per-item section_type override now round-trips
    to_dict / from_dict like a floor slab's (the pre-L283 version of this test
    pinned the open bug)."""
    from firepro3d.floor_slab import FloorSlab
    from firepro3d.wall import WallSegment
    from firepro3d import fill_types as ft
    from firepro3d import materials as mt
    from firepro3d.fill_layers import BackgroundLayer, FillLayers
    ft.project_table().add(ft.FillType("some-id", "Some Cut", FillLayers(BackgroundLayer("#ff0000", 1.0))))
    w = _wall(model_space)
    w._display_overrides["section_type"] = "some-id"
    d = w.to_dict()
    assert d["display_overrides"] == {"section_type": "some-id"}
    # M7: the retired override converts to a material on load; the key does not survive it
    w2 = WallSegment.from_dict(d)
    assert mt.fill_type_of(w2) == "some-id" and "section_type" not in w2._display_overrides
    slab = FloorSlab(points=[QPointF(0, 0), QPointF(100, 0), QPointF(100, 100)])
    slab._display_overrides["section_type"] = "some-id"
    s2 = FloorSlab.from_dict(slab.to_dict())
    assert mt.fill_type_of(s2) == "some-id" and "section_type" not in s2._display_overrides


def test_dialog_preview_and_ok_write_no_section_keys(qapp, model_space):
    """M5: nothing the Model tab previews or OK writes is a section cell (the old
    Cancel-removes-the-preview-keys guard retires with the preview writer)."""
    from firepro3d import display_manager as dm
    s = QSettings("GV", "FirePro3D")
    _wall(model_space)
    dlg = dm.DisplayManager(model_space)
    try:
        dlg._apply_preview()
        dlg._set_model_as_default()
        dlg.accept()
    finally:
        dlg.close()
    for cat in ("Wall", "Floor"):
        for k in ("section_type", "section_look", "default_section_type", "default_section_look"):
            assert not s.contains(f"display/{cat}/{k}")


# -- review fixes: alpha scales, token / No Fill bodies, app-wide patterns ---------

def test_transparent_element_colour_draws_no_hatch(qapp, model_space, shipped_hatches):
    """A per-item colour override of '' (No Fill) makes By element transparent:
    the cut keeps its body but draws no hatch (the old hatch drew nothing)."""
    ms = model_space
    shipped_hatches(ms)
    w = _wall(ms)
    w._display_overrides["fill"] = ""
    w._display_overrides["color"] = ""
    _apply_wall_category(ms)
    _give_material(w, _factory_cut())
    px = _render(ms, w)
    assert {c.name() for c in px} == {"#666666"}


def test_wall_token_body_renders_the_resolved_token(qapp, model_space, shipped_hatches):
    from firepro3d.colour_tokens import resolve_colour
    from firepro3d.constants import TOKEN_ACCENT
    ms = model_space
    shipped_hatches(ms)
    w = _wall(ms)
    w._display_overrides["fill"] = ""
    _apply_wall_category(ms)
    _give_material(w, ft.legacy_section_layers(TOKEN_ACCENT, "diagonal", 1.0))
    assert _body(_render(ms, w)) == resolve_colour(TOKEN_ACCENT).name()


def test_wall_no_fill_body_renders_no_body(qapp, model_space, shipped_hatches):
    ms = model_space
    shipped_hatches(ms)
    w = _wall(ms)
    w._display_overrides["fill"] = ""
    w._display_overrides["color"] = "#aa0000"
    _apply_wall_category(ms)
    _give_material(w, ft.legacy_section_layers("", "diagonal", 1.0))
    px = _render(ms, w)
    assert _body(px) == "#ffffff"
    assert len([c for c in px if _near(c, (170, 0, 0), 60)]) > 10      # hatch still draws


def test_old_qsettings_category_pattern_no_longer_feeds_the_project_refs(qapp):
    """D-A39 / M5: patterns come from the Fill Type table (every material's type);
    an old app-wide Wall section look in QSettings is no longer walked."""
    from firepro3d import hatch_patterns as hp
    from firepro3d.model_space import Model_Space
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Wall/section_type", "Old Cut")
    s.setValue("display/Wall/section_look", json.dumps({"pattern": {"ref": "old-qsettings-only-ref"}}))
    try:
        sc = Model_Space()
        refs = hp.project_pattern_refs(sc)
        assert "old-qsettings-only-ref" not in refs
        assert hp.BUILTIN_BRICK in refs              # the starters' types still cover their patterns
    finally:
        s.remove("display/Wall/section_type")
        s.remove("display/Wall/section_look")
