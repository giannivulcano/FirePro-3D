"""SB2b G-M2 + blank-revert -- duplicate Mark warn state on the panel row; clearing a Mark is refused."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor

from firepro3d import marks
from firepro3d.property_manager import PropertyManager
from firepro3d.theme import DARK, build_app_qss
from firepro3d.wall import WallSegment
from firepro3d.wall_opening import WallOpening


def _doors(scene, n):
    w = WallSegment(QPointF(0, 0), QPointF(8000, 0), thickness_mm=200.0)
    w.level = scene.active_level
    scene.addItem(w)
    scene._walls.append(w)
    out = []
    for i in range(n):
        op = WallOpening(w, feature_id="door_914", offset_along=1000.0 + 2000 * i)
        op.level = w.level
        w.openings.append(op)
        scene.addItem(op)
        marks.mint(scene, op)
        out.append(op)
    return out


def _panel(item):
    pm = PropertyManager()
    pm.setStyleSheet(build_app_qss(DARK))
    pm.show_properties(item)
    return pm


def _commit(pm, text):
    edit = pm._prop_widgets["Mark"]
    edit.setText(text)
    edit.editingFinished.emit()


def test_duplicate_flags_row_with_count_tooltip_and_clears(qapp, shown_model_view):
    view, scene = shown_model_view
    d1, d2, d3 = _doors(scene, 3)
    pm = _panel(d2)
    _commit(pm, "D1")
    pm._do_refresh()
    edit = pm._prop_widgets["Mark"]
    assert edit.property("state") == "warn"
    assert edit.toolTip() == "2 doors share Mark D1"
    pm.show_properties(d1)
    assert pm._prop_widgets["Mark"].property("state") == "warn"
    pm.show_properties(d2)
    _commit(pm, "D9")
    pm._do_refresh()
    assert pm._prop_widgets["Mark"].property("state") in (None, "")


def test_warn_state_paints_warn_colour(qapp, shown_model_view):
    view, scene = shown_model_view
    d1, d2 = _doors(scene, 2)
    marks.set_mark(d2, "D1")
    pm = _panel(d2)
    pm.resize(320, 600)
    pm.show()
    edit = pm._prop_widgets["Mark"]
    qapp.processEvents()
    img = edit.grab().toImage()
    warn = QColor(DARK.warn)

    def close(c):
        return abs(c.red() - warn.red()) + abs(c.green() - warn.green()) + abs(c.blue() - warn.blue()) < 60

    edge = [QColor(img.pixel(x, 0)) for x in range(img.width())] + \
           [QColor(img.pixel(x, img.height() - 1)) for x in range(img.width())]
    assert sum(close(c) for c in edge) > img.width() // 2


def test_blank_mark_is_refused_with_status(qapp, shown_model_view, monkeypatch):
    view, scene = shown_model_view
    (d1,) = _doors(scene, 1)
    msgs = []
    monkeypatch.setattr(scene, "_show_status", lambda m, timeout=5000: msgs.append((m, timeout)))
    pm = _panel(d1)
    _commit(pm, "   ")
    assert marks.get_mark(d1) == "D1"
    assert pm._prop_widgets["Mark"].text() == "D1"
    assert msgs == [("Mark can't be blank - restored to D1", 4000)]


def test_panel_mark_edit_is_one_undo_step(qapp, shown_model_view):
    view, scene = shown_model_view
    (d1,) = _doors(scene, 1)
    scene.push_undo_state()
    pm = _panel(d1)
    _commit(pm, "X7")
    scene.undo()
    assert marks.get_mark(scene._walls[0].openings[0]) == "D1"


def test_duplicates_never_reach_paper(qapp, shown_model_view):
    view, scene = shown_model_view
    import hashlib
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QImage, QPainter

    def digest():
        img = QImage(400, 200, QImage.Format.Format_ARGB32)
        img.fill(0xFFFFFFFF)
        p = QPainter(img)
        scene.render(p, QRectF(0, 0, 400, 200), QRectF(-500, -1000, 9000, 4500))
        p.end()
        return hashlib.sha256(bytes(img.constBits().asarray(img.sizeInBytes()))).hexdigest()

    d1, d2 = _doors(scene, 2)
    unique = digest()
    marks.set_mark(d2, "D1")          # now a duplicate pair
    pm = _panel(d2)
    assert pm._prop_widgets["Mark"].property("state") == "warn"
    # nothing on the canvas carries the flag: no item is added or recoloured
    before = {id(i) for i in scene.items()}
    marks.refresh_duplicates(scene)
    assert {id(i) for i in scene.items()} == before
    assert digest() == unique
