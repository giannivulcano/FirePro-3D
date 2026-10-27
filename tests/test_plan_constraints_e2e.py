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
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication

import firepro3d.paper_display as pd

from firepro3d.gridline import GridlineItem
from firepro3d.wall import WallSegment
from tests.test_build_editor_tabs import _editors, _plan_index, mw  # noqa: F401
from tests.test_constraint_e2e import _click, _drag


@pytest.fixture
def plan(mw, qapp):
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    qapp.processEvents()
    sc, view = mw.scene, mw.view
    view.resetTransform()
    view.centerOn(1500, 0)
    yield sc, view
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
    sc.set_mode("select")
    sc.clearSelection()
    w.setSelected(True)                              # grips visible
    qapp.processEvents()
    end = QPointF(w._pt2)
    _drag(view, end, QPointF(end.x() + 900, end.y() + 600))
    assert _len(w) == pytest.approx(L, abs=1e-6)      # length held
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
    assert w._pt1.x() - gl._origin.x() == pytest.approx(1000.0, abs=1e-6)   # offset held


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
