"""todo #70 integration: No Fill end-to-end through the real panels."""
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QImage, QPainter, QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d import colour_picker
from firepro3d.text_item import TextAnnotationData, TextItem


def _count_nonwhite(item):
    scene = QGraphicsScene(); scene.addItem(item)
    src = item.sceneBoundingRect().adjusted(-6, -6, 6, 6)
    img = QImage(260, 180, QImage.Format.Format_ARGB32); img.fill(QColor("white"))
    p = QPainter(img); scene.render(p, QRectF(0, 0, 260, 180), src); p.end()
    scene.removeItem(item)
    w = QColor("white").rgb()
    return sum(1 for y in range(img.height()) for x in range(img.width()) if img.pixel(x, y) != w)


def _fill_swatch(pm):
    from firepro3d.ui_kit import Swatch
    return next(s for s in pm.findChildren(Swatch) if s._context == "Fill Color")


def test_model_text_panel_no_fill_end_to_end(qapp, monkeypatch):
    from firepro3d.property_manager import PropertyManager
    baseline = _count_nonwhite(TextItem(TextAnnotationData(text="AB", height_mm=4.0)))
    item = TextItem(TextAnnotationData(text="AB", height_mm=4.0, fill_color="#c0392b"))
    assert _count_nonwhite(item) > baseline + 50            # filled
    pm = PropertyManager(); pm.show_properties(item)
    sw = _fill_swatch(pm)
    assert sw._allow_none is True
    seen = {}
    def fake(initial, parent=None, context="", *, allow_none=False):
        seen.update(initial=initial, allow_none=allow_none, context=context)
        return ""
    monkeypatch.setattr(colour_picker, "pick_colour", fake)
    QTest.mouseClick(sw._chip, Qt.MouseButton.LeftButton)
    assert seen == {"initial": "#c0392b", "allow_none": True, "context": "Fill Color"}
    assert item._data.fill_color == ""                      # true No Fill, not opacity 0
    assert item._data.fill_opacity == 100.0                 # opacity untouched
    assert _count_nonwhite(item) == baseline                 # observable: no fill pixels


def test_model_panel_passes_empty_fill_and_disables_opacity(qapp):
    item = TextItem(TextAnnotationData(text="A", fill_color=""))
    p = item.get_properties()
    assert p["Fill Color"]["value"] == "" and p["Fill Color"]["allow_none"] is True
    assert p["Fill Opacity"].get("disabled") is True
    item2 = TextItem(TextAnnotationData(text="A", fill_color="#112233"))
    assert not item2.get_properties()["Fill Opacity"].get("disabled")


def test_panel_opacity_widget_disabled_when_no_fill(qapp):
    from firepro3d.property_manager import PropertyManager
    item = TextItem(TextAnnotationData(text="A", fill_color=""))
    pm = PropertyManager(); pm.show_properties(item)
    sw = _fill_swatch(pm)
    assert sw._label.text() == "None"
    # the percent widget for Fill Opacity is disabled
    w = pm._prop_widgets["Fill Opacity"]
    assert not w.isEnabled()


def test_paper_panel_no_fill(qapp):
    from firepro3d.paper_space import _text_panel_properties
    d = TextAnnotationData(text="A", fill_color="")
    p = _text_panel_properties(d)
    assert p["Fill Color"]["value"] == "" and p["Fill Color"]["allow_none"] is True
    assert p["Fill Opacity"].get("disabled") is True


def test_swatch_non_allow_none_never_shows_none(qapp, monkeypatch):
    from firepro3d.ui_kit import Swatch
    sw = Swatch("", context="Font Color")                   # legacy empty value
    assert sw.hex() == "#000000" and sw._label.text() == "#000000"
    monkeypatch.setattr(colour_picker, "pick_colour", lambda *a, **k: None)   # cancel
    got = []; sw.colorChanged.connect(got.append)
    QTest.mouseClick(sw._chip, Qt.MouseButton.LeftButton)
    assert got == [] and sw.hex() == "#000000"


def test_opacity_reenables_after_picking_colour(qapp, monkeypatch):
    from firepro3d.property_manager import PropertyManager
    item = TextItem(TextAnnotationData(text="A", fill_color=""))
    pm = PropertyManager(); pm.show_properties(item)
    monkeypatch.setattr(colour_picker, "pick_colour", lambda *a, **k: "#00aa00")
    QTest.mouseClick(_fill_swatch(pm)._chip, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    pm.show_properties(item)            # the app re-shows on requestPropertyUpdate
    assert item._data.fill_color == "#00aa00"
    assert pm._prop_widgets["Fill Opacity"].isEnabled()


# ── Smoke 2026-09-22: model text panel edits must be one undo step ───────────

def _model_scene_with_text(fill="#c0392b"):
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    t = TextItem(TextAnnotationData(text="AB", height_mm=4.0, fill_color=fill))
    s.addItem(t); s._texts.append(t)
    s.push_undo_state()                      # the placement's undo point
    return s, t


def _only_text(s):
    return [i for i in s._texts if type(i).__name__ == "TextItem"][0]


def test_model_text_property_edit_is_one_undo_step(qapp):
    """User smoke: Ctrl+Z after Fill Color → No Fill reverted the PLACEMENT
    instead of the property (set_property never snapshotted)."""
    s, t = _model_scene_with_text()
    depth = s._undo_pos
    t.set_property("Fill Color", "")
    assert s._undo_pos == depth + 1          # exactly one new step
    s.undo()
    assert _only_text(s)._data.fill_color == "#c0392b"   # property reverted, text still placed
    s.redo()
    assert _only_text(s)._data.fill_color == ""


def test_model_text_noop_property_edit_pushes_nothing(qapp):
    s, t = _model_scene_with_text()
    depth = s._undo_pos
    t.set_property("Fill Color", "#c0392b")  # unchanged value
    assert s._undo_pos == depth
