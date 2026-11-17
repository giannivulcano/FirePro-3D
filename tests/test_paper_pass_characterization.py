"""Paper pass protocol, Task 1 (the Gate): characterization guards written at
base, before any item class moves onto the protocol.

* AC2   round trip: every attribute the pass touches, for every item kind and
        its owned children, is equal before ``apply_paper_overrides`` and after
        ``restore_model_display`` (row As Authored on and off).
* AC3   pixel parity of one sheet holding every kind (golden in
        ``tests/data/paper_pass_parity.json``; ``--regen-paper-pass-golden``
        rewrites it) and the same sheet through ``paper_export``.
* AC4 / AC5 / AC6 / AC8  RED-at-base guards (``xfail(strict=True)``), each
        flipped by the task its reason names.

The golden hashes are host-specific (fonts, antialiasing): regenerate them on
the machine that runs the suite (``--regen-paper-pass-golden``).

Everything drives the real pass (``pd.apply_paper_overrides`` /
``pd.restore_model_display`` or a real sheet render) on real domain objects,
under the isolated paper settings of ``tests/test_selection_never_plots.py``.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QBrush, QColor, QImage, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsItem

import firepro3d.paper_display as pd
from tests.test_selection_never_plots import (_CROP, _KINDS, _digest,   # noqa: F401
                                              _paper, paper_env)

_GOLDEN = Path(__file__).parent / "data" / "paper_pass_parity.json"
SCALE = 0.02                    # paper mm per model mm (1:50)
_MISSING = "<missing>"
_ROW_RED, _ROW_GREEN, _ROW_BLUE = "#d01010", "#10a030", "#1030d0"


# ---------------------------------------------------------------------------
# paper rows
# ---------------------------------------------------------------------------

def set_rows(env, as_authored: bool, *, coloured: bool = True) -> None:
    """Every toggled row As Authored on / off; off rows carry distinct row
    colours so a missed restore (or a missed enter) shows."""
    for key, row in env.cats.items():
        if key not in pd._LW_ONLY:
            row["as_authored"] = as_authored
        if coloured:
            row["color"] = _ROW_RED
            if row.get("fill") is not None:
                row["fill"] = _ROW_GREEN
            if row.get("section_color") is not None:
                row["section_color"] = _ROW_BLUE


# ---------------------------------------------------------------------------
# extra kind builders (the kinds _KINDS lacks)
# ---------------------------------------------------------------------------

def _pipe_labelled(s):
    """A pipe whose label is a real top-level block in the scene (SB4a D10)."""
    from tests.test_selection_never_plots import _pipe
    p = _pipe(s)
    p.update_label()
    assert p.label.scene() is s and p.label.isVisible()
    return p


def _room_tagged(s):
    from tests.test_selection_never_plots import _room
    r = _room(s)
    r.set_property("Room Name", "R1")
    r._update_label()
    assert r._tag.scene() is s and r._tag.isVisible()
    return r


def _gridline(s):
    from firepro3d.gridline import GridlineItem
    gl = GridlineItem(QPointF(-800, 0), QPointF(800, 0), label="1")
    s._gridlines.append(gl)
    s.addItem(gl)
    return gl


def _sprinkler(s):
    from firepro3d.node import Node
    n = s.add_node(0.0, 0.0) if hasattr(s, "add_node") else Node(0.0, 0.0)
    n.add_sprinkler()
    return n.sprinkler


def _fitting_node(s):
    """A node (in ``sprinkler_system.nodes``) whose fitting draws a symbol."""
    n = s.add_node(0.0, 0.0)
    n.fitting.update()
    assert n.fitting.symbol is not None and n.fitting.symbol.isVisible()
    return n


def _marker_cardinal(s):
    from firepro3d.section_marker import SectionMarker
    m = SectionMarker.for_cardinal("north", QRectF(-600, -600, 1200, 1200))
    s.addItem(m)
    return m


def _marker_placed(s):
    from firepro3d.section_marker import SectionMarker
    m = SectionMarker("Section 1", QPointF(-800.0, 0.0), QPointF(800.0, 0.0),
                      1, 600.0)
    s.addItem(m)
    return m


def _block_def(s):
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.geometry_2d import LineItem
    d = BlockDefinition.new(
        name="PP", library="L", series="S", origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(-400, 0), QPointF(400, 0)).to_dict(),
                    LineItem(QPointF(0, -400), QPointF(0, 400)).to_dict()])
    s.register_block_definition(d)
    return d


def _block_instance(s):
    return s.place_block_instance(_block_def(s).id, (0.0, 0.0))


def _placed_tag(s):
    """An SB6 placed tag: a BlockInstance + tag record hosted on a wall."""
    from tests._sb6_helpers import add_wall, place_tag
    return place_tag(s, add_wall(s))


def _text_printed(s):
    from firepro3d.text_item import TextAnnotationData, TextItem
    s.text_print_scale = 20.0          # a Printed schematic (N15)
    t = TextItem(TextAnnotationData(text="H", height_mm=60.0, x=-200.0, y=-300.0))
    s.addItem(t)
    return t


def _line_named_weight(s):
    from firepro3d.geometry_2d import LineItem
    it = LineItem(QPointF(-800, 0), QPointF(800, 0))
    it.style["weight"] = "Wide"            # a named authored weight (LT2-5)
    s.addItem(it)
    return it


def _underlay_layer_weight(s):
    from firepro3d.underlay import Underlay
    rec = Underlay(type="dxf", path="x.dxf")
    rec.layer_overrides["A"] = {"line_weight": "Thick"}
    geoms = [{"kind": "line", "x1": -800, "y1": 0, "x2": 800, "y2": 0, "layer": "A"},
             {"kind": "line", "x1": 0, "y1": -800, "x2": 0, "y2": 800, "layer": "A"}]
    group, _layers = s._build_batched_underlay_group(geoms, rec)
    group.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                   | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
    s.underlays.append((rec, group))        # as every real caller does after the build
    return group


def _pick_excluded(s):
    it = _KINDS["line"](s)
    it.PAPER_EXCLUDED = True            # instance-level exclusion (the block ghost)
    return it


def _pick_origin(s):
    it = _KINDS["line"](s)
    it.setData(0, "origin")             # the model origin cross
    return it


def _pick_scaffold(s):
    it = _KINDS["line"](s)
    it.reference = True                 # a non-printed reference item (RG11)
    it.printed = False
    return it


def _pick_detail(s):
    return _KINDS["detail_marker"](s)


# Kinds that exercise the driver's pick-rule hides (visibility tokens); not on
# the AC3 sheet (they plot nothing).
_PICK = {"pick_excluded": _pick_excluded, "pick_origin": _pick_origin,
         "pick_scaffold": _pick_scaffold, "pick_detail_hidden": _pick_detail,
         "pick_detail_self": _pick_detail}
_VIEWPORT = {   # the SheetViewData fields the pass reads
    "pick_detail_hidden": SimpleNamespace(source_view_type="plan", source_view_name="V",
                                          hidden_detail_ids={"D1"}),
    "pick_detail_self": SimpleNamespace(source_view_type="detail", source_view_name="D1",
                                        hidden_detail_ids=set()),
}


_EXTRA = {
    "pipe_labelled": _pipe_labelled, "room_tagged": _room_tagged,
    "gridline": _gridline, "sprinkler": _sprinkler, "fitting_node": _fitting_node,
    "marker_cardinal": _marker_cardinal, "marker_placed": _marker_placed,
    "block_instance": _block_instance, "placed_tag": _placed_tag,
    "text_printed": _text_printed, "line_named_weight": _line_named_weight,
    "underlay_layer_weight": _underlay_layer_weight,
}


# Section / elevation kinds live in a SectionScene (proxies, elevation items).
def _sec_walls(sec_for):
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import WallOpening
    ms, sec = sec_for("north")
    w = WallSegment(QPointF(-3000.0, 0.0), QPointF(3000.0, 0.0))
    ms._walls.append(w)
    ms.addItem(w)
    op = WallOpening(w, offset_along=3000.0, width_mm=1200.0, height_mm=2100.0,
                     sill_mm=0.0, feature_id="door_914")
    w.openings.append(op)
    sec.rebuild()
    return sec, QRectF(-3000.0, -3000.0, 6000.0, 6000.0)


def _sec_pipe_label(sec_for):
    """A section over a model holding the shipped PipeLabel block and a line
    pipe: the line proxy carries a ``pipe_label``."""
    import os

    import firepro3d
    from firepro3d import block_library
    from tests.test_section_classification import _placed_scene
    from tests.test_section_pipe_symbols import _pipe
    ms, sec = _placed_scene(sec_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    ms.register_block_definition(block_library.load_block_file(os.path.join(
        os.path.dirname(firepro3d.__file__), "system_blocks", "Tags", "PipeLabel.fpdb")))
    _pipe(ms, (2000.0, -1000.0, 2500.0), (6000.0, -1000.0, 2500.0))
    sec.rebuild()
    return sec, QRectF(-1000.0, -6000.0, 12000.0, 12000.0)


def _sec_elevation(sec_for):
    """An elevation with a gridline (bubbles) and a level datum (head)."""
    from firepro3d.gridline import GridlineItem
    ms, sec = sec_for("north")
    gl = GridlineItem(QPointF(2500.0, -3000.0), QPointF(2500.0, 3000.0), label="1")
    ms._gridlines.append(gl)
    ms.addItem(gl)
    sec._gridline_z_overrides[gl._uid] = {"v_top": -1500.0, "v_bot": 500.0}
    sec.rebuild()
    return sec, QRectF(-7000.0, -4000.0, 10500.0, 5000.0)      # gridline bubbles + datum heads


_SECTION = {"sec_walls": _sec_walls, "sec_pipe_label": _sec_pipe_label,
            "sec_elevation": _sec_elevation}

ALL_KINDS = [*_KINDS, *_EXTRA, *_SECTION]
AC2_KINDS = [*ALL_KINDS, *_PICK]


def build(kind, request):
    """``(scene, crop)`` holding *kind*; the scene is kept alive by the
    caller (the fixtures own the section scenes)."""
    if kind in _SECTION:
        return _SECTION[kind](request.getfixturevalue("section_scene_for"))
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    request.node._pp_keep = [*getattr(request.node, "_pp_keep", []), ms]
    maker = _KINDS.get(kind) or _EXTRA.get(kind) or _PICK[kind]
    maker(ms)
    if kind == "underlay_group":            # the _KINDS builder leaves the group unregistered
        from firepro3d.underlay import Underlay
        (grp,) = [i for i in ms.items() if type(i).__name__ == "_UnderlayGroup"]
        ms.underlays.append((Underlay(type="dxf", path="x.dxf"), grp))
    return ms, QRectF(_CROP)


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------

_ATTRS = ("_display_color", "_display_fill_color", "_display_section_color",
          "_paper_pen_width", "_paper_scale", "_paper_pen_color",
          "_paper_blocks_colour", "_paper_fill_colour", "_paper_fill_opaque",
          "_paper_no_fill", "_paper_gap_color", "_grid_color", "_paper_render",
          "_paper_line_w", "_paper_line_w_mm", "_marker_color", "_tag_color",
          "_pen_src", "_brush_src", "_section_src", "_src_alpha", "_colour_src",
          "_paper_cat", "_grid_src", "_color_src", "_print_pass")
# Absent-vs-set matters for these (generic restore deletes them).  Not for
# ``_paper_pen_width``: base restore puts ``None`` back on a Pipe / Sprinkler
# where it was absent, and both read as "no paper width" (getattr default).
_PRESENT = ("_paper_fill_opaque", "_paper_no_fill", "_paper_gap_color")
_ABSENT_IS_NONE = ("_paper_pen_width",)


def _norm(v):
    if isinstance(v, QColor):
        return v.name(QColor.NameFormat.HexArgb)
    if isinstance(v, QPen):
        return ("pen", _norm(v.color()), round(v.widthF(), 9), v.isCosmetic(),
                int(v.style().value), int(v.joinStyle().value), int(v.capStyle().value))
    if isinstance(v, QBrush):
        return ("brush", int(v.style().value), _norm(v.color()))
    if isinstance(v, QPointF):
        return (round(v.x(), 6), round(v.y(), 6))
    if isinstance(v, QRectF):
        return tuple(round(x, 6) for x in (v.x(), v.y(), v.width(), v.height()))
    if isinstance(v, (list, tuple)):
        return tuple(_norm(x) for x in v)
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return repr(type(v).__name__)


def _svg_identity(item):
    """Small render digest of an SVG symbol's renderer (what ``_set_svg_tint``
    writes: shared renderer + graphics effect) so a missed re-tint shows."""
    r = getattr(item, "renderer", None)
    if not callable(r) or r() is None:
        return None
    img = QImage(24, 24, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    r().render(p)
    p.end()
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    import hashlib
    return (hashlib.sha1(bytes(ptr)).hexdigest(), item.graphicsEffect() is None)


def _item_state(item) -> dict:
    st = {"opacity": item.opacity(), "visible": item.isVisible(),
          "pos": _norm(item.pos()), "svg": _svg_identity(item)}
    for a in _ATTRS:
        st[a] = _norm(getattr(item, a, None if a in _ABSENT_IS_NONE else _MISSING))
    for a in _PRESENT:
        st[a + "?"] = a in vars(item)
    if callable(getattr(item, "pen", None)):
        st["pen"] = _norm(item.pen())
    if callable(getattr(item, "brush", None)):
        st["brush"] = _norm(item.brush())
    li = getattr(item, "_lock_indicator", None)
    if li is not None:
        st["lock_visible"] = li.isVisible()
    st["rect"] = _norm(item.boundingRect())
    return st


def snapshot(scene) -> dict:
    """Every attribute the pass touches, on every item in the scene (owned
    children, top-level labels and tags, fitting symbols and the underlay
    children included) and on the Fitting wrappers."""
    items = scene.items()
    for it in items:            # warm lazy caches so before / after compare equal
        it.boundingRect()
    snap = {("item", i): _item_state(it) for i, it in enumerate(items)}
    sys_ = getattr(scene, "sprinkler_system", None)
    for i, n in enumerate(list(getattr(sys_, "nodes", ()))):
        f = n.fitting
        snap[("fitting", i)] = {a: _norm(getattr(f, a, _MISSING))
                                for a in ("_display_color", "_display_fill_color")}
    snap["hatch_scale"] = getattr(scene, "_hatch_paper_scale", _MISSING)
    snap["thin_suspend"] = pd._THIN_SUSPEND
    return snap


# ---------------------------------------------------------------------------
# AC2: round trip
# ---------------------------------------------------------------------------

def primary_item(kind, scene):
    """The item the kind is about (not a Node, wall or pipe it happens to need)."""
    def first(*names, cat=None):
        for it in scene.items():
            if type(it).__name__ in names and (
                    cat is None or getattr(it, "_paper_cat", None) == cat):
                return it
        raise AssertionError(f"{kind}: no {names} in the scene")

    def top_group():
        return scene.underlays[-1][1]

    def layer_child():
        return next(c for c in top_group().childItems() if c.data(1) is not None)

    by_kind = {
        "wall": lambda: first("WallSegment"), "pipe": lambda: first("Pipe"),
        "node": lambda: first("Node"), "roof": lambda: first("RoofItem"),
        "room": lambda: first("Room"), "floor_slab": lambda: first("FloorSlab"),
        "wall_opening": lambda: first("WallOpening"),
        "detail_marker": lambda: first("DetailMarker"),
        "hydraulic_badge": lambda: first("HydraulicNodeBadge"),
        "filled_region": lambda: first("FilledRegionItem"),
        "water_supply": lambda: first("WaterSupply"),
        "underlay_pixmap": top_group, "underlay_placeholder": top_group,
        # a vector underlay's pass writes its layer path children (pen / brush)
        "underlay_group": layer_child, "underlay_layer_weight": layer_child,
        "line": lambda: first("LineItem"), "rectangle": lambda: first("RectangleItem"),
        "circle": lambda: first("CircleItem"), "arc": lambda: first("ArcItem"),
        "polygon": lambda: first("RegularPolygonItem"),
        "ellipse": lambda: first("EllipseItem"), "spline": lambda: first("SplineItem"),
        "pipe_labelled": lambda: first("Pipe").label,
        "room_tagged": lambda: first("Room")._tag,
        "gridline": lambda: first("GridlineItem"),
        "sprinkler": lambda: first("Sprinkler"),
        "fitting_node": lambda: first("Node").fitting.symbol,
        "marker_cardinal": lambda: first("SectionMarker"),
        "marker_placed": lambda: first("SectionMarker"),
        "block_instance": lambda: first("BlockInstance"),
        "placed_tag": lambda: first("BlockInstance"),
        "text_printed": lambda: first("TextItem"),
        "line_named_weight": lambda: first("LineItem"),
        "sec_walls": lambda: first("_ElevProxyRect", cat="Wall"),
        "sec_pipe_label": lambda: first("_ElevProxyLine"),
        "sec_elevation": lambda: first("ElevGridlineItem"),
        "pick_excluded": lambda: first("LineItem"),
        "pick_origin": lambda: first("LineItem"),
        "pick_scaffold": lambda: first("LineItem"),
        "pick_detail_hidden": lambda: first("DetailMarker"),
        "pick_detail_self": lambda: first("DetailMarker"),
    }
    return by_kind[kind]()


# (kind, mode) pairs where the base pass genuinely leaves the kind's own item
# unchanged (filled in from the first run; each is explained here).
_PRIMARY_UNCHANGED = {
    # an underlay's pass writes its group (visibility / opacity) and its path
    # children; a raster pixmap or the placeholder box has neither to change
    # unless the row hides it
    ("underlay_pixmap", "authored"), ("underlay_pixmap", "row_off"),
    ("underlay_placeholder", "authored"), ("underlay_placeholder", "row_off"),
    # the fitting symbol is only re-tinted when a model-side token or the row
    # colour reaches it; an As Authored row with a hex colour leaves it alone
    ("fitting_node", "authored"),
    # a layer with no override keeps its own colour and weight on an As
    # Authored row: the path child's pen is rewritten with equal values
    ("underlay_group", "authored"),
}


def set_ac2_mode(env, mode: str) -> None:
    """authored: rows on; row_off: rows off with row colours; hidden: every row
    ``visible=False`` (the visibility-token path)."""
    set_rows(env, mode != "row_off")
    if mode == "hidden":
        for row in env.cats.values():
            row["visible"] = False


def _changed_by_pass(before, during):
    """Item-level keys (never the scene-level hatch / thin-lines keys, which
    always differ) whose state the pass changed."""
    return [k for k in before if isinstance(k, tuple) and before[k] != during.get(k)]


@pytest.mark.parametrize("mode", ["authored", "row_off", "hidden"])
@pytest.mark.parametrize("kind", AC2_KINDS)
def test_ac2_round_trip(qapp, request, paper_env, real_system_library, kind, mode):
    set_ac2_mode(paper_env, mode)
    scene, crop = build(kind, request)
    vd = _VIEWPORT.get(kind)
    before = snapshot(scene)
    saved = pd.apply_paper_overrides(scene, crop, paper_scale=SCALE, viewport_data=vd)
    during = snapshot(scene)
    pd.restore_model_display(saved)
    after = snapshot(scene)
    if before.keys() != after.keys():
        diff = "item set changed"
    else:
        diff = {k: {a: (before[k][a], after[k][a]) for a in before[k]
                    if before[k][a] != after[k].get(a)}
                for k in before if before[k] != after.get(k)}
    assert not diff, f"{kind}/{mode}: restore did not return {diff}"
    assert _changed_by_pass(before, during), (
        f"{kind}/{mode}: the pass changed no item attribute (vacuous guard)")
    prim = primary_item(kind, scene)
    if (kind, mode) not in _PRIMARY_UNCHANGED:
        idx = next(i for i, it in enumerate(scene.items()) if it is prim)
        assert before[("item", idx)] != during[("item", idx)], (
            f"{kind}/{mode}: the pass left the kind's own item "
            f"{type(prim).__name__} unchanged")


# ---------------------------------------------------------------------------
# AC3: pixel parity, and export parity through paper_export
# ---------------------------------------------------------------------------

_MODES = ("on", "off", "named", "hidden")
_COLS, _CELL, _BOX, _PX_PER_MM = 6, 95.0, 90.0, 3


def set_mode(env, mode: str) -> None:
    """(a) every row As Authored on, (b) off with row colours, (c) the named
    weight path: rows on, every row weight at the finest, so a named authored
    weight (a construction line's ``style.weight``, an underlay layer weight)
    visibly wins over the category weight."""
    set_rows(env, mode in ("on", "named", "hidden"), coloured=(mode == "off"))
    if mode == "hidden":
        for row in env.cats.values():
            row["visible"] = False
    if mode == "named":
        for row in env.cats.values():
            if row.get("line_weight"):
                row["line_weight"] = "Extra Thin"


def make_grid(request, kinds=ALL_KINDS):
    """One sheet holding a viewport per item kind (each over its own scene)."""
    from firepro3d.paper_space import (PaperScene, Sheet, SheetViewData,
                                       ViewResolver)
    scenes, views = {}, []
    for i, kind in enumerate(kinds):
        scenes[kind] = build(kind, request)
        crop = scenes[kind][1]          # box = crop x scale: keep every box <= _BOX
        views.append(SheetViewData("plan", kind, kind,
                                   _BOX / max(crop.width(), crop.height()),
                                   5.0 + (i % _COLS) * _CELL,
                                   5.0 + (i // _COLS) * _CELL, _BOX, _BOX))
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.side_effect = lambda vt, vn: (scenes[vn][0], QRectF(scenes[vn][1]))
    sh = Sheet.create_default()
    sh.paper_size = "A1"
    sh.sheet_views = views
    paper = PaperScene(sh, resolver)
    return SimpleNamespace(sheet=sh, resolver=resolver, paper=paper, scenes=scenes)


@pytest.fixture
def grid(qapp, request, paper_env, real_system_library):
    set_rows(paper_env, True)
    g = make_grid(request)
    yield g
    g.paper.dispose()


def _golden() -> dict:
    return json.loads(_GOLDEN.read_text(encoding="utf-8")) if _GOLDEN.exists() else {}


def _check(request, section: str, mode: str, got: str) -> None:
    if request.config.getoption("--regen-paper-pass-golden"):
        data = _golden()
        data.setdefault(section, {})[mode] = got
        _GOLDEN.parent.mkdir(exist_ok=True)
        _GOLDEN.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n",
                           encoding="utf-8")
        return
    want = _golden().get(section, {}).get(mode)
    assert want is not None, f"no {section}/{mode} golden: --regen-paper-pass-golden"
    assert got == want, f"{section}/{mode}: the sheet no longer plots as at base"


def _sheet_image(paper) -> QImage:
    r = paper.sceneRect()
    w, h = int(r.width() * _PX_PER_MM), int(r.height() * _PX_PER_MM)
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    paper.render(p, QRectF(0, 0, w, h), r)
    p.end()
    return img


_BLANK_BY_DESIGN = {"marker_cardinal"}      # PAPER_EXCLUDED: a cardinal never plots


def _assert_cells_inked(img: QImage, grid) -> None:
    by_name = {v.source_view_name: v for v in grid.sheet.sheet_views}
    for kind in ALL_KINDS:
        if kind in _BLANK_BY_DESIGN:
            continue
        v = by_name[kind]
        x0, y0 = int((v.x + 2) * _PX_PER_MM), int((v.y + 2) * _PX_PER_MM)
        x1, y1 = int((v.x + v.w - 2) * _PX_PER_MM), int((v.y + v.h - 2) * _PX_PER_MM)
        ink = any(img.pixel(x, y) != 0xFFFFFFFF
                  for y in range(y0, y1) for x in range(x0, x1))
        assert ink, f"grid cell {kind!r} is blank: it would pin nothing into the golden"


@pytest.mark.parametrize("mode", _MODES)
def test_ac3_sheet_pixel_parity(request, grid, paper_env, mode):
    set_mode(paper_env, mode)
    img = _sheet_image(grid.paper)
    first = _digest(img)
    if request.config.getoption("--regen-paper-pass-golden") and mode != "hidden":
        _assert_cells_inked(img, grid)       # never pin a blank kind into the golden
    assert _digest(_sheet_image(grid.paper)) == first, "the sheet render is not stable"
    _check(request, "pixels", mode, first)


@pytest.mark.parametrize("mode", _MODES)
def test_ac3_export_parity(request, grid, paper_env, mode):
    """The same sheet through ``paper_export.render_sheet`` (the page raster
    ``export_pdf`` paints), digested as a QImage."""
    from firepro3d import paper_export
    set_mode(paper_env, mode)
    w_mm, h_mm = paper_export.sheet_page_mm(grid.sheet)
    w, h = int(w_mm * _PX_PER_MM), int(h_mm * _PX_PER_MM)
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    paper_export.render_sheet(grid.sheet, grid.resolver, p, QRectF(0, 0, w, h))
    p.end()
    _check(request, "export", mode, _digest(img))


# ---------------------------------------------------------------------------
# RED-at-base guards (xfail strict; each flipped by the task its reason names)
# ---------------------------------------------------------------------------

def _render_white(scene, rect, w, h) -> QImage:
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, w, h), QRectF(rect))
    p.end()
    return img


def _sheet_over(scene, crop, box=60.0):
    """A one-viewport sheet over *scene* through the real PaperScene path."""
    from firepro3d.paper_space import (PaperScene, Sheet, SheetViewData,
                                       ViewResolver)
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.side_effect = lambda vt, vn: (scene, QRectF(crop))
    sh = Sheet.create_default()
    sh.paper_size = "A4"
    sh.sheet_views = [SheetViewData("plan", "V", "V",
                                    box / max(crop.width(), crop.height()),
                                    65.0, 60.0, box, box)]
    return PaperScene(sh, resolver)


def _ink_near(img: QImage, rect: QRectF, crop: QRectF, rgb, tol=70) -> int:
    """Pixels inside *rect* (scene mm) of an image of *crop* within *tol* of *rgb*."""
    sx, sy = img.width() / crop.width(), img.height() / crop.height()
    n = 0
    for py in range(max(0, int((rect.top() - crop.top()) * sy)),
                    min(img.height(), int((rect.bottom() - crop.top()) * sy) + 1)):
        for px in range(max(0, int((rect.left() - crop.left()) * sx)),
                        min(img.width(), int((rect.right() - crop.left()) * sx) + 1)):
            c = QColor(img.pixel(px, py))
            if (abs(c.red() - rgb[0]) + abs(c.green() - rgb[1])
                    + abs(c.blue() - rgb[2])) <= tol:
                n += 1
    return n


def _label_scene(pipe_x0: float, pipe_x1: float, pipe_y: float = 0.0):
    """A model whose pipe spans x0..x1 and whose label sits at the origin."""
    from firepro3d.model_space import Model_Space
    from firepro3d.node import Node
    from firepro3d.pipe import Pipe
    ms = Model_Space()
    n1, n2 = Node(pipe_x0, pipe_y), Node(pipe_x1, pipe_y)
    for n in (n1, n2):
        ms.addItem(n)
    p = Pipe(n1, n2)
    ms.addItem(p)
    p.update_label()
    p.label.set_anchor(QPointF(0.0, 0.0))        # the label pokes into the crop
    assert p.label.scene() is ms and p.label.isVisible()
    return ms, p


def _label_after_apply(env, pipe_x0, pipe_x1, pipe_y=0.0):
    """``(label _paper_scale, red px under the label box)`` after the pass."""
    set_rows(env, False)
    env.cats["Pipe"]["color"] = "#ff0000"        # the OWNER's row colour
    env.cats["Blocks"]["color"] = "#0000ff"      # another row: never the label's
    ms, p = _label_scene(pipe_x0, pipe_x1, pipe_y)
    crop = QRectF(_CROP)
    pipe_in = crop.intersects(p.sceneBoundingRect())
    assert pipe_in == (pipe_x0 < crop.right() and pipe_x1 > crop.left()), (
        "setup: the pipe's crop membership is not the one the case names")
    saved = pd.apply_paper_overrides(ms, crop, paper_scale=SCALE)
    try:
        lab = p.label
        box = lab.mapRectToScene(lab.boundingRect())
        assert crop.intersects(box), "setup: the label box must lie in the crop"
        assert not box.intersects(p.sceneBoundingRect()), (
            "setup: the pipe line runs under the label box (its ink would fool the probe)")
        img = _render_white(ms, crop, 600, 600)
        return lab._paper_scale, _ink_near(img, box, crop, (255, 0, 0))
    finally:
        pd.restore_model_display(saved)


def test_ac4_control_label_with_pipe_in_crop_plots_in_row_colour(
        qapp, paper_env, real_system_library):
    """Control for the AC4 guard: with the pipe inside the crop the label plots
    at paper size in the Pipe row colour (passes at base: the ink probe works)."""
    scale, ink = _label_after_apply(paper_env, -800.0, 800.0, -1000.0)
    assert scale == pytest.approx(SCALE)
    assert ink > 0, "no Pipe-row-colour ink under the label box"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="AC4 - fixed in Task 7")
def test_ac4_pipe_label_inside_crop_owner_outside(qapp, paper_env, real_system_library):
    scale, ink = _label_after_apply(paper_env, 3000.0, 5000.0)
    assert scale == pytest.approx(SCALE), "the label did not plot at paper size"
    assert ink > 0, "the label did not plot in the Pipe row colour"


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="AC5 - fixed in Task 2 (every other exit runs and the first error "
                          "re-raises after the full unwind)")
def test_ac5_raising_exit_does_not_stop_the_rest(
        qapp, paper_env, real_system_library, monkeypatch):
    from firepro3d.model_space import Model_Space
    from firepro3d.wall import WallSegment
    monkeypatch.setattr(pd, "_THIN_SUSPEND", 0)       # a failed unwind must not leak
    set_rows(paper_env, False)
    ms = Model_Space()
    walls = []
    for y in (-600.0, 600.0):
        w = WallSegment(QPointF(-800, y), QPointF(800, y))
        w.setZValue(1000.0)           # scene.items() is stacking order, top first:
        ms.addItem(w)                 # the walls' entries come first, the gridline's after
        ms._walls.append(w)
        walls.append(w)
    gl = _gridline(ms)
    gl.setZValue(-1000.0)
    saved = pd.apply_paper_overrides(ms, QRectF(_CROP), paper_scale=SCALE)
    if all(isinstance(e, dict) for e in saved):         # base shape only (pre-Task 2)
        order = [type(e["item"]).__name__ for e in saved if "item" in e]
        assert order.index("GridlineItem") > order.index("WallSegment"), \
            f"setup: the gridline entry must follow a wall's at base: {order}"
    raised = []
    real_update = WallSegment.update

    def update(self, *a):
        if not raised:
            raised.append(self)
            raise RuntimeError("boom")
        return real_update(self, *a)

    monkeypatch.setattr(WallSegment, "update", update)
    with pytest.raises(RuntimeError):
        pd.restore_model_display(saved)
    monkeypatch.undo()
    assert raised, "the armed raise never fired"
    assert gl._paper_render is False, "the gridline stayed in paper mode"
    assert gl.bubble1._paper_scale is None, "the gridline bubble stayed in paper mode"
    assert all("_paper_fill_opaque" not in vars(w) for w in walls if w is not raised[0]), \
        "a wall after the raising one stayed in paper mode"


def _sub_gridline_bubble(request):
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    request.node._pp_keep = [ms]
    gl = _gridline(ms)
    return ms, QRectF(_CROP), gl.bubble1


def _sub_marker_head(request):
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    request.node._pp_keep = [ms]
    m = _marker_placed(ms)
    assert m.head_a.isVisible()
    return ms, QRectF(_CROP), m.head_a


def _sub_elev_head(request):
    from firepro3d.section_scene import ElevDatumItem
    scene, crop = _sec_elevation(request.getfixturevalue("section_scene_for"))
    heads = [i.head for i in scene.items() if isinstance(i, ElevDatumItem)
             and i.head is not None and i.head.isVisible()
             and crop.intersects(i.sceneBoundingRect())]
    assert heads, "no visible level datum head inside the crop"
    return scene, crop, heads[0]


@pytest.mark.parametrize("which", [
    pytest.param("gridline_bubble", marks=pytest.mark.xfail(
        strict=True, raises=AssertionError, reason="AC6 - fixed in Task 9")),
    pytest.param("marker_head", marks=pytest.mark.xfail(
        strict=True, raises=AssertionError, reason="AC6 - fixed in Task 10")),
    pytest.param("elev_head", marks=pytest.mark.xfail(
        strict=True, raises=AssertionError, reason="AC6 - fixed in Task 11")),
])
def test_ac6_sub_item_opacity_survives(qapp, request, paper_env, real_system_library,
                                       which):
    scene, crop, sub = {"gridline_bubble": _sub_gridline_bubble,
                        "marker_head": _sub_marker_head,
                        "elev_head": _sub_elev_head}[which](request)
    sub.setOpacity(0.4)
    paper = _sheet_over(scene, crop)
    try:
        r = paper.sceneRect()
        _render_white(paper, r, int(r.width() * 2), int(r.height() * 2))
        assert sub.opacity() == pytest.approx(0.4), \
            f"{which} opacity is {sub.opacity()} after one sheet render"
    finally:
        paper.dispose()


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="AC8 - fixed in Task 13")
def test_ac8_fitting_enters_when_node_hit(qapp, paper_env, real_system_library):
    from firepro3d.model_space import Model_Space
    set_rows(paper_env, False)
    ms = Model_Space()
    crop = QRectF(_CROP)
    n = ms.add_node(crop.left() + 10.0, 0.0)             # the node is in the crop...
    n.fitting.update()
    f = n.fitting
    assert f.symbol is not None and f.symbol.isVisible(), "setup: no visible fitting symbol"
    assert crop.contains(n.scenePos()) \
        and not crop.contains(f.symbol.scenePos()), \
        f"setup: the symbol origin {f.symbol.scenePos()} must lie outside the crop"
    tint_before = _svg_identity(f.symbol)
    saved = pd.apply_paper_overrides(ms, crop, paper_scale=SCALE)
    try:
        assert _svg_identity(f.symbol) != tint_before, "the symbol was not re-tinted"
        assert f._display_color == _ROW_RED, \
            f"the Fitting row colour did not reach the symbol ({f._display_color!r})"
    finally:
        pd.restore_model_display(saved)
