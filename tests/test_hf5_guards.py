"""HF5 Task 11 -- end-to-end guards (AC2, AC4, AC5, AC9, R8; Group D / E carry-ins).

Every guard drives the real path: ``MainWindow._load_project`` on a real project
file, the real Display Manager + Fill Types tab + ``accept()``, a real scene /
paper-PDF render, asserting pixels or digests (VC3).

The legacy fixture ``tests/fixtures/hf5_legacy.fpd`` was generated at the
pre-HF5 base 703f4043 by the env-gated ``test_record_legacy_fixture`` below, and
the two digest constants were recorded there by the same ``_digests`` code
(``HF5_RECORD_DIR=<dir>`` prints them). Both must stay identical on the branch.
"""
from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import fitz
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d import app_data
from firepro3d import hatch_patterns as hp
from firepro3d.block_definition import BlockDefinition
from firepro3d.fill_layers import BackgroundLayer, FillLayers, PatternLayer
from firepro3d.filled_region import FilledRegionItem
from firepro3d.floor_slab import FloorSlab
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from firepro3d.wall import WallSegment
from tests._mainwindow_helpers import dispose_main_window

FIXTURE = Path(__file__).parent / "fixtures" / "hf5_legacy.fpd"

# Recorded at base 703f4043 (HF5_RECORD_DIR run of test_record_legacy_fixture).
_BASE_CANVAS = "ca651730d217210e27fc4640357347058393aabe389b7814d0b5968e7e3ab5ca"
_BASE_PAPER_BW = "cf5c7d341de1d50e8f44527e2e07d927be499849edea3498a27072cfb44a31a1"
_BASE_PAPER_COLOUR = "6108ff2e6e18c5040204fd7a7c405698509bc3adf668d72c564422d816882115"

_PT = 25.4 / 72.0
_VP_X, _VP_Y, _VP_W = 65.0, 30.0, 80.0
_PAPER_SCALE = 0.01                        # 80 mm viewport = 8000 mm of model
_PAPER_CROP = QRectF(-1500.0, -2600.0, 8000.0, 8000.0)
_CANVAS_RECT = QRectF(-300.0, -2600.0, 4600.0, 6600.0)
_CANVAS_PX = 0.2                           # px per mm (920 x 1320)


# -- fixture scene (generated once at the base; kept for provenance) ----------

def _wall(ms, y):
    w = WallSegment(QPointF(0, y), QPointF(4000, y))
    w.level = "Level 1"
    ms._walls.append(w)
    ms.addItem(w)
    return w


def _legacy_region_record():
    """A custom Filled Region: red background + the shipped Diagonal pattern."""
    a, b, c, d = QPointF(-500, -500), QPointF(500, -500), QPointF(500, 500), QPointF(-500, 500)
    r = FilledRegionItem.from_pieces([[LineItem(a, b), LineItem(b, c), LineItem(c, d), LineItem(d, a)]])
    r.fill_layers = FillLayers(BackgroundLayer("#ff0000", 1.0),
                               PatternLayer(hp.BUILTIN_DIAGONAL, "#0000ff", 1.0, 1.0))
    return r.to_dict()


def _build_legacy_project(path: str) -> None:
    ms = Model_Space()
    _wall(ms, -2000)                                       # category look
    _wall(ms, -1000)                                       # gets a red line colour after open
    slab = FloorSlab(points=[QPointF(0, 0), QPointF(4000, 0),
                             QPointF(4000, 1500), QPointF(0, 1500)])
    slab.level = "Level 1"
    ms._floor_slabs.append(slab)
    ms.addItem(slab)
    host = BlockDefinition.new(name="Slab Block", library="Mine", series="S",
                               origin=(0.0, 0.0), primitives=[_legacy_region_record()])
    ms.register_block_definition(host)
    ms.place_block_instance(host.id, (2000.0, 3000.0), level=ms.active_level)
    ms.save_to_file(path)


# -- open + render + digest ----------------------------------------------------

@pytest.fixture()
def mw(qapp, tmp_path, monkeypatch):
    """Fresh MainWindow (isolated QSettings / block library via conftest)."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    folder = app_data.hatch_patterns_dir()
    os.makedirs(str(folder), exist_ok=True)
    for _bid, src in hp.shipped_pattern_files():
        shutil.copyfile(src, os.path.join(str(folder), os.path.basename(src)))
    import main as main_mod
    from firepro3d import snap_engine
    from firepro3d.view_3d import View3D
    main_mod.View3D = View3D
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    w = main_mod.MainWindow()
    yield w
    dispose_main_window(w)
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


def _open_fixture(win, path=FIXTURE):
    """Real open path, then the cut flags + the per-item red line colour (wall
    per-item overrides are not serialized -- open bug -- so they are applied
    after open exactly as a user's Display Manager edit would)."""
    win._load_project(str(path))
    sc = win.scene
    walls = sorted(sc._walls, key=lambda w: w.sceneBoundingRect().center().y())
    assert len(walls) == 2 and len(sc._floor_slabs) == 1
    for item in (*walls, *sc._floor_slabs):
        item._is_section_cut = True
    walls[1]._display_color = "#ff0000"
    sc.update()
    return walls[0], walls[1], sc._floor_slabs[0]


def _render(scene, rect, px_w, px_h):
    img = QImage(px_w, px_h, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, px_w, px_h), rect)
    p.end()
    return img


def _canvas_img(scene):
    return _render(scene, _CANVAS_RECT, int(_CANVAS_RECT.width() * _CANVAS_PX),
                   int(_CANVAS_RECT.height() * _CANVAS_PX))


def _img_digest(img) -> str:
    return hashlib.sha256(bytes(img.constBits().asarray(img.sizeInBytes()))).hexdigest()


def _paper_pdf(scene, tmp_path, name="p.pdf"):
    from firepro3d import paper_export
    from firepro3d.paper_space import Sheet, SheetViewData, ViewResolver
    sheet = Sheet.create_default()
    sheet.paper_size = "A4"
    sheet.sheet_views = [SheetViewData("plan", "Plan: Level 1", "P", _PAPER_SCALE,
                                       _VP_X, _VP_Y, _VP_W, _VP_W)]
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.side_effect = lambda vt, vn: (scene, QRectF(_PAPER_CROP))
    out = tmp_path / name
    paper_export.export_pdf([sheet], resolver, str(out), dpi=300)
    return out


def _pt(v):
    if hasattr(v, "x0"):
        return (round(v.x0, 2), round(v.y0, 2), round(v.x1, 2), round(v.y1, 2))
    if hasattr(v, "x"):
        return (round(v.x, 2), round(v.y, 2))
    return repr(v)


def _paper_digest(pdf) -> str:
    """sha256 of every stroked / filled drawing strictly inside the viewport."""
    lo_x, hi_x = (_VP_X + 0.5) / _PT, (_VP_X + _VP_W - 0.5) / _PT
    lo_y, hi_y = (_VP_Y + 0.5) / _PT, (_VP_Y + _VP_W - 0.5) / _PT
    doc = fitz.open(str(pdf))
    try:
        sig = []
        for d in doc[0].get_drawings():
            r = d["rect"]
            if not (lo_x < r.x0 and r.x1 < hi_x and lo_y < r.y0 and r.y1 < hi_y):
                continue
            sig.append((d.get("type"), round(d.get("width") or 0.0, 4),
                        repr(d.get("color")), repr(d.get("fill")),
                        tuple((it[0],) + tuple(_pt(v) for v in it[1:]) for it in d["items"])))
    finally:
        doc.close()
    sig.sort(key=repr)
    assert len(sig) > 10                      # really drew
    return hashlib.sha256(repr(sig).encode()).hexdigest()


def _digests(win, tmp_path, path=FIXTURE):
    """(canvas, paper B&W, paper full colour) of the opened legacy fixture."""
    _open_fixture(win, path)
    canvas = _img_digest(_canvas_img(win.scene))
    save_paper_color_mode(PaperColorMode.BW)
    bw = _paper_digest(_paper_pdf(win.scene, tmp_path, "bw.pdf"))
    save_paper_color_mode(PaperColorMode.FULL_COLOR)
    colour = _paper_digest(_paper_pdf(win.scene, tmp_path, "colour.pdf"))
    return canvas, bw, colour


@pytest.mark.skipif(not os.environ.get("HF5_RECORD_DIR"), reason="base-SHA recorder")
def test_record_legacy_fixture(mw, tmp_path):
    out = Path(os.environ["HF5_RECORD_DIR"]) / "hf5_legacy.fpd"
    _build_legacy_project(str(out))
    print("HF5_DIGESTS", *(repr(d) for d in _digests(mw, tmp_path, out)))


# -- AC4: a pre-HF5 project opens pixel-identical ------------------------------

def test_legacy_open_is_digest_identical(mw, tmp_path):
    """Regions + wall / floor section cuts, canvas and paper (B&W pen remap and
    full colour), digest-equal to the pre-HF5 base render; the wall with the red
    per-item line colour keeps a red hatch through By element (R8)."""
    canvas, bw, colour = _digests(mw, tmp_path)
    assert (canvas, bw, colour) == (_BASE_CANVAS, _BASE_PAPER_BW, _BASE_PAPER_COLOUR)


# -- G6: restyle through the real tab (AC2, AC5) -------------------------------

def _tab(dlg):
    return next(dlg._tabs.widget(i) for i in range(dlg._tabs.count())
                if dlg._tabs.tabText(i) == "Fill Types")


def _body(wall) -> QRectF:
    """Scene rect of the wall's body polygon (the cut's fill area)."""
    return wall.mapRectToScene(wall.outline().body.boundingRect())


def _inner(scene_rect):
    """*scene_rect* shrunk 10 % per side (clear of the outline stroke)."""
    return scene_rect.adjusted(scene_rect.width() * 0.1, scene_rect.height() * 0.1,
                               -scene_rect.width() * 0.1, -scene_rect.height() * 0.1)


def _count(img, scene_rect, pred) -> tuple[int, int]:
    """(pixels in the shrunk rect satisfying *pred*(QColor), total pixels)."""
    r = _inner(scene_rect)
    n = hit = 0
    for y in range(int((r.top() - _CANVAS_RECT.top()) * _CANVAS_PX),
                   int((r.bottom() - _CANVAS_RECT.top()) * _CANVAS_PX)):
        for x in range(int((r.left() - _CANVAS_RECT.left()) * _CANVAS_PX),
                       int((r.right() - _CANVAS_RECT.left()) * _CANVAS_PX)):
            n += 1
            hit += bool(pred(QColor(img.pixel(x, y))))
    return hit, max(n, 1)


def _share(img, scene_rect, rgb) -> float:
    """Fraction of the (shrunk) rect's pixels that are exactly *rgb*."""
    want = QColor(rgb).rgb()
    hit, n = _count(img, scene_rect, lambda c: c.rgb() == want)
    return hit / n


def _is_red(c) -> bool:
    return c.red() > 200 and c.green() < 90 and c.blue() < 90


def _is_green(c) -> bool:
    return c.green() > 150 and c.red() < 80 and c.blue() < 80


def _count_red(img, scene_rect) -> int:
    """Red pixels inside the body (the outline stroke is excluded: only the
    hatch can be red there)."""
    return _count(img, scene_rect, _is_red)[0]


def _place_typed_region_block(win, type_name):
    """A block whose Filled Region takes its look from *type_name*, chosen the
    way the region panel does (``set_property("Fill Type", name)``), placed once
    inside the canvas rect. Returns the instance's scene rect."""
    a, b, c, d = QPointF(-500, -500), QPointF(500, -500), QPointF(500, 500), QPointF(-500, 500)
    r = FilledRegionItem.from_pieces([[LineItem(a, b), LineItem(b, c), LineItem(c, d), LineItem(d, a)]])
    r.set_property("Fill Type", type_name)
    assert r.fill_type
    host = BlockDefinition.new(name="Typed", library="Mine", series="S",
                               origin=(0.0, 0.0), primitives=[r.to_dict()])
    win.scene.register_block_definition(host)
    win.scene.place_block_instance(host.id, (3500.0, 3000.0), level=win.scene.active_level)
    return QRectF(3000.0, 2500.0, 1000.0, 1000.0)


def test_restyle_through_tab_updates_region_and_cut_wall(mw):
    """G6 (AC2 + AC5): the Fill Types tab restyles a typed region and a cut wall
    on OK; the red-line wall keeps its red hatch (R8). Entry point for the
    typed region: the region panel's ``set_property("Fill Type", ...)`` on a
    region that is then compiled into a placed block's definition."""
    from firepro3d import fill_types as ft
    save_paper_color_mode(PaperColorMode.FULL_COLOR)
    w1, w2, _slab = _open_fixture(mw)
    w2._display_overrides["color"] = "#ff0000"        # as the Display Manager sets it

    dlg = mw._make_display_manager("model")           # create the project type through the tab
    tab = _tab(dlg)
    tab.add_type()
    assert tab.set_name("Concrete")
    tab.set_background(True, "#00aa00", 1.0)
    tab.set_pattern(False, None, "#000000", 1.0, 1.0)
    dlg.accept()
    region = _place_typed_region_block(mw, "Concrete")
    mw.scene.update()

    before = _canvas_img(mw.scene)
    assert _share(before, region, "#00aa00") > 0.9               # the type's green
    assert _share(before, _body(w1), "#666666") > 0.8   # category look (legacy section)
    red_before = _count_red(before, _body(w2))
    assert red_before > 20                                       # red hatch by element

    dlg = mw._make_display_manager("model")
    tab = _tab(dlg)
    assert tab.select_name("Wall Section")
    cur = tab.current_type()
    tab.set_background(True, "#ffaa00", 1.0)
    assert tab.select_name("Concrete")
    tab.set_background(True, "#0000ff", 1.0)
    dlg.accept()

    after = _canvas_img(mw.scene)
    assert _share(after, region, "#0000ff") > 0.9                # placed instance restyled
    assert _share(after, region, "#00aa00") == 0
    assert _share(after, _body(w1), "#ffaa00") > 0.8   # cut wall restyled
    assert _share(after, _body(w2), "#ffaa00") > 0.8
    assert _count_red(after, _body(w2)) > 20        # R8: hatch still red
    assert _count_red(after, _body(w1)) == 0        # un-overridden wall: no red
    assert cur.name == "Wall Section"


# -- AC9: a deleted type draws the fallback ------------------------------------

def test_missing_type_cut_draws_fallback(mw):
    """A cut wall whose type id left the table draws Solid Grey 20 % (D-A36).

    Expected body RGB: the wall's own body fill is removed (``""`` = no colour)
    so the fallback blends on the white canvas. Grey #808080 = 128 at opacity
    0.20 -> alpha round(0.20 * 255) = 51; 128*51/255 + 255*(255-51)/255
    = 25.6 + 204.0 = 229.6 -> 229 or 230 per channel (Qt integer blend)."""
    from firepro3d import fill_types as ft
    from firepro3d.constants import FILL_TYPE_FALLBACK_COLOR, FILL_TYPE_FALLBACK_OPACITY
    w1, _w2, _slab = _open_fixture(mw)
    gone = ft.project_table().add(ft.FillType(ft.new_id(), "Doomed", FillLayers(
        BackgroundLayer("#00ff00", 1.0))))
    w1._display_section_type = gone.id
    w1._display_fill_color = ""
    mw.scene.update()
    assert _share(_canvas_img(mw.scene), _body(w1), "#00ff00") > 0.9
    ft.project_table().remove(gone.id)
    mw.scene.update()
    img = _canvas_img(mw.scene)
    grey = QColor(FILL_TYPE_FALLBACK_COLOR)
    a = round(FILL_TYPE_FALLBACK_OPACITY * 255)
    want = [round((grey.red() * a + 255 * (255 - a)) / 255)] * 3
    r = _body(w1)
    px = QColor(img.pixel(int((r.center().x() - _CANVAS_RECT.left()) * _CANVAS_PX),
                          int((r.center().y() - _CANVAS_RECT.top()) * _CANVAS_PX)))
    assert all(abs(c - w) <= 1 for c, w in zip((px.red(), px.green(), px.blue()), want))
    assert want == [230] * 3


# -- R8: By element follows the element's line colour --------------------------

def test_by_element_follows_category_colour_and_item_override(mw):
    """A converted section type colours its hatch By element: changing the Wall
    category colour recolours the un-overridden wall's hatch; the wall with a
    red per-item line colour keeps red (AC5)."""
    from PyQt6.QtCore import QSettings
    from firepro3d import display_manager as dm
    save_paper_color_mode(PaperColorMode.FULL_COLOR)
    w1, w2, _slab = _open_fixture(mw)
    w2._display_overrides["color"] = "#ff0000"
    vals = dm._read_category_from_settings("Wall", QSettings("GV", "FirePro3D"))
    vals = {**vals, "color": "#00cc00"}
    dm._apply_to_scene_items(mw.scene, "Wall", vals, respect_overrides=True)
    mw.scene.update()
    img = _canvas_img(mw.scene)

    assert _count(img, _body(w1), _is_green)[0] > 20   # the hatch (body interior) takes the new line colour
    assert _count_red(img, _body(w1)) == 0
    assert _count_red(img, _body(w2)) > 20       # per-item override wins (hatch, not outline)


# -- Group D carry-in: a region record inside a definition blocks the pattern delete --

def _tile(name="Zig"):
    return BlockDefinition.new(
        name=name, library="L", series="S", origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()],
        tile={"w": 5.0, "h": 5.0, "row_shift": 0.0, "size": "model"})


def _region_record_with_pattern(ref):
    a, b, c, d = QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)
    r = FilledRegionItem.from_pieces([[LineItem(a, b), LineItem(b, c), LineItem(c, d), LineItem(d, a)]])
    r.fill_layers = FillLayers(None, PatternLayer(ref, "#000000", 1.0, 1.0))
    return r.to_dict()


def test_region_record_in_a_definition_reaches_the_inside_clause(qapp):
    """A Filled Region record inside a block definition tiling with a pattern
    block: the real delete path refuses and names the host in "inside:"."""
    ms = Model_Space()
    pat = _tile()
    host = BlockDefinition.new(name="Slab", library="L", series="S", origin=(0.0, 0.0),
                               primitives=[_region_record_with_pattern(pat.id)])
    ms.register_block_definition(pat)
    ms.register_block_definition(host)
    assert ms.delete_block_definition(pat.id) is False
    assert pat.id in ms._block_definitions
    assert ms.block_users_message(pat.id) == (
        "\u201cZig\u201d is used inside: Slab \u2014 explode or remove it there first.")
    # the region switched to no pattern: the delete goes through
    host.primitives[0]["fill"] = {"background": {"color": "#ff0000", "opacity": 1.0}}
    host.invalidate_cache()
    ms.block_registry.add(host)
    assert ms.block_users_message(pat.id) is None
    assert ms.delete_block_definition(pat.id) is True


def test_typed_region_record_in_a_definition_names_host_and_type(qapp):
    """The typed variant: the type owns the pattern, the host region inherits it."""
    from firepro3d import fill_types as ft
    ms = Model_Space()
    pat = _tile()
    t = ft.project_table().add(ft.FillType(ft.new_id(), "Concrete", FillLayers(
        None, PatternLayer(pat.id, "#000000", 1.0, 1.0))))
    a, b, c, d = QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)
    r = FilledRegionItem.from_pieces([[LineItem(a, b), LineItem(b, c), LineItem(c, d), LineItem(d, a)]])
    r.set_fill_type(t.id)
    host = BlockDefinition.new(name="Slab", library="L", series="S", origin=(0.0, 0.0),
                               primitives=[r.to_dict()])
    ms.register_block_definition(pat)
    ms.register_block_definition(host)
    assert ms.delete_block_definition(pat.id) is False
    assert ms.block_users_message(pat.id) == (
        "\u201cZig\u201d is used inside: Slab, and by Fill Types: Concrete"
        " \u2014 explode or remove it there, and change their pattern first.")
