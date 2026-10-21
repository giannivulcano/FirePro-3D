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


def test_double_click_opens_dialog_only_with_attributes(qapp, monkeypatch):
    class _Ev:                      # QGraphicsSceneMouseEvent is not constructible
        def __init__(self, pos):
            self._pos = QPointF(*pos)
            self.accepted = False

        def button(self):
            return Qt.MouseButton.LeftButton

        def scenePos(self):
            return self._pos

        def accept(self):
            self.accepted = True

    opened = []
    monkeypatch.setattr("firepro3d.block_attributes_dialog.EditAttributesDialog.exec",
                        lambda self: opened.append(self._inst) or 1)
    from PyQt6.QtWidgets import QGraphicsView
    ms, d, inst = _setup()
    view = QGraphicsView(ms)        # the HALO pick of a line-only block needs a view
    view.resize(600, 600)
    view.resetTransform()
    ev = _Ev((10.0, 0.0))                        # on the static line
    ms.mouseDoubleClickEvent(ev)
    assert opened == [inst]
    # a definition without attributes: no-op
    plain = BlockDefinition.new(name="P", library="", series="", origin=(0.0, 0.0),
                                primitives=[_LINE, _text("plain")])
    ms.register_block_definition(plain)
    p = ms.place_block_instance(plain.id, (100.0, 0.0))
    ev2 = _Ev((110.0, 0.0))
    try:
        ms.mouseDoubleClickEvent(ev2)
    except TypeError:               # fell through to the Qt base (stub event); not accepted
        pass
    assert ev2.accepted is False
    assert opened == [inst]


def test_panel_button_row_disabled_without_attributes(qapp):
    ms, d, inst = _setup()
    row = inst.get_properties()["Edit attributes"]
    assert row["type"] == "button" and row.get("enabled", True) is True
    plain = BlockDefinition.new(name="P", library="", series="", origin=(0.0, 0.0),
                                primitives=[_LINE, _text("plain")])
    ms.register_block_definition(plain)
    p = ms.place_block_instance(plain.id, (100.0, 0.0))
    assert p.get_properties()["Edit attributes"]["enabled"] is False
