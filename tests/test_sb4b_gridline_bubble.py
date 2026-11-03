"""SB4b -- plan gridline bubble drawn by an annotation block (design
docs/superpowers/specs/2026-11-02-sb4b-gridline-bubble-design.md)."""
import math

import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition
from firepro3d.gridline import GridlineItem
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space


def _scene():
    ms = Model_Space()
    ms._level_manager = LevelManager()
    return ms


def _gridline(ms, p1=(0.0, 0.0), p2=(0.0, 5000.0), label="A"):
    gl = GridlineItem(QPointF(*p1), QPointF(*p2), label)
    ms.addItem(gl)
    ms._gridlines.append(gl)
    return gl


CIRCLE_R = 4.75          # authored mm (9.5 mm across, D14)


def _bubble_def(ms, shape="circle", name="TestBubble", fill=False):
    """An eligible Gridline bubble: Annotative, Scale with zoom, host Gridline;
    *shape* 'circle' = a 4.75 mm circle, 'square' = a 12 x 6 mm rectangle
    (non-circular trim, G6); @[Mark] 3 mm centred. *fill* adds an opaque black background
    layer to the shape (solid head for the paper render measurements). Mapped as the
    project default."""
    if shape == "circle":
        geom = {"type": "draw_circle", "cx": 0.0, "cy": 0.0, "radius": CIRCLE_R,
                "color": "token:auto", "lineweight": 1.0}
    else:
        geom = {"type": "draw_rectangle", "x": -6.0, "y": -3.0, "w": 12.0, "h": 6.0,
                "color": "token:auto", "lineweight": 1.0}
    if fill:
        geom["fill"] = {"background": {"color": "#000000", "opacity": 1.0}}   # fraction, fill_layers
    text = {"type": "text", "text": "@[Mark]", "x": -5.0, "y": -2.0, "height_mm": 3.0,
            "wrap_width_mm": 10.0, "box_height_mm": 4.0, "align": "C", "valign": "M"}
    d = BlockDefinition.new(name=name, library="", series="", origin=(0.0, 0.0),
                            primitives=[geom, text])
    d.scale_mode = "annotative"
    d.host_category = "Gridline"
    d.attributes = [normalise_attr({"key": "Mark", "source": "host", "host_key": "Mark",
                                    "placeholder": ""})]
    ms.register_block_definition(d)
    ms.annotation_defaults["Gridline"] = d.id
    return d


def test_gridline_is_an_annotation_category_with_a_system_default(qapp):
    from firepro3d import system_blocks as sb
    assert "Gridline" in sb.ANNOTATION_CATEGORIES
    assert sb.SYSTEM_DEFAULTS["Gridline"] == "system-tags-gridlinebubble"
    assert sb.LABEL_FIELD["Gridline"] == "Mark"
    assert sb.PAINT_WHEN_BLANK == frozenset({"Gridline"})


def test_d3_blank_mark_still_paints_the_static_geometry(qapp):
    """A blank label keeps the circle: the static ops draw, the bound text is empty."""
    from firepro3d.bound_label import BoundLabelItem
    ms = _scene()
    _bubble_def(ms)
    gl = _gridline(ms, label="")
    lab = BoundLabelItem(gl)
    ops = lab._ops(1.0)
    assert ops and all(op.kind != "text" or op.path.isEmpty() for op in ops)
    assert any(op.kind == "stroke" for op in ops)


def test_q13_blank_room_name_still_paints_nothing(qapp):
    """The Q13 rule is unchanged for every other category."""
    from firepro3d.bound_label import BoundLabelItem
    from firepro3d.room import Room
    from tests.test_sb3_paper import _tag_def
    ms = _scene()
    _tag_def(ms)
    r = Room(boundary=[QPointF(-1000, -1000), QPointF(1000, -1000),
                       QPointF(1000, 1000), QPointF(-1000, 1000)])
    r.name = ""
    r.level = "Level 1"
    ms.addItem(r)
    ms._rooms.append(r)
    assert r._tag._ops(1.0) == []


def test_shipped_gridlinebubble_is_eligible_and_binds_mark(qapp):
    import json, os
    import firepro3d
    from firepro3d import block_library
    from firepro3d.bound_label import eligible_definition
    path = os.path.join(os.path.dirname(firepro3d.__file__), "system_blocks", "Tags",
                        "GridlineBubble.fpdb")
    d = block_library.load_block_file(path)
    assert d.id == "system-tags-gridlinebubble" and eligible_definition(d, "Gridline")
    attrs = [a for a in d.effective_attributes() if a.get("source") == "host"]
    assert [a["host_key"] for a in attrs] == ["Mark"] and attrs[0]["placeholder"] == ""
    raw = json.load(open(path, encoding="utf-8"))
    kinds = sorted(p["type"] for p in raw["primitives"])
    assert kinds == ["draw_circle", "text"]
    circ = next(p for p in raw["primitives"] if p["type"] == "draw_circle")
    assert circ["radius"] == pytest.approx(4.75) and (circ["cx"], circ["cy"]) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# Task 4 -- GridlineBubble pose, outline, trim, overlays, hit
# ---------------------------------------------------------------------------

def _k(ms):
    return ms.scale_manager.drawing_scale        # scene units per authored mm on the plan


def test_g1_bubble_is_a_bound_label_child_sized_by_the_drawing_scale(qapp):
    from firepro3d.bound_label import BoundLabelItem
    ms = _scene()
    _bubble_def(ms)
    gl = _gridline(ms)
    for b in (gl.bubble1, gl.bubble2):
        assert isinstance(b, BoundLabelItem) and b.parentItem() is gl and b.category == "Gridline"
        assert not (b.flags() & b.GraphicsItemFlag.ItemIgnoresTransformations)
    widths = []
    for ds in (50.0, 200.0):
        ms.scale_manager.drawing_scale = ds
        ms.refresh_annotation_tags()
        w = gl.bubble1.boundingRect().width()
        assert w == pytest.approx(2 * CIRCLE_R * ds, abs=0.1 * ds + 2 * 2.0)   # PEN_MARGIN
        widths.append(w)
    assert widths[1] > widths[0] * 3.5


def test_g5_bubble_stays_upright_on_an_angled_gridline(qapp):
    ms = _scene()
    _bubble_def(ms)
    gl = _gridline(ms, (0.0, 0.0), (5000.0 * math.cos(math.radians(30)),
                                    -5000.0 * math.sin(math.radians(30))))
    assert gl.angle_deg() == pytest.approx(30.0)
    assert gl.bubble1.rotation() == 0.0 and gl.bubble2.rotation() == 0.0
    assert gl.bubble1._pose_rot == 0.0
    ux, uy = gl._direction()
    assert gl.bubble1.pos() == QPointF(-gl.bubble1_offset() * ux, -gl.bubble1_offset() * uy)


def test_g6_trim_meets_the_block_outline_circle_and_rectangle(qapp):
    ms = _scene()
    k = _k(ms)
    _bubble_def(ms, "circle")
    gl = _gridline(ms)                              # vertical: direction (0, 1)
    p1, p2 = gl.drawn_endpoints()
    assert p1.y() == pytest.approx(gl.bubble1.pos().y() + CIRCLE_R * k, abs=0.05 * k)
    assert p2.y() == pytest.approx(gl.bubble2.pos().y() - CIRCLE_R * k, abs=0.05 * k)
    _bubble_def(ms, "square")                       # 12 x 6 mm box: half-height 3 mm on the axis
    ms.refresh_annotation_tags()
    p1, _ = gl.drawn_endpoints()
    assert p1.y() == pytest.approx(gl.bubble1.pos().y() + 3.0 * k, abs=0.05 * k)
    gl.set_bubble_visible(1, False)
    p1, _ = gl.drawn_endpoints()
    assert p1 == gl.bubble1.pos()                   # hidden end: no trim


def test_g6_halo_trace_is_the_trimmed_line_plus_both_outlines(qapp):
    from firepro3d.halo import halo_scene_path
    ms = _scene()
    _bubble_def(ms)
    gl = _gridline(ms)
    p = gl.halo_trace_path()
    p1, p2 = gl.drawn_endpoints()
    r = p.boundingRect()
    o1 = gl.mapFromItem(gl.bubble1, gl.bubble1.outline_path()).boundingRect()
    assert r.contains(o1) and r.top() == pytest.approx(o1.top(), abs=1e-6)
    assert not halo_scene_path(gl).isEmpty()
    # the line subpath stops at the trimmed endpoint: no segment reaches the bubble centre
    polys = [poly for poly in p.toSubpathPolygons() if len(poly) == 2]
    assert polys and min(pt.y() for poly in polys for pt in poly) == pytest.approx(p1.y(), abs=1e-6)
    # a zero-area line path has no interior, so the span is checked on its subpath
    assert any(min(pt.y() for pt in poly) < (p1.y() + p2.y()) / 2 < max(pt.y() for pt in poly)
               for poly in polys)


def test_d3_blank_label_keeps_the_circle_and_the_trim(qapp):
    ms = _scene()
    k = _k(ms)
    _bubble_def(ms)
    gl = _gridline(ms, label="")
    assert gl.bubble1.paints()
    p1, _ = gl.drawn_endpoints()
    assert p1.y() == pytest.approx(gl.bubble1.pos().y() + CIRCLE_R * k, abs=0.05 * k)


def test_orphan_block_trims_at_the_placeholder_box(qapp):
    from firepro3d.bound_label import PLACEHOLDER_MM
    ms = _scene()
    gl = _gridline(ms, label="A")            # no block mapped, no System default loadable here
    ms.annotation_defaults["Gridline"] = "no-such-block"
    from firepro3d.system_blocks import SYSTEM_DEFAULTS
    saved = dict(SYSTEM_DEFAULTS); SYSTEM_DEFAULTS.clear()
    try:
        ms.refresh_annotation_tags()
        assert gl.bubble1._orphan_visible()
        p1, _ = gl.drawn_endpoints()
        assert p1.y() == pytest.approx(gl.bubble1.pos().y() + PLACEHOLDER_MM / 2, abs=3.0)
    finally:
        SYSTEM_DEFAULTS.update(saved)


def test_g8_selection_ring_and_duplicate_ring_flags_are_screen_only(qapp):
    ms = _scene()
    _bubble_def(ms)
    a = _gridline(ms, label="A")
    b = _gridline(ms, (1000.0, 0.0), (1000.0, 5000.0), label="A")
    from firepro3d.gridline import apply_duplicate_warnings
    apply_duplicate_warnings(ms._gridlines)
    assert a.bubble1._duplicate and b.bubble2._duplicate
    b.grid_label = "B"
    apply_duplicate_warnings(ms._gridlines)
    assert not a.bubble1._duplicate and not b.bubble1._duplicate
    a.setSelected(True)
    assert a.bubble1.overlay_pens() and len(a.bubble1.overlay_pens()) == 1
    a._paper_render = True
    assert a.bubble1.overlay_pens() == []            # never on paper
    a._paper_render = False
    apply_duplicate_warnings(ms._gridlines + [_gridline(ms, (2000.0, 0.0), (2000.0, 5000.0), label="A")])
    assert [p.color().name() for p in a.bubble1.overlay_pens()][-1] == "#ff8800"   # drawn last


def test_g9_per_end_visibility_grips_and_lock_carry_over(qapp):
    ms = _scene()
    _bubble_def(ms)
    gl = _gridline(ms)
    gl.set_bubble_visible(2, False)
    assert not gl.bubble2.isVisible() and gl.grip_hittable(3) is False
    assert len(gl.grip_points()) == 4 and gl.grip_points()[2] == gl.bubble1.pos()
    gl.setSelected(True)
    assert gl._lock_indicator.isVisible()
    # padlock sits past bubble 1's outline, screen-fixed 6 px gap: its path is offset
    # from the bubble centre by (outline half-extent along the perpendicular) in scene units
    gl._lock_indicator._rebuild()
    c = gl._lock_indicator.path().boundingRect().center()
    assert math.hypot(c.x(), c.y()) > 6.0 + 1.0           # past the outline (px), not at the centre


# ---------------------------------------------------------------------------
# Task 5 -- paper pass through _apply_block
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scale", [0.02, 0.005])          # 1:50, 1:200
def test_g2_pdf_bubble_mark_cap_height_is_the_authored_mm(qapp, tmp_path, scale):
    from tests.test_sb3_paper import _export, _text_height, TAG_MM
    from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
    save_paper_color_mode(PaperColorMode.BW)
    ms = _scene()
    _bubble_def(ms)
    gl = _gridline(ms, (0.0, 0.0), (0.0, 1.0e6), label="H")     # far end outside the crop
    gl.set_bubble_offset(1, 0.0)                                  # bubble 1 at the origin
    h = _text_height(_export(tmp_path, ms, scale, f"g{int(1 / scale)}.pdf"))
    assert abs(h - TAG_MM) < 0.3, h
    assert gl.bubble1._paper_scale is None and not gl._paper_render   # restored


def test_g3_duplicate_ring_never_plots_and_line_trims_at_paper_size(qapp, tmp_path):
    import fitz
    from tests.test_sb3_paper import _export
    from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
    from firepro3d.gridline import apply_duplicate_warnings
    save_paper_color_mode(PaperColorMode.FULL_COLOR)
    ms = _scene()
    _bubble_def(ms)
    a = _gridline(ms, (0.0, 0.0), (0.0, 1.0e6), label="A")
    b = _gridline(ms, (1.0e6, 0.0), (1.0e6, 1.0e6), label="A")
    a.set_bubble_offset(1, 0.0)
    apply_duplicate_warnings(ms._gridlines)
    assert a.bubble1._duplicate
    pdf = _export(tmp_path, ms, 0.02, "dup.pdf")
    doc = fitz.open(str(pdf))
    try:
        cols = {tuple(round(c, 2) for c in (d.get("color") or ())) for d in doc[0].get_drawings()}
    finally:
        doc.close()
    assert (1.0, 0.53, 0.0) not in cols                  # #ff8800 never plots


def test_g4_dm_grid_line_colour_tints_the_line_not_the_bubble(qapp):
    from firepro3d.display_manager import _apply_gridline, _category_has_fill, _category_has_scale
    ms = _scene()
    _bubble_def(ms)
    gl = _gridline(ms)
    before = [op.colour for op in gl.bubble1._ops(1.0)]
    _apply_gridline(gl, "#ff00ff", 1.0, 100, True, None)
    assert gl._grid_color.name() == "#ff00ff"
    assert [op.colour for op in gl.bubble1._ops(1.0)] == before
    assert gl.bubble1.scale() == 1.0 and not hasattr(gl, "_display_scale")
    assert not _category_has_fill("Grid Line") and not _category_has_scale("Grid Line")


def test_g4_saved_fill_and_scale_are_ignored_at_load(qapp):
    from firepro3d.display_manager import apply_display_to_item
    ms = _scene()
    _bubble_def(ms)
    gl = _gridline(ms)
    apply_display_to_item(gl, "#4488cc", 2.0, 100, True, fill_color="#123456")
    assert gl.bubble1.scale() == 1.0 and gl.bubble2.scale() == 1.0
