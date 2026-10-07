"""constraint_paint — axes, glyph placement / hit / pixels, glyph hover glow,
glyph select, grip precedence and Delete (parametric-constraint-system.md
D3/D4, D11, D27, §10). Shown views, posted mouse events, pixel sampling."""
import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QColor, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d import constraint_paint as cp
from firepro3d import theme as th
from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.scale_manager import ScaleManager
from firepro3d.theme import M


@pytest.fixture
def be(qapp):
    """(view, scene) — shown Block Editor scene at 1 px / mm, centred."""
    sc = Model_Space(scene_role="block_editor")
    sc.scale_manager = ScaleManager()
    v = Model_View(sc)
    v.resize(800, 600)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.resetTransform()
    v.centerOn(0, 0)
    sc.set_mode("select")
    QApplication.processEvents()
    yield v, sc
    sc.clearSelection()
    sc.cleanup()
    v.close()
    v.deleteLater()
    QApplication.processEvents()


def _line(sc, a=(-100, 50), b=(100, 50)):
    ln = LineItem(QPointF(*a), QPointF(*b))
    sc.addItem(ln)
    sc._draw_lines.append(ln)
    return ln


def _horizontal(sc, ln):
    c = sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    assert c is not None
    QApplication.processEvents()       # settle any sceneRect growth / scroll
    return c


def _grab(v):
    v.viewport().repaint()
    QApplication.processEvents()
    img = v.viewport().grab().toImage()
    return img, img.devicePixelRatio()


def _move(v, vp):
    """A real hover move delivered through the viewport (no buttons)."""
    QApplication.sendEvent(v.viewport(), QMouseEvent(
        QEvent.Type.MouseMove, QPointF(vp), Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
    QApplication.processEvents()


def _px(img, dpr, x, y) -> QColor:
    return img.pixelColor(int(round(x * dpr)), int(round(y * dpr)))


def _dist(a, b: QColor) -> int:
    if isinstance(a, _Near):
        return min(_dist(c, b) for c in a.cols)
    return (abs(a.red() - b.red()) + abs(a.green() - b.green())
            + abs(a.blue() - b.blue()))


def _pt(p):
    return QPointF(p).toPoint()


# ── layout / hit ────────────────────────────────────────────────────────────

def test_glyph_sits_beside_its_edge_and_hits(be):
    v, sc = be
    ln = _line(sc)
    c = _horizontal(sc, ln)
    sc.constraint_ctl.show_all = True          # D32: Show Constraints ON
    lays = cp.glyph_layouts(v, sc.constraint_ctl)
    assert [cid for cid, _ in lays] == [c.id]
    rect = lays[0][1]
    box = M.CONSTRAINT_GLYPH_PX + 2 * M.CONSTRAINT_GLYPH_PAD_PX
    assert rect.width() == rect.height() == box == 20
    mid = v.mapFromScene(QPointF(0, 50))
    assert abs(rect.center().x() - mid.x()) <= 1
    assert abs(abs(rect.center().y() - mid.y()) - (12 + box / 2)) <= 1
    assert cp.glyph_at(v, sc.constraint_ctl, rect.center()) == c.id
    assert cp.glyph_at(v, sc.constraint_ctl, rect.center() + QPointF(40, 0)) is None


def test_glyph_on_rect_edge_sits_away_from_the_centroid(be):
    v, sc = be
    r = RectangleItem(QPointF(-80, -40), QPointF(80, 40))
    sc.addItem(r)
    sc._draw_rects.append(r)
    ctl = sc.constraint_ctl
    ctl.show_all = True                        # D32: Show Constraints ON
    top = ctl.add("horizontal", [{"uid": r._uid, "h": "top"}])
    bot = ctl.add("horizontal", [{"uid": r._uid, "h": "bottom"}])
    lays = dict(cp.glyph_layouts(v, ctl))
    top_y = v.mapFromScene(QPointF(0, -40)).y()
    bot_y = v.mapFromScene(QPointF(0, 40)).y()
    assert lays[top.id].bottom() < top_y              # above the top edge (outside)
    assert lays[bot.id].top() > bot_y                 # below the bottom edge (outside)
    assert abs((top_y - lays[top.id].center().y()) - 22) <= 1
    assert abs((lays[bot.id].center().y() - bot_y) - 22) <= 1


def test_two_glyphs_on_one_anchor_sit_side_by_side(be):
    v, sc = be
    ln = _line(sc)
    ctl = sc.constraint_ctl
    _horizontal(sc, ln)
    _horizontal(sc, ln)
    ctl.show_all = True                        # D32: Show Constraints ON
    (_, a), (_, b) = cp.glyph_layouts(v, ctl)
    assert a.top() == b.top()
    assert not a.intersects(b)
    assert b.left() - a.right() == pytest.approx(M.CONSTRAINT_GLYPH_GAP_PX, abs=1)


def test_show_all_off_hides_unselected_glyphs(be):
    """D32: with Show Constraints off (the default) and nothing selected, no
    glyph lays out or picks; the constraint itself is untouched."""
    v, sc = be
    ln = _line(sc)
    c = _horizontal(sc, ln)
    ctl = sc.constraint_ctl
    assert ctl.show_all is False
    ctl.show_all = True
    rect = cp.glyph_layouts(v, ctl)[0][1]
    ctl.show_all = False
    assert cp.glyph_layouts(v, ctl) == []
    assert cp.glyph_at(v, ctl, rect.center()) is None
    assert c in ctl.constraints


# ── pixels (D27) ────────────────────────────────────────────────────────────

def test_glyph_box_and_icon_pixels_render(be):
    v, sc = be
    ln = _line(sc)
    _horizontal(sc, ln)
    ctl = sc.constraint_ctl
    t = th.detect()
    ctl.show_all = False                       # D32: nothing selected -> none
    base, dpr = _grab(v)
    ctl.show_all = True
    img, dpr = _grab(v)
    rect = cp.glyph_layouts(v, ctl)[0][1]      # layout at grab time
    cy = rect.center().y()
    # 1 px line_strong border on the box's left column.
    border = t.color("line_strong")
    got = _px(img, dpr, rect.left(), cy)
    assert _dist(got, border) <= 24, (got.name(), border.name())
    assert _dist(_px(base, dpr, rect.left(), cy), border) > _dist(got, border)
    # surface fill in the 2 px pad between border and icon.
    assert _dist(_px(img, dpr, rect.left() + 1.5, cy), t.color("surface")) <= 24
    # The Horizontal icon (accent-only bar, constraint family D25) draws the
    # theme accent across the middle of the 16 px icon rect.
    accent = t.color("accent")
    pad = M.CONSTRAINT_GLYPH_PAD_PX
    inner = rect.adjusted(pad, pad, -pad, -pad)
    near = [_dist(_px(img, dpr, inner.left() + i + 0.5, inner.top() + j + 0.5), accent)
            for i in range(16) for j in range(16)]
    # The 0.96 px bar straddles two pixel rows at 16 px (half coverage), so
    # the bar pixels are a surface/accent blend: well toward accent vs base.
    base_near = min(_dist(_px(base, dpr, inner.left() + i + 0.5, inner.top() + j + 0.5),
                          accent) for i in range(16) for j in range(16))
    assert min(near) < 0.6 * base_near, (min(near), base_near)


def test_axes_paint_dash_dot_through_the_origin(be):
    v, sc = be
    img, dpr = _grab(v)
    o = v.mapFromScene(QPointF(0, 0))
    t = th.detect()
    on = _px(img, dpr, 5, o.y())                 # inside the first 12 px dash
    gap = _px(img, dpr, 13.5, o.y())             # the 4 px gap after it
    muted = t.color("muted")
    assert on != gap
    assert _dist(on, muted) < _dist(gap, muted)
    on_y = _px(img, dpr, o.x(), 5)               # Y axis
    gap_y = _px(img, dpr, o.x(), 13.5)
    assert _dist(on_y, muted) < _dist(gap_y, muted)


# ── hover / select / grip precedence (posted events) ───────────────────────

def test_glyph_hover_sets_hover_id_and_glows_its_target(be):
    v, sc = be
    ln = _line(sc)
    c = _horizontal(sc, ln)
    ctl = sc.constraint_ctl
    ctl.show_all = True                        # D32: Show Constraints ON
    rect = cp.glyph_layouts(v, ctl)[0][1]
    _move(v, QPointF(5, 5))
    assert ctl.hover_id is None
    probe = v.mapFromScene(QPointF(-60, 50))
    before, dpr = _grab(v)
    _move(v, rect.center())
    assert ctl.hover_id == c.id
    after, dpr = _grab(v)
    hover = th.detect().color("selection_hover")
    b = _px(before, dpr, probe.x(), probe.y() - 3)    # 3 px off the edge
    a = _px(after, dpr, probe.x(), probe.y() - 3)
    assert _dist(a, hover) + 30 < _dist(b, hover), (b.name(), a.name())
    # glyph border turns selection_hover
    g = _px(after, dpr, rect.left(), rect.center().y())
    assert _dist(g, hover) <= 40
    # leaving clears hover
    _move(v, QPointF(5, 5))
    assert ctl.hover_id is None


def test_glyph_click_selects_clears_items_and_item_select_clears_it(be):
    v, sc = be
    ln = _line(sc)
    other = _line(sc, (-100, -120), (100, -120))
    c = _horizontal(sc, ln)
    ctl = sc.constraint_ctl
    ln.setSelected(True)                       # D32: the line's glyph shows
    QApplication.processEvents()
    rect = cp.glyph_layouts(v, ctl)[0][1]
    QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, pos=_pt(rect.center()))
    QApplication.processEvents()
    assert ctl.selected_id == c.id
    assert sc.selectedItems() == []
    # D32: the selected constraint's glyph stays with its entity deselected.
    assert [cid for cid, _ in cp.glyph_layouts(v, ctl)] == [c.id]
    # glyph border is painted in the selection colour
    img, dpr = _grab(v)
    sel = th.detect().color("selection")
    assert _dist(_px(img, dpr, rect.left(), rect.center().y()), sel) <= 40
    # selecting an item drops the selected constraint
    other.setSelected(True)
    QApplication.processEvents()
    assert ctl.selected_id is None
    # an empty-canvas click drops it too
    ctl.select(c.id)
    QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, pos=QPointF(30, 30).toPoint())
    QApplication.processEvents()
    assert ctl.selected_id is None


def test_grip_under_the_glyph_wins(be):
    v, sc = be
    ln = _line(sc)
    c = _horizontal(sc, ln)
    ctl = sc.constraint_ctl
    ctl.show_all = True                        # D32: Show Constraints ON
    rect = cp.glyph_layouts(v, ctl)[0][1]
    # A second line whose end grip sits exactly on the glyph centre.
    g = v.mapToScene(_pt(rect.center()))
    other = _line(sc, (g.x(), g.y()), (g.x() + 150, g.y() + 90))
    other.setSelected(True)
    QApplication.processEvents()
    assert sc._live_manip().hit_handle(g)
    assert cp.glyph_at(v, ctl, rect.center()) is None
    QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, pos=_pt(rect.center()))
    QApplication.processEvents()
    assert ctl.selected_id is None
    assert other.isSelected()
    assert c in ctl.constraints


def test_glyph_click_then_delete_removes_only_the_constraint(be):
    v, sc = be
    ln = _line(sc)
    c = _horizontal(sc, ln)
    ln.setSelected(True)                       # D32: the line's glyph shows
    QApplication.processEvents()
    rect = cp.glyph_layouts(v, sc.constraint_ctl)[0][1]
    QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, pos=_pt(rect.center()))
    assert sc.constraint_ctl.selected_id == c.id
    assert sc.constraint_ctl.delete_selected() == 1
    assert sc.constraint_ctl.constraints == []
    assert sc.constraint_ctl.selected_id is None
    assert ln.scene() is sc and ln in sc._draw_lines


# ── Delete through the real MainWindow chokepoint ──────────────────────────

@pytest.fixture(scope="module")
def mw(qapp, tmp_path_factory):
    import os
    from firepro3d import snap_engine
    prev_qss, prev_font = qapp.styleSheet(), qapp.font()
    prev_appdata = os.environ.get("APPDATA")
    os.environ["APPDATA"] = str(tmp_path_factory.mktemp("appdata"))
    th.apply_app_font(qapp)
    qapp.setStyleSheet(th.build_app_qss(th.detect()))
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    import main as main_mod
    from firepro3d.view_3d import View3D
    main_mod.View3D = View3D
    w = main_mod.MainWindow()
    w.resize(1400, 850)
    w.show()
    QTest.qWaitForWindowExposed(w)
    QTest.qWait(200)
    yield w
    for i in reversed(range(w.central_tabs.count())):
        from firepro3d.block_editor import BlockEditorWidget
        ed = w.central_tabs.widget(i)
        if isinstance(ed, BlockEditorWidget):
            ed.editor_scene.clearSelection()
            w.block_editor_manager.close(ed)
    w.scene.clearSelection()
    w._modified = False
    w.close()
    w.deleteLater()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol
    qapp.setStyleSheet(prev_qss)
    qapp.setFont(prev_font)
    if prev_appdata is None:
        os.environ.pop("APPDATA", None)
    else:
        os.environ["APPDATA"] = prev_appdata


def test_delete_key_in_main_window_removes_only_the_selected_constraint(mw, qapp):
    ed = mw.block_editor_manager.open_new()
    qapp.processEvents()
    sc, v = ed.editor_scene, ed.view
    assert mw._active_scene() is sc
    v.resetTransform()                       # 1 px / mm: glyphs apart
    ln = _line(sc)
    keep = _line(sc, (-100, -150), (100, -150))
    c = _horizontal(sc, ln)
    k = _horizontal(sc, keep)
    sc.constraint_ctl.show_all = True          # D32: Show Constraints ON
    v.centerOn(0, 0)
    qapp.processEvents()
    lays = dict(cp.glyph_layouts(v, sc.constraint_ctl))
    QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton,
                     pos=_pt(lays[c.id].center()))
    qapp.processEvents()
    assert sc.constraint_ctl.selected_id == c.id
    geom = [(it._pt1, it._pt2) for it in (ln, keep)]
    mw.activateWindow()
    v.setFocus()
    qapp.processEvents()
    QTest.keyClick(v.viewport(), Qt.Key.Key_Delete)
    qapp.processEvents()
    assert [x.id for x in sc.constraint_ctl.constraints] == [k.id]
    assert sc.constraint_ctl.selected_id is None
    assert ln.scene() is sc and keep.scene() is sc
    assert ln in sc._draw_lines and keep in sc._draw_lines
    assert [(it._pt1, it._pt2) for it in (ln, keep)] == geom
    # A second Delete with nothing selected deletes nothing.
    mw._delete_if_not_editing()
    assert [x.id for x in sc.constraint_ctl.constraints] == [k.id]
    assert ln.scene() is sc


def test_moving_constrained_geometry_repaints_old_and_new_glyph_regions(be):
    """Glyphs sit outside item dirty regions (MinimalViewportUpdate): a
    geometry change must repaint where the glyph was and where it now is."""
    from PyQt6.QtCore import QObject, QEvent as _E
    from PyQt6.QtGui import QRegion
    v, sc = be
    ln = _line(sc)
    _horizontal(sc, ln)
    ctl = sc.constraint_ctl
    ctl.show_all = True                             # D32: Show Constraints ON
    _grab(v)                                        # a real paint records the region
    old = cp.glyph_layouts(v, ctl)[0][1].toAlignedRect()

    class _Spy(QObject):
        def __init__(self):
            super().__init__()
            self.region = QRegion()

        def eventFilter(self, obj, ev):
            if ev.type() == _E.Type.Paint:
                self.region = self.region.united(ev.region())
            return False

    spy = _Spy()
    v.viewport().installEventFilter(spy)
    try:
        ln._pt1, ln._pt2 = QPointF(-100, 150), QPointF(100, 150)
        ln.setLine(-100, 150, 100, 150)
        for _ in range(5):
            QApplication.processEvents()
            QTest.qWait(20)
    finally:
        v.viewport().removeEventFilter(spy)
    new = cp.glyph_layouts(v, ctl)[0][1].toAlignedRect()
    assert new != old
    # QRegion.contains(QRect) only tests overlap: require full coverage.
    for r in (new, old):
        assert spy.region.intersected(QRegion(r)) == QRegion(r), (
            spy.region.boundingRect(), r)


# ── CS2 D39 tint + glyph state borders (pixels, both themes) ────────────────

@pytest.fixture(params=["dark", "light"])
def themed(request, monkeypatch):
    t = th.DARK if request.param == "dark" else th.LIGHT
    monkeypatch.setattr(th, "detect", lambda: t)
    return t


class _Near:
    """The pixels within +-1 row/col of a stroke point; ``_dist`` against it
    is the BEST match (an anti-aliased stroke straddles two rows)."""
    def __init__(self, cols):
        self.cols = cols


def _line_px(img, dpr, v, a, b):
    """Pixels around the midpoint of scene segment a-b."""
    m = v.mapFromScene(QPointF((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
    return _Near([_px(img, dpr, m.x() + dx, m.y() + dy)
                  for dx in (-1, 0, 1) for dy in (-1, 0, 1)])


def test_tint_free_and_conflict_pixels(be, themed):
    v, sc = be
    t = themed
    _line(sc, (-200, -100), (-50, -100))                        # untouched -> free
    held = _line(sc, (-200, 100), (-50, 140))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": held._uid, "h": "edge"}])
    ctl.add("vertical", [{"uid": held._uid, "h": "edge"}])       # red -> conflict
    sc.clearSelection()
    img, dpr = _grab(v)
    assert _dist(_line_px(img, dpr, v, (-200, -100), (-50, -100)),
                 t.color("constraint_free")) <= 40
    y = held._pt1.y()
    assert _dist(_line_px(img, dpr, v, (-200, y), (-50, y)), t.color("danger")) <= 40


def test_tint_token_for_defined_is_ink(be, themed):
    """Paint-level mapping only (defined -> ink): with H/V alone a line cannot
    be fully defined (D36), so the cache is seeded; the real defined-state
    guard is test_constraint_controller::test_fully_defined_text_ins_at_origin."""
    from firepro3d.constraint_controller import SketchDiag
    v, sc = be
    t = themed
    ln = _line(sc, (-200, -100), (-50, -100))
    ctl = sc.constraint_ctl
    d = ctl.diagnostics()
    ctl._diag = (ctl._diag[0], SketchDiag(0, d.redundant, {ln._uid: 0}, d.conflict_uids))
    img, dpr = _grab(v)
    assert _dist(_line_px(img, dpr, v, (-200, -100), (-50, -100)), t.color("ink")) <= 40


def test_tint_off_restores_item_colour(be, themed):
    v, sc = be
    t = themed
    _line(sc, (-200, -100), (-50, -100))
    sc.constraint_ctl.show_status = False
    img, dpr = _grab(v)
    assert _dist(_line_px(img, dpr, v, (-200, -100), (-50, -100)),
                 t.color("constraint_free")) > 60


def test_selected_item_is_not_tinted(be, themed):
    v, sc = be
    t = themed
    ln = _line(sc, (-200, -100), (-50, -100))
    ln.setSelected(True)
    img, dpr = _grab(v)
    assert _dist(_line_px(img, dpr, v, (-200, -100), (-50, -100)),
                 t.color("constraint_free")) > 60


def test_glyph_border_red_and_amber(be, themed):
    v, sc = be
    t = themed
    ln = _line(sc)
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    amber = ctl.add("horizontal", [{"uid": ln._uid, "h": "p1"}, {"uid": ln._uid, "h": "p2"}])
    red = ctl.add("vertical", [{"uid": ln._uid, "h": "edge"}])
    assert amber.id in ctl.diagnostics().redundant and ctl.red == {red.id}
    ctl.show_all = True
    img, dpr = _grab(v)
    lays = dict(cp.glyph_layouts(v, ctl))
    for cid, tok in ((amber.id, "warn"), (red.id, "danger")):
        r = lays[cid]
        got = _Near([_px(img, dpr, r.left() + dx, r.center().y()) for dx in (0, 1, 2)])
        assert _dist(got, t.color(tok)) <= 48, (tok, [c.name() for c in got.cols])


def test_tinted_reference_line_keeps_its_dashes(be, themed):
    """User, 2026-10-02 (CS2 smoke): reference lines must keep looking like
    reference lines -- the tint follows their dash pattern (dash lengths in
    px unchanged), so the line reads blue AND dashed."""
    from firepro3d.geometry_2d import ReferenceLineItem
    v, sc = be
    t = themed
    rl = ReferenceLineItem(QPointF(-300, -150), QPointF(0, -150))
    sc.addItem(rl); sc._reference_lines.append(rl)
    sc.clearSelection()
    img, dpr = _grab(v)
    a, b = v.mapFromScene(QPointF(-290, -150)), v.mapFromScene(QPointF(-10, -150))
    bp = v.mapFromScene(QPointF(-150, -250))
    free, bg = t.color("constraint_free"), _px(img, dpr, bp.x(), bp.y())
    # MW-12 (H-MW-g retires CONSTRAINT_TINT_EXTRA_PX): the tint is the item
    # drawn in its state colour at its own width + AA, so an unsplit 1 px
    # reference line on a pixel boundary paints two part-intensity rows.
    # "Tinted" = every lit pixel a pure tint / background blend (no original
    # colour shows through), not a full-intensity match.
    from tests.mw_support import blend_spread
    on = gaps = other = 0
    for x in range(a.x(), b.x()):
        lit = [c for c in (_px(img, dpr, x, a.y() + dy) for dy in (-1, 0, 1))
               if _dist(c, bg) > 30]
        if not lit:
            gaps += 1
        elif all((blend_spread(c, bg, free) or 9) <= 0.12 for c in lit):
            on += 1
        else:
            other += 1
    span = b.x() - a.x()
    assert on > 0.3 * span, (on, span)          # tinted
    assert gaps > 0.15 * span, (gaps, span)     # still dashed
    assert other == 0, (other, span)            # no original colour


# ── CS3: point-on-curve glyph + glow ─────────────────────────────────────────

def test_point_on_curve_glyph_anchors_at_the_point_and_glows_the_circle(be):
    import math
    from PyQt6.QtCore import QRectF
    from firepro3d.geometry_2d import CircleItem
    v, sc = be
    circ = CircleItem(QPointF(0, 0), 50); sc.addItem(circ); sc._draw_circles.append(circ)
    ln = LineItem(QPointF(50, 0), QPointF(150, 60)); sc.addItem(ln); sc._draw_lines.append(ln)
    c = sc.constraint_ctl.add("point_on_curve", [{"uid": ln._uid, "h": "p1"},
                                                 {"uid": circ._uid, "h": "curve"}])
    assert c is not None
    by = sc.constraint_ctl.item_by_uid()
    a = cp._anchor(v, c, by)
    p = QPointF(v.mapFromScene(ln._pt1))
    assert math.hypot(a.x() - p.x(), a.y() - p.y()) < 40          # beside the point
    path = cp._refs_path(v, c.refs, by, QRectF(v.viewport().rect()),
                         QPointF(v.mapFromScene(QPointF(0, 0))))
    # The circle's full outline (the point's glow dot sits on its right rim).
    r, o = path.boundingRect(), QPointF(v.mapFromScene(circ._center))
    assert r.left() == pytest.approx(o.x() - circ._radius, abs=1.0)
    assert r.height() == pytest.approx(2 * circ._radius, abs=1.0)
