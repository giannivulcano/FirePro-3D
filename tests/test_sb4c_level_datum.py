"""SB4c half B -- the level datum head drawn by the "Level" annotation block
(design docs/superpowers/specs/2026-11-03-sb4c-elev-bubble-datum-design.md D3-D5)."""
import hashlib

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QTransform

from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition

HEAD_R = 5.0              # test circle radius, authored mm (= the seed, OQ1 option A)
# Non-circular, ORIGIN-ASYMMETRIC test block: a 12 x 6 mm rectangle spanning
# x -4 .. +8, so the ray toward the line's far end (+h) leaves it at 8 mm and the
# opposite ray at 4 mm -- a sign error in the trim direction reads 4, not 8.
SQ_X0, SQ_W, SQ_H = -4.0, 12.0, 6.0
SQ_TRIM = SQ_X0 + SQ_W    # 8.0: the +h exit
BG = 0xFF101010


def _level_def(ms, shape="circle", name="TestLevelHead"):
    """An eligible Level head: Annotative, Scale with zoom, host Level; *shape*
    'circle' = a HEAD_R circle, 'square' = the asymmetric 12 x 6 mm rectangle
    (non-circular trim, sign-pinning); @[Level.Name] above-right,
    @[Level.Elevation] below-right (the seed's layout). Mapped as the project
    default."""
    quadrant = None
    if shape in ("circle", "noisy_quadrant"):
        geom = {"type": "draw_circle", "cx": 0.0, "cy": 0.0, "radius": HEAD_R,
                "color": "token:auto", "lineweight": 1.0}
        if shape == "noisy_quadrant":
            # A Block-Editor-authored filled quadrant INSIDE the circle whose
            # corner carries 1e-16 float noise (a real restyle of the shipped
            # seed, 2026-11-03): Qt's clipper breaks on the un-snapped union
            # and reports every interior point as outside.
            quadrant = {"type": "draw_filled_region", "outline": False,
                        "fill": {"background": {"color": "token:auto", "opacity": 1.0}},
                        "loops": [[
                {"type": "arc", "cx": 0.0, "cy": 0.0, "radius": HEAD_R,
                 "start_deg": 0.0, "span_deg": 90.0},
                {"type": "draw_line", "pt1": [HEAD_R, 0.0], "pt2": [4.440892098500626e-16, 0.0]},
                {"type": "draw_line", "pt1": [0.0, -4.440892098500626e-16], "pt2": [0.0, -HEAD_R]},
            ], [
                {"type": "draw_line", "pt1": [0.0, -4.440892098500626e-16], "pt2": [0.0, HEAD_R + 1e-12]},
                {"type": "arc", "cx": 0.0, "cy": 0.0, "radius": HEAD_R,
                 "start_deg": 180.0, "span_deg": 90.0},
                {"type": "draw_line", "pt1": [-(HEAD_R + 1e-12), 0.0], "pt2": [4.440892098500626e-16, 0.0]},
            ]]}
    else:
        geom = {"type": "draw_rectangle", "x": SQ_X0, "y": -SQ_H / 2, "w": SQ_W,
                "h": SQ_H, "color": "token:auto", "lineweight": 1.0}
    name_t = {"type": "text", "text": "@[Level.Name]", "x": 6.25, "y": -5.5,
              "height_mm": 3.0, "wrap_width_mm": 30.0, "box_height_mm": 5.0,
              "align": "L", "valign": "B"}
    elev_t = {"type": "text", "text": "@[Level.Elevation]", "x": 6.25, "y": 0.5,
              "height_mm": 2.4, "wrap_width_mm": 30.0, "box_height_mm": 4.0,
              "align": "L", "valign": "T"}
    prims = [geom, name_t, elev_t] + ([quadrant] if quadrant else [])
    d = BlockDefinition.new(name=name, library="", series="", origin=(0.0, 0.0),
                            primitives=prims)
    d.scale_mode = "annotative"
    d.host_category = "Level"
    d.attributes = [
        normalise_attr({"key": "Level.Name", "source": "host", "host_key": "Level.Name",
                        "placeholder": "-"}),
        normalise_attr({"key": "Level.Elevation", "source": "host",
                        "host_key": "Level.Elevation", "placeholder": "-"}),
    ]
    ms.register_block_definition(d)
    ms.annotation_defaults["Level"] = d.id
    return d


def _datum_scene(section_scene_for, shape="circle", direction="north"):
    """(ms, sec, Level 1 datum, definition): a real SectionScene over a real
    Model_Space (LevelManager seeds Level 1 / 2 / 3 at 0 / 3048 / 6096 mm,
    level_manager.DEFAULT_LEVELS), the Level block mapped, rebuilt."""
    from firepro3d.section_scene import ElevDatumItem
    ms, sec = section_scene_for(direction)
    d = _level_def(ms, shape)
    sec.rebuild()
    (dt,) = [i for i in sec.items() if isinstance(i, ElevDatumItem) and abs(i._v) < 1e-6]
    return ms, sec, dt, d


def _render(scene, rect, w, h, bg=BG):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(bg)
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, w, h), rect, Qt.AspectRatioMode.IgnoreAspectRatio)
    p.end()
    return img


def _digest(img):
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    return hashlib.sha256(bytes(ptr)).hexdigest()


# -- T7: registries ----------------------------------------------------------------

def test_level_is_an_element_and_annotation_category(qapp):
    from firepro3d import element_params as ep
    from firepro3d import system_blocks as sb
    assert "Level" in ep.CATEGORIES                          # SB4d appends the three marker categories
    assert [(k, s.tier, s.kind, s.label) for k, s in ep.PARAMS["Level"].items()] == [
        ("Level.Name", 1, "text", "Name"), ("Level.Elevation", 1, "length", "Elevation")]
    assert sb.ANNOTATION_CATEGORIES[:4] == ("Room", "Pipe", "Gridline", "Level")   # SB4d appends three
    assert sb.LABEL_FIELD["Level"] == "Level.Name"
    assert sb.SYSTEM_DEFAULTS["Level"] == "system-tags-leveldatum"
    assert "Level" not in sb.PAINT_WHEN_BLANK


def test_category_of_an_elevation_datum_is_level_and_others_are_unchanged(qapp, section_scene_for):
    from firepro3d import element_params as ep
    from firepro3d.section_scene import ElevDatumItem
    _ms, sec = section_scene_for("north")
    sec.rebuild()
    dts = [i for i in sec.items() if isinstance(i, ElevDatumItem)]
    assert len(dts) == 3                                    # Level 1 / 2 / 3 (DEFAULT_LEVELS)
    assert {ep.category_of(d) for d in dts} == {"Level"}
    assert ep.category_of(object()) is None


# -- T8: shipped seed ---------------------------------------------------------------

def test_shipped_leveldatum_reproduces_todays_head(qapp):
    import json
    from firepro3d import block_library
    from firepro3d.assets import system_blocks_path
    from firepro3d.bound_label import eligible_definition
    from firepro3d.render_op import FILL, STROKE
    path = system_blocks_path("Tags", "LevelDatum.fpdb")
    d = block_library.load_block_file(path)
    assert d is not None and d.id == "system-tags-leveldatum"
    assert d.library == block_library.SYSTEM_LIBRARY and d.series == "Tags"
    assert eligible_definition(d, "Level")
    host = [a for a in d.effective_attributes() if a.get("source") == "host"]
    assert [a["host_key"] for a in host] == ["Level.Name", "Level.Elevation"]

    def box(op):
        r = op.path.boundingRect()
        return tuple(round(v, 3) for v in (r.x(), r.y(), r.width(), r.height()))
    ops = d.render_ops()
    # today's bespoke head: datum-colour quadrants (upper-right, lower-left),
    # circle + cross -- restyled in the Block Editor at the SB4c smoke gate
    # (2026-11-03): radius 3 mm (was OQ1's 5 mm), name cap 2.70 mm.
    assert sorted(box(o) for o in ops if o.kind == FILL) == [(-3.0, 0.0, 3.0, 3.0),
                                                              (0.0, -3.0, 3.0, 3.0)]
    assert sorted(box(o) for o in ops if o.kind == STROKE) == [
        (-3.0, -3.0, 6.0, 6.0), (-3.0, 0.0, 6.0, 0.0), (0.0, -3.0, 0.0, 6.0)]
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    texts = {p["text"]: p for p in raw["primitives"] if p["type"] == "text"}
    name, elev = texts["@[Level.Name]"], texts["@[Level.Elevation]"]
    assert (name["x"], name["valign"], name["align"], name["bold"]) == (6.25, "B", "L", True)
    assert name["y"] + name["box_height_mm"] == pytest.approx(-0.392, abs=1e-3)
    assert name["height_mm"] == pytest.approx(2.7016, abs=1e-4)
    assert (elev["x"], elev["valign"], elev["align"], elev["height_mm"], elev["bold"]) == (
        pytest.approx(6.25), "T", "L", 2.4, False)
    assert elev["y"] == pytest.approx(0.6286, abs=1e-4)


# -- T9: the head on the section canvas ----------------------------------------------

def test_ac3_each_datum_owns_one_level_head_at_its_left_end(qapp, section_scene_for):
    from firepro3d.bound_label import OutlinedLabel
    from firepro3d.gridline import BUBBLE_RADIUS_MM
    from firepro3d.section_scene import ElevDatumItem, LevelDatumHead
    ms, sec, dt, d = _datum_scene(section_scene_for)
    dts = [i for i in sec.items() if isinstance(i, ElevDatumItem)]
    assert len(dts) == 3
    for x in dts:
        heads = [c for c in x.childItems() if isinstance(c, LevelDatumHead)]
        assert heads == [x.head]
        assert isinstance(x.head, OutlinedLabel)
        assert x.head.host is x and x.head.category == "Level" and x.head.rotation() == 0.0
        assert x.head.definition() is d
        # origin on the line at today's circle centre: half a BUBBLE_RADIUS_MM left of h_min
        assert x._bx == pytest.approx(sec.basis.h_min - 0.5 * BUBBLE_RADIUS_MM)
        assert x.head.pos() == QPointF(x._bx, x._v)
        assert x._level in ms._level_manager.levels           # the real Level object (D3)


def test_ac3_head_paints_name_and_elevation_and_a_rename_repaints(qapp, section_scene_for):
    ms, sec, dt, _d = _datum_scene(section_scene_for)
    k = ms.scale_manager.drawing_scale                       # 100 (ScaleManager default)
    rect = QRectF(dt._bx - 6.0 * k, -12.0 * k, 40.0 * k, 24.0 * k)
    hv = dt.head.host_values({"Level.Name", "Level.Elevation"})
    assert hv["Level.Name"].text == "Level 1"
    assert hv["Level.Elevation"].text == ms.scale_manager.format_length(0.0)
    shown = _digest(_render(sec, rect, 400, 240))
    lm = ms._level_manager
    assert lm.rename_level("Level 1", "Roof", [])           # the real rename (mutates the Level)
    renamed = _digest(_render(sec, rect, 400, 240))
    assert renamed != shown                                  # pulled on paint, no rebuild
    assert lm.rename_level("Roof", "Level 1", [])
    assert _digest(_render(sec, rect, 400, 240)) == shown    # same name -> same ink
    dt._level.elevation = 1000.0                             # the Elevation field re-paints too
    assert _digest(_render(sec, rect, 400, 240)) != shown
    dt._level.elevation = 0.0
    assert _digest(_render(sec, rect, 400, 240)) == shown


def test_ac3_name_is_shown_as_typed(qapp, section_scene_for):
    ms, sec, dt, _d = _datum_scene(section_scene_for)
    k = ms.scale_manager.drawing_scale
    rect = QRectF(dt._bx - 6.0 * k, -12.0 * k, 40.0 * k, 24.0 * k)
    lm = ms._level_manager
    assert lm.rename_level("Level 1", "level one", [])
    lower = _digest(_render(sec, rect, 400, 240))
    assert lm.rename_level("level one", "LEVEL ONE", [])
    assert _digest(_render(sec, rect, 400, 240)) != lower    # an upper-cased paint would match


@pytest.mark.parametrize("shape,half", [("circle", HEAD_R), ("square", SQ_TRIM)])
def test_ac4_screen_datum_line_starts_at_the_head_outline(qapp, section_scene_for, shape, half):
    """The painted dash-dot line (drawForeground) starts where the ray from the
    head toward the line's far end (+h) leaves the block outline: 5 mm (circle)
    or 8 mm (the asymmetric rectangle; the opposite ray would read 4) x k."""
    ms, sec, dt, _d = _datum_scene(section_scene_for, shape)
    k = ms.scale_manager.drawing_scale                       # 100 -> 500 / 600 scene mm
    dt.head.setOpacity(0.0)          # still visible (the trim holds) but paints no ink
    rect = QRectF(dt._bx - 1000.0, -250.0, 2000.0, 500.0)   # 2 mm per px; v = 0 -> row 125
    img = _render(sec, rect, 1000, 250)
    xs = [x for x in range(1000) for y in (123, 124, 125, 126, 127) if img.pixel(x, y) != BG]
    assert xs, "no datum line painted"
    first_h = rect.left() + min(xs) * 2.0
    # tolerance: SquareCap half pen (8.128 / 2 mm) + 2 px antialias
    assert first_h == pytest.approx(dt._bx + half * k, abs=8.5)


def test_ac5_selection_ring_on_screen_never_with_the_paper_flag(qapp, section_scene_for):
    ms, sec, dt, _d = _datum_scene(section_scene_for)
    k = ms.scale_manager.drawing_scale
    # left of the line start (bx + 5k) and of the text: only the head symbol + ring
    rect = QRectF(dt._bx - 7.0 * k, -7.0 * k, 11.0 * k, 14.0 * k)
    off = _digest(_render(sec, rect, 220, 280))
    assert dt.head.overlay_pens() == []
    dt.setSelected(True)
    # the selection manipulator frames the selected datum: hide it so the
    # digests compare the head's own ink only (it is not under test here)
    sec._live_manip().setVisible(False)
    assert len(dt.head.overlay_pens()) == 1
    assert _digest(_render(sec, rect, 220, 280)) != off      # the ring inks on screen
    dt._paper_render = True
    try:
        assert dt.head.overlay_pens() == []
        assert _digest(_render(sec, rect, 220, 280)) == off  # never on paper
    finally:
        dt._paper_render = False


def test_head_scales_with_the_drawing_scale_and_the_datum_bounds_follow(qapp, section_scene_for):
    ms, sec, dt, _d = _datum_scene(section_scene_for)
    for ds in (50.0, 200.0):
        ms.scale_manager.drawing_scale = ds
        sec.refresh_annotation_tags()
        o = dt.head.outline_path().boundingRect()
        assert o.width() == pytest.approx(2 * HEAD_R * ds, abs=0.02 * ds)
        assert dt.line_start_h() == pytest.approx(dt._bx + HEAD_R * ds, abs=0.02 * ds)
        outline_in_parent = dt.head.mapToParent(dt.head.outline_path()).boundingRect()
        assert dt.boundingRect().contains(outline_in_parent)
        assert dt.shape().boundingRect().contains(outline_in_parent.center())   # hit shape = outline


def test_ac8_a_press_on_the_head_selects_the_datum_and_hover_resolves_to_it(qapp, section_scene_for):
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
    from firepro3d.elevation_view import SectionView
    ms, sec, dt, _d = _datum_scene(section_scene_for)
    k = ms.scale_manager.drawing_scale
    inside = QPointF(dt._bx - 0.5 * HEAD_R * k, -0.25 * HEAD_R * k)   # upper-left quadrant: off the cross and the line
    v = SectionView(sec)
    try:
        v.resize(900, 700)
        v.show()
        QTest.qWaitForWindowExposed(v)
        v.fitInView(QRectF(dt._bx - 3000.0, -3000.0, 6000.0, 6000.0),
                    Qt.AspectRatioMode.KeepAspectRatio)
        QApplication.processEvents()
        vp = v.mapFromScene(inside)
        QTest.mouseMove(v.viewport(), vp)
        QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, vp)
        assert dt.isSelected()
    finally:
        v.close()
    sec.clearSelection()
    sec.halo_update(inside, 15.0, QTransform())              # identity: 1 scene unit = 1 px
    assert sec.halo_item() is dt
    assert sec._manip_exclude(dt.head)


def test_ac8_left_grip_and_interior_move_carry_the_head(qapp, section_scene_for):
    from firepro3d.gridline import BUBBLE_RADIUS_MM
    ms, sec, dt, _d = _datum_scene(section_scene_for)
    x2 = dt.line().p2().x()
    dt.apply_grip(0, QPointF(dt.line().p1().x() - 700.0, 999.0))    # y ignored (V pinned)
    new_x = dt.line().p1().x()
    assert dt.line().p1().y() == 0.0 and dt.line().p2().x() == x2
    assert dt._bx == pytest.approx(new_x - 0.5 * BUBBLE_RADIUS_MM)
    assert dt.head.pos() == QPointF(dt._bx, 0.0)
    bx0 = dt._bx
    dt.manip_translate(40.0, 20.0)
    assert dt._bx == pytest.approx(bx0 + 40.0) and dt.head.pos() == QPointF(bx0 + 40.0, 0.0)
    assert [c for c in dt.childItems()] == [dt.head]          # moved, never rebuilt


def test_ac3_shipped_leveldatum_draws_the_head_through_the_system_tier(
        qapp, section_scene_for, real_system_library):
    from firepro3d.section_scene import ElevDatumItem
    ms, sec = section_scene_for("north")
    ms.annotation_block("Level")          # eager embed, as scene_io / template do (never inside paint)
    sec.rebuild()
    dt = next(i for i in sec.items() if isinstance(i, ElevDatumItem) and abs(i._v) < 1e-6)
    assert dt.head.definition().id == "system-tags-leveldatum"
    assert dt.head.paints()
    k = ms.scale_manager.drawing_scale
    assert dt.line_start_h() == pytest.approx(dt._bx + 3.0 * k, abs=0.02 * k)   # seed r = 3 mm


# -- T10: paper ------------------------------------------------------------------------

def _circles_at(pdf, cx, cy, tol=0.5):
    """Diameters (mm) of the stroked near-square drawings centred on paper
    (cx, cy), bounded below the 80 mm viewport frame."""
    from tests._section_paper_helpers import drawings
    out = []
    for d in drawings(pdf):
        x0, y0, x1, y1 = d["rect"]
        if ("s" in d["type"] and abs((x0 + x1) / 2 - cx) < tol and abs((y0 + y1) / 2 - cy) < tol
                and abs((x1 - x0) - (y1 - y0)) < 0.2 and 1.0 < x1 - x0 < 40.0):
            out.append(x1 - x0)
    return out


@pytest.mark.parametrize("scale", [0.02, 0.005])     # 1:50, 1:200; canvas k = 100 would print 20 / 5 mm
def test_ac7_datum_head_prints_at_its_authored_mm(qapp, tmp_path, section_scene_for, scale):
    from tests.paper_mode_shim import set_paper_mode
    from tests._section_paper_helpers import export_scene, to_paper
    set_paper_mode("bw")
    ms, sec, dt, _d = _datum_scene(section_scene_for)
    centre = QPointF(dt._bx, 0.0)
    pdf = export_scene(tmp_path, sec, scale, centre, f"head_{int(1 / scale)}.pdf")
    dias = _circles_at(pdf, *to_paper(centre, centre, scale))
    assert dias, "no head circle on paper"
    assert max(dias) == pytest.approx(2 * HEAD_R, abs=0.1)
    # restored after the pass
    assert dt.head._paper_scale is None and dt.head._paper_pen_width is None
    assert not dt._paper_render and dt._paper_line_w_mm == 0.0 and dt.head.opacity() == 1.0


@pytest.mark.parametrize("scale", [0.02, 0.005])
def test_ac7_elevation_bubble_prints_at_the_plan_blocks_authored_mm(
        qapp, tmp_path, section_scene_for, scale):
    from firepro3d.gridline import GridlineItem
    from tests.paper_mode_shim import set_paper_mode
    from firepro3d.section_scene import ElevGridlineItem
    from tests._section_paper_helpers import export_scene, to_paper
    from tests.test_sb4b_gridline_bubble import CIRCLE_R, _bubble_def
    set_paper_mode("bw")
    ms, sec = section_scene_for("north")
    _bubble_def(ms)                                           # 4.75 mm circle, the plan Gridline default
    gl = GridlineItem(QPointF(2500.0, -3000.0), QPointF(2500.0, 3000.0), label="1")
    ms._gridlines.append(gl)
    ms.addItem(gl)
    sec._gridline_z_overrides["1"] = {"v_top": -1500.0, "v_bot": 500.0}
    sec.rebuild()
    (eg,) = [i for i in sec.items() if isinstance(i, ElevGridlineItem)]
    top = eg.bubble1                                          # plan Bubble 1 -> elevation top (D2)
    assert top.isVisible()
    centre = top.scenePos()
    pdf = export_scene(tmp_path, sec, scale, centre, f"elev_bubble_{int(1 / scale)}.pdf")
    dias = _circles_at(pdf, *to_paper(centre, centre, scale))
    assert dias, "no elevation bubble on paper"
    assert max(dias) == pytest.approx(2 * CIRCLE_R, abs=0.1)
    assert top._paper_scale is None and not eg._paper_render


def test_ac4_paper_datum_line_starts_at_the_printed_outline(qapp, tmp_path, section_scene_for):
    """1:50: the printed trim is SQ_TRIM = 8 mm (paper k = 1 / S = 50) on the
    ray toward the line's far end; the canvas k (100) would leave 16 mm, the
    reversed ray 4 mm."""
    from tests.paper_mode_shim import set_paper_mode
    from tests._section_paper_helpers import drawings, export_scene, to_paper
    set_paper_mode("bw")
    ms, sec, dt, _d = _datum_scene(section_scene_for, "square")
    scale = 0.02
    centre = QPointF(dt._bx, 0.0)
    pdf = export_scene(tmp_path, sec, scale, centre, "trim.pdf")
    cx, y = to_paper(centre, centre, scale)
    hits = [d for d in drawings(pdf)
            if abs(d["rect"][1] - y) < 0.3 and abs(d["rect"][3] - y) < 0.3
            and d["rect"][2] - d["rect"][0] > 10.0]
    assert hits, "no datum line"
    assert min(d["rect"][0] for d in hits) == pytest.approx(cx + SQ_TRIM, abs=0.3)


def test_ac5_datum_selection_ring_never_plots(qapp, tmp_path, section_scene_for):
    from tests.paper_mode_shim import set_paper_mode
    from tests._section_paper_helpers import drawings, export_scene
    set_paper_mode("full_color")
    ms, sec, dt, _d = _datum_scene(section_scene_for)
    dt.setSelected(True)
    ring = dt.line_color().lighter(150)
    want = tuple(round(c, 2) for c in (ring.redF(), ring.greenF(), ring.blueF()))
    pdf = export_scene(tmp_path, sec, 0.01, QPointF(dt._bx, 0.0), "ring.pdf")
    cols = {tuple(round(c, 2) for c in (d["color"] or ())) for d in drawings(pdf)}
    assert dt.isSelected()                                    # still selected: the pass hid nothing
    assert want not in cols


# -- T11: Display Manager ----------------------------------------------------------------

def test_ac6_dm_level_datum_row_is_line_only_and_stale_values_are_ignored(qapp, section_scene_for):
    from PyQt6.QtCore import QSettings
    from firepro3d.display_manager import (_CATEGORY_MAP, _category_has_fill,
                                           _category_has_font, _category_has_scale)
    from firepro3d.paper_display import factory_paper_categories
    from firepro3d.section_scene import ElevDatumItem
    row = _CATEGORY_MAP["Level Datum"]
    assert row["fill"] is None and row["font"] is None
    assert not _category_has_fill("Level Datum")
    assert not _category_has_font("Level Datum")
    assert not _category_has_scale("Level Datum")
    assert factory_paper_categories()["Level Datum"]["fill"] is None
    assert factory_paper_categories()["Grid Line"]["fill"] is None
    ms, sec, dt, _d = _datum_scene(section_scene_for)
    assert set(sec._datum_display_props()) == {"color", "opacity", "visible"}
    assert set(sec._gridline_display_props()) == {"color", "opacity", "visible"}
    k = ms.scale_manager.drawing_scale
    rect = QRectF(dt._bx - 6.0 * k, -12.0 * k, 40.0 * k, 24.0 * k)
    before = (_digest(_render(sec, rect, 400, 240)), dt._pen_w, dt.line_start_h())
    s = QSettings("GV", "FirePro3D")                          # conftest-isolated
    stale = {"display/Level Datum/scale": 3.0, "display/Level Datum/font": 30,
             "display/Level Datum/fill": "#ff0000", "display/Grid Line/scale": 3.0,
             "display/Grid Line/fill": "#00ff00"}
    try:
        for key, val in stale.items():
            s.setValue(key, val)
        sec.rebuild()
        dt2 = next(i for i in sec.items() if isinstance(i, ElevDatumItem) and abs(i._v) < 1e-6)
        after = (_digest(_render(sec, rect, 400, 240)), dt2._pen_w, dt2.line_start_h())
    finally:
        for key in stale:
            s.remove(key)
    assert after == before


def test_ac6_level_datum_colour_tints_the_line_not_the_head(qapp, section_scene_for):
    from PyQt6.QtCore import QSettings
    from firepro3d.section_scene import ElevDatumItem
    ms, sec, dt, _d = _datum_scene(section_scene_for)
    head_ops = [op.colour for op in dt.head._ops(dt.head._k())]
    s = QSettings("GV", "FirePro3D")
    try:
        s.setValue("display/Level Datum/color", "#ff00ff")
        sec.rebuild()
        dt2 = next(i for i in sec.items() if isinstance(i, ElevDatumItem) and abs(i._v) < 1e-6)
        assert dt2.line_color().name() == "#ff00ff"
        assert [op.colour for op in dt2.head._ops(dt2.head._k())] == head_ops
    finally:
        s.remove("display/Level Datum/color")


# -- Phase 6 smoke fix: a restyled head's noisy quadrant + the HALO trace ---------------

def test_outline_survives_a_noisy_nested_quadrant_so_the_line_trims(qapp, section_scene_for):
    """Smoke 2026-11-03: a Block-Editor restyle of the shipped seed put 1e-16
    noise on the filled quadrants' corners (the lower-left one's
    radius lines overshoot by 1e-12); Qt's clipper then returned a union
    that contains NO interior point, so the trim read 0 (line from the origin)
    and the head's hit shape was dead. Operands are snapped before the union
    (the wall-outline lesson) -- the outline stays the circle."""
    ms, sec, dt, _d = _datum_scene(section_scene_for, shape="noisy_quadrant")
    k = ms.scale_manager.drawing_scale
    outline = dt.head.outline_path()
    assert outline.contains(QPointF(0.0, 0.0))
    assert outline.contains(QPointF(0.5 * HEAD_R * k, 0.0))      # on the quadrant seam
    assert dt.head.trim_distance(1.0, 0.0) == pytest.approx(HEAD_R * k, abs=0.02 * k)
    assert dt.line_start_h() == pytest.approx(dt._bx + HEAD_R * k, abs=0.02 * k)
    assert dt.shape().contains(QPointF(dt._bx + 0.5 * HEAD_R * k, dt._v))


def test_halo_trace_is_the_trimmed_line_plus_the_head_outline(qapp, section_scene_for):
    """Smoke 2026-11-03: the HALO glow traced the raw ``line()`` (from h_min,
    inside the head, through the text); it now mirrors ``drawForeground`` --
    the line from the outline to h_max -- plus the head outline (plan
    ``GridlineItem`` / ``ElevGridlineItem`` parity)."""
    from firepro3d import halo
    ms, sec, dt, _d = _datum_scene(section_scene_for, shape="square")
    k = ms.scale_manager.drawing_scale
    trace = halo._halo_local(dt)
    assert not halo.halo_is_area(dt)
    p0 = trace.elementAt(0)
    assert (p0.x, p0.y) == pytest.approx((dt._bx + SQ_TRIM * k, dt._v), abs=0.02 * k)
    p1 = trace.elementAt(1)
    assert (p1.x, p1.y) == pytest.approx((dt._h_max, dt._v))
    outline = dt.head.mapToParent(dt.head.outline_path()).boundingRect()
    assert trace.boundingRect().united(outline) == trace.boundingRect()   # outline is in the trace
    assert trace.boundingRect().left() == pytest.approx(outline.left())
