"""HF5 Task 6 -- section cuts via Fill Types (R4/R7/R8)."""
import json
from collections import Counter

from PyQt6.QtCore import QPointF, QRectF, QSettings
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d import fill_types as ft
from firepro3d.constants import TOKEN_ELEMENT
from firepro3d.fill_layers import BackgroundLayer, FillLayers, PatternLayer, to_record


def test_legacy_cell_converts_to_look_identical_layers():
    lay = ft.legacy_section_layers("#666666", "diagonal", 2.0)
    assert lay.background == BackgroundLayer("#666666", 1.0)
    assert lay.pattern.color == TOKEN_ELEMENT and lay.pattern.scale == 2.0
    assert lay.pattern.ref == "builtin-hatch-diagonal"
    assert ft.legacy_section_layers("", None, None).background is None
    assert ft.legacy_section_layers("hatch:#ff0000", None, None).background is None


def test_category_named_type_project_wins_else_added():
    ft.set_project_table(ft.FillTypeTable([ft.FillType("w", "Wall Section",
                                            FillLayers(BackgroundLayer("#123456", 1.0)))]))
    assert ft.category_section_type("Wall", {"section_type": "Wall Section",
                                             "section_look": {"background": {"color": "#ffffff"}}}) == "w"
    fid = ft.category_section_type("Floor", {"section_type": "Floor Section",
                                             "section_look": {"background": {"color": "#00ff00"}}})
    assert ft.project_table().get(fid).layers.background.color == "#00ff00"


def test_legacy_category_converts_once():
    ft.set_project_table(ft.FillTypeTable())
    vals = {"section": "#666666", "section_pattern": "diagonal", "section_scale": 1.0}
    a = ft.category_section_type("Wall", vals)
    assert ft.category_section_type("Wall", vals) == a
    assert ft.project_table().get(a).name == "Wall Section"


def test_item_override_converts_and_distinct_looks_number():
    ft.set_project_table(ft.FillTypeTable())
    ft.category_section_type("Wall", {"section": "#666666", "section_pattern": "diagonal"})
    ov = {"section": "#ff0000", "section_pattern": "diagonal", "color": "#00ff00"}
    ft.convert_item_section_override("Wall", ov)
    assert set(ov) == {"color", "section_type"}
    assert ft.project_table().get(ov["section_type"]).name == "Wall Section 2"


def test_item_override_with_only_a_pattern_inherits_the_category_body():
    """Legacy per-key fallback: an override naming only a pattern kept the
    category's body colour and scale."""
    ft.set_project_table(ft.FillTypeTable())
    tid = ft.category_section_type("Wall", {"section": "#666666",
                                            "section_pattern": "diagonal",
                                            "section_scale": 2.0})
    ov = {"section_pattern": "horizontal"}
    ft.convert_item_section_override("Wall", ov, ft.resolve(tid, None)[0])
    lay = ft.project_table().get(ov["section_type"]).layers
    assert lay.background.color == "#666666"
    assert lay.pattern.ref == "builtin-hatch-horizontal" and lay.pattern.scale == 2.0


# -- the real path: wall + floor through the Display Manager apply -----------------

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
    tid = w._display_section_type
    assert ft.project_table().get(tid).name == "Wall Section"

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

    # 4. an item override naming a type that does not exist draws the fallback grey
    w._display_overrides["section_type"] = "no-such-type"
    _apply_wall_category(ms)
    px = _render(ms, w)
    assert _near(QColor(_body(px)), (230, 230, 230), 3)     # #808080 at 20 % on white
    assert not [c for c in px if _near(c, (0, 0, 255), 30)]


def test_wall_without_a_type_draws_the_default_look(qapp, model_space, shipped_hatches):
    """An item no Display Manager apply has touched (type None) keeps the
    pre-HF5 default: diagonal hatch in the line colour, no body."""
    ms = model_space
    shipped_hatches(ms)
    w = _wall(ms)
    w._display_color = "#aa0000"
    px = _render(ms, w)
    assert w._display_section_type is None
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
    t = ft.project_table().get(slab._display_section_type)
    assert t.name == "Floor Section"
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

def test_category_settings_store_type_name_and_look_and_retire_legacy_keys(qapp):
    from firepro3d import display_manager as dm
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Wall/section", "#aa0000")             # a pre-HF5 install
    s.setValue("display/Wall/section_pattern", "diagonal")
    s.setValue("display/Wall/section_scale", 2.0)
    vals = dm._read_category_from_settings("Wall")
    assert vals["section_type"] == "Wall Section"
    assert vals["section_look"]["background"]["color"] == "#aa0000"
    assert vals["section_look"]["pattern"]["color"] == TOKEN_ELEMENT
    assert vals["section_look"]["pattern"]["scale"] == 2.0
    assert "section" not in vals and "section_pattern" not in vals
    dm._write_category_to_settings("Wall", vals)
    for legacy in ("section", "section_pattern", "section_scale", "hatch"):
        assert not s.contains(f"display/Wall/{legacy}")
    assert s.value("display/Wall/section_type") == "Wall Section"
    assert json.loads(s.value("display/Wall/section_look")) == vals["section_look"]
    assert dm._read_category_from_settings("Wall")["section_look"] == vals["section_look"]
    # the project payload never carries the retired keys
    entry = dm.get_display_settings_for_save()["Wall"]
    assert not {"section", "section_pattern", "section_scale"} & set(entry)
    assert entry["section_type"] == "Wall Section"


def test_roof_has_no_section_cell_and_no_type():
    from firepro3d import display_manager as dm
    assert not dm._category_has_section("Roof")
    assert dm._category_has_section("Wall") and dm._category_has_section("Floor")
    vals = dm._read_category_from_settings("Roof")
    assert vals["section_type"] is None and vals["section_look"] is None


def test_project_payload_with_legacy_keys_wins_over_stored_type(qapp, model_space):
    """An old project's legacy section keys convert on apply, even when the
    app QSettings already holds a Fill Type for the category."""
    from firepro3d import display_manager as dm
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Wall/section_type", "Wall Section")
    s.setValue("display/Wall/section_look", json.dumps(
        to_record(FillLayers(BackgroundLayer("#111111", 1.0)))))
    w = _wall(model_space)
    dm.apply_project_display_settings(model_space, {"Wall": {
        "color": "#666666", "section": "#abcdef", "section_pattern": "diagonal"}})
    lay = ft.project_table().get(w._display_section_type).layers
    assert lay.background.color == "#abcdef"


def test_floor_slab_override_round_trips_and_wall_overrides_are_not_serialized(qapp, model_space):
    """Wall per-item overrides are not serialized (open bug, not fixed here); a
    floor slab's section_type override persists beside the project table."""
    from firepro3d.floor_slab import FloorSlab
    from firepro3d.wall import WallSegment
    w = _wall(model_space)
    w._display_overrides["section_type"] = "some-id"
    d = w.to_dict()
    assert "section_type" not in json.dumps(d) and "display_overrides" not in d
    assert WallSegment.from_dict(d)._display_overrides == {}
    slab = FloorSlab(points=[QPointF(0, 0), QPointF(100, 0), QPointF(100, 100)])
    slab._display_overrides["section_type"] = "some-id"
    assert FloorSlab.from_dict(slab.to_dict())._display_overrides["section_type"] == "some-id"


def test_cancel_removes_the_preview_written_type_keys(qapp, model_space):
    """A pre-HF5 install (legacy keys only): Cancel after a live preview leaves
    no section_type / section_look behind, so the legacy cell reads as before."""
    from firepro3d import display_manager as dm
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Wall/section", "#aa0000")
    dlg = dm.DisplayManager(model_space)
    try:
        dm._store_section_cell(s, "Wall", {"section_type": "Previewed",
                                           "section_look": {"background": {"color": "#00ff00"}}})
        assert s.value("display/Wall/section_type") == "Previewed"
        dlg.reject()
    finally:
        dlg.close()
    assert not s.contains("display/Wall/section_type")
    assert not s.contains("display/Wall/section_look")
