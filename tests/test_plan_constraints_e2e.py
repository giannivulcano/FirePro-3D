"""Editor/Build slice 2 Task 6: plan Constrain / Inspect on the real
MainWindow (shown, live QSS), real ribbon buttons, posted mouse events on
the plan view; glyphs never plot (sheet render + PDF raster digests, the
pixel-guard convention). Guards T4 (e2e), T7."""
from __future__ import annotations

import copy
import hashlib
import math
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import firepro3d.paper_display as pd

from firepro3d.gridline import GridlineItem
from firepro3d.wall import WallSegment
from tests.test_build_editor_tabs import _editors, _plan_index, mw  # noqa: F401
from tests.test_constraint_e2e import _click, _drag, _send


@pytest.fixture
def plan(mw, qapp):
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    qapp.processEvents()
    sc, view = mw.scene, mw.view
    # Fit every point the tests touch into the (~640 x 480 px) viewport:
    # the gridline at x=-1000 (y +-1500), the wall 0..3000, the dim click at
    # y=-800 and the end drag to (3900, 1000).  Posted events outside the
    # viewport still reach the scene, but a grip pick off-screen misses.
    view.resetTransform()
    view.fitInView(QRectF(-1500, -2000, 6000, 4000),
                   Qt.AspectRatioMode.KeepAspectRatio)
    yield sc, view
    if sc.readouts.is_editing():        # a failed test's open HUD must not
        sc.readouts.cancel_edit()       # leave the canvas inert for the next
    sc.set_mode("select")
    sc.clearSelection()
    for w in list(sc._walls):
        sc.removeItem(w)
        sc._walls.remove(w)
    for g in list(sc._gridlines):
        sc.removeItem(g)
        sc._gridlines.remove(g)
    sc.constraint_ctl.restore([])
    qapp.processEvents()


def _wall(sc, a, b):
    w = WallSegment(QPointF(*a), QPointF(*b))
    sc.addItem(w)
    sc._walls.append(w)
    return w


def _len(w):
    return math.hypot(w._pt2.x() - w._pt1.x(), w._pt2.y() - w._pt1.y())


def test_constrain_and_inspect_are_live_in_plan(mw, plan):
    for name in ("Smart Dimension", "Horizontal", "Coincident", "Show Constraints"):
        assert mw._be_constrain_buttons[name].isEnabled(), name


def test_t4_selection_first_horizontal_and_smart_dim_on_a_wall(mw, plan, qapp):
    sc, view = plan
    w = _wall(sc, (0, 0), (3000, 400))             # tilted
    sc.clearSelection()
    w.setSelected(True)
    qapp.processEvents()
    mw._be_constrain_buttons["Horizontal"].click()   # the REAL button
    qapp.processEvents()
    assert [c.type for c in sc.constraint_ctl.constraints_on(w)] == ["horizontal"]
    assert w._pt1.y() == pytest.approx(w._pt2.y(), abs=1e-6)
    L = _len(w)
    sc.clearSelection()
    w.setSelected(True)
    qapp.processEvents()
    mw._be_constrain_buttons["Smart Dimension"].click()   # selected wall -> placement click
    qapp.processEvents()
    _click(view, view.mapFromScene(QPointF(1500, w._pt1.y() - 800)))
    assert sorted(c.type for c in sc.constraint_ctl.constraints_on(w)) == [
        "dim_distance", "horizontal"]
    # D50: the placement opens the value HUD and the canvas is inert until it
    # closes (Model_Space.mousePressEvent is_input_mode gate) -- "type a
    # length" (smoke seed), as tests/test_constraint_dims_e2e.py does.
    assert sc.readouts.is_editing(), "no value HUD after the placement click"
    (field,) = sc.readouts.hud.field_names()        # the one dim field
    ed = sc.readouts.hud.editor(field)
    ed.selectAll()
    QTest.keyClicks(ed, "2800")
    QTest.keyClick(ed, Qt.Key.Key_Return)
    qapp.processEvents()
    assert not sc.readouts.is_editing()
    assert _len(w) == pytest.approx(2800.0, abs=1e-6)          # the typed length drives the wall
    assert w._pt1.y() == pytest.approx(w._pt2.y(), abs=1e-6)   # still level
    # (Which end moves on a typed length is not ruled for walls -- today the
    # solve shortens about the midpoint, both ends by 100; smoke row.)
    L = _len(w)
    sc.set_mode("select")
    sc.clearSelection()
    w.setSelected(True)                              # grips visible
    qapp.processEvents()
    assert not sc.is_input_mode()
    end = QPointF(w._pt2)
    assert view.viewport().rect().contains(view.mapFromScene(end)), \
        "wall end grip is off the viewport -- the drag would miss it"
    _drag(view, end, QPointF(end.x() + 900, end.y() + 600))
    assert (w._pt2 - end).manhattanLength() > 100.0, "the end grip did not move"
    assert _len(w) == pytest.approx(L, abs=1e-3)      # length held (Newton solve: 1e-3 mm)
    assert w._pt1.y() == pytest.approx(w._pt2.y(), abs=1e-6)   # still level


def test_t4_end_to_gridline_offset_holds_when_the_gridline_moves(mw, plan, qapp):
    sc, view = plan
    w = _wall(sc, (0, 0), (3000, 0))
    gl = GridlineItem(QPointF(-1000, -1500), QPointF(-1000, 1500), label="A")
    sc._gridlines.append(gl)
    sc.addItem(gl)
    c = sc.constraint_ctl.add("dim_point_line", [{"uid": w._uid, "h": "p1"},
                                                 {"uid": gl._uid, "h": "edge"}])
    assert c is not None and c.value == pytest.approx(1000.0)
    qapp.processEvents()
    sc.clearSelection()
    gl.setSelected(True)
    qapp.processEvents()
    # Body drag of the gridline 400 mm right (a point on the line, off its grips).
    _drag(view, QPointF(-1000, 700), QPointF(-600, 700))
    assert gl._origin.x() > -900.0        # the gridline moved right (snap may round it)
    assert w._pt1.x() - gl._origin.x() == pytest.approx(1000.0, abs=1e-3)   # offset held (Newton solve)


def _digest(img) -> str:
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    return hashlib.sha256(bytes(ptr)).hexdigest()


def _settle(mw, qapp):
    """Run the debounced sceneModified refresh now (main.py
    ``_on_scene_modified`` -> 200 ms -> ``_refresh_all_views``), which
    re-applies the level pass and sets the wall's ``_is_section_cut``.  A
    digest taken before it fires is compared against one taken after it, and
    the wall's section fill -- not a glyph -- makes them differ."""
    mw._refresh_all_views()
    qapp.processEvents()


def _canvas(view, qapp):
    view.viewport().repaint()
    qapp.processEvents()
    return _digest(view.viewport().grab().toImage())


_CROP = QRectF(-500.0, -1500.0, 4000.0, 3000.0)   # shows the 0..3000 mm wall


@pytest.fixture
def paper_env(monkeypatch):
    """Controlled paper settings -- never the real QSettings (copied from
    tests/test_selection_never_plots.py)."""
    cats = copy.deepcopy(pd.factory_paper_categories())
    monkeypatch.setattr(pd, "load_paper_categories",
                        lambda settings=None: copy.deepcopy(cats))
    monkeypatch.setattr(pd, "load_paper_color_mode",
                        lambda settings=None: pd.PaperColorMode.BW)
    monkeypatch.setattr(pd, "load_line_weights",
                        lambda settings=None: list(pd.FACTORY_LINE_WEIGHTS))


def _sheet_digests(mw, path, paper_export, fitz):
    """(sheet render digest, PDF raster digest) of one A4 sheet with one plan
    viewport over the real plan scene (resolver mocked to the plan scene)."""
    from firepro3d.paper_space import Sheet, SheetViewData, ViewResolver
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.side_effect = lambda vt, vn: (mw.scene, QRectF(_CROP))
    sh = Sheet.create_default()
    sh.paper_size = "A4"
    sh.sheet_views = [SheetViewData("plan", "V", "V", 0.02, 65.0, 60.0, 60.0, 60.0)]
    img = QImage(840, 594, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    paper_export.render_sheet(sh, resolver, p, QRectF(0, 0, 840, 594))
    p.end()
    paper_export.export_pdf([sh], resolver, str(path), dpi=72)
    pix = fitz.open(str(path))[0].get_pixmap(dpi=72)
    return _digest(img), hashlib.sha256(pix.samples).hexdigest()


def test_t7_glyphs_paint_in_plan_and_never_plot(mw, plan, qapp, tmp_path, paper_env):
    """T7: a selected constrained wall shows its glyph in the plan view; the
    sheet viewport render and the exported PDF are byte-identical with the
    constraint present or absent (glyphs live only in Model_View.drawForeground,
    which scene.render never runs)."""
    import fitz                                         # PyMuPDF (project dep)
    from firepro3d import paper_export
    sc, view = plan
    w = _wall(sc, (0, 0), (3000, 0))
    sc.clearSelection()
    w.setSelected(True)
    _settle(mw, qapp)
    assert w._is_section_cut, "plan wall not section-cut after the level pass"
    canvas_off = _canvas(view, qapp)
    paper_off, pdf_off = _sheet_digests(mw, tmp_path / "off.pdf", paper_export, fitz)
    w.setVisible(False)
    paper_none, pdf_none = _sheet_digests(mw, tmp_path / "none.pdf", paper_export, fitz)
    w.setVisible(True)
    assert paper_off != paper_none, "the wall does not plot on the sheet (vacuous)"
    assert pdf_off != pdf_none, "the wall does not plot in the PDF (vacuous)"
    c = sc.constraint_ctl.add("horizontal", [{"uid": w._uid, "h": "edge"}])
    assert c is not None
    sc.clearSelection()
    w.setSelected(True)                                 # D32: selected -> glyph
    _settle(mw, qapp)
    assert w._is_section_cut
    assert _canvas(view, qapp) != canvas_off, "no glyph painted in the plan view"
    paper_on, pdf_on = _sheet_digests(mw, tmp_path / "on.pdf", paper_export, fitz)
    assert paper_on == paper_off, "a constraint glyph plots on the sheet"
    assert pdf_on == pdf_off, "a constraint glyph plots in the PDF"


# -- VC9 M1: detail (clip) views paint and pick constraints inside the crop ---

def _detail_view(sc, crop, qapp):
    """A detail view exactly as detail_view.py builds one: a plain Model_View
    of the plan scene with ``_clip_rect`` set to the marker's crop."""
    from firepro3d.model_view import Model_View
    view = Model_View(sc)
    view._clip_rect = crop
    view.resize(640, 480)
    view.show()
    qapp.processEvents()
    view.resetTransform()
    view.fitInView(QRectF(-1500, -2000, 6000, 4000),
                   Qt.AspectRatioMode.KeepAspectRatio)
    qapp.processEvents()
    return view


def _glyph_region_digest(view, rect, qapp):
    view.viewport().repaint()
    qapp.processEvents()
    img = view.viewport().grab().toImage()
    dpr = img.devicePixelRatio()
    r = rect.toAlignedRect().adjusted(-3, -3, 3, 3)
    return _digest(img.copy(int(r.x() * dpr), int(r.y() * dpr),
                            int(r.width() * dpr), int(r.height() * dpr)))


@pytest.fixture
def detail_wall(mw, plan, qapp):
    sc, _view = plan
    w = _wall(sc, (0, 0), (3000, 0))
    sc.clearSelection()
    w.setSelected(True)
    qapp.processEvents()
    mw._be_constrain_buttons["Horizontal"].click()   # the real selection-first path
    qapp.processEvents()
    (c,) = sc.constraint_ctl.constraints_on(w)
    sc.clearSelection()
    sc.constraint_ctl.show_all = True            # glyphs visible without a selection
    qapp.processEvents()
    views = []
    yield sc, w, c, views
    sc.constraint_ctl.show_all = False
    for v in views:
        v.close()
        v.deleteLater()
    sc.constraint_ctl.clear_selected()
    qapp.processEvents()


def _glyph_vp(view, sc, c):
    from firepro3d import constraint_paint as cp
    (rect,) = [r for cid, r in cp.glyph_layouts(view, sc.constraint_ctl) if cid == c.id]
    return rect


def test_vc9_m1_detail_view_paints_the_glyph_inside_the_crop(detail_wall, qapp):
    sc, w, c, views = detail_wall
    crop = QRectF(-500.0, -1500.0, 4000.0, 3000.0)       # covers the wall + glyph
    dv = _detail_view(sc, crop, qapp)
    views.append(dv)
    rect = _glyph_vp(dv, sc, c)
    assert dv.viewport().rect().contains(rect.toAlignedRect())
    assert crop.contains(dv.mapToScene(rect.center().toPoint())), "glyph not in the crop"
    with_c = _glyph_region_digest(dv, rect, qapp)
    saved = sc.constraint_ctl.constraints[:]
    sc.constraint_ctl.constraints = []
    qapp.processEvents()
    without_c = _glyph_region_digest(dv, rect, qapp)
    sc.constraint_ctl.constraints = saved
    qapp.processEvents()
    assert with_c != without_c, "detail view painted no constraint glyph in the crop"


def test_vc9_m1_detail_view_does_not_paint_the_glyph_outside_the_crop(detail_wall, qapp):
    sc, w, c, views = detail_wall
    crop = QRectF(2000.0, 600.0, 1000.0, 800.0)          # excludes the glyph
    dv = _detail_view(sc, crop, qapp)
    views.append(dv)
    rect = _glyph_vp(dv, sc, c)
    assert not crop.contains(dv.mapToScene(rect.center().toPoint()))
    with_c = _glyph_region_digest(dv, rect, qapp)
    saved = sc.constraint_ctl.constraints[:]
    sc.constraint_ctl.constraints = []
    qapp.processEvents()
    without_c = _glyph_region_digest(dv, rect, qapp)
    sc.constraint_ctl.constraints = saved
    qapp.processEvents()
    assert with_c == without_c, "the constraint layer painted over the clip mask"


def test_vc9_m1_detail_view_picks_the_glyph_inside_the_crop_only(detail_wall, qapp):
    sc, w, c, views = detail_wall
    ctl = sc.constraint_ctl
    sc.set_mode("select")
    inside = _detail_view(sc, QRectF(-500.0, -1500.0, 4000.0, 3000.0), qapp)
    views.append(inside)
    pt = _glyph_vp(inside, sc, c).center()
    _send(inside, QEvent.Type.MouseMove, pt, Qt.MouseButton.NoButton,
          Qt.MouseButton.NoButton)
    assert ctl.hover_id == c.id, "glyph hover is blind in a detail view"
    _click(inside, pt)
    assert ctl.selected_id == c.id, "glyph click did not select in a detail view"
    ctl.clear_selected()
    ctl.hover_id = None
    outside = _detail_view(sc, QRectF(2000.0, 600.0, 1000.0, 800.0), qapp)
    views.append(outside)
    pt2 = _glyph_vp(outside, sc, c).center()
    _send(outside, QEvent.Type.MouseMove, pt2, Qt.MouseButton.NoButton,
          Qt.MouseButton.NoButton)
    assert ctl.hover_id is None
    _click(outside, pt2)
    assert ctl.selected_id is None, "a click outside the crop picked a glyph"


# -- VC9 M2: a hidden level's wall is never a pick candidate but still moves ---

def test_vc9_m2_hidden_level_wall_is_not_pickable_but_still_moves(mw, plan, qapp):
    sc, view = plan
    ctl = sc.constraint_ctl
    hidden = _wall(sc, (0, 0), (3000, 0))         # drawn first: wins a distance tie
    vis = _wall(sc, (0, 0), (3000, 0))
    mw.level_mgr.add_level("Level 2", elevation=20000.0)
    try:
        _vc9_m2_body(mw, sc, view, ctl, hidden, vis, qapp)
    finally:
        mw.level_mgr.remove_level("Level 2")
        mw._apply_plan_level("Level 1")


def _vc9_m2_body(mw, sc, view, ctl, hidden, vis, qapp):
    hidden._base_level = hidden._top_level = hidden.level = "Level 2"
    mw._apply_plan_level("Level 1")               # the real level pass
    qapp.processEvents()
    assert not hidden.isVisible() and vis.isVisible(), "level pass did not hide Level 2"
    assert ctl.add("coincident", [{"uid": hidden._uid, "h": "p2"},
                                  {"uid": vis._uid, "h": "p2"}]) is not None
    ctl.begin_pick("coincident")
    pick = ctl.pick
    refs = [ref for _k, ref, _a, _b in pick._candidates()]
    assert all(r.get("uid") != hidden._uid for r in refs if "uid" in r), \
        "hidden wall handles are pick candidates"
    assert any(r.get("uid") == vis._uid for r in refs if "uid" in r)
    got = pick.hover_at(view, QPointF(view.mapFromScene(QPointF(0, 0))))
    assert got is not None and got["uid"] == vis._uid
    ctl.cancel_pick() if hasattr(ctl, "cancel_pick") else None
    sc.set_mode("select")
    ctl.pick = None
    # "still moves with its component": drag the visible wall's p2 grip.
    sc.clearSelection()
    vis.setSelected(True)
    qapp.processEvents()
    end = QPointF(vis._pt2)
    _drag(view, end, QPointF(end.x() + 500, end.y() + 300))
    assert (vis._pt2 - end).manhattanLength() > 100.0, "the grip did not move"
    assert (hidden._pt2 - vis._pt2).manhattanLength() < 1e-3, \
        "the hidden wall did not follow its coincident partner"
