"""Guard tests for the block-polish slice-1 bug batch (2026-09-23).

* Deleting a selection must drop the manipulator frame (no stale bbox).
* ``Model_Space.select_items`` selects a batch with ONE selectionChanged.
* Block Editor import selects its result in one batch (was O(n^2)).
* Block Editor text is compiled into saved blocks.
* Import preview crop honours the preview rotation.
* Import preview pans freely at fit.
* Import rotation is NOT sticky across fresh dialog opens.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, QSettings, Qt, QPoint, QEvent
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QTabWidget

from firepro3d.model_space import Model_Space
from firepro3d.geometry_2d import LineItem, RectangleItem


def _add_line(scene, x1=0.0, y1=0.0, x2=1000.0, y2=0.0):
    it = LineItem(QPointF(x1, y1), QPointF(x2, y2))
    scene.addItem(it)
    scene._draw_lines.append(it)
    return it


# ── Delete leaves no stale manipulator frame ─────────────────────────────────

def test_delete_hides_manipulator_frame(qapp):
    sc = Model_Space()
    for make in (lambda: _add_line(sc),
                 lambda: _rect(sc)):
        it = make()
        sc.clearSelection()
        it.setSelected(True)
        assert sc._manipulator.isVisible()
        sc.delete_selected_items()
        assert it.scene() is None
        assert not sc._manipulator.isVisible(), (
            "manipulator frame must not outlive the deleted selection")


def _rect(sc):
    it = RectangleItem(QPointF(0, 0), QPointF(500, 500))
    sc.addItem(it)
    sc._draw_rects.append(it)
    return it


def test_delete_notifies_selection_listeners(qapp):
    sc = Model_Space()
    it = _add_line(sc)
    it.setSelected(True)
    hits = []
    sc.selectionChanged.connect(lambda: hits.append(len(sc.selectedItems())))
    sc.delete_selected_items()
    assert hits and hits[-1] == 0


# ── Batch selection ─────────────────────────────────────────────────────────

def test_select_items_emits_selection_changed_once(qapp):
    sc = Model_Space()
    items = [_add_line(sc, i * 10.0, 0, i * 10.0, 100) for i in range(50)]
    hits = []
    sc.selectionChanged.connect(lambda: hits.append(1))
    sc.select_items(items)
    assert set(sc.selectedItems()) == set(items)
    assert len(hits) == 1
    assert sc._manipulator.isVisible()


def test_block_editor_import_selects_in_one_batch(qapp):
    from firepro3d.block_editor import BlockEditorWidget
    w = BlockEditorWidget(Model_Space())
    geoms = [{"kind": "line", "x1": i, "y1": 0, "x2": i, "y2": 100,
              "layer": "0"} for i in range(200)]
    hits = []
    w.editor_scene.selectionChanged.connect(lambda: hits.append(1))
    added, skipped = w._add_imported_geoms(geoms, 1.0)
    assert added == 200
    assert len(w.editor_scene.selectedItems()) == 200
    assert len(hits) == 1, f"expected one selectionChanged, got {len(hits)}"


# ── Block Editor text is compiled into saved blocks ─────────────────────────

def test_block_editor_text_only_block_saves(qapp):
    from firepro3d.block_editor import BlockEditorManager
    from firepro3d.text_item import TextItem, TextAnnotationData
    project = Model_Space()
    mgr = BlockEditorManager(QTabWidget(), project)
    w = mgr.open_new()
    w.seed_from_dicts([TextItem(TextAnnotationData(
        text="A", x=0.0, y=0.0, height_mm=10.0)).to_dict()])
    defn = w.commit_block("T", "Lib", "Ser")
    assert defn is not None, "a text-only editor must save a block"
    assert [p.get("type") for p in defn.primitives] == ["text"]


# ── Import preview: crop honours rotation ───────────────────────────────────

def _dialog_with(geoms, rotation):
    from firepro3d.underlay_import_dialog import UnderlayImportDialog
    dlg = UnderlayImportDialog()
    dlg._all_geoms = geoms
    dlg._has_vectors = True
    dlg._layers = ["0"]
    dlg._base_x_edit.set_value_mm(0.0)
    dlg._base_y_edit.set_value_mm(0.0)
    dlg._set_rotation(rotation)
    dlg._populate_layer_list()
    dlg._rebuild_preview()
    return dlg


def _seg(x1, y1, x2, y2):
    return {"kind": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "layer": "0"}


def test_crop_rect_is_mapped_through_preview_rotation(qapp):
    # Two segments: A near +X, B near +Y (source coords).
    a = _seg(1000, 0, 1100, 0)
    b = _seg(0, 1000, 0, 1100)
    dlg = _dialog_with([a, b], 90.0)
    try:
        group = dlg._preview_geom_group
        # Where does A actually DRAW in the preview after rotation?
        pa = group.mapToScene(QPointF(1000, 0))   # A's start endpoint
        rect = QRectF(pa.x() - 20, pa.y() - 20, 40, 40)
        dlg._on_rubber_band(rect)      # the user dragged around what they SEE
        assert dlg._selected_indices == {0}, (
            f"crop must pick the geometry drawn under the rectangle, "
            f"got {dlg._selected_indices}")
    finally:
        dlg.deleteLater()


# ── Import preview: free pan at fit ─────────────────────────────────────────

def _drag(view, start, end, button):
    vp = view.viewport()
    for typ, pos, btns in (
            (QEvent.Type.MouseButtonPress, start, button),
            (QEvent.Type.MouseMove, end, button),
            (QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.NoButton)):
        ev = QMouseEvent(typ, QPointF(pos), QPointF(vp.mapToGlobal(pos)),
                         button, btns, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(vp, ev)


def test_preview_pans_at_fit(qapp):
    from PyQt6.QtTest import QTest
    dlg = _dialog_with([_seg(0, 0, 1000, 0), _seg(0, 0, 0, 1000)], 0.0)
    try:
        dlg.resize(1100, 700)
        dlg.show()
        QTest.qWaitForWindowExposed(dlg)
        dlg._fit_preview_to_content()
        view = dlg._preview_view
        vp_c = view.viewport().rect().center()
        before = view.mapToScene(vp_c)
        _drag(view, vp_c, vp_c + QPoint(120, 80), Qt.MouseButton.MiddleButton)
        after = view.mapToScene(vp_c)
        assert (after - before).manhattanLength() > 1.0, (
            "middle-drag must pan the preview even at fit")
    finally:
        dlg.close()
        dlg.deleteLater()


# ── Import rotation is not sticky across fresh opens ────────────────────────

def test_fresh_import_dialog_starts_at_zero_rotation(qapp):
    from firepro3d.underlay_import_dialog import UnderlayImportDialog
    s = QSettings("GV", "FirePro3D")
    s.setValue("UnderlayImport/rotation", 90.0)
    first = UnderlayImportDialog()
    first._set_rotation(45.0)
    first._save_settings()
    first.deleteLater()
    dlg = UnderlayImportDialog()
    try:
        assert dlg._get_rotation() == 0.0
    finally:
        dlg.deleteLater()


# ── Smoke round 1 (2026-09-23) ──────────────────────────────────────────────

def test_halo_highlight_drops_deleted_item(qapp):
    from PyQt6.QtGui import QTransform
    sc = Model_Space()
    it = _add_line(sc)
    sc.halo_update(QPointF(500.0, 0.0), 8.0, QTransform())
    assert sc.halo_item() is it
    it.setSelected(True)
    sc.delete_selected_items()          # cursor has NOT moved
    assert sc.halo_item() is None, "HALO must not keep painting a deleted item"


def test_crop_keeps_the_current_view(qapp):
    from PyQt6.QtTest import QTest
    dlg = _dialog_with([_seg(0, 0, 1000, 0), _seg(0, 0, 0, 1000)], 0.0)
    try:
        dlg.resize(1100, 700)
        dlg.show()
        QTest.qWaitForWindowExposed(dlg)
        dlg._fit_preview_to_content()
        view = dlg._preview_view
        view._apply_zoom(4.0)           # user zoomed in to crop a detail
        before = view.transform()
        dlg._on_rubber_band(QRectF(-50, -50, 100, 100))
        assert dlg._selected_indices == {0, 1}
        assert view.transform() == before, "crop must not re-fit the preview"
        dlg._clear_selection()
        assert view.transform() == before, "clearing a crop must not re-fit"
    finally:
        dlg.close()
        dlg.deleteLater()


def test_new_block_tab_retitles_and_rekeys_on_save(qapp):
    from firepro3d.block_editor import BlockEditorManager
    project = Model_Space()
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, project)
    w = mgr.open_new()
    _add_line(w.editor_scene)
    defn = w.commit_block("Pump", "Lib", "Ser")
    assert tabs.tabText(tabs.indexOf(w)) == "Block: Pump"
    # Re-opening the saved block focuses THIS editor, not a duplicate.
    assert mgr.open_for_definition(defn.id) is w
    assert tabs.count() == 1
    # A rename on a later save retitles again.
    w.commit_block("Pump 2", "Lib", "Ser")
    assert tabs.tabText(tabs.indexOf(w)) == "Block: Pump 2"


# ── Smoke round 3: import base point / insert-at-origin ─────────────────────

def _params(base, origin, rot=0.0, scale=2.0):
    from firepro3d.underlay_import_dialog import ImportParams
    p = ImportParams()
    p.geom_list = [_seg(10, 20, 60, 20), _seg(60, 20, 60, 80)]
    p.scale, p.base_x, p.base_y, p.rotation = scale, base[0], base[1], rot
    p.insert_at_origin = origin
    return p


def _vertex_at(w, pt, tol=1e-6):
    """True if some imported line has an endpoint at scene point *pt*."""
    for it in w.editor_scene._draw_lines:
        for q in (it.mapToScene(it.line().p1()), it.mapToScene(it.line().p2())):
            if abs(q.x() - pt[0]) < tol and abs(q.y() - pt[1]) < tol:
                return True
    return False


def test_insert_at_origin_lands_base_point_on_new_block_origin(qapp):
    from firepro3d.block_editor import BlockEditorWidget
    w = BlockEditorWidget(Model_Space())
    w.import_with_params(_params(base=(60, 20), origin=True))
    assert _vertex_at(w, (0.0, 0.0)), "picked base vertex must land on the origin"
    o = w.origin_point()
    assert (o.x(), o.y()) == (0.0, 0.0) and w._origin is not None, (
        "an empty editor's origin is pinned at the import base point")


def test_insert_at_origin_honours_a_pinned_origin(qapp):
    from firepro3d.block_editor import BlockEditorWidget
    w = BlockEditorWidget(Model_Space())
    w.set_origin_point(QPointF(100.0, 50.0))
    w.import_with_params(_params(base=(60, 20), origin=True, rot=90.0))
    assert _vertex_at(w, (100.0, 50.0))


def test_insert_off_places_base_point_where_the_user_clicks(qapp):
    from firepro3d.block_editor import BlockEditorWidget
    w = BlockEditorWidget(Model_Space())
    w.import_with_params(_params(base=(60, 20), origin=False))
    sc = w.editor_scene
    assert sc.mode == "move", "Off must hand the import to an interactive move"
    assert len(sc.selectedItems()) == 2
    click = QPointF(300.0, 200.0)
    sc._press_paste_move(None, click, click, None, None, None)   # the placing click
    assert _vertex_at(w, (300.0, 200.0)), "base vertex must follow to the click"
    assert sc.mode != "move"


def test_base_pick_on_rotated_preview_records_the_source_point(qapp):
    # Smoke round 3 dump: with the preview rotated 90 deg the picked base was
    # stored in ROTATED preview coords (y=4746 on a 2592-tall page), so the
    # import landed far from the picked feature.
    dlg = _dialog_with([_seg(100, 200, 400, 200), _seg(400, 200, 400, 500)], 90.0)
    try:
        group = dlg._preview_geom_group
        seen = group.mapToScene(QPointF(400, 200))      # where the corner DRAWS
        before = group.sceneTransform()
        dlg._on_point_picked(seen)
        assert (round(dlg._base_x_edit.value_mm(), 6),
                round(dlg._base_y_edit.value_mm(), 6)) == (400.0, 200.0)
        assert dlg._preview_geom_group.sceneTransform() == before, (
            "picking a base point must not move the preview")
        h, v = dlg._base_markers
        mark = QPointF(v.line().x1(), h.line().y1())
        assert (mark - seen).manhattanLength() < 1e-6, "marker sits on the pick"
    finally:
        dlg.deleteLater()
