"""Constraints panel section — rows, Suppress, Delete, DOF footer, constraint
adapter, inert read-only rows, refresh, glyph select, row hover, live style
(parametric-constraint-system.md §10, D11, D27, §6.4; property-panel.md)."""
import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QColor, QEnterEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QLineEdit

from firepro3d import constraint_paint as cp
from firepro3d import theme as th
from firepro3d.constraint_controller import ConstraintAdapter
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.property_manager import PropertyManager
from firepro3d.scale_manager import ScaleManager
from firepro3d.theme import M
from firepro3d.ui_kit import ActionRowList


def _flush():
    QApplication.processEvents()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    QApplication.processEvents()


def _section(pm):
    """The ONE live Constraints section in *pm* (deferred deletes flushed)."""
    _flush()
    secs = pm.findChildren(ActionRowList)
    assert len(secs) <= 1, secs
    return secs[0] if secs else None


def _line(sc, a=(0, 0), b=(100, 0)):
    ln = LineItem(QPointF(*a), QPointF(*b))
    sc.addItem(ln)
    sc._draw_lines.append(ln)
    return ln


def _setup():
    sc = Model_Space(scene_role="block_editor")
    ln = _line(sc)
    c = sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    assert c is not None
    return sc, ln, c


def _wired_pm(sc):
    """A panel wired like MainWindow._adopt_block_editor (refresh path)."""
    pm = PropertyManager()
    sc.requestPropertyUpdate.connect(pm.show_properties)
    return pm


def _editors(pm):
    return [w for w in pm.findChildren((QCheckBox, QLineEdit, QComboBox))
            if w.isEnabled() and not (isinstance(w, QLineEdit) and w.isReadOnly())]


# ── plan tests ──────────────────────────────────────────────────────────────

def test_selected_entity_lists_its_constraints_with_dof(qapp):
    sc, ln, c = _setup()
    pm = PropertyManager()
    pm.show_properties(ln)
    sec = _section(pm)
    assert sec is not None and sec.row_count() == 1
    assert sec.row_text(0) == "Horizontal"
    assert sec.row_subtext(0) == "Line · edge"
    assert "Sketch DOF 3" in sec.footer_text()
    assert sec.row_actions(0) == ["suppress", "delete"]


def test_selection_list_shape_from_mainwindow_gets_the_section(qapp):
    sc, ln, c = _setup()
    pm = PropertyManager()
    pm.show_properties([ln])            # MainWindow passes selectedItems()
    sec = _section(pm)
    assert sec is not None and sec.row_count() == 1


def test_suppress_and_delete_buttons(qapp):
    sc, ln, c = _setup()
    pm = PropertyManager()
    pm.show_properties(ln)
    _section(pm).trigger(0, "suppress")
    assert sc.constraint_ctl.constraints[0].enabled is False
    pm.show_properties(ln)
    _section(pm).trigger(0, "delete")
    assert sc.constraint_ctl.constraints == []


def test_plan_scene_items_get_no_section(qapp):
    sc = Model_Space()
    ln = LineItem(QPointF(0, 0), QPointF(1, 0))
    sc.addItem(ln)
    pm = PropertyManager()
    pm.show_properties(ln)
    assert _section(pm) is None


def test_constraint_adapter_panel(qapp):
    sc, ln, c = _setup()
    ad = ConstraintAdapter(sc.constraint_ctl, c)
    props = ad.get_properties()
    assert props["Kind"]["value"] == "Horizontal"
    assert props["Targets"]["value"] == "Line · edge"
    ad.set_property("Suppressed", True)
    assert c.enabled is False


# ── guards ──────────────────────────────────────────────────────────────────

def test_inert_rows_are_read_only_delete_only(qapp):
    """§6.4: unknown-type AND invalid records list as "Unsupported
    constraint" with Delete only; their adapter exposes no editable field."""
    sc = Model_Space(scene_role="block_editor")
    ln = _line(sc)
    ctl = sc.constraint_ctl
    ctl.load([
        {"id": "u1", "type": "from_the_future", "refs": [{"uid": ln._uid, "h": "edge"}]},
        {"id": "i1", "type": "horizontal", "refs": [{"uid": ln._uid, "h": "nope"}]},
    ])
    assert all(c.inert for c in ctl.constraints)
    pm = _wired_pm(sc)
    pm.show_properties(ln)
    sec = _section(pm)
    assert sec.row_count() == 2
    for i in range(2):
        assert sec.row_text(i) == "Unsupported constraint"
        assert sec.row_actions(i) == ["delete"]
    # Selected inert constraint: the adapter panel has no editor at all.
    for c in list(ctl.constraints):
        ctl.select(c.id)
        _flush()
        assert isinstance(pm._targets[0], ConstraintAdapter)
        assert all(m["type"] in ("label", "header")
                   for m in pm._targets[0].get_properties().values())
        assert _editors(pm) == []
        sec = _section(pm)
        assert sec.row_actions(0) == ["delete"]
        before = c.to_dict()
        ConstraintAdapter(ctl, c).set_property("Suppressed", True)
        ctl.set_enabled(c.id, False)
        assert c.enabled is True and c.to_dict() == before
    # Delete works on an inert row.
    ctl.clear_selected()
    pm.show_properties(ln)
    _section(pm).trigger(0, "delete")
    assert [c.id for c in ctl.constraints] == ["i1"]


def test_panel_refreshes_after_add_suppress_delete(qapp):
    sc, ln, c = _setup()
    ctl = sc.constraint_ctl
    pm = _wired_pm(sc)
    ln.setSelected(True)
    pm.show_properties(sc.selectedItems())
    assert _section(pm).row_count() == 1
    c2 = ctl.add("horizontal", [{"uid": ln._uid, "h": "p1"}, {"ref": "origin"}])
    assert c2 is not None
    assert _section(pm).row_count() == 2                 # no re-select
    assert _section(pm).row_subtext(1) == "Line · p1 ↔ Origin"
    _section(pm).trigger(1, "suppress")
    sec = _section(pm)
    assert c2.enabled is False
    assert sec.row_count() == 2 and sec.row_suppressed(1)
    assert sec.action_tooltip(1, "suppress").startswith("Unsuppress")
    ctl.delete([c.id])
    sec = _section(pm)
    assert sec.row_count() == 1 and sec.row_suppressed(0)
    assert "Sketch DOF 4" in sec.footer_text()


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


def _labels(pm):
    return [w.text() for w in pm.findChildren(QLabel)]


def test_glyph_click_shows_the_constraint_adapter(be):
    v, sc = be
    ln = _line(sc, (-100, 50), (100, 50))
    c = sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    QApplication.processEvents()
    pm = _wired_pm(sc)
    sc.constraint_ctl.show_all = True          # D32: Show Constraints ON
    rect = cp.glyph_layouts(v, sc.constraint_ctl)[0][1]
    QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton,
                     pos=QPointF(rect.center()).toPoint())
    _flush()
    assert sc.constraint_ctl.selected_id == c.id
    assert isinstance(pm._targets[0], ConstraintAdapter)
    texts = _labels(pm)
    assert "Constraint" in texts and "Horizontal" in texts
    sec = _section(pm)
    assert sec.row_count() == 1 and sec.row_text(0) == "Horizontal"
    # The adapter's Suppressed checkbox routes through the controller.
    box = [b for b in pm.findChildren(QCheckBox) if b.isEnabled()]
    assert len(box) == 1
    box[0].click()
    _flush()
    assert c.enabled is False
    # An empty-canvas click drops the constraint and clears the panel.
    QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, pos=QPointF(30, 30).toPoint())
    _flush()
    assert sc.constraint_ctl.selected_id is None
    assert pm._targets == [] and _section(pm) is None


def _grab(v):
    v.viewport().repaint()
    QApplication.processEvents()
    img = v.viewport().grab().toImage()
    return img, img.devicePixelRatio()


def _dist(a: QColor, b: QColor) -> int:
    return (abs(a.red() - b.red()) + abs(a.green() - b.green())
            + abs(a.blue() - b.blue()))


def test_row_hover_sets_hover_id_and_glows(be):
    v, sc = be
    ln = _line(sc, (-100, 50), (100, 50))
    c = sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    pm = PropertyManager()
    pm.show_properties(ln)
    row = _section(pm).row_widget(0)
    probe = v.mapFromScene(QPointF(-60, 50))
    before, dpr = _grab(v)
    QApplication.sendEvent(row, QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))
    assert sc.constraint_ctl.hover_id == c.id
    after, dpr = _grab(v)
    hover = th.detect().color("selection_hover")
    px = lambda img: img.pixelColor(int(round(probe.x() * dpr)),  # noqa: E731
                                    int(round((probe.y() - 3) * dpr)))
    assert _dist(px(after), hover) + 30 < _dist(px(before), hover)
    QApplication.sendEvent(row, QEvent(QEvent.Type.Leave))
    assert sc.constraint_ctl.hover_id is None


def test_row_click_selects_the_constraint(qapp):
    sc, ln, c = _setup()
    pm = _wired_pm(sc)
    pm.show_properties(ln)
    row = _section(pm).row_widget(0)
    QTest.mouseClick(row, Qt.MouseButton.LeftButton, pos=row.rect().center())
    _flush()
    assert sc.constraint_ctl.selected_id == c.id
    assert isinstance(pm._targets[0], ConstraintAdapter)


@pytest.fixture
def app_qss(qapp):
    prev_qss, prev_font = qapp.styleSheet(), qapp.font()
    th.apply_app_font(qapp)
    qapp.setStyleSheet(th.build_app_qss(th.detect()))
    yield
    qapp.setStyleSheet(prev_qss)
    qapp.setFont(prev_font)


def test_live_style_title_accent_and_row_height(qapp, app_qss):
    sc, ln, c = _setup()
    pm = PropertyManager()
    pm.resize(320, 600)
    pm.show()
    QTest.qWaitForWindowExposed(pm)
    pm.show_properties(ln)
    sec = _section(pm)
    QApplication.processEvents()
    t = th.detect()
    assert sec.row_widget(0).height() == M.PROP_CONSTRAINT_ROW_H
    title = sec.findChild(QLabel, "actionRowTitle")
    assert title.text().startswith("CONSTRAINTS")
    img = title.grab().toImage()
    acc = QColor(t.accent)
    best = min(_dist(img.pixelColor(x, y), acc)
               for x in range(img.width()) for y in range(img.height()))
    assert best <= 40, best
    # Body row text is NOT accent (title colour is not leaking to rows).
    body = sec.row_widget(0).findChild(QLabel, "actionRowText").grab().toImage()
    assert min(_dist(body.pixelColor(x, y), acc)
               for x in range(body.width()) for y in range(body.height())) > 60
    pm.close()
