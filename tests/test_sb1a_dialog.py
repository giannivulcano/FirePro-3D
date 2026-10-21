"""SB1a: Edit Attributes dialog (A3 / A4 / AC5)."""
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from firepro3d.block_attributes import normalise_attr
from firepro3d.block_attributes_dialog import EditAttributesDialog
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _text(text, **kw):
    d = {"type": "text", "text": text, "x": 0.0, "y": 0.0, "height_mm": 5.0}
    d.update(kw)
    return d


_LINE = LineItem(QPointF(0, 0), QPointF(20, 0)).to_dict()


def _attr(key, **kw):
    return normalise_attr({"key": key, **kw})


def _setup():
    ms = Model_Space()
    d = BlockDefinition.new(name="Tag", library="", series="", origin=(0.0, 0.0),
                            primitives=[_LINE, _text("@[Mark] @[Area]")])
    d.attributes = [_attr("Mark", label="Mark", default="A1"),
                    _attr("Area", type="number", precision=1, source="host",
                          host_key="Room.Area", placeholder="--")]
    ms.register_block_definition(d)
    inst = ms.place_block_instance(d.id, (0.0, 0.0))
    return ms, d, inst


def test_rows_show_source_and_value(qapp):
    ms, d, inst = _setup()
    dlg = EditAttributesDialog(inst, ms)
    rows = dlg.rows
    assert [r.key for r in rows.rows] == ["Mark", "Area"]
    assert rows.rows[0].editor.text() == "A1"           # instance default shown
    assert rows.rows[1].override.isChecked() is False
    assert rows.rows[1].editor.isEnabled() is False
    assert rows.rows[1].resolved.text() == "--"         # host, no provider


def test_ok_is_one_undo_step_and_override_toggle(qapp):
    ms, d, inst = _setup()
    n0 = len(ms._undo_stack)
    dlg = EditAttributesDialog(inst, ms)
    r = dlg.rows.rows
    r[0].editor.setText("B2")
    r[1].override.setChecked(True)
    assert r[1].editor.isEnabled() is True
    r[1].editor.setText("12.5")
    dlg.accept()
    assert inst.attributes == {"Mark": "B2", "Area": "12.5"}
    assert len(ms._undo_stack) == n0 + 1                # A4: one undo entry
    # reopen, uncheck the override -> binding restored (key deleted, D4)
    dlg2 = EditAttributesDialog(inst, ms)
    assert dlg2.rows.rows[1].override.isChecked() is True
    dlg2.rows.rows[1].override.setChecked(False)
    dlg2.accept()
    assert inst.attributes == {"Mark": "B2"}
    assert len(ms._undo_stack) == n0 + 2


def test_cancel_discards(qapp):
    ms, d, inst = _setup()
    n0 = len(ms._undo_stack)
    dlg = EditAttributesDialog(inst, ms)
    dlg.rows.rows[0].editor.setText("ZZ")
    dlg.reject()
    assert inst.attributes == {} and len(ms._undo_stack) == n0


def test_number_row_refuses_non_numeric(qapp):
    ms, d, inst = _setup()
    dlg = EditAttributesDialog(inst, ms)
    r = dlg.rows.rows[1]
    r.override.setChecked(True)
    r.editor.setText("abc")
    assert r.editor.hasAcceptableInput() is False
    dlg.accept()
    assert "Area" not in inst.attributes                # unacceptable text not stored


def _shown_view(ms):
    from PyQt6.QtWidgets import QGraphicsView
    view = QGraphicsView(ms)
    view.resize(600, 600)
    view.resetTransform()
    view.show()
    QTest.qWaitForWindowExposed(view)
    return view


def _dclick(view, x, y):
    QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton,
                      pos=view.mapFromScene(QPointF(x, y)))


def _plain_def(ms):
    plain = BlockDefinition.new(name="P", library="", series="", origin=(0.0, 0.0),
                                primitives=[_LINE, _text("plain")])
    ms.register_block_definition(plain)
    return plain


def _labels(menu):
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def test_right_click_menus_offer_edit_attributes_only_with_attributes(qapp, monkeypatch):
    """A3 as re-ruled at smoke (2026-10-21): the scene's entity menu (direct
    right-click) and the view's plan menu (selection right-click) carry
    "Edit Attributes..." below "Edit Block" for a placed instance whose
    definition declares attributes; a plain block gets neither."""
    opened = []
    monkeypatch.setattr("firepro3d.block_attributes_dialog.EditAttributesDialog.exec",
                        lambda self: opened.append(self._inst) or 1)
    ms, d, inst = _setup()
    plain = _plain_def(ms)
    p = ms.place_block_instance(plain.id, (100.0, 0.0))
    assert ms._find_entity_at(QPointF(10.0, 0.0)) is inst   # a real right-click hits it
    m = ms._build_entity_context_menu(inst)
    labels = _labels(m)
    assert labels.index("Edit Block") + 1 == labels.index("Edit Attributes\u2026")
    next(a for a in m.actions() if a.text() == "Edit Attributes\u2026").trigger()
    assert opened == [inst]
    assert "Edit Attributes\u2026" not in _labels(ms._build_entity_context_menu(p))
    from firepro3d.model_view import Model_View
    mv = Model_View(ms)
    try:
        inst.setSelected(True)
        gm = mv._build_plan_context_menu(ms, [inst], "select")
        assert "Edit Attributes\u2026" in _labels(gm)
        next(a for a in gm.actions() if a.text() == "Edit Attributes\u2026").trigger()
        assert opened == [inst, inst]
        inst.setSelected(False)
        p.setSelected(True)
        assert "Edit Attributes\u2026" not in _labels(
            mv._build_plan_context_menu(ms, [p], "select"))
    finally:
        mv.close()
        mv.deleteLater()


def test_right_click_menu_inert_in_block_editor(qapp):
    ms, d, inst = _setup()
    ms.scene_role = "block_editor"
    assert "Edit Attributes\u2026" not in _labels(ms._build_entity_context_menu(inst))
    assert ms.can_edit_attributes(inst) is False


def test_double_click_on_instance_opens_no_dialog(qapp, monkeypatch):
    """A3 re-ruling: double-click keeps its pre-SB1a behaviour (no block action)."""
    opened = []
    monkeypatch.setattr("firepro3d.block_attributes_dialog.EditAttributesDialog.exec",
                        lambda self: opened.append(self._inst) or 1)
    ms, d, inst = _setup()
    view = _shown_view(ms)
    _dclick(view, 10.0, 0.0)
    assert opened == []
    view.close()


def test_ok_unchanged_pushes_nothing(qapp):
    ms, d, inst = _setup()
    n0 = len(ms._undo_stack)
    dlg = EditAttributesDialog(inst, ms)
    dlg.accept()
    assert inst.attributes == {} and len(ms._undo_stack) == n0


def test_untouched_non_numeric_number_row_kept(qapp):
    ms, d, inst = _setup()
    inst.set_attributes({"Area": "n/a"})
    n0 = len(ms._undo_stack)
    dlg = EditAttributesDialog(inst, ms)
    dlg.accept()
    assert inst.attributes == {"Area": "n/a"} and len(ms._undo_stack) == n0


def test_resolved_label_reads_provider_not_override(qapp, monkeypatch):
    ms, d, inst = _setup()
    inst.set_attributes({"Area": "1"})
    monkeypatch.setattr(inst, "host_values", lambda: {"Room.Area": "9"})
    dlg = EditAttributesDialog(inst, ms)
    r = dlg.rows.rows[1]
    assert r.resolved.text() == "9.0"
    assert r.editor.text() == "1" and r.override.isChecked() is True


def test_number_row_empty_text_restores_binding(qapp):
    ms, d, inst = _setup()
    inst.set_attributes({"Area": "1"})
    dlg = EditAttributesDialog(inst, ms)
    r = dlg.rows.rows[1]
    r.editor.setText("")
    dlg.accept()
    assert "Area" not in inst.attributes


def test_panel_button_row_disabled_without_attributes(qapp):
    ms, d, inst = _setup()
    row = inst.get_properties()["Edit attributes"]
    assert row["type"] == "button" and row.get("enabled", True) is True
    plain = _plain_def(ms)
    p = ms.place_block_instance(plain.id, (100.0, 0.0))
    assert p.get_properties()["Edit attributes"]["enabled"] is False


def test_block_editor_nested_instance_offers_no_edit_attributes(qapp, monkeypatch):
    """VC9 F2 (A1/D10): inside the Block Editor a placed child's panel button
    is disabled and ``open_edit_attributes`` refuses -- the nested record
    drops ``attributes`` at Save, so values entered there would be lost."""
    opened = []
    monkeypatch.setattr("firepro3d.block_attributes_dialog.EditAttributesDialog.exec",
                        lambda self: opened.append(self._inst) or 1)
    ms = Model_Space(scene_role="block_editor")
    d = BlockDefinition.new(name="Tag", library="", series="", origin=(0.0, 0.0),
                            primitives=[_LINE, _text("@[Mark]")])
    d.attributes = [_attr("Mark", default="A1")]
    ms.register_block_definition(d)
    inst = ms.place_block_instance(d.id, (0.0, 0.0))
    assert inst.get_properties()["Edit attributes"]["enabled"] is False
    assert ms.open_edit_attributes(inst) is False and opened == []
