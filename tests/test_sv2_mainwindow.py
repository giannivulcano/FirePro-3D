"""SV2 Task 9 -- real-MainWindow guards: G1 sheet half, G3, G5, G6 SV2 half
(schematics.md D-S7 / D-S8 / D-S10 / D-S11a / D-S12)."""
from __future__ import annotations

import fitz
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QColor, QDragEnterEvent, QDragMoveEvent, QDropEvent,
                         QImage, QPainter)
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog

from firepro3d import paper_display as pd
from firepro3d.block_editor import BlockEditorWidget, BlockSaveDialog
from firepro3d.geometry_2d import LineItem
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from firepro3d.paper_space import SheetViewPropertiesDialog, sheet_page_mm
from firepro3d.project_browser import _ROLE_NAME, _ROLE_TYPE
from tests.test_sv1_schematics_mainwindow import (  # noqa: F401 (fixture)
    _fake_exec, _new_saved_schematic, mw)

PT = 25.4 / 72.0


def _leaf_item(win, block_id):
    stack = [win.project_browser._schem_root]
    while stack:
        it = stack.pop()
        if (it.data(0, _ROLE_TYPE) == "schematic"
                and it.data(0, _ROLE_NAME) == block_id):
            return it
        stack.extend(it.child(i) for i in range(it.childCount()))
    return None


def _drop_on_sheet(win, monkeypatch, block_id):
    """Drag the REAL browser leaf payload onto the paper view's centre."""
    monkeypatch.setattr(SheetViewPropertiesDialog, "exec",
                        lambda self: QDialog.DialogCode.Accepted)
    mime = win.project_browser._tree.mimeData([_leaf_item(win, block_id)])
    view = win.paper_space_widget.view
    view.resize(900, 700)
    ps = win.paper_space_widget.paper_scene
    pw, ph = sheet_page_mm(ps.sheet)
    view.centerOn(pw / 2, ph / 2)
    pt = view.mapFromScene(QPointF(pw / 2, ph / 2))
    act = Qt.DropAction.CopyAction
    vp = view.viewport()
    for ev in (QDragEnterEvent(pt, act, mime, Qt.MouseButton.LeftButton,
                               Qt.KeyboardModifier.NoModifier),
               QDragMoveEvent(pt, act, mime, Qt.MouseButton.LeftButton,
                              Qt.KeyboardModifier.NoModifier),
               QDropEvent(QPointF(pt), act, mime, Qt.MouseButton.LeftButton,
                          Qt.KeyboardModifier.NoModifier)):
        QApplication.sendEvent(vp, ev)
    QApplication.processEvents()
    vps = [v for v in ps._viewports if v.data.source_view_type == "schematic"]
    assert len(vps) == 1
    return vps[0]


def _interior_ink(win, vp):
    """Non-white pixels strictly inside the viewport box (border excluded)."""
    d = vp.data
    inner = QRectF(d.x + 1.5, d.y + 1.5, d.w - 3.0, d.h - 3.0)
    img = QImage(int(inner.width() * 10), int(inner.height() * 10),
                 QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    win.paper_space_widget.paper_scene.render(
        p, QRectF(0, 0, img.width(), img.height()), inner)
    p.end()
    return sum(1 for y in range(img.height()) for x in range(img.width())
               if QColor(img.pixel(x, y)).name() != "#ffffff")


# The SV1 helper's schematic: line (0,0)-(100,0) + Sym (line 0..10 along x)
# nested at (50, 20) -> pen-free bounds (0,0)-(100,20); pad 2 -> 104 x 24.

def test_g3_drop_is_nts_sized_to_extent(mw, monkeypatch):
    w, defn, _ = _new_saved_schematic(mw, monkeypatch)
    vp = _drop_on_sheet(mw, monkeypatch, defn.id)
    assert vp.data.scale == 0.0
    assert vp.data.title == ""                         # live name
    assert vp.display_title() == "Riser A"
    assert (vp.data.w, vp.data.h) == pytest.approx((104.0, 24.0))
    assert vp.manip_capabilities() == {"translate", "scale"}


def test_g6_italics_follow_placement(mw, monkeypatch):
    w, defn, _ = _new_saved_schematic(mw, monkeypatch)
    assert not _leaf_item(mw, defn.id).font(0).italic()
    vp = _drop_on_sheet(mw, monkeypatch, defn.id)
    assert _leaf_item(mw, defn.id).font(0).italic()
    mw.paper_space_widget.paper_scene.remove_viewport(vp)
    assert not _leaf_item(mw, defn.id).font(0).italic()


def test_g3_edit_and_save_refits_every_viewport(mw, monkeypatch):
    w, defn, _ = _new_saved_schematic(mw, monkeypatch)
    vp = _drop_on_sheet(mw, monkeypatch, defn.id)
    w._add_primitive(LineItem(QPointF(0, 0), QPointF(200, 0)))
    w.editor_scene.push_undo_state()
    monkeypatch.setattr(BlockSaveDialog, "exec", _fake_exec("Riser A"))
    assert w.save(mw) is not None
    assert (vp.data.w, vp.data.h) == pytest.approx((104.0, 24.0))   # NTS box
    assert vp._effective_crop() == QRectF(-4, -4, 208, 28)          # content


def test_g6_rename_retitles_viewport(mw, monkeypatch):
    import firepro3d.themed_message as tm
    w, defn, _ = _new_saved_schematic(mw, monkeypatch)
    vp = _drop_on_sheet(mw, monkeypatch, defn.id)
    monkeypatch.setattr(tm, "themed_input_text",
                        lambda *a, **k: ("Riser B", True))
    ps = mw.paper_space_widget.paper_scene
    # Qt only processes dirty regions for a visible view: show the sheet.
    mw.show()
    QTest.qWaitForWindowExposed(mw)
    mw._activate_paper_sheet()                         # real sheet tab
    assert mw.paper_space_widget.view.isVisible()
    QApplication.processEvents()                       # flush drop repaints
    regions = []
    ps.changed.connect(regions.extend)
    mw.project_browser.renameSchematic.emit(defn.id)
    QApplication.processEvents()                       # scene.changed is queued
    ps.changed.disconnect(regions.extend)
    assert vp.display_title() == "Riser B"
    # display_title() reads the name live at paint time, so the retitle only
    # reaches the screen if the rename schedules a repaint over the viewport
    # (title bubble included) -- the observable effect of the refresh wiring.
    box = vp.sceneBoundingRect()
    assert any(QRectF(r).intersects(box) for r in regions), (regions, box)


def test_go_to_view_opens_schematic_editor(mw, monkeypatch):
    w, defn, _ = _new_saved_schematic(mw, monkeypatch)
    vp = _drop_on_sheet(mw, monkeypatch, defn.id)
    mw._activate_paper_sheet()                         # start on the sheet tab
    assert mw.central_tabs.currentWidget() is mw.paper_space_widget
    vp.navigate_requested.emit("schematic", defn.id)
    cur = mw.central_tabs.currentWidget()
    assert isinstance(cur, BlockEditorWidget) and cur._edit_block_id == defn.id


def test_g1_sheet_round_trip_renders(mw, monkeypatch, tmp_path):
    w, defn, _ = _new_saved_schematic(mw, monkeypatch)
    vp = _drop_on_sheet(mw, monkeypatch, defn.id)
    ps = mw.paper_space_widget.paper_scene
    ps.remove_viewport(vp)                             # one paper step
    assert not [v for v in ps._viewports
                if v.data.source_view_type == "schematic"]
    ps.undo_stack.undo()
    vp = next(v for v in ps._viewports
              if v.data.source_view_type == "schematic")
    for ed in mw.block_editor_manager.open_editors():
        ed._mark_clean()
    path = tmp_path / "sv2.fpd"
    mw.scene.save_to_file(str(path))
    mw._apply_loaded_file(str(path))
    ps = mw.paper_space_widget.paper_scene
    vps = [v for v in ps._viewports if v.data.source_view_type == "schematic"]
    assert len(vps) == 1 and not vps[0]._placeholder
    assert vps[0].data.source_view_name == defn.id
    assert _interior_ink(mw, vps[0]) > 50


def test_g3_pdf_strokes_weights_and_nts(mw, monkeypatch, tmp_path):
    from firepro3d import paper_export
    save_paper_color_mode(PaperColorMode.BW)
    w, defn, _ = _new_saved_schematic(mw, monkeypatch)
    vp = _drop_on_sheet(mw, monkeypatch, defn.id)
    d = vp.data
    out = tmp_path / "sv2.pdf"
    paper_export.export_pdf([mw._sheet], mw._view_resolver, str(out), dpi=300)
    cats = pd.load_paper_categories()
    constr = pd.resolve_line_weight_mm(cats["Construction"]["line_weight"])
    blocks = pd.resolve_line_weight_mm(cats["Blocks"]["line_weight"])
    raw, nested = [], []
    doc = fitz.open(str(out))
    try:
        page = doc[0]
        for dr in page.get_drawings():
            if "s" not in (dr.get("type") or ""):
                continue
            for it in dr["items"]:
                if it[0] != "l":
                    continue
                a, b = it[1], it[2]
                x0, y0, x1, y1 = a.x * PT, a.y * PT, b.x * PT, b.y * PT
                inside = (d.x + 1 < min(x0, x1) and max(x0, x1) < d.x + d.w - 1
                          and d.y + 1 < min(y0, y1)
                          and max(y0, y1) < d.y + d.h - 1)
                if not inside or abs(y0 - y1) > 0.01:
                    continue
                length = abs(x1 - x0)
                width = dr["width"] * PT
                # fit = 1 paper mm / model mm: raw line 100 mm, nested 10 mm.
                if abs(length - 100.0) < 0.5:
                    raw.append(width)
                elif abs(length - 10.0) < 0.5:
                    nested.append(width)
        text = page.get_text()
    finally:
        doc.close()
    assert raw and all(abs(wd - constr) < 0.01 for wd in raw), (raw, constr)
    assert nested and all(abs(wd - blocks) < 0.01 for wd in nested), (nested, blocks)
    assert "NTS" in text


def test_g5_delete_placed_refused_then_allowed(mw, monkeypatch):
    import firepro3d.themed_message as tm
    w, defn, _ = _new_saved_schematic(mw, monkeypatch)
    vp = _drop_on_sheet(mw, monkeypatch, defn.id)
    infos = []
    monkeypatch.setattr(tm, "themed_confirm", lambda *a, **k: True)
    monkeypatch.setattr(tm, "themed_info", lambda *a, **k: infos.append(a))
    mw.project_browser.deleteSchematic.emit(defn.id)
    assert mw.scene.get_block_definition(defn.id) is not None
    assert infos and mw._sheet.number in infos[-1][2]
    assert defn.id in mw.schematic_scenes.live_ids()
    mw.paper_space_widget.paper_scene.remove_viewport(vp)
    mw.project_browser.deleteSchematic.emit(defn.id)
    assert mw.scene.get_block_definition(defn.id) is None
    assert defn.id not in mw.schematic_scenes.live_ids()   # disposed
