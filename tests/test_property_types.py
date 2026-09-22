"""tests/test_property_types.py

Tests for the four new property-panel render types:
  icon_enum, bool_group, number, percent
"""
from PyQt6.QtWidgets import QSlider, QLineEdit, QAbstractButton
from firepro3d.property_manager import PropertyManager


class _Item:
    def __init__(self, props):
        self._p = props; self.applied = {}
    def get_properties(self): return self._p
    def set_property(self, k, v):
        self.applied[k] = v
        if k in self._p: self._p[k]["value"] = v
    def scene(self): return None


def _buttons(pm):
    return pm.findChildren(QAbstractButton)


def test_icon_enum_renders_and_commits(qapp):
    pm = PropertyManager()
    it = _Item({"Corner": {"type": "icon_enum", "value": "square",
                           "options": [("square", "corner_square.svg"),
                                       ("round", "corner_fillet.svg"),
                                       ("chamfer", "corner_chamfer.svg")]}})
    pm.show_properties(it)
    btns = [b for b in _buttons(pm) if b.property("icon_enum_val")]
    assert len(btns) == 3
    next(b for b in btns if b.property("icon_enum_val") == "chamfer").click()
    assert it.applied.get("Corner") == "chamfer"


def test_bool_group_renders_and_commits(qapp):
    pm = PropertyManager()
    it = _Item({"Style": {"type": "bool_group",
                          "keys": [("Bold", "B"), ("Italic", "I"), ("Underline", "U")],
                          "values": {"Bold": False, "Italic": True, "Underline": False}}})
    pm.show_properties(it)
    bold = next(b for b in _buttons(pm) if b.text() == "B")
    bold.click()
    assert it.applied.get("Bold") is True


def test_number_type_commits_int(qapp):
    pm = PropertyManager()
    it = _Item({"Height": {"type": "number", "value": 48}})
    pm.show_properties(it)
    edit = next(e for e in pm.findChildren(QLineEdit) if e.property("number_key") == "Height")
    assert edit.text() == "48"
    edit.setText("60"); edit.editingFinished.emit()
    assert it.applied.get("Height") == 60


def test_percent_slider_commits(qapp):
    pm = PropertyManager()
    it = _Item({"Fill Opacity": {"type": "percent", "value": 35}})
    pm.show_properties(it)
    sl = pm.findChildren(QSlider)[0]
    assert sl.value() == 35
    sl.setValue(80)
    assert it.applied.get("Fill Opacity") == 80
