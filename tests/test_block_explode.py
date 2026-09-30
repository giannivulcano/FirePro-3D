"""Explode a block instance in the Block Editor (AC6, AC7)."""
import math
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_instance import BlockInstance
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


@pytest.fixture(scope="module")
def _main_window_singleton(qapp, tmp_path_factory):
    """Module-scoped MainWindow (test_modify_tools_ribbon.py pattern; the
    autosave path is redirected so a real recovery file can't pop a modal)."""
    from PyQt6.QtTest import QTest
    import main as _main_module
    from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
    _main_module.View3D = View3D
    from main import MainWindow
    recovery = str(tmp_path_factory.mktemp("autosave") / "recovery.FPD")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(MainWindow, "_autosave_path", staticmethod(lambda: recovery))
        win = MainWindow()
        win.show()
        QTest.qWaitForWindowExposed(win)
        yield win
        win._modified = False
        win.close()
        win.deleteLater()


@pytest.fixture
def main_window(_main_window_singleton):
    yield _main_window_singleton


def _forget_defs(proj, *defs):
    """Drop test definitions from the shared MainWindow scene (singleton hygiene)."""
    for d in defs:
        proj._block_definitions.pop(d.id, None)
    proj.blockDefinitionsChanged.emit()


def _proj_and_editor(*defs):
    from firepro3d.block_editor import BlockEditorWidget
    proj = Model_Space()
    for d in defs:
        proj.register_block_definition(d)
    w = BlockEditorWidget(proj)
    return proj, w, w.editor_scene


def _line_def(name, p1, p2, origin=(0.0, 0.0), extra=()):
    return BlockDefinition.new(name=name, library="L", series="S", origin=origin,
                               primitives=[LineItem(QPointF(*p1), QPointF(*p2)).to_dict(), *extra])


def _render(scene):
    img = QImage(500, 500, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.black)
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, 500, 500), QRectF(-250, -250, 500, 500))
    p.end()
    return img


def _lit(img):
    return {(x, y) for x in range(0, 500, 5) for y in range(0, 500, 5)
            if QColor(img.pixel(x, y)).lightness() > 60}


def test_explode_matches_the_instance_exactly_and_undoes(qapp):
    b = _line_def("B", (10, 0), (110, 0), origin=(10.0, 0.0))
    proj, w, es = _proj_and_editor(b)
    try:
        inst = es.place_block_instance(b.id, (20.0, 30.0), rotation=30.0)
        es.push_undo_state()
        before = _render(es)
        inst.setSelected(True)
        new = es.explode_selected_blocks()      # the real path: select + one undo step
        ln = [i for i in new if isinstance(i, LineItem)][0]
        c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
        # origin-relative (0,0)->(100,0) rotated 30° Y-up CCW, placed at (20,30)
        assert abs(ln._pt1.x() - 20) < 1e-6 and abs(ln._pt1.y() - 30) < 1e-6
        assert abs(ln._pt2.x() - (20 + 100 * c)) < 1e-6
        assert abs(ln._pt2.y() - (30 - 100 * s)) < 1e-6
        assert inst.scene() is None and all(i.isSelected() for i in new)
        es.clearSelection()     # selection highlight differs by type; compare geometry
        assert len(_lit(_render(es)) ^ _lit(before)) <= 6      # same pixels (AA fringe)
        es.undo()
        assert len(es._block_instances) == 1 and es._draw_lines == []
    finally:
        es.cleanup()


def _every_primitive():
    from firepro3d import geometry_2d as g
    from firepro3d.text_item import TextAnnotationData, TextItem
    out = []
    r = g.RectangleItem(QPointF(0, 0), QPointF(60, 30)); r.set_angle(15)
    out.append(r.to_dict())
    out.append(g.CircleItem(QPointF(-40, 20), 15).to_dict())
    out.append(g.ArcItem(QPointF(40, -40), 25, 10, 200).to_dict())
    p = g.PolylineItem(QPointF(-80, -60))
    p.append_point(QPointF(-40, -90)); p.append_point(QPointF(-10, -60))
    out.append(p.to_dict())
    out.append(g.RegularPolygonItem(QPointF(90, 40), 5, 20).to_dict())
    out.append(g.EllipseItem(QPointF(-90, 60), 25, 10, 20).to_dict())
    out.append(g.SplineItem([QPointF(0, 80), QPointF(30, 110),
                             QPointF(60, 70), QPointF(90, 100)]).to_dict())
    tx = TextItem(TextAnnotationData(text="AB", x=-60, y=100, height_mm=15,
                                     color="#ffffff"))
    tx.set_angle(20)
    out.append(tx.to_dict())
    return out


def _lit_all(img):
    return {(x, y) for x in range(500) for y in range(500)
            if QColor(img.pixel(x, y)).lightness() > 60}


@pytest.mark.parametrize("answer", ["level", "all"])
def test_explode_matches_every_primitive_type_and_nesting(qapp, monkeypatch, answer):
    """Every primitive type + a rotated nested block, origin-shifted, rotated
    30° — the exploded pixels equal the placed instance's own render."""
    from firepro3d import geometry_2d as g
    c = _line_def("C", (0, 0), (0, 50), extra=[g.CircleItem(QPointF(10, 10), 8).to_dict()])
    b = BlockDefinition.new(
        name="B", library="L", series="S", origin=(10.0, 5.0),
        primitives=_every_primitive() + [{"type": "block_instance", "block_id": c.id,
                                          "pos": [100, -60], "rotation": 45.0}])
    proj, w, es = _proj_and_editor(c, b)
    try:
        inst = es.place_block_instance(b.id, (20.0, 30.0), rotation=30.0)
        before = _lit_all(_render(es))
        inst.setSelected(True)
        monkeypatch.setattr("firepro3d.themed_message.themed_choice",
                            lambda *a, **k: answer)
        new = es.explode_selected_blocks()
        assert len(new) >= 9 and inst.scene() is None
        es.clearSelection()
        diff = before ^ _lit_all(_render(es))
        assert len(before) > 800 and len(diff) <= 25, sorted(diff)[:20]   # AA fringe only
    finally:
        es.cleanup()


def test_explode_one_level_keeps_nested_blocks_live(qapp):
    c = _line_def("C", (0, 0), (0, 50))
    b = _line_def("B", (0, 0), (100, 0),
                  extra=[{"type": "block_instance", "block_id": c.id,
                          "pos": [100, 0], "rotation": 90.0}])
    proj, w, es = _proj_and_editor(c, b)
    try:
        inst = es.place_block_instance(b.id, (0.0, 0.0), rotation=0.0)
        from firepro3d.block_explode import explode_instances
        new = explode_instances(es, [inst], flatten=False)
        nested = [i for i in new if isinstance(i, BlockInstance)]
        assert [(n.block_id, n.block_pos(), n.block_rotation()) for n in nested] == \
               [(c.id, (100.0, 0.0), 90.0)]
        flat = explode_instances(es, nested, flatten=True)
        assert not any(isinstance(i, BlockInstance) for i in flat)
    finally:
        es.cleanup()


@pytest.mark.parametrize("answer,expect_blocks", [("level", 1), ("all", 0)])
def test_prompt_choice_controls_depth(qapp, monkeypatch, answer, expect_blocks):
    c = _line_def("C", (0, 0), (0, 50))
    b = _line_def("B", (0, 0), (100, 0),
                  extra=[{"type": "block_instance", "block_id": c.id,
                          "pos": [100, 0], "rotation": 0.0}])
    proj, w, es = _proj_and_editor(c, b)
    try:
        inst = es.place_block_instance(b.id, (0.0, 0.0))
        inst.setSelected(True)
        asked = []
        monkeypatch.setattr("firepro3d.themed_message.themed_choice",
                            lambda *a, **k: asked.append(a) or answer)
        es.explode_selected_blocks()
        assert len(asked) == 1
        assert len(es._block_instances) == expect_blocks
    finally:
        es.cleanup()


def test_explode_ignores_non_blocks_and_needs_no_prompt_without_nesting(qapp, monkeypatch):
    b = _line_def("B", (0, 0), (100, 0))
    proj, w, es = _proj_and_editor(b)
    try:
        loose = LineItem(QPointF(0, 200), QPointF(50, 200))
        es.addItem(loose); es._draw_lines.append(loose)
        inst = es.place_block_instance(b.id, (0.0, 0.0))
        loose.setSelected(True); inst.setSelected(True)
        monkeypatch.setattr("firepro3d.themed_message.themed_choice",
                            lambda *a, **k: pytest.fail("no prompt without nesting"))
        es.explode_selected_blocks()
        assert es._block_instances == [] and loose in es._draw_lines
        assert len(es._draw_lines) == 2
    finally:
        es.cleanup()


def test_explode_button_enabled_only_with_a_block_selected(qapp, main_window):
    proj = main_window.scene
    b = _line_def("B", (0, 0), (100, 0))
    proj.register_block_definition(b)
    w = main_window.block_editor_manager.open_new()
    QApplication.processEvents()
    try:
        es = w.editor_scene
        btn = main_window._be_modify_buttons["Explode"]
        assert btn.toolTip() and not btn.icon().isNull()
        ln = LineItem(QPointF(0, 200), QPointF(50, 200)); es.addItem(ln); es._draw_lines.append(ln)
        ln.setSelected(True); QApplication.processEvents()
        assert not btn.isEnabled()
        inst = es.place_block_instance(b.id, (0.0, 0.0)); inst.setSelected(True)
        QApplication.processEvents()
        assert btn.isEnabled()
        btn.click(); QApplication.processEvents()
        assert es._block_instances == []
        assert inst.scene() is None and any(isinstance(i, LineItem) and i.isSelected()
                                            and i is not ln for i in es.items())
    finally:
        w._modified = False
        main_window.block_editor_manager.close(w)
        _forget_defs(proj, b)
        QApplication.processEvents()


def test_right_click_menus_offer_edit_block_and_explode_in_editor(qapp):
    b = _line_def("B", (0, 0), (100, 0))
    proj, w, es = _proj_and_editor(b)
    try:
        inst = es.place_block_instance(b.id, (0.0, 0.0))
        from firepro3d.entity_context_menu import build_entity_context_menu
        m = build_entity_context_menu([inst], inst, scene=es,
                                      on_edit_block=lambda: None, on_explode=lambda: None)
        labels = [a.text() for a in m.actions()]
        assert "Edit Block" in labels and "Explode" in labels
        assert es._find_entity_at(QPointF(50, 0)) is inst       # entity path reaches blocks
        inst.setSelected(True)
        gm = w.view._build_plan_context_menu(es, [inst], "select")
        acts = {a.text(): a for a in gm.actions()}
        assert {"Edit Block", "Explode"} <= set(acts)
        asked = []
        es.blockEditRequested.connect(asked.append)
        acts["Edit Block"].trigger()
        assert asked == [b.id]
        acts["Explode"].trigger()
        assert es._block_instances == [] and inst.scene() is None
    finally:
        es.cleanup()


def test_entity_menu_actions_explode_and_request_edit(qapp, monkeypatch):
    """The scene's own entity menu (the path a right-click on a block takes)
    carries working Edit Block / Explode actions."""
    b = _line_def("B", (0, 0), (100, 0))
    proj, w, es = _proj_and_editor(b)
    try:
        inst = es.place_block_instance(b.id, (0.0, 0.0))
        inst.setSelected(True)
        menus = []
        from PyQt6.QtWidgets import QMenu
        monkeypatch.setattr(QMenu, "exec", lambda self, *a: menus.append(self))
        es._show_entity_context_menu(inst, None)
        acts = {a.text(): a for a in menus[0].actions()}
        asked = []
        es.blockEditRequested.connect(asked.append)
        acts["Edit Block"].trigger()
        assert asked == [b.id]
        acts["Explode"].trigger()
        assert es._block_instances == [] and inst.scene() is None
    finally:
        es.cleanup()


def test_plan_scene_menus_do_not_offer_explode(qapp):
    """Smoke 1: the plan offers Edit Block on a placed block (entity path and
    the one-block selection fallback) but never Explode (containment C1)."""
    from firepro3d.geometry_2d import CircleItem
    sc = Model_Space()
    # A block WITH AREA (a circle) so items(pos) really hits it.
    b = _line_def("B", (0, 0), (100, 0),
                  extra=[CircleItem(QPointF(50, 0), 20).to_dict()])
    sc.register_block_definition(b)
    inst = sc.place_block_instance(b.id, (0.0, 0.0))
    inst.setSelected(True)
    assert inst in sc.items(QPointF(50, 0))               # the exact-hit path sees it
    from firepro3d.model_view import Model_View
    v = Model_View(sc)
    gm = v._build_plan_context_menu(sc, [inst], "select")
    acts = {a.text(): a for a in gm.actions()}
    assert "Explode" not in acts
    assert "Edit Block" in acts
    asked = []
    sc.blockEditRequested.connect(asked.append)
    acts["Edit Block"].trigger()
    assert asked == [b.id]
    assert sc._find_entity_at(QPointF(50, 0)) is inst     # plan entity path reaches blocks
    sc.explode_selected_blocks()
    assert sc._block_instances == [inst]                  # C1: never explodes on a plan
    sc.cleanup()


# ── Plan (Model Space) right-click → Edit Block (smoke round 1) ───────────

def _plan_view(main_window):
    """The shown plan Model_View of the MainWindow's project scene."""
    from firepro3d.model_view import Model_View
    from PyQt6.QtTest import QTest
    v = main_window.central_tabs.currentWidget()
    if not (isinstance(v, Model_View) and v.scene() is main_window.scene):
        v = next(w for w in main_window.scene.views()
                 if isinstance(w, Model_View) and w.isVisible())
    QTest.qWaitForWindowExposed(v.window())
    return v


def _plan_right_click(view, scene_pt, monkeypatch):
    """Send a real QContextMenuEvent to *view*; return the captured menu."""
    from PyQt6.QtGui import QContextMenuEvent
    from PyQt6.QtWidgets import QMenu
    menus = []
    monkeypatch.setattr(QMenu, "exec", lambda self, *a: menus.append(self))
    vp = view.viewport()
    pt = view.mapFromScene(scene_pt)
    QApplication.sendEvent(vp, QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse, pt, vp.mapToGlobal(pt)))
    QApplication.processEvents()
    return menus[-1] if menus else None


# Far from the default grid seed so only the test geometry is near the click.
_FAR = (987_000.0, 913_000.0)


class _PlanBlock:
    """Place a block on the MainWindow plan, frame it 1:1, clean up after."""

    def __init__(self, main_window, defn, loose=None):
        self.mw, self.defn, self.loose = main_window, defn, loose
        self.sc = main_window.scene

    def __enter__(self):
        self.sc.clearSelection()
        self.sc.register_block_definition(self.defn)
        self.inst = self.sc.place_block_instance(self.defn.id, _FAR)
        if self.loose is not None:
            self.sc.addItem(self.loose); self.sc._draw_lines.append(self.loose)
        from PyQt6.QtTest import QTest
        self.view = _plan_view(self.mw)
        QTest.qWait(250)        # let MainWindow's deferred startup fits land first
        self._t = self.view.transform()
        self._c = self.view.mapToScene(self.view.viewport().rect().center())
        self.view.resetTransform(); self.view.centerOn(_FAR[0] + 50, _FAR[1])
        QApplication.processEvents()
        assert self.view.transform().m11() == 1.0     # 1 px = 1 mm framing held
        return self

    def at(self, dx, dy):
        return QPointF(_FAR[0] + dx, _FAR[1] + dy)

    def __exit__(self, *exc):
        mgr = self.mw.block_editor_manager
        for w in list(mgr.open_editors()):
            w._modified = False
            mgr.close(w)
        for it in (self.inst, self.loose):
            if it is not None and it.scene() is self.sc:
                self.sc.removeItem(it)
        if self.inst in self.sc._block_instances:
            self.sc._block_instances.remove(self.inst)
        if self.loose is not None and self.loose in self.sc._draw_lines:
            self.sc._draw_lines.remove(self.loose)
        _forget_defs(self.sc, self.defn)
        self.mw.central_tabs.setCurrentWidget(self.view)
        self.view.setTransform(self._t); self.view.centerOn(self._c)
        QApplication.processEvents()


def test_plan_right_click_on_a_block_offers_edit_block_and_opens_its_editor(
        qapp, main_window, monkeypatch):
    """Guard (a): a block WITH AREA on the plan — a real right-click selects
    it and shows the entity menu with Edit Block (no Explode); triggering it
    opens a seeded Block Editor tab for that block."""
    from firepro3d.geometry_2d import CircleItem
    b = _line_def("PlanB", (0, 0), (100, 0),
                  extra=[CircleItem(QPointF(50, 0), 20).to_dict()])
    with _PlanBlock(main_window, b) as pb:
        assert pb.inst in pb.sc.items(pb.at(50, 10))
        menu = _plan_right_click(pb.view, pb.at(50, 10), monkeypatch)
        assert menu is not None
        acts = {a.text(): a for a in menu.actions()}
        assert "Edit Block" in acts and "Explode" not in acts
        assert pb.inst.isSelected()
        n_tabs = main_window.central_tabs.count()
        acts["Edit Block"].trigger(); QApplication.processEvents()
        assert main_window.central_tabs.count() == n_tabs + 1
        w = main_window.central_tabs.currentWidget()
        assert getattr(w, "_edit_block_id", None) == b.id
        assert len(w.gather_primitives()) == 2                 # seeded (line + circle)
        # A second Edit Block focuses the open tab (no duplicate).
        acts["Edit Block"].trigger(); QApplication.processEvents()
        assert main_window.central_tabs.count() == n_tabs + 1


def test_plan_right_click_resolves_a_line_only_block_via_nearest_pick(
        qapp, main_window, monkeypatch):
    """Guard (b): a line-only block (zero-area shape) resolves through the
    HALO nearest-pick fallback on the plan too."""
    b = _line_def("PlanLine", (0, 0), (100, 0))
    with _PlanBlock(main_window, b) as pb:
        pt = pb.at(50, 4.0)
        assert pb.inst not in pb.sc.items(pt)                  # only HALO reaches it
        assert pb.sc._find_entity_at(pt) is pb.inst
        menu = _plan_right_click(pb.view, pt, monkeypatch)
        labels = {a.text() for a in menu.actions()}
        assert pb.inst.isSelected()
        assert "Edit Block" in labels and "Explode" not in labels


def test_plan_right_click_a_nearer_loose_line_beats_the_block(
        qapp, main_window, monkeypatch):
    """Guard (c): 6 mm from a loose line, 14 mm from a line-only block — the
    line is nearest, so the block is neither targeted nor offered Edit Block."""
    b = _line_def("PlanNear", (0, 0), (100, 0))
    loose = LineItem(QPointF(_FAR[0], _FAR[1] + 20), QPointF(_FAR[0] + 100, _FAR[1] + 20))
    with _PlanBlock(main_window, b, loose=loose) as pb:
        pt = pb.at(50, 14.0)
        assert pb.sc.items(pt) == []                           # only HALO reaches either
        assert pb.sc._find_entity_at(pt) is not pb.inst
        menu = _plan_right_click(pb.view, pt, monkeypatch)
        labels = {a.text() for a in menu.actions()} if menu else set()
        assert not pb.inst.isSelected()
        assert "Edit Block" not in labels and "Explode" not in labels


def test_plan_entity_menu_delete_removes_the_block(qapp, main_window, monkeypatch):
    """The entity menu keeps Delete/Copy/Hide for a block, and Delete works."""
    b = _line_def("PlanDel", (0, 0), (100, 0))
    with _PlanBlock(main_window, b) as pb:
        menu = _plan_right_click(pb.view, pb.at(50, 3.0), monkeypatch)
        acts = {a.text(): a for a in menu.actions()}
        assert {"Edit Block", "Copy", "Hide", "Delete"} <= set(acts)
        acts["Delete"].trigger(); QApplication.processEvents()
        assert pb.inst.scene() is None
        assert pb.inst not in pb.sc._block_instances


def test_plan_generic_menu_offers_edit_block_for_one_selected_block(
        qapp, main_window, monkeypatch):
    """Right-click on empty plan space with exactly one block selected: the
    generic menu offers Edit Block (not Explode); two selected → neither."""
    b = _line_def("PlanGen", (0, 0), (100, 0))
    with _PlanBlock(main_window, b) as pb:
        pb.inst.setSelected(True)
        empty = pb.at(50, -300.0)
        assert pb.sc._find_entity_at(empty) is None
        menu = _plan_right_click(pb.view, empty, monkeypatch)
        acts = {a.text(): a for a in menu.actions()}
        assert "Delete" in acts                               # the generic menu
        assert "Edit Block" in acts and "Explode" not in acts
        acts["Edit Block"].trigger(); QApplication.processEvents()
        w = main_window.central_tabs.currentWidget()
        assert getattr(w, "_edit_block_id", None) == b.id
        mgr = main_window.block_editor_manager
        w._modified = False; mgr.close(w)
        main_window.central_tabs.setCurrentWidget(pb.view); QApplication.processEvents()
        other = pb.sc.place_block_instance(b.id, (_FAR[0], _FAR[1] + 100))
        try:
            pb.inst.setSelected(True); other.setSelected(True)
            menu = _plan_right_click(pb.view, empty, monkeypatch)
            labels = {a.text() for a in menu.actions()}
            assert "Edit Block" not in labels and "Explode" not in labels
        finally:
            pb.sc.removeItem(other); pb.sc._block_instances.remove(other)


def test_real_right_click_on_a_nested_block_offers_edit_block_and_explode(qapp, monkeypatch):
    """Real event path: a context-menu event on the editor viewport over a
    line-only block (zero-area shape) reaches the entity menu with both
    actions and selects the block."""
    from PyQt6.QtGui import QContextMenuEvent
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QMenu
    b = _line_def("B", (0, 0), (100, 0))
    proj, w, es = _proj_and_editor(b)
    try:
        inst = es.place_block_instance(b.id, (0.0, 0.0))
        w.resize(800, 600); w.show(); QTest.qWaitForWindowExposed(w)
        w.view.resetTransform(); w.view.centerOn(0, 0); QApplication.processEvents()
        menus = []
        monkeypatch.setattr(QMenu, "exec", lambda self, *a: menus.append(self))
        vp = w.view.viewport()
        pt = w.view.mapFromScene(QPointF(50, 0))
        QApplication.sendEvent(vp, QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse, pt, vp.mapToGlobal(pt)))
        QApplication.processEvents()
        assert menus and {"Edit Block", "Explode"} <= {a.text() for a in menus[-1].actions()}
        assert inst.isSelected()
    finally:
        w.hide()
        es.cleanup()


def _shown_editor(*defs):
    from PyQt6.QtTest import QTest
    proj, w, es = _proj_and_editor(*defs)
    w.resize(800, 600); w.show(); QTest.qWaitForWindowExposed(w)
    w.view.resetTransform(); w.view.centerOn(0, 0); QApplication.processEvents()
    return proj, w, es


def _right_click(w, scene_pt, monkeypatch):
    from PyQt6.QtGui import QContextMenuEvent
    from PyQt6.QtWidgets import QMenu
    menus = []
    monkeypatch.setattr(QMenu, "exec", lambda self, *a: menus.append(self))
    vp = w.view.viewport()
    pt = w.view.mapFromScene(scene_pt)
    QApplication.sendEvent(vp, QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse, pt, vp.mapToGlobal(pt)))
    QApplication.processEvents()
    return {a.text() for a in menus[-1].actions()} if menus else set()


def test_a_nearer_loose_line_beats_a_block_within_the_aperture(qapp, monkeypatch):
    """Right-click 6 mm from a loose line and 14 mm from a line-only block
    (both inside the HALO aperture): the line is nearest, so the block is
    neither targeted, selected nor offered Edit Block / Explode."""
    b = _line_def("B", (0, 0), (100, 0))
    proj, w, es = _shown_editor(b)
    try:
        inst = es.place_block_instance(b.id, (0.0, 0.0))
        loose = LineItem(QPointF(0, 20), QPointF(100, 20))
        es.addItem(loose); es._draw_lines.append(loose)
        pt = QPointF(50, 14.0)
        assert es.items(pt) == []                              # only HALO reaches either
        assert es._find_entity_at(pt) is not inst
        labels = _right_click(w, pt, monkeypatch)
        assert not inst.isSelected()
        assert not ({"Edit Block", "Explode"} & labels)
    finally:
        w.hide()
        es.cleanup()


def test_a_line_only_block_resolves_when_it_is_nearest(qapp, monkeypatch):
    b = _line_def("B", (0, 0), (100, 0))
    proj, w, es = _shown_editor(b)
    try:
        inst = es.place_block_instance(b.id, (0.0, 0.0))
        loose = LineItem(QPointF(0, 20), QPointF(100, 20))
        es.addItem(loose); es._draw_lines.append(loose)
        pt = QPointF(50, 5.0)                                  # 5 mm from block, 15 from line
        assert es._find_entity_at(pt) is inst
        labels = _right_click(w, pt, monkeypatch)
        assert inst.isSelected() and {"Edit Block", "Explode"} <= labels
    finally:
        w.hide()
        es.cleanup()


def test_prompt_cancel_explodes_nothing(qapp, monkeypatch):
    c = _line_def("C", (0, 0), (0, 50))
    b = _line_def("B", (0, 0), (100, 0),
                  extra=[{"type": "block_instance", "block_id": c.id,
                          "pos": [100, 0], "rotation": 0.0}])
    proj, w, es = _proj_and_editor(c, b)
    try:
        inst = es.place_block_instance(b.id, (0.0, 0.0))
        es.push_undo_state()
        inst.setSelected(True)
        depth = len(es._undo_stack)
        monkeypatch.setattr("firepro3d.themed_message.themed_choice",
                            lambda *a, **k: None)
        assert es.explode_selected_blocks() == []
        assert es._block_instances == [inst] and inst.scene() is es
        assert es.selectedItems() == [inst] and es._draw_lines == []
        assert len(es._undo_stack) == depth
    finally:
        es.cleanup()


def test_nothing_explodable_keeps_selection_and_pushes_no_undo(qapp):
    """Only a missing-definition block selected: status only — no selection
    change, no undo step."""
    b = _line_def("B", (0, 0), (100, 0))
    proj, w, es = _proj_and_editor(b)
    try:
        orphan = es.place_block_instance("no-such-block", (0.0, 0.0))
        es.push_undo_state()
        orphan.setSelected(True)
        depth, pos = len(es._undo_stack), es._undo_pos
        msgs = []
        es._show_status = lambda *a, **k: msgs.append(a)
        assert es.explode_selected_blocks() == []
        assert es.selectedItems() == [orphan] and orphan.scene() is es
        assert (len(es._undo_stack), es._undo_pos) == (depth, pos)
        assert msgs
    finally:
        es.cleanup()


def test_a_failing_explode_rolls_back_cleanly(qapp, monkeypatch, caplog):
    """A primitive that raises mid-explode: the instance is still there, no
    stray primitives, no undo step, the error is logged, nothing propagates."""
    from firepro3d import geometry_2d as g
    b = BlockDefinition.new(name="B", library="L", series="S", origin=(0.0, 0.0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict(),
                                        g.CircleItem(QPointF(50, 50), 10).to_dict()])
    proj, w, es = _proj_and_editor(b)
    try:
        es.place_block_instance(b.id, (0.0, 0.0), rotation=30.0)
        es.push_undo_state()
        es._block_instances[0].setSelected(True)
        depth, pos = len(es._undo_stack), es._undo_pos

        def boom(self, *a):
            raise RuntimeError("boom")
        monkeypatch.setattr(g.CircleItem, "manip_rotate", boom)
        with caplog.at_level("ERROR"):
            assert es.explode_selected_blocks() == []
        assert len(es._block_instances) == 1
        assert es._block_instances[0].scene() is es
        assert es._draw_lines == [] and es._draw_circles == []
        assert not [i for i in es.items() if isinstance(i, (LineItem, g.CircleItem))]
        assert (len(es._undo_stack), es._undo_pos) == (depth, pos)
        assert any("explode" in r.getMessage().lower() for r in caplog.records)
    finally:
        es.cleanup()
